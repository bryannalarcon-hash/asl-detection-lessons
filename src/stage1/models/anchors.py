"""SSD-style anchor generation, matching, and NMS for the palm detector.

Anchor layouts:

  Legacy (192 input, uniform scales): 3 grids tied to backbone strides
  8/16/32 = grids 24/12/6. At each cell, 3 square anchors at relative
  scales {0.10, 0.20, 0.35} of the input. Total = 2268 anchors.

  Multi-stride (256 input, per-stride scales): grids derived from
  ``strides`` (default 8/16/32 -> grids 32/16/8 at 256 input). Per-stride
  scale lists let small palms get tiny anchors at stride 8 while large
  palms get coarse anchors at stride 32. Default scales
  ``[[0.05, 0.10], [0.20, 0.35], [0.55]]`` give 32*32*2 + 16*16*2 + 8*8*1
  = 2624 anchors.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import torch


# Legacy anchor configuration tuned for 192x192 input.
INPUT_SIZE = 192
FEAT_GRID_SIZES = (24, 12, 6)
ANCHOR_SCALES_FRAC = (0.10, 0.20, 0.35)  # relative to INPUT_SIZE
N_ANCHORS_PER_CELL = len(ANCHOR_SCALES_FRAC)

# Multi-stride configuration. P1 catches small palms, P2 medium, P3 large.
# Strides are wrt the input image (e.g. stride 8 at input 256 -> grid 32).
MULTI_STRIDE_INPUT_SIZE = 256
MULTI_STRIDE_STRIDES = (8, 16, 32)
MULTI_STRIDE_SCALES: tuple[tuple[float, ...], ...] = (
    (0.05, 0.10),
    (0.20, 0.35),
    (0.55,),
)


def generate_anchors(input_size: int = INPUT_SIZE,
                     grid_sizes: tuple[int, ...] = FEAT_GRID_SIZES,
                     scales_frac: tuple[float, ...] = ANCHOR_SCALES_FRAC,
                     ) -> np.ndarray:
    """Return (N, 4) array of anchors in (cx, cy, w, h) image-pixel coords.

    Legacy single-list-of-scales generator. Every grid uses the same scale
    list - all three feature maps emit ``len(scales_frac)`` anchors per
    cell. The order is grid-major then cell-major then scale-major so the
    indices match the legacy detection head concat order.
    """
    anchors = []
    for grid_h in grid_sizes:
        cell = input_size / grid_h
        for gy in range(grid_h):
            for gx in range(grid_h):
                cx = (gx + 0.5) * cell
                cy = (gy + 0.5) * cell
                for s in scales_frac:
                    side = s * input_size
                    anchors.append((cx, cy, side, side))
    return np.array(anchors, dtype=np.float32)


def multi_stride_anchors(
    input_size: int = MULTI_STRIDE_INPUT_SIZE,
    scales_per_stride: Sequence[Sequence[float]] = MULTI_STRIDE_SCALES,
    strides: Sequence[int] = MULTI_STRIDE_STRIDES,
) -> np.ndarray:
    """Build anchors with a separate scale list at each stride.

    Args:
        input_size: input image side (square). ``input_size / stride`` must
            be a positive integer for every stride.
        scales_per_stride: outer sequence of length ``len(strides)``. Each
            inner sequence holds the per-cell anchor scales (relative to
            ``input_size``) for that stride. Empty inner sequences are
            rejected.
        strides: feature-map strides. Smaller strides come first so the
            anchor order matches the head concat order (P1 -> P2 -> P3).

    Returns:
        (N, 4) float32 numpy array of anchors in image-pixel (cx, cy, w, h)
        coords. N = sum_i (input_size/strides[i])^2 * len(scales_per_stride[i]).
        Within each stride the order is grid-row-major then cell-major then
        scale-major.
    """
    if len(scales_per_stride) != len(strides):
        raise ValueError(
            f"scales_per_stride ({len(scales_per_stride)}) and strides "
            f"({len(strides)}) must have the same length")
    anchors: list[tuple[float, float, float, float]] = []
    for stride, scales in zip(strides, scales_per_stride):
        if stride <= 0:
            raise ValueError(f"strides must be positive (got {stride})")
        if input_size % stride != 0:
            raise ValueError(
                f"input_size {input_size} not divisible by stride {stride}")
        if len(scales) == 0:
            raise ValueError(f"empty scale list at stride {stride}")
        grid = input_size // stride
        cell = float(stride)
        for gy in range(grid):
            for gx in range(grid):
                cx = (gx + 0.5) * cell
                cy = (gy + 0.5) * cell
                for s in scales:
                    side = float(s) * input_size
                    anchors.append((cx, cy, side, side))
    return np.asarray(anchors, dtype=np.float32)


_ANCHORS_CACHE: dict[tuple, np.ndarray] = {}


def get_anchors(input_size: int = INPUT_SIZE,
                scales_per_stride: Sequence[Sequence[float]] | None = None,
                strides: Sequence[int] | None = None) -> np.ndarray:
    """Return cached anchors for the given layout.

    With no override args, returns the legacy uniform-scale anchors at
    ``input_size`` (back-compat for existing callers). If either
    ``scales_per_stride`` or ``strides`` is provided, both must be given
    and the multi-stride generator is used instead. The cache key
    discriminates the two layouts so they cannot collide.
    """
    if scales_per_stride is None and strides is None:
        key = ("legacy", int(input_size))
        if key not in _ANCHORS_CACHE:
            _ANCHORS_CACHE[key] = generate_anchors(input_size=input_size)
        return _ANCHORS_CACHE[key]
    if scales_per_stride is None or strides is None:
        raise ValueError(
            "scales_per_stride and strides must both be provided for the "
            "multi-stride layout")
    key = (
        "multi",
        int(input_size),
        tuple(tuple(float(s) for s in lst) for lst in scales_per_stride),
        tuple(int(s) for s in strides),
    )
    if key not in _ANCHORS_CACHE:
        _ANCHORS_CACHE[key] = multi_stride_anchors(
            input_size=input_size,
            scales_per_stride=scales_per_stride,
            strides=strides,
        )
    return _ANCHORS_CACHE[key]


def xywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    """(N, 4) center-form → corner-form."""
    cx, cy, w, h = boxes[..., 0], boxes[..., 1], boxes[..., 2], boxes[..., 3]
    return np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=-1)


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(N, 4) and (M, 4) xyxy boxes → (N, M) IoU."""
    a = a.reshape(-1, 1, 4)
    b = b.reshape(1, -1, 4)
    inter_w = np.maximum(0, np.minimum(a[..., 2], b[..., 2]) - np.maximum(a[..., 0], b[..., 0]))
    inter_h = np.maximum(0, np.minimum(a[..., 3], b[..., 3]) - np.maximum(a[..., 1], b[..., 1]))
    inter = inter_w * inter_h
    area_a = (a[..., 2] - a[..., 0]) * (a[..., 3] - a[..., 1])
    area_b = (b[..., 2] - b[..., 0]) * (b[..., 3] - b[..., 1])
    union = area_a + area_b - inter
    return inter / np.maximum(union, 1e-9)


