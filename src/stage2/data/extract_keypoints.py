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
import time
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
from src.stage1.models.anchors import decode_box, get_anchors, nms
from src.stage1.models.detector import KeypointDetector, soft_argmax_2d
from src.stage1.models.landmark_net import HandLandmarkNet
from src.stage1.models.palm_detector import PalmDetector


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
    input_size = int(data_block.get("input_size", 192))
    strides_cfg = anchors_block.get("strides")
    scales_per_stride = anchors_block.get("scales_per_stride")

    pd_kwargs = dict(n_anchors_per_cell=n_anchors, n_aux_kpts=0)
    if use_fpn:
        pd_kwargs["use_fpn"] = True
    if aps:
        pd_kwargs["anchors_per_scale"] = tuple(int(x) for x in aps)
    model = PalmDetector(**pd_kwargs).to(device).eval()
    model.load_state_dict(state, strict=False)

    if scales_per_stride and strides_cfg:
        anchors = get_anchors(input_size, scales_per_stride=scales_per_stride,
                              strides=strides_cfg)
    else:
        anchors = get_anchors(input_size)
    meta = {"input_size": input_size,
            "anchors_xywh": torch.from_numpy(anchors).float().to(device)}
    return model, meta


def load_net3(ckpt_path: str, device: str) -> HandLandmarkNet:
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    state = ckpt.get("model", ckpt)
    cfg = ckpt.get("config", {}) or {}
    model_cfg = cfg.get("model", {}) if isinstance(cfg, dict) else {}
    model = HandLandmarkNet(
        num_keypoints=int(model_cfg.get("num_keypoints", 21)),
        heatmap_channels=int(model_cfg.get("heatmap_channels", 128)),
    ).to(device).eval()
    model.load_state_dict(state, strict=False)
    return model


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


def run_net2(model: PalmDetector, meta: dict, frame_bgr: np.ndarray,
             device: str, conf: float = 0.3, iou_thresh: float = 0.3,
             max_boxes: int = 2) -> list[tuple[float, tuple[float, float, float, float]]]:
    """Returns list of (score, (x1,y1,x2,y2)) in original-frame coords."""
    H, W = frame_bgr.shape[:2]
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    boxed, scale, dx, dy = letterbox(rgb, meta["input_size"])
    tensor = (boxed.astype(np.float32) / 255.0 - 0.5) / 0.5
    tensor = torch.from_numpy(tensor).permute(2, 0, 1).unsqueeze(0).to(device)
    with torch.no_grad():
        preds = model(tensor)
    cls = torch.sigmoid(preds["cls"][0]).squeeze(-1)
    deltas = preds["box"][0]
    keep = cls >= conf
    if not keep.any():
        return []
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
    kept_idx = nms(xyxy, scores, iou_threshold=iou_thresh, top_k=max_boxes)
    out: list[tuple[float, tuple[float, float, float, float]]] = []
    for ki in kept_idx.tolist():
        x1, y1, x2, y2 = xyxy[ki].tolist()
        x1 = (x1 - dx) / scale; y1 = (y1 - dy) / scale
        x2 = (x2 - dx) / scale; y2 = (y2 - dy) / scale
        out.append((float(scores[ki].item()), (x1, y1, x2, y2)))
    return out


def run_net3(model: HandLandmarkNet, frame_bgr: np.ndarray, bbox_xyxy: tuple,
             device: str, crop_size: int = 224) -> np.ndarray | None:
    """Net 3 takes a bbox crop and returns 21 hand keypoints in original coords."""
    H, W = frame_bgr.shape[:2]
    x1, y1, x2, y2 = bbox_xyxy
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    box = HandBBox(x=x1, y=y1, w=x2 - x1, h=y2 - y1, side="right")
    crop, M = crop_hand(rgb, box, out_size=crop_size, rotation_deg=0.0)
    tensor = torch.from_numpy(crop).permute(2, 0, 1).float() / 255.0
    tensor = ((tensor - 0.5) / 0.5).unsqueeze(0).to(device)
    with torch.no_grad():
        heatmaps = model(tensor)
    coords_hm = soft_argmax_2d(heatmaps)[0].cpu().numpy()
    hm_size = heatmaps.shape[-1]
    coords_crop = coords_hm * (crop_size / hm_size)
    # crop_hand returns M : image → crop. Invert for crop → image.
    img_coords = unproject_kpts(coords_crop.astype(np.float32), M)
    return img_coords.astype(np.float32)


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
        score, (x1, y1, x2, y2) = bboxes[0]
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
                     clip_path: Path, device: str, max_frames: int = 64
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
        for (score, xyxy), side in zip(bboxes, sides):
            hand_kpts = run_net3(net3, frame, xyxy, device)
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
    args = p.parse_args()

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[init] device={device}", flush=True)

    net1, net1_k, net1_kslice = load_net1(args.net1, device)
    net2, net2_meta = load_net2(args.net2, device)
    net3 = load_net3(args.net3, device)
    print(f"[init] net1 K={net1_k} slice={net1_kslice}", flush=True)
    print(f"[init] net2 input={net2_meta['input_size']} "
          f"anchors={net2_meta['anchors_xywh'].shape}", flush=True)
    print(f"[init] net3 loaded", flush=True)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    n_done = 0
    n_skip = 0
    n_fail = 0
    t0 = time.time()
    with open(args.manifest) as f:
        for line_no, line in enumerate(f, 1):
            if args.limit and line_no > args.limit:
                break
            e = json.loads(line)
            clip_path = Path(e["clip_path"])
            gloss = e["gloss"]
            split = e.get("split", "train")
            out_path = out_dir / f"{clip_path.stem}.npz"
            if args.skip_existing and out_path.exists():
                n_skip += 1
                continue
            if not clip_path.exists():
                print(f"[miss] {clip_path}", flush=True)
                n_fail += 1
                continue
            result = extract_one_clip(net1, net1_k, net1_kslice, net2,
                                      net2_meta, net3, clip_path, device,
                                      max_frames=args.max_frames)
            if result is None:
                n_fail += 1
                print(f"[fail] {clip_path}", flush=True)
                continue
            kpts, vis, W, H = result
            np.savez_compressed(out_path,
                                keypoints=kpts.astype(np.float32),
                                visibility=vis.astype(np.float32),
                                width=W, height=H,
                                gloss=gloss, split=split,
                                clip_id=clip_path.stem)
            n_done += 1
            if args.delete_after:
                try:
                    clip_path.unlink()
                except OSError:
                    pass
            if n_done % 50 == 0:
                rate = n_done / max(time.time() - t0, 1e-6)
                print(f"[prog] done={n_done} skip={n_skip} fail={n_fail} "
                      f"rate={rate:.1f}/s elapsed={time.time()-t0:.0f}s",
                      flush=True)
    rate = n_done / max(time.time() - t0, 1e-6)
    print(f"[done] {n_done} extracted, {n_skip} skipped, {n_fail} failed "
          f"({rate:.2f}/s)", flush=True)


if __name__ == "__main__":
    main()
