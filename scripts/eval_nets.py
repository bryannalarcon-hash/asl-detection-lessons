"""Held-out eval for Net 1 (face+body keypoints) and Net 2 (palm bbox).

Uses the COCO-WholeBody val split cache that lives at /tmp/eval_cache/coco_val/.

Outputs:
  Net 1: PCK@0.05 on the 7 face+body keypoints (per-kpt and combined)
  Net 2: palm AP @ IoU=0.5, computed against keypoint-derived GT palm boxes
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.stage1.data import schema as S
from src.stage1.data.palm_boxes import palm_bbox_for_each_hand
from src.stage1.models.anchors import decode_box, get_anchors, nms
from src.stage1.models.detector import KeypointDetector, soft_argmax_2d
from src.stage1.models.palm_detector import PalmDetector


# ----- Net 1 eval (face+body PCK) -----

def eval_net1_pck(net1_path: str, cache_root: Path, max_samples: int | None) -> dict:
    device = "cpu"
    ckpt = torch.load(net1_path, map_location=device, weights_only=False)
    state = ckpt["model"]
    K = int(state["final.weight"].shape[0])
    cfg = ckpt.get("config", {})
    kslice = cfg.get("data", {}).get("keypoint_slice")
    assert kslice and len(kslice) == 2, f"Expected kpt slice (K=7); got {kslice}"

    model = KeypointDetector(num_keypoints=K).to(device)
    model.load_state_dict(state)
    model.eval()

    meta = json.load((cache_root / "meta.json").open())
    img_size = int(meta["cache_size"])
    N_total = int(meta["n_samples"])
    img_dir = cache_root / "images"
    kp = np.load(cache_root / "keypoints.npy")    # (N, 49, 2) in img-256 coords
    vis = np.load(cache_root / "visible.npy")     # (N, 49)
    N = min(max_samples or N_total, N_total)
    print(f"[net1] evaluating on {N} samples (cache_size={img_size})", flush=True)

    def _load_img(i):
        return np.load(img_dir / f"{i:07d}.npy")

    s_start, s_end = kslice
    threshold_px = 0.05 * img_size

    per_kpt_correct = np.zeros(K, dtype=np.float64)
    per_kpt_total = np.zeros(K, dtype=np.float64)
    t0 = time.time()
    for i in range(N):
        img_u8 = _load_img(i)
        img = img_u8.astype(np.float32) / 255.0
        img = (img - 0.5) / 0.5
        ten = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).float()
        with torch.no_grad():
            heatmaps = model(ten)
            coords_hm = soft_argmax_2d(heatmaps)[0].numpy()
        # heatmap → image coords: heatmap is img_size/4 = 64
        hm_size = heatmaps.shape[-1]
        scale = img_size / hm_size
        pred_xy = coords_hm * scale                                # (K, 2)
        gt_xy = kp[i, s_start:s_end, :]                            # (K, 2)
        gt_vis = vis[i, s_start:s_end]
        for k in range(K):
            if gt_vis[k] == 0:
                continue
            d = np.linalg.norm(pred_xy[k] - gt_xy[k])
            per_kpt_total[k] += 1
            if d <= threshold_px:
                per_kpt_correct[k] += 1
        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            it_s = (i + 1) / elapsed
            print(f"  net1 {i+1}/{N}  ({it_s:.1f} it/s)", flush=True)

    pck_per_kp = np.where(per_kpt_total > 0,
                          per_kpt_correct / per_kpt_total.clip(min=1),
                          float("nan"))
    pck_overall = float(np.nanmean(pck_per_kp))
    # Face = local 0,1,2 (NOSE, CHIN, FOREHEAD).
    # Body = local 3,4,5,6 (CHEST, L_SHO, R_SHO, NECK).
    face_idx = [0, 1, 2]
    body_idx = [3, 4, 5, 6]
    return {
        "net1_pck_overall": pck_overall,
        "net1_pck_face": float(np.nanmean(pck_per_kp[face_idx])),
        "net1_pck_body": float(np.nanmean(pck_per_kp[body_idx])),
        "net1_pck_per_kp": pck_per_kp.tolist(),
        "net1_samples": int(N),
    }


# ----- Net 2 eval (palm AP @ IoU=0.5) -----

def _iou_xyxy(a: np.ndarray, b: np.ndarray) -> float:
    inter_x1 = max(a[0], b[0]); inter_y1 = max(a[1], b[1])
    inter_x2 = min(a[2], b[2]); inter_y2 = min(a[3], b[3])
    iw = max(0.0, inter_x2 - inter_x1); ih = max(0.0, inter_y2 - inter_y1)
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / max(union, 1e-9)


def eval_net2_ap(net2_path: str, cache_root: Path, max_samples: int | None,
                 iou_thresh: float = 0.5, score_thresh: float = 0.05,
                 input_size: int = 192, use_fpn: bool = False) -> dict:
    device = "cpu"
    ckpt = torch.load(net2_path, map_location=device, weights_only=False)
    state = ckpt.get("model", ckpt)
    # Pull model config off the checkpoint so eval mirrors training.
    ck_cfg = ckpt.get("config") or {}
    model_block = (ck_cfg.get("model") if isinstance(ck_cfg, dict)
                   else getattr(ck_cfg, "model", None)) or {}
    ck_n_anchors = (model_block.get("n_anchors_per_cell")
                    if isinstance(model_block, dict)
                    else getattr(model_block, "n_anchors_per_cell", None))
    ck_aps = (model_block.get("anchors_per_scale")
              if isinstance(model_block, dict)
              else getattr(model_block, "anchors_per_scale", None))
    pd_kwargs = dict(n_anchors_per_cell=int(ck_n_anchors) if ck_n_anchors else 3,
                     n_aux_kpts=0)
    if use_fpn:
        pd_kwargs["use_fpn"] = True
    if ck_aps:
        pd_kwargs["anchors_per_scale"] = tuple(int(x) for x in ck_aps)
    model = PalmDetector(**pd_kwargs).to(device)
    model.load_state_dict(state, strict=False)
    model.eval()

    meta = json.load((cache_root / "meta.json").open())
    img_size_cache = int(meta["cache_size"])  # 256
    net2_input = int(input_size)
    N_total = int(meta["n_samples"])
    img_dir = cache_root / "images"
    kp = np.load(cache_root / "keypoints.npy")
    vis = np.load(cache_root / "visible.npy")
    N = min(max_samples or N_total, N_total)
    print(f"[net2] evaluating on {N} samples (image_size {img_size_cache} → {net2_input})",
          flush=True)

    def _load_img(i):
        return np.load(img_dir / f"{i:07d}.npy")

    # Multi-stride (FPN) anchors when the trained config recorded them;
    # otherwise the legacy uniform-scale single-stride layout. The
    # checkpoint embeds the training config so eval matches train.
    ck_cfg = ckpt.get("config") or {}
    anchors_block = (ck_cfg.get("anchors") if isinstance(ck_cfg, dict)
                     else getattr(ck_cfg, "anchors", None)) or {}
    scales_per_stride = (anchors_block.get("scales_per_stride")
                         if isinstance(anchors_block, dict)
                         else getattr(anchors_block, "scales_per_stride", None))
    strides_cfg = (anchors_block.get("strides")
                   if isinstance(anchors_block, dict)
                   else getattr(anchors_block, "strides", None))
    if scales_per_stride and strides_cfg:
        anchors_xywh = torch.from_numpy(get_anchors(
            net2_input, scales_per_stride=scales_per_stride,
            strides=strides_cfg)).float()
    else:
        anchors_xywh = torch.from_numpy(get_anchors(net2_input)).float()

    # Collect (score, tp/fp flag) records across samples + total GT count.
    score_tp_fp: list[tuple[float, int]] = []
    n_gt_total = 0

    t0 = time.time()
    for i in range(N):
        # Resize 256² letterboxed image down to 192² (preserves letterbox).
        img256 = _load_img(i)
        img192 = cv2.resize(img256, (net2_input, net2_input), interpolation=cv2.INTER_AREA)
        ten = img192.astype(np.float32) / 255.0
        ten = (ten - 0.5) / 0.5
        ten = torch.from_numpy(ten).permute(2, 0, 1).unsqueeze(0).float()

        # Derive GT palm boxes from keypoints (which are in 256² coords).
        # Scale keypoints 256 → 192 before deriving palm boxes.
        sc = net2_input / img_size_cache
        kp_192 = kp[i] * sc  # (49, 2)
        gt_boxes = palm_bbox_for_each_hand(kp_192, vis[i], pad=0.5)  # list of HandBBox
        gt_xyxy = []
        for b in gt_boxes:
            x1 = b.x; y1 = b.y; x2 = b.x + b.w; y2 = b.y + b.h
            # Clip + drop degenerate
            x1 = max(0, x1); y1 = max(0, y1)
            x2 = min(net2_input, x2); y2 = min(net2_input, y2)
            if x2 - x1 > 1 and y2 - y1 > 1:
                gt_xyxy.append([x1, y1, x2, y2])
        n_gt_total += len(gt_xyxy)
        gt_xyxy_np = np.array(gt_xyxy, dtype=np.float32) if gt_xyxy else np.zeros((0, 4), dtype=np.float32)

        with torch.no_grad():
            preds = model(ten)
        cls = torch.sigmoid(preds["cls"][0]).squeeze(-1)  # (N_anchor,)
        deltas = preds["box"][0]                           # (N_anchor, 4)
        keep = cls >= score_thresh
        if not keep.any():
            continue
        scores = cls[keep]
        a = anchors_xywh[keep]
        d = deltas[keep]
        decoded = decode_box(d, a)
        # xywh → xyxy
        decoded_xyxy = torch.stack([
            decoded[:, 0] - decoded[:, 2] * 0.5,
            decoded[:, 1] - decoded[:, 3] * 0.5,
            decoded[:, 0] + decoded[:, 2] * 0.5,
            decoded[:, 1] + decoded[:, 3] * 0.5,
        ], dim=1)
        from src.stage1.models.anchors import nms as _nms
        kept_idx = _nms(decoded_xyxy, scores, iou_threshold=0.3, top_k=20)
        pred_xyxy = decoded_xyxy[kept_idx].numpy()
        pred_scores = scores[kept_idx].numpy()

        # Greedy match: sort by score desc, assign each to best-IoU unmatched GT.
        order = np.argsort(-pred_scores)
        gt_matched = [False] * len(gt_xyxy_np)
        for j in order:
            best_iou = 0.0; best_g = -1
            for g, gb in enumerate(gt_xyxy_np):
                if gt_matched[g]:
                    continue
                iou = _iou_xyxy(pred_xyxy[j], gb)
                if iou > best_iou:
                    best_iou = iou; best_g = g
            if best_iou >= iou_thresh and best_g >= 0:
                gt_matched[best_g] = True
                score_tp_fp.append((float(pred_scores[j]), 1))  # TP
            else:
                score_tp_fp.append((float(pred_scores[j]), 0))  # FP

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            it_s = (i + 1) / elapsed
            print(f"  net2 {i+1}/{N}  ({it_s:.1f} it/s)  preds={len(score_tp_fp)}  gts={n_gt_total}",
                  flush=True)

    if n_gt_total == 0:
        return {"net2_palm_AP_iou50": float("nan"), "net2_samples": N,
                "net2_n_gt": 0, "net2_n_preds": len(score_tp_fp)}

    # AP @ IoU=0.5 via integration of precision-recall curve.
    score_tp_fp.sort(key=lambda x: -x[0])
    tps = np.cumsum([x[1] for x in score_tp_fp]).astype(np.float64)
    fps = np.cumsum([1 - x[1] for x in score_tp_fp]).astype(np.float64)
    recall = tps / n_gt_total
    precision = tps / (tps + fps).clip(min=1)
    # 11-point interpolated AP (Pascal VOC style).
    ap11 = 0.0
    for t in np.linspace(0, 1, 11):
        mask = recall >= t
        if mask.any():
            ap11 += precision[mask].max()
    ap11 /= 11.0
    # Continuous AP (area under interpolated PR curve).
    p_interp = precision.copy()
    for i in range(len(p_interp) - 2, -1, -1):
        p_interp[i] = max(p_interp[i], p_interp[i + 1])
    r_steps = np.concatenate([[0.0], recall, [1.0]])
    p_steps = np.concatenate([[p_interp[0]], p_interp, [0.0]])
    ap_cont = float(np.sum((r_steps[1:] - r_steps[:-1]) * p_steps[1:]))

    return {
        "net2_palm_AP_iou50_11point": float(ap11),
        "net2_palm_AP_iou50_continuous": ap_cont,
        "net2_samples": int(N),
        "net2_n_gt": int(n_gt_total),
        "net2_n_preds": int(len(score_tp_fp)),
        "net2_max_recall": float(recall.max()) if len(recall) else 0.0,
    }


def _strtobool(v) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off", ""):
        return False
    raise argparse.ArgumentTypeError(f"expected boolean, got {v!r}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--net1", default="results/v3/net1/stage1_v2_facebody/best.pt")
    p.add_argument("--net2", default="results/v3/net2/best.pt")
    # Generic alias — `--checkpoint` overrides `--net2` when set. Lets the v3.1
    # launcher point at the new arch without juggling two flags.
    p.add_argument("--checkpoint", default=None,
                   help="Override Net 2 checkpoint path (alias for --net2).")
    p.add_argument("--cache-root", default="/tmp/eval_cache/coco_val")
    p.add_argument("--max-samples", type=int, default=None,
                   help="Cap samples (for fast smoke). Default: all.")
    p.add_argument("--input-size", type=int, default=192,
                   help="Net 2 input resolution. v3 ckpt: 192. v3.1 ckpt: 256.")
    p.add_argument("--use-fpn", type=_strtobool, default=False,
                   help="Instantiate PalmDetector with the v3.1 mini-FPN branch.")
    p.add_argument("--out", default="results/v3/eval_summary.json")
    args = p.parse_args()
    cache_root = Path(args.cache_root)
    net2_path = args.checkpoint or args.net2
    out = {}

    if Path(args.net1).exists():
        print(f"=== Net 1 eval ({args.net1}) ===", flush=True)
        out.update(eval_net1_pck(args.net1, cache_root, args.max_samples))
    else:
        print(f"[skip] Net 1 not found at {args.net1}")

    if Path(net2_path).exists():
        print(f"=== Net 2 eval ({net2_path}) ===", flush=True)
        out.update(eval_net2_ap(net2_path, cache_root, args.max_samples,
                                input_size=args.input_size,
                                use_fpn=args.use_fpn))
    else:
        print(f"[skip] Net 2 not found at {net2_path}")

    print()
    print("=== FINAL ===")
    for k, v in out.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        elif isinstance(v, list) and len(v) > 0 and isinstance(v[0], float):
            print(f"  {k}: [{', '.join(f'{x:.3f}' for x in v)}]")
        else:
            print(f"  {k}: {v}")
    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with out_p.open("w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved → {out_p}")


if __name__ == "__main__":
    main()
