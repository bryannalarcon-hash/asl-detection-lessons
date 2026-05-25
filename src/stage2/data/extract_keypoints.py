"""Offline keypoint extraction for Net 4 training data.

Walks a manifest of (clip_path, gloss, split) entries, runs each clip
through the frozen Stage 1 stack (Net 1 face+body, Net 2 palm bbox, Net 3
hand landmarks) and writes one .npz per clip containing the per-frame
49-keypoint tensors that Net 4 consumes.

The extractor is the single bridge between Stage 1 (per-frame CV) and
Stage 2 (sequence classifier). It can also be reused at inference time
in batch mode for offline scoring; live webcam inference takes the same
code path inline.

Usage:
    python -m src.stage2.data.extract_keypoints \\
        --manifest data/signs/manifest.jsonl \\
        --net1 results/v3/net1_v3_1/best.pt \\
        --net2 results/v3/net2_v3_1/best.pt \\
        --net3 results/v3/net3_v1/best.pt \\
        --out data/signs/kpt_cache/ \\
        --max-frames 64

The .npz layout per clip:
    keypoints       (T, 49, 2)  image-space (x, y) before normalisation
    visibility      (T, 49)     1 = present, 0 = padded/missing
    width, height   int         original frame size for downstream norm
    gloss, split    str         label + split tag
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from src.stage1.data import schema as S
from src.stage1.data.palm_boxes import HandBBox
from src.stage1.data.hand_crops import crop_hand, project_kpts, unproject_kpts
from src.stage1.models import anchors as anchors_mod
from src.stage1.models.anchors import decode_box, get_anchors, nms
from src.stage1.models.detector import KeypointDetector, soft_argmax_2d
from src.stage1.models.landmark_net import HandLandmarkNet, HandLandmarkRegNet
from src.stage1.models.palm_detector import PalmDetector


def upright_rotation_deg(wrist: tuple[float, float],
                         mcp: tuple[float, float]) -> float:
    """Rotation (deg, CCW) that points the wrist->MCP vector UP in the crop.

    ``crop_hand`` builds M so an image point p maps to crop coords as
    R(theta) @ (p - centre) * scale + crop_centre, where R(theta) is a CCW
    rotation by ``rotation_deg`` in the image coordinate frame (x right, y
    down). We want the wrist->MCP direction to land on the crop's "up"
    direction, i.e. (0, -1) in crop pixels.

    In image coords the vector is v = mcp - wrist with angle
    a = atan2(dy, dx) measured from +x (down-positive y). Applying R(theta)
    rotates that angle to a + theta. "Up" in the (x-right, y-down) crop frame
    is angle -90 deg. So theta = -90 - a. Returns degrees.
    """
    dx = float(mcp[0]) - float(wrist[0])
    dy = float(mcp[1]) - float(wrist[1])
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return 0.0
    a = np.degrees(np.arctan2(dy, dx))
    return -90.0 - a


def letterbox(img: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    h, w = img.shape[:2]
    scale = size / max(h, w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    out = np.zeros((size, size, 3), dtype=img.dtype)
    dy = (size - nh) // 2
    dx = (size - nw) // 2
    out[dy:dy + nh, dx:dx + nw] = resized
    return out, scale, dx, dy


def load_net1(ckpt_path: str, device: str) -> tuple[KeypointDetector, int, list | None]:
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    state = ckpt.get("model", ckpt)
    cfg = ckpt.get("config", {}) or {}
    model_cfg = cfg.get("model", {}) if isinstance(cfg, dict) else {}
    data_cfg = cfg.get("data", {}) if isinstance(cfg, dict) else {}
    k = int(model_cfg.get("num_keypoints", S.NUM_KEYPOINTS))
    kslice = data_cfg.get("keypoint_slice")
    final_w = state.get("final.weight")
    if final_w is not None and final_w.shape[0] != k:
        k = int(final_w.shape[0])
    model = KeypointDetector(num_keypoints=k).to(device).eval()
    model.load_state_dict(state)
    return model, k, kslice


def load_net2(ckpt_path: str, device: str) -> tuple[PalmDetector, dict]:
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    state = ckpt.get("model", ckpt)
    cfg = ckpt.get("config") or {}
    model_block = cfg.get("model", {}) if isinstance(cfg, dict) else {}
    data_block = cfg.get("data", {}) if isinstance(cfg, dict) else {}
    anchors_block = cfg.get("anchors", {}) if isinstance(cfg, dict) else {}
    n_anchors = int(model_block.get("n_anchors_per_cell", 3))
    aps = model_block.get("anchors_per_scale")
    use_fpn = bool(model_block.get("use_fpn", False))
    n_kpts = int(model_block.get("n_kpts", 0))
    input_size = int(data_block.get("input_size", 192))
    strides_cfg = anchors_block.get("strides")
    scales_per_stride = anchors_block.get("scales_per_stride")
    square = bool(anchors_block.get("square", False))

    # n_kpts MUST be passed: a detector trained with a keypoint head stores
    # its kpt.* tensors, and a strict=False load would silently drop them if
    # the model were built with n_kpts=0 — leaving inference with no
    # orientation keypoints and forcing the slow 2-pass crop fallback.
    pd_kwargs = dict(n_anchors_per_cell=n_anchors, n_aux_kpts=0, n_kpts=n_kpts)
    if use_fpn:
        pd_kwargs["use_fpn"] = True
    if aps:
        pd_kwargs["anchors_per_scale"] = tuple(int(x) for x in aps)
    model = PalmDetector(**pd_kwargs).to(device).eval()
    incompatible = model.load_state_dict(state, strict=False)
    dropped_kpt = [k for k in getattr(incompatible, "unexpected_keys", [])
                   if "kpt" in k]
    if dropped_kpt:
        raise RuntimeError(
            f"Net 2 checkpoint has keypoint weights that were dropped on load "
            f"(model built with n_kpts={n_kpts}): {dropped_kpt[:4]}... — the "
            f"oriented-crop path would be silently disabled.")

    # Anchor generation at inference MUST mirror training (square in
    # particular) or box/keypoint decode is misaligned.
    if scales_per_stride and strides_cfg:
        anchors = get_anchors(input_size, scales_per_stride=scales_per_stride,
                              strides=strides_cfg, square=square)
    else:
        anchors = get_anchors(input_size, square=square)
    meta = {"input_size": input_size, "n_kpts": n_kpts,
            "anchors_xywh": torch.from_numpy(anchors).float().to(device)}
    return model, meta


def load_net3(ckpt_path: str, device: str) -> tuple[torch.nn.Module, str]:
    """Load Net 3 in either head mode.

    Returns (model, head_type) where head_type is "regression" (new
    ``HandLandmarkRegNet`` — forward returns {"coords": (B,21,3)} with
    coords[...,:2] normalized to [0,1]) or "heatmap" (legacy
    ``HandLandmarkNet`` — forward returns (B,21,56,56)). The mode is read
    from ckpt["head_type"] when present, else inferred from the config or
    the state dict keys for backward compatibility.
    """
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    state = ckpt.get("model", ckpt)
    cfg = ckpt.get("config", {}) or {}
    model_cfg = cfg.get("model", {}) if isinstance(cfg, dict) else {}

    head_type = ckpt.get("head_type")
    if head_type is None:
        head_type = model_cfg.get("head_type")
    if head_type is None:
        # Infer from weights: the regressor has coord_head/fc1; the heatmap
        # net has deconv layers + a conv head.
        keys = list(state.keys())
        if any(k.startswith("coord_head") for k in keys):
            head_type = "regression"
        else:
            head_type = "heatmap"
    head_type = str(head_type).lower()

    num_keypoints = int(model_cfg.get("num_keypoints", 21))
    if head_type == "regression":
        with_z = bool(model_cfg.get("with_z", True))
        with_presence = bool(model_cfg.get("with_presence", True))
        if not any(k.startswith("presence_head") for k in state.keys()):
            with_presence = False
        model = HandLandmarkRegNet(
            num_keypoints=num_keypoints, with_z=with_z,
            with_presence=with_presence,
        ).to(device).eval()
    else:
        model = HandLandmarkNet(
            num_keypoints=num_keypoints,
            heatmap_channels=int(model_cfg.get("heatmap_channels", 128)),
        ).to(device).eval()
    model.load_state_dict(state, strict=False)
    return model, head_type


def iter_video_frames(path: Path, max_frames: int = 64) -> Iterator[np.ndarray]:
    """Uniformly sample up to max_frames frames from a video."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if n <= 0:
        n = max_frames
    if n > max_frames:
        idxs = np.linspace(0, n - 1, max_frames).astype(int)
    else:
        idxs = list(range(n))
    idx_set = set(idxs.tolist() if isinstance(idxs, np.ndarray) else idxs)
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i in idx_set:
            yield frame
        i += 1
    cap.release()


