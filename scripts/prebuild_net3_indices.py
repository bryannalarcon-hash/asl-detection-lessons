"""Pre-build validated index files for Net 3 datasets.

Each Net 3 dataset adapter currently walks raw annotations + validates
files on-the-fly during training. That makes process startup slow and
leaves missing-image errors to be discovered (and logged) per batch.

This script does the validation pass ONCE and writes compact JSONL
indices the adapters consume directly:
  data/FreiHAND_pub_v2/index_valid.jsonl
  data/RHD_published_v2/{training,evaluation}/index_valid.jsonl
  data/interhand/index_smart_{train,val,test}.jsonl

For InterHand, also applies a SMARTER filter than the original
single-hand-only logic. ASL signs frequently use both hands, so we
want as many two-hand training samples as possible without
contaminating per-hand keypoint loss:

  KEEP   hand_type in {right, left}               (single hand, always clean)
  KEEP   hand_type == interacting                 (both hands present)
         AND wrist3d_distance > 100mm             (3D centroids far apart -
                                                   no 2D overlap risk)
  DROP   hand_type == interacting AND close       (likely overlapping in
                                                   2D -> ambiguous GT)

Distance threshold 100mm comes from: clasped hands are ~50mm apart,
relaxed hands at side are ~200mm, so 100mm is the natural "definitely
separate" boundary. Per-hand bbox IoU would be stricter but requires
2D projection per camera; centroid distance approximates well.

Usage:
  python -m scripts.prebuild_net3_indices --data-root data
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable

import numpy as np


def _emit_jsonl(path: Path, entries: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
            count += 1
    return count


def _freihand_image_path(root: Path, idx: int, variant: int) -> Path:
    return root / "training" / "rgb" / f"{idx:08d}.jpg" if variant == 0 \
        else root / "training" / "rgb" / f"{idx + variant * 32560:08d}.jpg"


def build_freihand(root: Path) -> None:
    print(f"\n=== FreiHAND ({root}) ===")
    # FreiHAND ships its 32,560 base images in /training/rgb/00000000.jpg ...
    # with 4 augmented variants extending the index range up to 130,240.
    n_kept = 0
    n_missing = 0
    rgb_dir = root / "training" / "rgb"
    if not rgb_dir.is_dir():
        print(f"  WARN: {rgb_dir} missing; skipping")
        return

    def _gen():
        nonlocal n_kept, n_missing
        for idx in range(130_240):
            img_path = rgb_dir / f"{idx:08d}.jpg"
            if not img_path.is_file():
                n_missing += 1
                continue
            yield {
                "image_path": str(img_path.relative_to(root)),
                "frei_idx": idx,
            }
            n_kept += 1

    out_path = root / "index_valid.jsonl"
    count = _emit_jsonl(out_path, _gen())
    print(f"  wrote {out_path.name}: {count} entries (missing {n_missing})")


def build_rhd(root: Path) -> None:
    print(f"\n=== RHD ({root}) ===")
    import pickle
    for split in ("training", "evaluation"):
        anno_path = root / split / f"anno_{split}.pickle"
        if not anno_path.exists():
            print(f"  WARN: {anno_path} missing; skipping {split}")
            continue
        with anno_path.open("rb") as f:
            anno = pickle.load(f)
        color_dir = root / split / "color"

        n_kept = 0
        n_missing = 0

        def _gen(anno=anno, color_dir=color_dir):
            nonlocal n_kept, n_missing
            for idx, rec in anno.items():
                img_path = color_dir / f"{int(idx):05d}.png"
                if not img_path.is_file():
                    n_missing += 1
                    continue
                yield {
                    "image_path": str(img_path.relative_to(root)),
                    "rhd_idx": int(idx),
                }
                n_kept += 1

        out_path = root / split / "index_valid.jsonl"
        count = _emit_jsonl(out_path, _gen())
        print(f"  wrote {split}/{out_path.name}: {count} entries (missing {n_missing})")


def _hand_centroid_mm(world_coord: np.ndarray, side: str) -> np.ndarray | None:
    # world_coord shape (42, 3): right 0-20, left 21-41. Values in mm.
    if side == "right":
        sub = world_coord[:21]
    else:
        sub = world_coord[21:42]
    valid = np.isfinite(sub).all(axis=1)
    if valid.sum() < 6:
        return None
    return sub[valid].mean(axis=0)


def build_interhand(root: Path, distance_threshold_mm: float = 100.0) -> None:
    print(f"\n=== InterHand2.6M ({root}) ===")
    ann_root = root / "annotations"
    if not ann_root.is_dir():
        print(f"  WARN: {ann_root} missing; skipping")
        return
    # Detect where images actually live. FB's 5fps tar extracts to
    # InterHand2.6M_5fps_batch1/images/<split>/...  not the bare
    # images/<split>/... layout the adapter originally assumed.
    candidates = [
        root / "images",
        root / "InterHand2.6M_5fps_batch1" / "images",
        root / "InterHand2.6M_5fps" / "images",
    ]
    images_root = next((c for c in candidates if c.is_dir()), None)
    if images_root is None:
        print(f"  WARN: no images/ subdir under {root}; skipping")
        return
    print(f"  images_root: {images_root.relative_to(root)}")

    for split in ("train", "val", "test"):
        meta_path = ann_root / split / f"InterHand2.6M_{split}_data.json"
        joint3d_path = ann_root / split / f"InterHand2.6M_{split}_joint_3d.json"
        camera_path = ann_root / split / f"InterHand2.6M_{split}_camera.json"
        if not (meta_path.exists() and joint3d_path.exists() and camera_path.exists()):
            print(f"  WARN: {split} annotation files missing; skipping")
            continue

        print(f"  loading {split}...", flush=True)
        with meta_path.open() as f:
            meta = json.load(f)
        with joint3d_path.open() as f:
            joint3d = json.load(f)

        images_by_id = {im["id"]: im for im in meta["images"]}

        kept_single = 0
        kept_interacting = 0
        dropped_overlap = 0
        dropped_missing_3d = 0
        dropped_missing_image = 0

        # Group annotations by image_id so we can evaluate interacting pairs together.
        anns_by_img: dict[int, list[dict]] = {}
        for ann in meta["annotations"]:
            anns_by_img.setdefault(ann["image_id"], []).append(ann)

        def _gen():
            nonlocal kept_single, kept_interacting
            nonlocal dropped_overlap, dropped_missing_3d, dropped_missing_image
            for img_id, anns in anns_by_img.items():
                img = images_by_id.get(img_id)
                if not img:
                    continue
                capture_id = str(img["capture"])
                seq_name = img["seq_name"]
                cam_id = img["camera"]
                frame_idx = img["frame_idx"]

                joints = joint3d.get(capture_id, {}).get(str(frame_idx), {})
                if "world_coord" not in joints:
                    dropped_missing_3d += 1
                    continue
                world_coord = np.asarray(joints["world_coord"], dtype=np.float32)

                img_path = (images_root / split / f"Capture{capture_id}"
                            / seq_name / f"cam{cam_id}"
                            / f"image{frame_idx:05d}.jpg")
                if not img_path.is_file():
                    dropped_missing_image += 1
                    continue

                # Categorize each annotation entry
                hand_types_in_frame = {ann.get("hand_type", "interacting") for ann in anns}

                # Singles: keep with the explicit side
                for ann in anns:
                    ht = ann.get("hand_type", "interacting")
                    if ht in ("right", "left"):
                        kept_single += 1
                        yield {
                            "image_path": str(img_path.relative_to(root)),
                            "image_id": img_id,
                            "capture_id": capture_id,
                            "frame_idx": frame_idx,
                            "cam_id": cam_id,
                            "seq_name": seq_name,
                            "hand_type": ht,
                            "image_width": img["width"],
                            "image_height": img["height"],
                        }

                # Interacting: keep BOTH sides only if hands are far enough apart
                if "interacting" in hand_types_in_frame:
                    r_cent = _hand_centroid_mm(world_coord, "right")
                    l_cent = _hand_centroid_mm(world_coord, "left")
                    if r_cent is None or l_cent is None:
                        dropped_missing_3d += 1
                        continue
                    dist_mm = float(np.linalg.norm(r_cent - l_cent))
                    if dist_mm < distance_threshold_mm:
                        dropped_overlap += 1
                        continue
                    for side in ("right", "left"):
                        kept_interacting += 1
                        yield {
                            "image_path": str(img_path.relative_to(root)),
                            "image_id": img_id,
                            "capture_id": capture_id,
                            "frame_idx": frame_idx,
                            "cam_id": cam_id,
                            "seq_name": seq_name,
                            "hand_type": side,  # treat as that side
                            "from_interacting": True,
                            "hand_distance_mm": dist_mm,
                            "image_width": img["width"],
                            "image_height": img["height"],
                        }

        out_path = root / f"index_smart_{split}.jsonl"
        total = _emit_jsonl(out_path, _gen())
        print(f"  {split}: wrote {total} entries (single={kept_single} interacting_kept={kept_interacting} "
              f"interacting_dropped={dropped_overlap} missing_3d={dropped_missing_3d} "
              f"missing_image={dropped_missing_image})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data", type=Path)
    parser.add_argument("--skip-freihand", action="store_true")
    parser.add_argument("--skip-rhd", action="store_true")
    parser.add_argument("--skip-interhand", action="store_true")
    parser.add_argument("--interhand-distance-mm", type=float, default=100.0,
                        help="3D centroid distance threshold to keep interacting frames")
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    print(f"data root: {data_root}")

    if not args.skip_freihand:
        build_freihand(data_root / "FreiHAND_pub_v2")
    if not args.skip_rhd:
        build_rhd(data_root / "RHD_published_v2")
    if not args.skip_interhand:
        build_interhand(data_root / "interhand", args.interhand_distance_mm)

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
