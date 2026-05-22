"""Run trained Net 2 over the Net 3 training data → JSON of predicted bboxes.

Used by Phase 2 fine-tune so Net 3 sees crops from Net 2's actual prediction
distribution (not just GT bboxes).

  python -u scripts/predict_bboxes_for_phase2.py \
      --palm checkpoints/stage1_v3_detector/best.pt \
      --out data/cache/net2_predictions.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.interhand import InterHand26MDataset
from src.stage1.models.anchors import decode_box, get_anchors, nms
from src.stage1.models.palm_detector import PalmDetector


def _letterbox(img, size):
    h, w = img.shape[:2]
    scale = size / max(h, w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    out = np.zeros((size, size, 3), dtype=img.dtype)
    dy, dx = (size - nh) // 2, (size - nw) // 2
    out[dy:dy + nh, dx:dx + nw] = resized
    return out, scale, dx, dy


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--palm", required=True)
    p.add_argument("--freihand-root", default="data/FreiHAND_pub_v2")
    p.add_argument("--interhand-root", default="data/interhand")
    p.add_argument("--out", default="data/cache/net2_predictions.json")
    p.add_argument("--detector-input", type=int, default=192)
    p.add_argument("--score-threshold", type=float, default=0.5)
    p.add_argument("--max-samples", type=int, default=None)
    args = p.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    palm = PalmDetector().to(device)
    state = torch.load(args.palm, map_location=device, weights_only=False)
    palm.load_state_dict(state.get("model", state))
    palm.eval()
    anchors_xywh = torch.from_numpy(get_anchors(args.detector_input)).to(device)

    sources: list = [FreiHANDDataset(args.freihand_root)]
    if (Path(args.interhand_root) / "annotations" / "train").exists():
        sources.append(InterHand26MDataset(args.interhand_root, split="train"))

    out: dict[str, list[float]] = {}
    n_seen = 0
    for ds in sources:
        for i in tqdm(range(len(ds)), desc=f"{type(ds).__name__}"):
            if args.max_samples and n_seen >= args.max_samples:
                break
            n_seen += 1
            sample = ds[i]
            img = cv2.imread(sample["image_path"])
            if img is None:
                continue
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            det_inp, scale, dx, dy = _letterbox(img, args.detector_input)
            t = torch.from_numpy(det_inp).permute(2, 0, 1).float() / 255.0
            t = ((t - 0.5) / 0.5).unsqueeze(0).to(device)
            with torch.no_grad():
                pred = palm(t)
            scores = torch.sigmoid(pred["cls"][0])
            kept = scores > args.score_threshold
            if kept.sum() == 0:
                continue
            decoded = decode_box(pred["box"][0][kept], anchors_xywh[kept])
            # Take highest-scoring box.
            best = int(scores[kept].argmax().item())
            best_box = decoded[best].cpu().numpy()
            # Convert back to original image coords.
            cx = (best_box[0] - dx) / scale
            cy = (best_box[1] - dy) / scale
            w = best_box[2] / scale
            h = best_box[3] / scale
            out[str(sample.get("image_id", n_seen))] = [
                float(cx - w / 2), float(cy - h / 2), float(w), float(h),
            ]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(out, f)
    print(f"[done] wrote {len(out):,} predictions to {out_path}")


if __name__ == "__main__":
    main()