def run_net1(model: KeypointDetector, k: int, kslice,
             frame_bgr: np.ndarray, device: str,
             input_size: int = 256) -> tuple[np.ndarray, np.ndarray]:
    """Returns (49, 2) keypoints in original-frame coords + visibility (49,).

    Net 1 is K=7 sliced (face+body indices). The slice maps local k→global
    via kslice = [s, e]. Hand slots stay zero/invisible here; Net 3 fills them.
    """
    H, W = frame_bgr.shape[:2]
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    boxed, scale, dx, dy = letterbox(rgb, input_size)
    tensor = (boxed.astype(np.float32) / 255.0 - 0.5) / 0.5
    tensor = torch.from_numpy(tensor).permute(2, 0, 1).unsqueeze(0).to(device)
    with torch.no_grad():
        heatmaps = model(tensor)
        coords_hm = soft_argmax_2d(heatmaps)[0].cpu().numpy()
        peak = heatmaps[0].view(heatmaps.shape[1], -1).max(dim=-1).values.cpu().numpy()
    hm_size = heatmaps.shape[-1]
    coords = coords_hm * (input_size / hm_size)
    coords[:, 0] = (coords[:, 0] - dx) / scale
    coords[:, 1] = (coords[:, 1] - dy) / scale

    out_kpts = np.zeros((S.NUM_KEYPOINTS, 2), dtype=np.float32)
    out_vis = np.zeros(S.NUM_KEYPOINTS, dtype=np.float32)
    if kslice and len(kslice) == 2:
        s_idx, e_idx = int(kslice[0]), int(kslice[1])
        K = min(k, e_idx - s_idx)
        for j in range(K):
            x, y = coords[j]
            if 0 <= x < W and 0 <= y < H and peak[j] > 0.05:
                out_kpts[s_idx + j] = (x, y)
                out_vis[s_idx + j] = 1.0
    else:
        K = min(k, S.NUM_KEYPOINTS)
        for j in range(K):
            x, y = coords[j]
            if 0 <= x < W and 0 <= y < H and peak[j] > 0.05:
                out_kpts[j] = (x, y)
                out_vis[j] = 1.0
    return out_kpts, out_vis