def encode_box(gt_xywh: np.ndarray, anchor_xywh: np.ndarray) -> np.ndarray:
    """Encode (N, 4) GT center-form boxes wrt anchors. Returns (N, 4) deltas."""
    dx = (gt_xywh[..., 0] - anchor_xywh[..., 0]) / anchor_xywh[..., 2]
    dy = (gt_xywh[..., 1] - anchor_xywh[..., 1]) / anchor_xywh[..., 3]
    dw = np.log(np.maximum(gt_xywh[..., 2] / anchor_xywh[..., 2], 1e-6))
    dh = np.log(np.maximum(gt_xywh[..., 3] / anchor_xywh[..., 3], 1e-6))
    return np.stack([dx, dy, dw, dh], axis=-1)


def decode_box(deltas: torch.Tensor, anchors_xywh: torch.Tensor) -> torch.Tensor:
    """Inverse of encode_box. Operates on torch tensors for use at inference."""
    cx = deltas[..., 0] * anchors_xywh[..., 2] + anchors_xywh[..., 0]
    cy = deltas[..., 1] * anchors_xywh[..., 3] + anchors_xywh[..., 1]
    w = torch.exp(deltas[..., 2]) * anchors_xywh[..., 2]
    h = torch.exp(deltas[..., 3]) * anchors_xywh[..., 3]
    return torch.stack([cx, cy, w, h], dim=-1)


