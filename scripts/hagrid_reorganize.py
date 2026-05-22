"""Merge per-gesture HaGRID annotation JSONs into train/val/test splits.

Reads kapitanov/hagrid layout:
    raw_ann/ann_train_val/<gesture>.json    (each: {uuid: meta, ...})
    raw_ann/ann_test/<gesture>.json

For each entry:
  - Keeps `bboxes`, `labels`, `leading_hand`, `leading_conf`, `user_id`
  - DROPS `landmarks` (MediaPipe-pseudo-labeled, banned by Req 7)
  - DROPS entries whose image file does not exist on disk under
    images-root/<gesture>/<uuid>.jpg (since the 500k mirror is a subset
    of HaGRID's 552k images).

Splits the merged train_val pool into train/val by user_id (so the same
person never appears in both splits) at val-frac fraction.

Writes:
    out-root/train.json
    out-root/val.json
    out-root/test.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


KEEP_FIELDS = ("bboxes", "labels", "leading_hand", "leading_conf", "user_id")


def load_gesture_jsons(ann_dir: Path) -> dict:
    merged: dict[str, dict] = {}
    for jp in sorted(ann_dir.glob("*.json")):
        with jp.open() as f:
            d = json.load(f)
        merged.update(d)
    return merged


def filter_and_strip(entries: dict, images_root: Path) -> dict:
    out: dict[str, dict] = {}
    for uuid, meta in entries.items():
        labels = meta.get("labels", [])
        if not labels:
            continue
        # Use first label as the gesture folder name.
        gesture = labels[0]
        if not (images_root / gesture / f"{uuid}.jpg").exists():
            continue
        stripped = {k: meta[k] for k in KEEP_FIELDS if k in meta}
        out[uuid] = stripped
    return out


def split_by_user(entries: dict, val_frac: float, seed: int = 7) -> tuple[dict, dict]:
    """Split by user_id so a person never appears in both splits."""
    user_ids = sorted({m.get("user_id", "") for m in entries.values()})
    val_users = set()
    for uid in user_ids:
        # Deterministic hash-based bucketing.
        h = int(hashlib.sha256(f"{seed}:{uid}".encode()).hexdigest(), 16) % 10_000
        if h < int(val_frac * 10_000):
            val_users.add(uid)
    train: dict[str, dict] = {}
    val: dict[str, dict] = {}
    for uuid, meta in entries.items():
        (val if meta.get("user_id", "") in val_users else train)[uuid] = meta
    return train, val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ann-root", required=True, help="dir with ann_train_val/ and ann_test/")
    ap.add_argument("--images-root", required=True, help="dir with <gesture>/<uuid>.jpg")
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--val-frac", type=float, default=0.05)
    args = ap.parse_args()

    ann_root = Path(args.ann_root)
    images_root = Path(args.images_root)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"  merging train_val JSONs from {ann_root}/ann_train_val/ ...")
    train_val_raw = load_gesture_jsons(ann_root / "ann_train_val")
    print(f"    {len(train_val_raw):,} raw entries")

    print(f"  merging test JSONs from {ann_root}/ann_test/ ...")
    test_raw = load_gesture_jsons(ann_root / "ann_test")
    print(f"    {len(test_raw):,} raw entries")

    print(f"  filtering by image existence + stripping MediaPipe landmarks ...")
    train_val = filter_and_strip(train_val_raw, images_root)
    test = filter_and_strip(test_raw, images_root)
    print(f"    {len(train_val):,} train_val survived  ({len(train_val_raw) - len(train_val):,} dropped)")
    print(f"    {len(test):,} test survived  ({len(test_raw) - len(test):,} dropped)")

    train, val = split_by_user(train_val, args.val_frac)
    print(f"  split: train={len(train):,}  val={len(val):,}  (target val_frac={args.val_frac})")

    for name, d in (("train", train), ("val", val), ("test", test)):
        p = out_root / f"{name}.json"
        with p.open("w") as f:
            json.dump(d, f)
        print(f"    wrote {p}  ({len(d):,} entries)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
