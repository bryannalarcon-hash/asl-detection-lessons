#!/usr/bin/env bash
# Pull COCO-WholeBody and FreiHAND datasets directly to the current directory.
# Run this on the rented GPU instance, NOT from your laptop.

set -euo pipefail

DATA_DIR="${DATA_DIR:-data}"
mkdir -p "$DATA_DIR/coco/annotations" "$DATA_DIR"

# ---- COCO 2017 images ----
echo "[1/4] Downloading COCO train2017 images (~18 GB)..."
if [ ! -d "$DATA_DIR/coco/train2017" ]; then
    wget -c -O "$DATA_DIR/coco/train2017.zip" http://images.cocodataset.org/zips/train2017.zip
    unzip -q "$DATA_DIR/coco/train2017.zip" -d "$DATA_DIR/coco/"
    rm "$DATA_DIR/coco/train2017.zip"
fi

echo "[2/4] Downloading COCO val2017 images (~1 GB)..."
if [ ! -d "$DATA_DIR/coco/val2017" ]; then
    wget -c -O "$DATA_DIR/coco/val2017.zip" http://images.cocodataset.org/zips/val2017.zip
    unzip -q "$DATA_DIR/coco/val2017.zip" -d "$DATA_DIR/coco/"
    rm "$DATA_DIR/coco/val2017.zip"
fi

# ---- COCO-WholeBody annotations ----
echo "[3/4] Downloading COCO-WholeBody annotations..."
COCO_WB_URL="https://drive.google.com/uc?export=download&id=1thErEToRbmM9uLNi1JXXfOsaS5VK2FXf"
if [ ! -f "$DATA_DIR/coco/annotations/coco_wholebody_train_v1.0.json" ]; then
    echo "  NOTE: COCO-WholeBody annotations are hosted on Google Drive."
    echo "  Please download manually from https://github.com/jin-s13/COCO-WholeBody"
    echo "  and place coco_wholebody_train_v1.0.json + coco_wholebody_val_v1.0.json"
    echo "  in $DATA_DIR/coco/annotations/"
fi

# ---- FreiHAND ----
echo "[4/4] Downloading FreiHAND..."
if [ ! -d "$DATA_DIR/FreiHAND_pub_v2" ]; then
    wget -c -O "$DATA_DIR/FreiHAND_pub_v2.zip" \
        https://lmb.informatik.uni-freiburg.de/data/freihand/FreiHAND_pub_v2.zip
    unzip -q "$DATA_DIR/FreiHAND_pub_v2.zip" -d "$DATA_DIR/"
    rm "$DATA_DIR/FreiHAND_pub_v2.zip"
fi

echo ""
echo "Done. Disk usage:"
du -sh "$DATA_DIR"/*
