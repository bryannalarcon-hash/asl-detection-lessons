"""SSD-style anchor generation, matching, and NMS for the palm detector.

Anchors are placed on a grid at 3 feature-map scales (P1 24x24, P2 12x12,
P3 6x6 for a 192x192 input). At each cell we have 3 square anchors at
relative scales {0.10, 0.20, 0.35} of the input image size.

Total anchors: (24*24 + 12*12 + 6*6) * 3 = 2,268.
"""
from __future__ import annotations

import numpy as np
import torch


# Anchor configuration tuned for 192x192 input.
INPUT_SIZE = 192
FEAT_GRID_SIZES = (24, 12, 6)
ANCHOR_SCALES_FRAC = (0.10, 0.20, 0.35)  # relative to INPUT_SIZE
N_ANCHORS_PER_CELL = len(ANCHOR_SCALES_FRAC)


def generate_anchors(input_size: int = INPUT_SIZE,
                     grid_sizes: tuple[int, ...] = FEAT_GRID_SIZES,
                     scales_frac: tuple[float, ...] = ANCHOR_SCALES_FRAC,
                     ) -> np.ndarray:
    """Return (N, 4) array of anchors in (cx, cy, w, h) image-pixel coords."""
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


_ANCHORS_CACHE = {}


def get_anchors(input_size: int = INPUT_SIZE) -> np.ndarray:
    if input_size not in _ANCHORS_CACHE:
        _ANCHORS_CACHE[input_size] = generate_anchors(input_size=input_size)
    return _ANCHORS_CACHE[input_size]


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
