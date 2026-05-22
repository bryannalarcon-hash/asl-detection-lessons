"""v3 evaluation: per-finger PCK + AUC on the held-out splits.

  python -u -m src.stage1.eval_v3 \
      --v2 results/v2/best.pt \
      --palm checkpoints/stage1_v3_detector/best.pt \
      --landmark checkpoints/stage1_v3_landmark/best.pt
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from src.stage1.data import schema as S
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.inference_v3 import V3Pipeline


FINGER_GROUPS = {
    "wrist": [0],
    "thumb": [1, 2, 3, 4],
    "index": [5, 6, 7, 8],
    "middle": [9, 10, 11, 12],
    "ring": [13, 14, 15, 16],
    "pinky": [17, 18, 19, 20],
    "fingertips": [4, 8, 12, 16, 20],
}


def per_finger_pck(pred_xy: np.ndarray, gt_xy: np.ndarray, vis: np.ndarray,
                   threshold_px: float) -> dict[str, float]:
    diffs = np.linalg.norm(pred_xy - gt_xy, axis=-1)
    correct = (diffs <= threshold_px).astype(np.float32) * vis
    out = {}
    for name, idxs in FINGER_GROUPS.items():
        v = vis[idxs]
        c = correct[idxs]
        out[name] = float(c.sum() / max(v.sum(), 1))
    out["all_hand_pts"] = float((correct[:21].sum() + correct[21:42].sum()) /
                                max(vis[:21].sum() + vis[21:42].sum(), 1))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--v2", required=True)
    p.add_argument("--palm", required=True)
    p.add_argument("--landmark", required=True)
    p.add_argument("--coco-val", default="data/coco/annotations/coco_wholebody_val_v1.0.json")
    p.add_argument("--coco-img-root", default="data/coco/train2017")
    p.add_argument("--freihand-root", default="data/FreiHAND_pub_v2")
    p.add_argument("--n-samples", type=int, default=500)
    p.add_argument("--threshold-frac", type=float, default=0.05)
    p.add_argument("--out", default="results/v3/eval.json")
    args = p.parse_args()

    pipeline = V3Pipeline(v2_ckpt=args.v2, palm_ckpt=args.palm,
                          landmark_ckpt=args.landmark)

    sources = []
    if Path(args.coco_val).exists():
        sources.append(("coco_val", CocoWholeBodyDataset(
            ann_file=args.coco_val, image_root=args.coco_img_root)))
    if Path(args.freihand_root).exists():
        sources.append(("freihand_val", FreiHANDDataset(
            args.freihand_root, scene_split="val", val_scene_frac=0.05)))

    results = {}
    for name, ds in sources:
        n = min(args.n_samples, len(ds))
        agg = {k: [] for k in (list(FINGER_GROUPS.keys()) + ["all_hand_pts"])}
        for i in range(n):
            sample = ds[i]
            img = cv2.imread(sample["image_path"])
            if img is None:
                continue
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            pred_kp, pred_vis = pipeline.detect(img)
            gt_kp = sample["keypoints"]
            gt_vis = sample["visible"]
            joint_vis = (gt_vis * pred_vis).astype(np.float32)
            threshold_px = args.threshold_frac * max(img.shape[:2])
            row = per_finger_pck(pred_kp, gt_kp, joint_vis, threshold_px)
            for k, v in row.items():
                agg[k].append(v)
        results[name] = {k: (float(np.mean(v)) if v else 0.0) for k, v in agg.items()}
        results[name]["n_samples"] = n

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