def _decode_box_kpts(kpt_offsets: torch.Tensor, anchors_xywh: torch.Tensor
                     ) -> torch.Tensor | None:
    """Decode Net 2 keypoint offsets to input-pixel points.

    Net 2's kpt head emits (M, 2*n_kpts) or (M, n_kpts, ...) anchor-relative
    offsets. Prefer the canonical ``decode_kpts`` from anchors.py when the
    Net 2 agent has landed it; otherwise fall back to the standard
    SSD-keypoint decoding x = ox*aw + acx, y = oy*ah + acy. Returns
    (M, n_kpts, 2) in input pixels, or None if the offset shape is
    unrecognised.
    """
    decode_fn = getattr(anchors_mod, "decode_kpts", None)
    if decode_fn is not None:
        try:
            pts = decode_fn(kpt_offsets, anchors_xywh)
            return pts[..., :2] if pts is not None else None
        except Exception:
            pass
    off = kpt_offsets
    if off.dim() == 2:
        if off.shape[1] % 2 != 0:
            return None
        off = off.view(off.shape[0], -1, 2)
    if off.dim() != 3 or off.shape[-1] < 2:
        return None
    acx = anchors_xywh[:, None, 0]
    acy = anchors_xywh[:, None, 1]
    aw = anchors_xywh[:, None, 2]
    ah = anchors_xywh[:, None, 3]
    x = off[..., 0] * aw + acx
    y = off[..., 1] * ah + acy
    return torch.stack([x, y], dim=-1)


