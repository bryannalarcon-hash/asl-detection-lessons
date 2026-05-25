"""Net 2 (palm detector) detection AP eval on COCO-WholeBody val.

Single-class (hand) AP@IoU0.5 + recall/precision at a confidence threshold,
so two checkpoints can be compared head-to-head. GT boxes are derived from the
COCO-WholeBody hand keypoints with palm_bbox_for_each_hand -- exactly the
target the detector was trained to predict.

  python3 scripts/eval_net2_ap.py --checkpoint results/v3/net2/best.pt \
      --coco-ann data/coco/annotations/coco_wholebody_val_v1.0.json \
      --coco-img data/coco/train2017 --limit 800 --conf 0.5

Reuses load_net2 (handles fpn / anchors / square / n_kpts from the embedded
config), so it works for both the new keypoint detector and net2_v3_1.
"""
from __future__ import annotations

import argparse

import cv2
import numpy as np
import torch

from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.palm_boxes import palm_bbox_for_each_hand
from src.stage1.models.anchors import decode_box, nms
from src.stage2.data.extract_keypoints import load_net2


def letterbox(rgb: np.ndarray, size: int):
    h, w = rgb.shape[:2]
    scale = size / max(h, w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    dy, dx = (size - nh) // 2, (size - nw) // 2
    canvas[dy:dy + nh, dx:dx + nw] = resized
    return canvas, scale, dx, dy


def iou_xyxy(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    # a: (N,4), b: (M,4) -> (N,M)
    area_a = (a[:, 2] - a[:, 0]).clip(0) * (a[:, 3] - a[:, 1]).clip(0)
    area_b = (b[:, 2] - b[:, 0]).clip(0) * (b[:, 3] - b[:, 1]).clip(0)
    lt = np.maximum(a[:, None, :2], b[None, :, :2])
    rb = np.minimum(a[:, None, 2:], b[None, :, 2:])
    wh = (rb - lt).clip(0)
    inter = wh[..., 0] * wh[..., 1]
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-9)


@torch.no_grad()
def detect(model, meta, rgb, device, conf, iou_nms):
    size = meta["input_size"]
    anchors = meta["anchors_xywh"]
    boxed, scale, dx, dy = letterbox(rgb, size)
    t = torch.from_numpy(boxed).permute(2, 0, 1).float().div(255.0)
    t = ((t - 0.5) / 0.5).unsqueeze(0).to(device)
    out = model(t)
    scores = torch.sigmoid(out["cls"][0])
    keep = scores > conf
    if keep.sum() == 0:
        return np.zeros((0, 4), np.float32), np.zeros((0,), np.float32)
    xywh = decode_box(out["box"][0][keep], anchors[keep])
    sc = scores[keep]
    x1 = xywh[:, 0] - xywh[:, 2] * 0.5
    y1 = xywh[:, 1] - xywh[:, 3] * 0.5
    x2 = xywh[:, 0] + xywh[:, 2] * 0.5
    y2 = xywh[:, 1] + xywh[:, 3] * 0.5
    xyxy = torch.stack([x1, y1, x2, y2], dim=1)
    ki = nms(xyxy, sc, iou_threshold=iou_nms, top_k=20)
    xyxy, sc = xyxy[ki].cpu().numpy(), sc[ki].cpu().numpy()
    # Undo letterbox -> original image coords.
    xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - dx) / scale
    xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - dy) / scale
    return xyxy, sc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--coco-ann", required=True)
    ap.add_argument("--coco-img", required=True)
    ap.add_argument("--limit", type=int, default=800)
    ap.add_argument("--conf", type=float, default=0.5, help="conf threshold for recall/precision")
    ap.add_argument("--iou-nms", type=float, default=0.3)
    ap.add_argument("--iou-match", type=float, default=0.5)
    ap.add_argument("--device", default=None)
    args = ap.parse_args()
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")

    model, meta = load_net2(args.checkpoint, device)
    model.eval()
    ds = CocoWholeBodyDataset(args.coco_ann, args.coco_img)
    n = min(args.limit, len(ds))
    print(f"[eval] {args.checkpoint} on {n} COCO-WholeBody val images "
          f"(input={meta['input_size']}, n_kpts={meta.get('n_kpts')})", flush=True)

    all_scores, all_tp = [], []
    n_gt = 0
    matched_ious = []
    # PR curve uses ALL predictions (low conf) for AP; recall/prec reported at args.conf.
    skipped = 0
    for i in range(n):
        s = ds[i]
        bgr = cv2.imread(s["image_path"])
        if bgr is None:
            skipped += 1
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        gt = palm_bbox_for_each_hand(s["keypoints"], s["visible"], pad=0.5)
        gt_xyxy = np.array([[b.x, b.y, b.x + b.w, b.y + b.h] for b in gt],
                           dtype=np.float32) if gt else np.zeros((0, 4), np.float32)
        n_gt += len(gt_xyxy)
        pred, sc = detect(model, meta, rgb, device, conf=0.05, iou_nms=args.iou_nms)
        if len(pred) == 0:
            continue
        order = np.argsort(-sc)
        pred, sc = pred[order], sc[order]
        taken = np.zeros(len(gt_xyxy), dtype=bool)
        ious = iou_xyxy(pred, gt_xyxy) if len(gt_xyxy) else np.zeros((len(pred), 0))
        for j in range(len(pred)):
            tp = 0
            if ious.shape[1] > 0:
                k = int(np.argmax(ious[j]))
                if ious[j, k] >= args.iou_match and not taken[k]:
                    taken[k] = True; tp = 1; matched_ious.append(float(ious[j, k]))
            all_scores.append(float(sc[j])); all_tp.append(tp)
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{n} images, gt so far={n_gt}", flush=True)

    all_scores = np.array(all_scores); all_tp = np.array(all_tp)
    order = np.argsort(-all_scores)
    tp_c = np.cumsum(all_tp[order]); fp_c = np.cumsum(1 - all_tp[order])
    rec = tp_c / max(n_gt, 1)
    prec = tp_c / np.maximum(tp_c + fp_c, 1)
    # AP = 101-point interpolated (VOC2010-style integral).
    ap_val = 0.0
    for r in np.linspace(0, 1, 101):
        p = prec[rec >= r].max() if np.any(rec >= r) else 0.0
        ap_val += p / 101
    # recall/precision at args.conf
    at = all_scores[order] >= args.conf
    tp_at = int(all_tp[order][at].sum()); n_at = int(at.sum())
    rec_at = tp_at / max(n_gt, 1)
    prec_at = tp_at / max(n_at, 1)
    print("=" * 60)
    print(f"RESULT {args.checkpoint}")
    print(f"  images={n - skipped} (skipped {skipped} missing)  GT_hands={n_gt}  preds(>=0.05)={len(all_scores)}")
    print(f"  AP@{args.iou_match:.2f} = {ap_val:.4f}")
    print(f"  @conf>={args.conf}:  recall={rec_at:.4f}  precision={prec_at:.4f}")
    print(f"  mean matched IoU = {np.mean(matched_ious) if matched_ious else 0:.4f}")
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
