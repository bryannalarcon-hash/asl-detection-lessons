"""Convert the Indiana University EgoHands dataset to YOLO-format labels.

Input layout (after unzipping the Wayback / IU egohands_data.zip):
  <in>/_LABELLED_SAMPLES/<VIDEO_ID>/
    frame_NNNN.jpg
    polygons.mat

Output layout (matches our existing EgoHandsDataset adapter):
  <out>/{train,valid,test}/
    images/<VIDEO_ID>__frame_NNNN.jpg   (symlinked from input)
    labels/<VIDEO_ID>__frame_NNNN.txt   (YOLO: "0 cx cy w h" per hand)

Split is by video id (70/15/15) to avoid frame-level leakage between splits.

Class id is always 0 (single class: "hand"). Polygons -> axis-aligned bbox
via min/max on vertex coords. Frames with no polygons get an empty .txt
(YOLO treats empty as no-objects-this-image).

Usage:
  python -m scripts.convert_egohands_to_yolo --in /path/to/unzipped --out data/egohands
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.io import loadmat


HAND_KEYS = ("myleft", "myright", "yourleft", "yourright")


def polygons_for_frame(mat_record) -> list[np.ndarray]:
    polys: list[np.ndarray] = []
    for key in HAND_KEYS:
        try:
            arr = mat_record[key][0, 0]
        except (KeyError, ValueError, IndexError):
            continue
        if arr is None or arr.size == 0:
            continue
        poly = np.asarray(arr, dtype=np.float64).reshape(-1, 2)
        if poly.shape[0] >= 3:
            polys.append(poly)
    return polys


def bbox_from_polygon(poly: np.ndarray, img_w: int, img_h: int) -> tuple[float, float, float, float] | None:
    x_min, y_min = poly.min(axis=0)
    x_max, y_max = poly.max(axis=0)
    x_min = max(0.0, x_min); y_min = max(0.0, y_min)
    x_max = min(float(img_w), x_max); y_max = min(float(img_h), y_max)
    w = x_max - x_min; h = y_max - y_min
    if w <= 1 or h <= 1:
        return None
    cx = (x_min + x_max) / 2.0 / img_w
    cy = (y_min + y_max) / 2.0 / img_h
    return cx, cy, w / img_w, h / img_h


def assign_split(video_ids: list[str], train_frac: float = 0.70, valid_frac: float = 0.15) -> dict[str, str]:
    rng = np.random.default_rng(seed=42)
    ids = sorted(video_ids)
    rng.shuffle(ids)
    n = len(ids)
    n_train = int(round(n * train_frac))
    n_valid = int(round(n * valid_frac))
    assignment = {}
    for i, v in enumerate(ids):
        if i < n_train:
            assignment[v] = "train"
        elif i < n_train + n_valid:
            assignment[v] = "valid"
        else:
            assignment[v] = "test"
    return assignment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_dir", required=True, type=Path,
                        help="path to unzipped egohands_data (containing _LABELLED_SAMPLES/)")
    parser.add_argument("--out", required=True, type=Path,
                        help="output root, will create {train,valid,test}/{images,labels}/")
    parser.add_argument("--symlink", action="store_true",
                        help="symlink images instead of copying (faster, smaller)")
    args = parser.parse_args()

    labelled = args.in_dir / "_LABELLED_SAMPLES"
    if not labelled.is_dir():
        return f"missing _LABELLED_SAMPLES under {args.in_dir}"

    video_dirs = sorted(p for p in labelled.iterdir() if p.is_dir())
    if not video_dirs:
        return f"no video directories under {labelled}"

    splits = assign_split([p.name for p in video_dirs])
    counts = {"train": 0, "valid": 0, "test": 0}
    boxes = {"train": 0, "valid": 0, "test": 0}

    for split in ("train", "valid", "test"):
        (args.out / split / "images").mkdir(parents=True, exist_ok=True)
        (args.out / split / "labels").mkdir(parents=True, exist_ok=True)

    for vdir in video_dirs:
        split = splits[vdir.name]
        mat_path = vdir / "polygons.mat"
        if not mat_path.exists():
            print(f"[skip] {vdir.name}: no polygons.mat", flush=True)
            continue

        polys_per_frame = loadmat(mat_path, squeeze_me=False)["polygons"][0]

        frame_paths = sorted(vdir.glob("frame_*.jpg"))
        for idx, frame_path in enumerate(frame_paths):
            try:
                with Image.open(frame_path) as im:
                    img_w, img_h = im.size
            except Exception as e:
                print(f"[warn] cannot read {frame_path}: {e}", flush=True)
                continue

            label_lines: list[str] = []
            if idx < len(polys_per_frame):
                for poly in polygons_for_frame(polys_per_frame[idx]):
                    bbox = bbox_from_polygon(poly, img_w, img_h)
                    if bbox is None:
                        continue
                    cx, cy, w, h = bbox
                    label_lines.append(f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

            stem = f"{vdir.name}__{frame_path.stem}"
            img_dst = args.out / split / "images" / f"{stem}.jpg"
            lbl_dst = args.out / split / "labels" / f"{stem}.txt"

            if not img_dst.exists():
                if args.symlink:
                    img_dst.symlink_to(frame_path.resolve())
                else:
                    shutil.copy2(frame_path, img_dst)
            lbl_dst.write_text("\n".join(label_lines))

            counts[split] += 1
            boxes[split] += len(label_lines)

    print("done:")
    for split in ("train", "valid", "test"):
        print(f"  {split}: {counts[split]} images, {boxes[split]} boxes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