def run_net2(model: PalmDetector, meta: dict, frame_bgr: np.ndarray,
             device: str, conf: float = 0.3, iou_thresh: float = 0.3,
             max_boxes: int = 2
             ) -> list[tuple[float, tuple[float, float, float, float],
                             np.ndarray | None]]:
    """Returns list of (score, (x1,y1,x2,y2), kpts) in original-frame coords.

    ``kpts`` is an (n_kpts, 2) array of (wrist, middle-MCP) in original-frame
    pixels when the loaded Net 2 exposes a keypoint head (``preds["kpt"]``)
    and the offsets decode cleanly; otherwise it is None (older Net 2 ckpt,
    or undecodable shape) and the caller uses the 2-pass Net 3 fallback.
    """
    H, W = frame_bgr.shape[:2]
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    boxed, scale, dx, dy = letterbox(rgb, meta["input_size"])
    tensor = (boxed.astype(np.float32) / 255.0 - 0.5) / 0.5
    tensor = torch.from_numpy(tensor).permute(2, 0, 1).unsqueeze(0).to(device)
    with torch.no_grad():
        preds = model(tensor)
    cls = torch.sigmoid(preds["cls"][0]).squeeze(-1)
    deltas = preds["box"][0]
    kpt_all = preds.get("kpt")  # (N, 2*n_kpts) or None — contract-dependent
    keep = cls >= conf
    if not keep.any():
        return []
    keep_idx_all = keep.nonzero(as_tuple=True)[0]
    scores = cls[keep]
    d = deltas[keep]
    a = meta["anchors_xywh"][keep]
    dec = decode_box(d, a)
    xyxy = torch.stack([
        dec[:, 0] - dec[:, 2] * 0.5,
        dec[:, 1] - dec[:, 3] * 0.5,
        dec[:, 0] + dec[:, 2] * 0.5,
        dec[:, 1] + dec[:, 3] * 0.5,
    ], dim=1)

    # Decode keypoints for the kept anchors, mapped to original-frame px.
    kpts_kept: torch.Tensor | None = None
    if kpt_all is not None:
        kpt_kept = kpt_all[0][keep]
        pts = _decode_box_kpts(kpt_kept, a)  # (M, n_kpts, 2) input px
        if pts is not None:
            pts = pts.clone()
            pts[..., 0] = (pts[..., 0] - dx) / scale
            pts[..., 1] = (pts[..., 1] - dy) / scale
            kpts_kept = pts

    nms_idx = nms(xyxy, scores, iou_threshold=iou_thresh, top_k=max_boxes)
    out: list[tuple[float, tuple[float, float, float, float],
                    np.ndarray | None]] = []
    for ki in nms_idx.tolist():
        x1, y1, x2, y2 = xyxy[ki].tolist()
        x1 = (x1 - dx) / scale; y1 = (y1 - dy) / scale
        x2 = (x2 - dx) / scale; y2 = (y2 - dy) / scale
        box_kpts = (kpts_kept[ki].cpu().numpy().astype(np.float32)
                    if kpts_kept is not None else None)
        out.append((float(scores[ki].item()), (x1, y1, x2, y2), box_kpts))
    return out


def _expand_box(bbox_xyxy: tuple, W: int, H: int,
                frac: float = 0.05) -> tuple | None:
    """Expand a palm box by ``frac`` each side, clamp to frame. None if tiny."""
    x1, y1, x2, y2 = bbox_xyxy
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    bw, bh = x2 - x1, y2 - y1
    x1 = max(0, x1 - frac * bw); x2 = min(W - 1, x2 + frac * bw)
    y1 = max(0, y1 - frac * bh); y2 = min(H - 1, y2 + frac * bh)
    return (x1, y1, x2, y2)