def match_anchors_to_gt(anchors_xyxy: np.ndarray, gt_xyxy: np.ndarray,
                        pos_iou: float = 0.5, neg_iou: float = 0.4
                        ) -> tuple[np.ndarray, np.ndarray]:
    """For each anchor, find the best-matching GT box.

    Returns:
        assignment: (N,) int array. -1 for negative, -2 for "ignore" (between
                    neg_iou and pos_iou), >=0 = index of matched GT.
        max_iou:    (N,) float, the IoU each anchor has with its best GT.
    """
    if gt_xyxy.shape[0] == 0:
        return -np.ones(anchors_xyxy.shape[0], dtype=np.int64), \
            np.zeros(anchors_xyxy.shape[0], dtype=np.float32)
    ious = iou_matrix(anchors_xyxy, gt_xyxy)  # (N_anchor, N_gt)
    best_iou = ious.max(axis=1)
    best_gt = ious.argmax(axis=1)
    assignment = np.full(anchors_xyxy.shape[0], -1, dtype=np.int64)
    assignment[best_iou >= pos_iou] = best_gt[best_iou >= pos_iou]
    ignore_mask = (best_iou >= neg_iou) & (best_iou < pos_iou)
    assignment[ignore_mask] = -2
    # Force at least one positive per GT (highest-IoU anchor).
    for gt_idx in range(gt_xyxy.shape[0]):
        a_idx = int(ious[:, gt_idx].argmax())
        assignment[a_idx] = gt_idx
    return assignment, best_iou


def nms(boxes_xyxy: torch.Tensor, scores: torch.Tensor,
        iou_threshold: float = 0.3, top_k: int = 100) -> torch.Tensor:
    """Standard NMS. Returns kept indices (sorted by score desc)."""
    if boxes_xyxy.numel() == 0:
        return torch.empty(0, dtype=torch.long, device=boxes_xyxy.device)
    order = scores.argsort(descending=True)[:top_k]
    keep: list[int] = []
    while order.numel() > 0:
        i = int(order[0].item())
        keep.append(i)
        if order.numel() == 1:
            break
        rest = order[1:]
        iou = _iou_one_vs_many(boxes_xyxy[i], boxes_xyxy[rest])
        order = rest[iou < iou_threshold]
    return torch.tensor(keep, dtype=torch.long, device=boxes_xyxy.device)


def _iou_one_vs_many(box: torch.Tensor, others: torch.Tensor) -> torch.Tensor:
    inter_x1 = torch.maximum(box[0], others[:, 0])
    inter_y1 = torch.maximum(box[1], others[:, 1])
    inter_x2 = torch.minimum(box[2], others[:, 2])
    inter_y2 = torch.minimum(box[3], others[:, 3])
    inter = (inter_x2 - inter_x1).clamp(min=0) * (inter_y2 - inter_y1).clamp(min=0)
    area_box = (box[2] - box[0]) * (box[3] - box[1])
    area_others = (others[:, 2] - others[:, 0]) * (others[:, 3] - others[:, 1])
    union = area_box + area_others - inter
    return inter / union.clamp(min=1e-9)


