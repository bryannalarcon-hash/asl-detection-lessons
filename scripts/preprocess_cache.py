"""Precompute decoded + base-resized images as .npy files (one-time prep).

Trains v2 data pipeline reads from this cache instead of decoding JPEGs every
step. The transform applied here is deterministic: decode → letterbox-resize
to a fixed size. Random augmentation stays at training time.

  python scripts/preprocess_cache.py \
      --config configs/stage1_v2.yaml \
      --out data/cache/stage1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.common.config import load_config
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.freihand import FreiHANDDataset


def letterbox(img: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    """Resize keeping aspect, pad to (size, size) with zeros.

    Returns (padded_img, scale, dx, dy) so the same transform can be applied
    to keypoints later: kp_new = kp_old * scale + (dx, dy).
    """
    h, w = img.shape[:2]
    scale = size / max(h, w)
    new_h, new_w = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    out = np.zeros((size, size, 3), dtype=np.uint8)
    dy = (size - new_h) // 2
    dx = (size - new_w) // 2
    out[dy:dy + new_h, dx:dx + new_w] = resized
    return out, scale, dx, dy


def cache_one(image_path: str, keypoints: np.ndarray, visible: np.ndarray,
              cache_size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    img = cv2.imread(image_path)
    if img is None:
        raise RuntimeError(f"cv2.imread failed for {image_path}")
    # cv2 loads BGR; convert to RGB.
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    out, scale, dx, dy = letterbox(img, cache_size)
    kp_new = keypoints.copy()
    kp_new[:, 0] = kp_new[:, 0] * scale + dx
    kp_new[:, 1] = kp_new[:, 1] * scale + dy
    return out, kp_new.astype(np.float32), visible.astype(np.int8)


def cache_dataset(dataset, out_dir: Path, name: str, cache_size: int) -> None:
    out_img_dir = out_dir / name / "images"
    out_img_dir.mkdir(parents=True, exist_ok=True)
    kp_arr = np.zeros((len(dataset), 49, 2), dtype=np.float32)
    vis_arr = np.zeros((len(dataset), 49), dtype=np.int8)
    failures: list[int] = []

    for i in tqdm(range(len(dataset)), desc=f"caching {name}"):
        sample = dataset[i]
        try:
            img, kp, vis = cache_one(
                sample["image_path"], sample["keypoints"], sample["visible"],
                cache_size,
            )
        except Exception as e:
            failures.append(i)
            continue
        np.save(out_img_dir / f"{i:07d}.npy", img)
        kp_arr[i] = kp
        vis_arr[i] = vis

    np.save(out_dir / name / "keypoints.npy", kp_arr)
    np.save(out_dir / name / "visible.npy", vis_arr)
    with (out_dir / name / "meta.json").open("w") as f:
        json.dump({
            "name": name, "n_samples": len(dataset),
            "cache_size": cache_size, "n_failures": len(failures),
            "failure_indices": failures[:100],
        }, f, indent=2)
    print(f"[{name}] wrote {len(dataset) - len(failures)} samples "
          f"({len(failures)} failures)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--out", default="data/cache/stage1")
    p.add_argument("--cache-size", type=int, default=320)
    args = p.parse_args()

    cfg = load_config(args.config)
    out_dir = Path(args.out)

    print(f"[cache] writing to {out_dir} at {args.cache_size}px")

    # COCO train
    coco_train = CocoWholeBodyDataset(
        ann_file=cfg.data.coco_ann_file,
        image_root=f"{cfg.data.coco_root}/{cfg.data.coco_train_images}",
    )
    cache_dataset(coco_train, out_dir, "coco_train", args.cache_size)

    coco_val = CocoWholeBodyDataset(
        ann_file=cfg.data.coco_val_ann_file,
        image_root=f"{cfg.data.coco_root}/{cfg.data.coco_val_images}",
    )
    cache_dataset(coco_val, out_dir, "coco_val", args.cache_size)

    # FreiHAND train + val (scene-level split)
    if (Path(cfg.data.freihand_root) / "training_K.json").exists():
        frei_train = FreiHANDDataset(
            cfg.data.freihand_root, scene_split="train", val_scene_frac=0.05,
        )
        cache_dataset(frei_train, out_dir, "freihand_train", args.cache_size)
        frei_val = FreiHANDDataset(
            cfg.data.freihand_root, scene_split="val", val_scene_frac=0.05,
        )
        cache_dataset(frei_val, out_dir, "freihand_val", args.cache_size)
    else:
        print(f"[cache] FreiHAND not at {cfg.data.freihand_root} — skipping")


if __name__ == "__main__":
    main()