def _net3_one_pass(model: torch.nn.Module, head_type: str, rgb: np.ndarray,
                   box: HandBBox, device: str, rotation_deg: float,
                   crop_size: int) -> tuple[np.ndarray, np.ndarray]:
    """One crop+forward. Returns (crop_px_coords (21,2), M).

    crop_px_coords are in the rotated crop's pixel space; M maps image->crop
    so unproject_kpts(crop_px_coords, M) recovers frame px (M encodes the
    rotation). Works for both the regression and heatmap heads.
    """
    crop, M = crop_hand(rgb, box, out_size=crop_size, rotation_deg=rotation_deg)
    tensor = torch.from_numpy(crop).permute(2, 0, 1).float() / 255.0
    tensor = ((tensor - 0.5) / 0.5).unsqueeze(0).to(device)
    with torch.no_grad():
        out = model(tensor)
    if head_type == "regression":
        coords = out["coords"][0, :, :2].cpu().numpy()  # normalized [0,1]
        coords_crop = (coords * crop_size).astype(np.float32)
    else:
        coords_hm = soft_argmax_2d(out)[0].cpu().numpy()
        hm_size = out.shape[-1]
        coords_crop = (coords_hm * (crop_size / hm_size)).astype(np.float32)
    return coords_crop, M


def run_net3(model: torch.nn.Module, head_type: str, frame_bgr: np.ndarray,
             bbox_xyxy: tuple, device: str, crop_size: int = 224,
             net2_kpts: np.ndarray | None = None,
             two_pass_fallback: bool = True) -> np.ndarray | None:
    """Run Net 3 on an ORIENTED hand crop; return 21 kpts in frame coords.

    Orientation strategy:
      (a) If Net 2 supplied wrist + middle-MCP keypoints (``net2_kpts``,
          shape (>=2, 2) in frame px), rotate the crop so the wrist->MCP
          vector points up, run Net 3 once, unproject.
      (b) Else, two-pass: crop axis-aligned, run Net 3, read its predicted
          wrist (idx 0) + middle-MCP (idx 9) in crop px, compute the angle,
          re-crop rotated, run Net 3 again, unproject. The second pass is
          skipped when ``two_pass_fallback`` is False (cost control) — the
          axis-aligned result is returned instead.

    unproject already handles the rotation because M encodes it.
    """
    H, W = frame_bgr.shape[:2]
    expanded = _expand_box(bbox_xyxy, W, H)
    if expanded is None:
        return None
    x1, y1, x2, y2 = expanded
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    box = HandBBox(x=x1, y=y1, w=x2 - x1, h=y2 - y1, side="right")

    if net2_kpts is not None and net2_kpts.shape[0] >= 2:
        rot = upright_rotation_deg(tuple(net2_kpts[0]), tuple(net2_kpts[1]))
        coords_crop, M = _net3_one_pass(model, head_type, rgb, box, device,
                                        rot, crop_size)
        return unproject_kpts(coords_crop, M).astype(np.float32)

    # Pass 1: axis-aligned.
    coords_crop, M = _net3_one_pass(model, head_type, rgb, box, device,
                                    0.0, crop_size)
    if not two_pass_fallback:
        return unproject_kpts(coords_crop, M).astype(np.float32)

    # Pass 2: re-crop oriented using Net 3's own wrist(0) + middle-MCP(9).
    wrist_crop = coords_crop[0]
    mcp_crop = coords_crop[9]
    rot = upright_rotation_deg(tuple(wrist_crop), tuple(mcp_crop))
    coords_crop2, M2 = _net3_one_pass(model, head_type, rgb, box, device,
                                      rot, crop_size)
    return unproject_kpts(coords_crop2, M2).astype(np.float32)


def assign_hand_side(bboxes: list, body_kpts: np.ndarray,
                     body_vis: np.ndarray) -> list[str]:
    """Assign each detected palm bbox to 'right' or 'left' (signer's POV).

    Heuristic: palm whose centre is on the SIGNER's right (camera's left,
    smaller x) maps to RIGHT_HAND. If body keypoints visible, use the nose
    x as midline; else use image width / 2.
    """
    if not bboxes:
        return []
    sides: list[str] = []
    # Nose lives at LEFT_HAND_START - 7? No — kslice on Net1 puts face+body at
    # configured slot. Use the mean x of any visible Net1 kpts as midline,
    # falling back to image-mid via body bbox if needed.
    visible_xs = body_kpts[body_vis > 0.5, 0]
    if visible_xs.size > 0:
        midline = float(visible_xs.mean())
    else:
        midline = None
    if len(bboxes) == 1:
        x1, y1, x2, y2 = bboxes[0][1]
        cx = (x1 + x2) * 0.5
        if midline is None or cx < midline:
            sides.append("right")
        else:
            sides.append("left")
        return sides
    sorted_b = sorted(enumerate(bboxes), key=lambda kv: (kv[1][1][0] + kv[1][1][2]) * 0.5)
    side_for_pos = ["right", "left"]
    pos_for_orig = {sorted_b[i][0]: side_for_pos[i] for i in range(min(2, len(sorted_b)))}
    sides = [pos_for_orig[i] for i in range(len(bboxes))]
    return sides


