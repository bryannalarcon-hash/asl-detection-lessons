"""Split a single COCO-WholeBody train annotation file into train/val.

We do this because the official val annotations are awkward to obtain (Google
Drive only, no stable mirror), and a random hold-out from the train set
gives us a valid val signal for our pilot.

  python scripts/split_train_val.py \\
      --in data/coco/annotations/coco_wholebody_train_v1.0.json \\
      --train-out data/coco/annotations/coco_wholebody_train_v1.0.json \\
      --val-out data/coco/annotations/coco_wholebody_val_v1.0.json \\
      --val-frac 0.05 --seed 42
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", required=True)
    p.add_argument("--train-out", required=True)
    p.add_argument("--val-out", required=True)
    p.add_argument("--val-frac", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    print(f"[split] loading {args.inp}")
    with open(args.inp) as f:
        data = json.load(f)

    images = data["images"]
    rng = random.Random(args.seed)
    rng.shuffle(images)
    n_val = max(1, int(len(images) * args.val_frac))
    val_imgs = images[:n_val]
    train_imgs = images[n_val:]
    val_img_ids = {im["id"] for im in val_imgs}
    train_img_ids = {im["id"] for im in train_imgs}

    val_anns = [a for a in data["annotations"] if a["image_id"] in val_img_ids]
    train_anns = [a for a in data["annotations"] if a["image_id"] in train_img_ids]

    print(f"[split] train: {len(train_imgs)} images / {len(train_anns)} annotations")
    print(f"[split] val:   {len(val_imgs)} images / {len(val_anns)} annotations")

    common = {k: v for k, v in data.items() if k not in ("images", "annotations")}
    train_out = {**common, "images": train_imgs, "annotations": train_anns}
    val_out = {**common, "images": val_imgs, "annotations": val_anns}

    Path(args.train_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.val_out, "w") as f:
        json.dump(val_out, f)
    print(f"[split] wrote {args.val_out}")
    with open(args.train_out, "w") as f:
        json.dump(train_out, f)
    print(f"[split] wrote {args.train_out}")


if __name__ == "__main__":
    main()