@torch.no_grad()
def build_targets_gpu(boxes_per_image: list[torch.Tensor],
                     anchors_xywh: torch.Tensor,
                     anchors_xyxy: torch.Tensor,
                     pos_iou: float = 0.5,
                     neg_iou: float = 0.4,
                     ) -> tuple[torch.Tensor, torch.Tensor]:
    """GPU-side equivalent of _build_targets in train_v3_detector.

    Replaces the per-sample numpy IoU + argmax + assignment loop with batched
    torch ops on GPU. Returns the same (cls_target, box_target) tensors.

    Args:
        boxes_per_image: list of length B; each element is a (M_b, 4) tensor of
                          GT boxes in (cx, cy, w, h) form (on CPU or GPU).
        anchors_xywh: (N, 4) tensor on the target device (cx, cy, w, h).
        anchors_xyxy: (N, 4) tensor on the target device (x1, y1, x2, y2).

    Returns:
        cls_target: (B, N) int tensor, -1 ignore / 0 neg / 1 pos.
        box_target: (B, N, 4) float tensor, encoded deltas wrt anchors.
    """
    B = len(boxes_per_image)
    N = anchors_xywh.shape[0]
    device = anchors_xywh.device

    cls_t = torch.zeros((B, N), dtype=torch.long, device=device)
    box_t = torch.zeros((B, N, 4), dtype=torch.float32, device=device)

    anchor_area = ((anchors_xyxy[:, 2] - anchors_xyxy[:, 0]) *
                   (anchors_xyxy[:, 3] - anchors_xyxy[:, 1]))  # (N,)

    for b in range(B):
        gt = boxes_per_image[b]
        if gt is None or gt.numel() == 0:
            continue
        gt = gt.to(device=device, dtype=torch.float32, non_blocking=True)
        M = gt.shape[0]
        # xywh → xyxy on the GT side
        gt_xyxy = torch.stack([
            gt[:, 0] - gt[:, 2] * 0.5,
            gt[:, 1] - gt[:, 3] * 0.5,
            gt[:, 0] + gt[:, 2] * 0.5,
            gt[:, 1] + gt[:, 3] * 0.5,
        ], dim=1)  # (M, 4)

        # IoU matrix: anchors (N, 4) vs gt (M, 4)
        a = anchors_xyxy.unsqueeze(1)  # (N, 1, 4)
        g = gt_xyxy.unsqueeze(0)       # (1, M, 4)
        inter_w = (torch.minimum(a[..., 2], g[..., 2]) -
                   torch.maximum(a[..., 0], g[..., 0])).clamp(min=0)
        inter_h = (torch.minimum(a[..., 3], g[..., 3]) -
                   torch.maximum(a[..., 1], g[..., 1])).clamp(min=0)
        inter = inter_w * inter_h  # (N, M)
        gt_area = ((gt_xyxy[:, 2] - gt_xyxy[:, 0]) *
                   (gt_xyxy[:, 3] - gt_xyxy[:, 1]))  # (M,)
        union = anchor_area.unsqueeze(1) + gt_area.unsqueeze(0) - inter
        ious = inter / union.clamp(min=1e-9)  # (N, M)

        best_iou, best_gt = ious.max(dim=1)  # (N,), (N,)
        # Initialize assignment: -1 = negative.
        assignment = torch.full((N,), -1, dtype=torch.long, device=device)
        # Ignore zone (neg_iou <= IoU < pos_iou) → -2.
        ignore_mask = (best_iou >= neg_iou) & (best_iou < pos_iou)
        assignment[ignore_mask] = -2
        # Positives: IoU >= pos_iou → assigned to argmax GT.
        pos_mask = best_iou >= pos_iou
        assignment[pos_mask] = best_gt[pos_mask]
        # Force at least one positive per GT (best-IoU anchor for each GT).
        best_anchor_per_gt = ious.argmax(dim=0)  # (M,)
        gt_indices = torch.arange(M, device=device)
        assignment[best_anchor_per_gt] = gt_indices

        # Build cls row
        cls_row = torch.zeros(N, dtype=torch.long, device=device)
        cls_row[assignment == -2] = -1
        cls_row[assignment >= 0] = 1
        cls_t[b] = cls_row

        # Encode box deltas only for positive anchors
        pos_idx = (assignment >= 0).nonzero(as_tuple=True)[0]
        if pos_idx.numel() > 0:
            gt_for_pos = gt[assignment[pos_idx]]            # (P, 4) xywh
            anchors_pos = anchors_xywh[pos_idx]              # (P, 4) xywh
            dx = (gt_for_pos[:, 0] - anchors_pos[:, 0]) / anchors_pos[:, 2]
            dy = (gt_for_pos[:, 1] - anchors_pos[:, 1]) / anchors_pos[:, 3]
            dw = torch.log((gt_for_pos[:, 2] / anchors_pos[:, 2]).clamp(min=1e-6))
            dh = torch.log((gt_for_pos[:, 3] / anchors_pos[:, 3]).clamp(min=1e-6))
            box_t[b, pos_idx] = torch.stack([dx, dy, dw, dh], dim=1)

    return cls_t, box_t