def extract_one_clip(net1, net1_k, net1_kslice, net2, net2_meta, net3,
                     net3_head_type, clip_path: Path, device: str,
                     max_frames: int = 64, two_pass_fallback: bool = True
                     ) -> tuple[np.ndarray, np.ndarray, int, int] | None:
    """Run the full Stage 1 stack on one clip. Returns (kpts, vis, W, H)."""
    kpts_out: list[np.ndarray] = []
    vis_out: list[np.ndarray] = []
    W_orig = H_orig = 0
    for frame in iter_video_frames(clip_path, max_frames=max_frames):
        if frame is None:
            continue
        H_orig, W_orig = frame.shape[:2]
        body_k, body_v = run_net1(net1, net1_k, net1_kslice, frame, device)
        kpts_frame = body_k.copy()
        vis_frame = body_v.copy()

        bboxes = run_net2(net2, net2_meta, frame, device)
        sides = assign_hand_side(bboxes, body_k, body_v)
        for (score, xyxy, box_kpts), side in zip(bboxes, sides):
            hand_kpts = run_net3(net3, net3_head_type, frame, xyxy, device,
                                 net2_kpts=box_kpts,
                                 two_pass_fallback=two_pass_fallback)
            if hand_kpts is None:
                continue
            slot_start = (S.RIGHT_HAND_START if side == "right"
                          else S.LEFT_HAND_START)
            for j in range(21):
                x, y = hand_kpts[j]
                if 0 <= x < W_orig and 0 <= y < H_orig:
                    kpts_frame[slot_start + j] = (x, y)
                    vis_frame[slot_start + j] = 1.0
        kpts_out.append(kpts_frame)
        vis_out.append(vis_frame)
    if not kpts_out:
        return None
    return (np.stack(kpts_out), np.stack(vis_out), W_orig, H_orig)


