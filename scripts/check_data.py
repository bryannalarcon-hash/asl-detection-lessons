"""Verify dataset loaders by rendering keypoints onto sample images.

Run after `scripts/download_data.sh` completes. Outputs annotated PNGs
under /tmp/data_check/. Inspect them visually to confirm the keypoint
mappings are correct (right vs left hand swapped is the classic bug).

  python scripts/check_data.py --config configs/stage1_baseline.yaml \
      [--out /tmp/data_check] [--n 6]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.common.config import load_config
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.visualize import draw_keypoints


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--out", default="/tmp/data_check")
    p.add_argument("--n", type=int, default=6)
    args = p.parse_args()
    cfg = load_config(args.config)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[check] loading COCO-WholeBody val from {cfg.data.coco_val_ann_file}")
    coco = CocoWholeBodyDataset(
        ann_file=cfg.data.coco_val_ann_file,
        image_root=f"{cfg.data.coco_root}/{cfg.data.coco_val_images}",
    )
    print(f"[check] coco val samples: {len(coco)}")
    for i in range(min(args.n, len(coco))):
        s = coco[i]
        draw_keypoints(
            s["image_path"], s["keypoints"], s["visible"],
            out / f"coco_{i:03d}.png",
        )

    from pathlib import Path as _P
    if (_P(cfg.data.freihand_root) / "training_K.json").exists():
        print(f"[check] loading FreiHAND from {cfg.data.freihand_root}")
        frei = FreiHANDDataset(cfg.data.freihand_root)
        print(f"[check] freihand samples: {len(frei)}")
        for i in range(min(args.n, len(frei))):
            s = frei[i]
            draw_keypoints(
                s["image_path"], s["keypoints"], s["visible"],
                out / f"freihand_{i:03d}.png",
            )
    else:
        print(f"[check] FreiHAND not at {cfg.data.freihand_root} — skipping")

    print(f"\n[check] wrote samples to {out}")
    print("       Open them and verify:")
    print("       - hand keypoints land on actual fingers/wrist")
    print("       - right-hand dots are red, left-hand are blue")
    print("       - face/body anchors are in plausible positions")


if __name__ == "__main__":
    main()