@torch.no_grad()
def build_targets_gpu_batched(boxes_per_image: list[torch.Tensor],
                              anchors_xywh: torch.Tensor,
                              anchors_xyxy: torch.Tensor,
                              pos_iou: float = 0.5,
                              neg_iou: float = 0.4,
                              ) -> tuple[torch.Tensor, torch.Tensor]:
    """Fully-batched GPU anchor matcher (no Python loop in the hot path).

    Pads every sample's GT boxes to ``max_M`` (max GT count in the batch),
    then computes IoU/assignment/encoding as one big batched op. Padded GT
    slots are masked out via ``gt_valid`` so they cannot win any match.

    Inputs match the numpy ``_build_targets``:
        boxes_per_image: list[Tensor(M_b, 4)] in (cx, cy, w, h) form. Tensors
                         may be on CPU or GPU; they are moved to ``device``.
        anchors_xywh:    (N, 4) GPU tensor in (cx, cy, w, h).
        anchors_xyxy:    (N, 4) GPU tensor in (x1, y1, x2, y2).
        pos_iou/neg_iou: SSD-style match thresholds.

    Returns:
        cls_target: (B, N) int64. -1 ignore / 0 negative / 1 positive.
        box_target: (B, N, 4) float32. Encoded deltas; zero where not positive.

    Numerically equivalent to ``match_anchors_to_gt`` + numpy ``_build_targets``
    within float32 precision. Forced-positive semantics match the numpy
    version: each valid GT gets at least one anchor (its highest-IoU one)
    even if that IoU is below ``pos_iou``, overwriting whatever assignment
    that anchor previously had.
    """
    B = len(boxes_per_image)
    N = anchors_xywh.shape[0]
    device = anchors_xywh.device

    # Empty-batch shortcut.
    max_M = max((b.shape[0] for b in boxes_per_image), default=0)
    if max_M == 0:
        return (torch.zeros(B, N, dtype=torch.long, device=device),
                torch.zeros(B, N, 4, dtype=torch.float32, device=device))

    # Build the padded (B, max_M, 4) GT tensor + (B, max_M) validity mask
    # WITHOUT a per-sample .to(device) loop (256 small CUDA copies = regression).
    # Strategy:
    #   1. Concatenate all GTs on CPU into one (sum_M, 4) tensor + a (sum_M,)
    #      batch-index tensor (which sample each GT belongs to).
    #   2. Single .to(device) for both tensors.
    #   3. Build the gt_idx_in_sample tensor (within-sample position) on CPU
    #      then move to device.
    #   4. Scatter into the padded (B, max_M, 4) buffer with one index_put op.
    counts = [b.shape[0] for b in boxes_per_image]
    sum_M = sum(counts)
    gt_padded = torch.zeros(B, max_M, 4, dtype=torch.float32, device=device)
    gt_valid = torch.zeros(B, max_M, dtype=torch.bool, device=device)
    if sum_M > 0:
        # Concat all GT boxes (each is already a CPU torch.Tensor)
        flat_gt = torch.cat([b for b in boxes_per_image if b.shape[0] > 0], dim=0)
        # Build batch-index + within-sample-index tensors on CPU
        batch_idx_cpu = torch.empty(sum_M, dtype=torch.long)
        inner_idx_cpu = torch.empty(sum_M, dtype=torch.long)
        ofs = 0
        for b_i, c in enumerate(counts):
            if c > 0:
                batch_idx_cpu[ofs:ofs + c] = b_i
                inner_idx_cpu[ofs:ofs + c] = torch.arange(c)
                ofs += c
        # Single async transfer of the three tensors → GPU
        flat_gt = flat_gt.to(device=device, dtype=torch.float32, non_blocking=True)
        batch_idx = batch_idx_cpu.to(device=device, non_blocking=True)
        inner_idx = inner_idx_cpu.to(device=device, non_blocking=True)
        # Scatter into the padded buffer
        gt_padded[batch_idx, inner_idx] = flat_gt
        gt_valid[batch_idx, inner_idx] = True

    # xywh → xyxy on the padded GTs: (B, max_M, 4).
    gt_xyxy_padded = torch.stack([
        gt_padded[..., 0] - gt_padded[..., 2] * 0.5,
        gt_padded[..., 1] - gt_padded[..., 3] * 0.5,
        gt_padded[..., 0] + gt_padded[..., 2] * 0.5,
        gt_padded[..., 1] + gt_padded[..., 3] * 0.5,
    ], dim=-1)

    # Batched IoU: (B, N, max_M). Broadcast anchors (1, N, 1, 4) against
    # padded GTs (B, 1, max_M, 4).
    a = anchors_xyxy.unsqueeze(0).unsqueeze(2)    # (1, N, 1, 4)
    g = gt_xyxy_padded.unsqueeze(1)               # (B, 1, max_M, 4)
    inter_w = (torch.minimum(a[..., 2], g[..., 2]) -
               torch.maximum(a[..., 0], g[..., 0])).clamp(min=0)
    inter_h = (torch.minimum(a[..., 3], g[..., 3]) -
               torch.maximum(a[..., 1], g[..., 1])).clamp(min=0)
    inter = inter_w * inter_h                     # (B, N, max_M)
    anchor_area = ((anchors_xyxy[:, 2] - anchors_xyxy[:, 0]) *
                   (anchors_xyxy[:, 3] - anchors_xyxy[:, 1]))  # (N,)
    gt_area = ((gt_xyxy_padded[..., 2] - gt_xyxy_padded[..., 0]) *
               (gt_xyxy_padded[..., 3] - gt_xyxy_padded[..., 1]))  # (B, max_M)
    union = anchor_area.view(1, N, 1) + gt_area.unsqueeze(1) - inter
    ious = inter / union.clamp(min=1e-9)          # (B, N, max_M)

    # Zero out IoU against padded GT positions so they cannot win any match
    # (best-IoU-per-anchor or best-anchor-per-GT).
    ious = ious * gt_valid.unsqueeze(1).to(ious.dtype)  # (B, N, max_M)

    # Best GT per anchor → drives the pos/ignore/neg decision.
    best_iou_per_anchor, best_gt_per_anchor = ious.max(dim=2)  # (B, N), (B, N)

    # Assignment encoding (internal):
    #   -1 = negative (default), -2 = ignore, >=0 = positive (GT index).
    assignment = torch.full((B, N), -1, dtype=torch.long, device=device)
    ignore = (best_iou_per_anchor >= neg_iou) & (best_iou_per_anchor < pos_iou)
    assignment[ignore] = -2
    positive = best_iou_per_anchor >= pos_iou
    assignment[positive] = best_gt_per_anchor[positive]

    # Forced positive: every valid GT gets its highest-IoU anchor, even if
    # that IoU is below pos_iou. This OVERWRITES whatever the anchor's prior
    # assignment was (matching the numpy loop:
    #   `assignment[a_idx] = gt_idx` for each gt).
    best_anchor_per_gt = ious.argmax(dim=1)        # (B, max_M)
    batch_idx = torch.arange(B, device=device).unsqueeze(1).expand(B, max_M)
    gt_idx_grid = torch.arange(max_M, device=device).unsqueeze(0).expand(B, max_M)
    flat_b = batch_idx[gt_valid]                   # (#valid,)
    flat_anchor = best_anchor_per_gt[gt_valid]     # (#valid,)
    flat_gt = gt_idx_grid[gt_valid]                # (#valid,)
    # Note: if two GTs in the same sample happen to share the same
    # best_anchor_per_gt (rare but possible at very-tiny GTs), the later
    # write wins. numpy's loop has the same property.
    assignment[flat_b, flat_anchor] = flat_gt

    # Build cls_target: positives → 1, ignore → -1, negative → 0.
    cls_target = torch.zeros((B, N), dtype=torch.long, device=device)
    cls_target[assignment == -2] = -1
    cls_target[assignment >= 0] = 1

    # Build box_target: encode deltas for positive anchors only.
    box_target = torch.zeros((B, N, 4), dtype=torch.float32, device=device)
    pos_mask = assignment >= 0                     # (B, N)
    if pos_mask.any():
        pos_b, pos_n = pos_mask.nonzero(as_tuple=True)
        gt_for_pos = gt_padded[pos_b, assignment[pos_b, pos_n]]  # (P, 4) xywh
        anchors_pos = anchors_xywh[pos_n]                         # (P, 4) xywh
        dx = (gt_for_pos[:, 0] - anchors_pos[:, 0]) / anchors_pos[:, 2]
        dy = (gt_for_pos[:, 1] - anchors_pos[:, 1]) / anchors_pos[:, 3]
        dw = torch.log((gt_for_pos[:, 2] / anchors_pos[:, 2]).clamp(min=1e-6))
        dh = torch.log((gt_for_pos[:, 3] / anchors_pos[:, 3]).clamp(min=1e-6))
        box_target[pos_b, pos_n] = torch.stack([dx, dy, dw, dh], dim=1)

    return cls_target, box_target