def process_one(entry: dict, *, extract_fn, models: tuple, out_dir: Path,
                device: str, max_frames: int, two_pass: bool,
                skip_existing: bool, delete_after: bool,
                write_lock: threading.Lock) -> str:
    """Handle one manifest entry end-to-end. Returns a status tag.

    Status is one of {"skip", "miss", "fail", "done"}. Models are shared
    (loaded once in main); each entry is owned by exactly one caller, so the
    per-clip npz write + source delete are race-free apart from the npz write
    itself, which is serialised under ``write_lock`` for safety. Thread-safe:
    the extract fns build their own per-call tensors and only read the shared
    models; torch inference releases the GIL.
    """
    net1, net1_k, net1_kslice, net2, net2_meta, net3, net3_head_type = models
    clip_path = Path(entry["clip_path"])
    gloss = entry["gloss"]
    split = entry.get("split", "train")
    out_path = out_dir / f"{clip_path.stem}.npz"
    if skip_existing and out_path.exists():
        return "skip"
    if not clip_path.exists():
        print(f"[miss] {clip_path}", flush=True)
        return "miss"
    result = extract_fn(net1, net1_k, net1_kslice, net2,
                        net2_meta, net3, net3_head_type,
                        clip_path, device,
                        max_frames=max_frames,
                        two_pass_fallback=two_pass)
    if result is None:
        print(f"[fail] {clip_path}", flush=True)
        return "fail"
    kpts, vis, W, H = result
    with write_lock:
        np.savez_compressed(out_path,
                            keypoints=kpts.astype(np.float32),
                            visibility=vis.astype(np.float32),
                            width=W, height=H,
                            gloss=gloss, split=split,
                            clip_id=clip_path.stem)
    if delete_after:
        try:
            clip_path.unlink()
        except OSError:
            pass
    return "done"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True,
                   help="JSONL with {clip_path, gloss, split} entries.")
    p.add_argument("--net1", required=True)
    p.add_argument("--net2", required=True)
    p.add_argument("--net3", required=True)
    p.add_argument("--out", required=True, help="Output dir for .npz files")
    p.add_argument("--max-frames", type=int, default=64)
    p.add_argument("--device", default=None)
    p.add_argument("--skip-existing", action="store_true", default=True)
    p.add_argument("--delete-after", action="store_true",
                   help="Delete the source video after successful extraction "
                        "(use when disk is tight)")
    p.add_argument("--limit", type=int, default=0,
                   help="Process only the first N entries (smoke test)")
    p.add_argument("--no-two-pass", action="store_true",
                   help="Disable the 2nd oriented Net 3 pass when Net 2 has "
                        "no keypoint head. Halves Net 3 cost at the price of "
                        "axis-aligned (unrotated) crops for those hands.")
    p.add_argument("--batched", action="store_true",
                   help="Use the GPU-batched extractor "
                        "(extract_one_clip_batched): one forward per network "
                        "per clip instead of one per frame. Output is "
                        "equivalent to the per-frame reference path.")
    p.add_argument("--workers", type=int, default=1,
                   help="Number of clip-processing threads (default 1 = "
                        "serial). >1 runs a ThreadPoolExecutor over clips; "
                        "cv2 video decode releases the GIL so decode "
                        "parallelises. Models load ONCE and are shared across "
                        "threads (do not use processes — they would reload "
                        "the models per worker).")
    args = p.parse_args()

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[init] device={device}", flush=True)

    net1, net1_k, net1_kslice = load_net1(args.net1, device)
    net2, net2_meta = load_net2(args.net2, device)
    net3, net3_head_type = load_net3(args.net3, device)
    two_pass = not args.no_two_pass
    if args.batched:
        from src.stage2.data.extract_keypoints_batched import (
            extract_one_clip_batched)
        extract_fn = extract_one_clip_batched
        print("[init] using batched extractor", flush=True)
    else:
        extract_fn = extract_one_clip
    print(f"[init] net1 K={net1_k} slice={net1_kslice}", flush=True)
    print(f"[init] net2 input={net2_meta['input_size']} "
          f"anchors={net2_meta['anchors_xywh'].shape}", flush=True)
    print(f"[init] net3 head={net3_head_type} two_pass_fallback={two_pass}",
          flush=True)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    with open(args.manifest) as f:
        for line_no, line in enumerate(f, 1):
            if args.limit and line_no > args.limit:
                break
            entries.append(json.loads(line))

    models = (net1, net1_k, net1_kslice, net2, net2_meta, net3,
              net3_head_type)
    write_lock = threading.Lock()
    counts = {"done": 0, "skip": 0, "miss": 0, "fail": 0}
    counts_lock = threading.Lock()
    t0 = time.time()
    workers = max(1, int(args.workers))
    print(f"[init] workers={workers}", flush=True)

    def work(entry: dict) -> str:
        status = process_one(
            entry, extract_fn=extract_fn, models=models, out_dir=out_dir,
            device=device, max_frames=args.max_frames, two_pass=two_pass,
            skip_existing=args.skip_existing, delete_after=args.delete_after,
            write_lock=write_lock)
        with counts_lock:
            counts[status] += 1
            n_done = counts["done"]
            if status == "done" and n_done % 50 == 0:
                rate = n_done / max(time.time() - t0, 1e-6)
                print(f"[prog] done={n_done} skip={counts['skip']} "
                      f"fail={counts['fail'] + counts['miss']} "
                      f"rate={rate:.1f}/s elapsed={time.time()-t0:.0f}s",
                      flush=True)
        return status

    if workers == 1:
        for entry in entries:
            work(entry)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(work, entry) for entry in entries]
            for fut in as_completed(futures):
                fut.result()

    n_done = counts["done"]
    n_fail = counts["fail"] + counts["miss"]
    rate = n_done / max(time.time() - t0, 1e-6)
    print(f"[done] {n_done} extracted, {counts['skip']} skipped, {n_fail} "
          f"failed ({rate:.2f}/s)", flush=True)


if __name__ == "__main__":
    main()
