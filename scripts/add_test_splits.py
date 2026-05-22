"""Sub-split existing COCO + HaGRID train.json into train/val/test in-place.

We had train+val splits but no held-out test. Carves 5% out of the current
train pool into a new test.json, preserving the original stratification:
  - COCO: random by image_id (same seed as split_train_val.py)
  - HaGRID: by user_id sha256 bucket (same as hagrid_reorganize.py)

Val files are left untouched. Idempotent: if test.json already exists and is
non-empty, the script is a no-op.

Usage:
  python scripts/add_test_splits.py
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path


COCO_TRAIN = Path("data/coco/annotations/coco_wholebody_train_v1.0.json")
COCO_TEST  = Path("data/coco/annotations/coco_wholebody_test_v1.0.json")
HAGRID_TRAIN = Path("data/hagrid/annotations/train.json")
HAGRID_TEST  = Path("data/hagrid/annotations/test.json")

TEST_FRAC = 0.05
SEED = 42


def split_coco() -> None:
    if not COCO_TRAIN.exists():
        print(f"[coco] skip: {COCO_TRAIN} missing"); return
    if COCO_TEST.exists():
        try:
            d = json.load(COCO_TEST.open())
            if len(d.get("images", [])) > 0:
                print(f"[coco] skip: {COCO_TEST} already has {len(d['images']):,} imgs")
                return
        except Exception:
            pass

    print(f"[coco] loading {COCO_TRAIN}")
    data = json.load(COCO_TRAIN.open())
    images = data["images"]
    rng = random.Random(SEED)
    rng.shuffle(images)
    n_test = max(1, int(len(images) * TEST_FRAC))
    test_imgs = images[:n_test]
    train_imgs = images[n_test:]
    test_ids = {im["id"] for im in test_imgs}
    train_ids = {im["id"] for im in train_imgs}

    test_anns  = [a for a in data["annotations"] if a["image_id"] in test_ids]
    train_anns = [a for a in data["annotations"] if a["image_id"] in train_ids]

    common = {k: v for k, v in data.items() if k not in ("images", "annotations")}
    test_out  = {**common, "images": test_imgs,  "annotations": test_anns}
    train_out = {**common, "images": train_imgs, "annotations": train_anns}

    print(f"[coco] train: {len(train_imgs):,} imgs / {len(train_anns):,} anns")
    print(f"[coco] test:  {len(test_imgs):,} imgs / {len(test_anns):,} anns")
    with COCO_TEST.open("w") as f:
        json.dump(test_out, f)
    print(f"[coco] wrote {COCO_TEST}")
    with COCO_TRAIN.open("w") as f:
        json.dump(train_out, f)
    print(f"[coco] rewrote {COCO_TRAIN}")


def split_hagrid() -> None:
    if not HAGRID_TRAIN.exists():
        print(f"[hagrid] skip: {HAGRID_TRAIN} missing"); return
    if HAGRID_TEST.exists():
        try:
            d = json.load(HAGRID_TEST.open())
            if len(d) > 0:
                print(f"[hagrid] skip: {HAGRID_TEST} already has {len(d):,} entries")
                return
        except Exception:
            pass

    print(f"[hagrid] loading {HAGRID_TRAIN}")
    entries = json.load(HAGRID_TRAIN.open())
    user_ids = sorted({m.get("user_id", "") for m in entries.values()})
    # Stable hash bucketing: bucket = (sha256(SEED:uid) % 10000) / 100  →  0..99
    # First 5 buckets (0..4) → test; bucket 5..9 left to val (already split); rest train.
    # But val users were already chosen by previous run; to avoid overlap, we
    # use a separate seed for the train→test carve, and additionally guard
    # against any user already in val.json.
    val_users = set()
    val_path = HAGRID_TRAIN.parent / "val.json"
    if val_path.exists():
        vd = json.load(val_path.open())
        val_users = {m.get("user_id", "") for m in vd.values()}

    test_users = set()
    for uid in user_ids:
        if uid in val_users:
            continue
        h = int(hashlib.sha256(f"test:{SEED}:{uid}".encode()).hexdigest(), 16) % 10_000
        if h < int(TEST_FRAC * 10_000):
            test_users.add(uid)

    train_out: dict[str, dict] = {}
    test_out: dict[str, dict] = {}
    for uuid, meta in entries.items():
        uid = meta.get("user_id", "")
        if uid in test_users:
            test_out[uuid] = meta
        else:
            train_out[uuid] = meta

    print(f"[hagrid] train: {len(train_out):,} entries / {len(set(m['user_id'] for m in train_out.values() if 'user_id' in m)):,} users")
    print(f"[hagrid] test:  {len(test_out):,} entries / {len(test_users):,} users")
    with HAGRID_TEST.open("w") as f:
        json.dump(test_out, f)
    print(f"[hagrid] wrote {HAGRID_TEST}")
    with HAGRID_TRAIN.open("w") as f:
        json.dump(train_out, f)
    print(f"[hagrid] rewrote {HAGRID_TRAIN}")


if __name__ == "__main__":
    split_coco()
    split_hagrid()
