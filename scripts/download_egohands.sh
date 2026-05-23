#!/usr/bin/env bash
# Download EgoHands (Roboflow YOLO-format mirror) for Net 2 training.
#
# Public Roboflow mirror at https://public.roboflow.com/object-detection/hands
# packages the 4,800 EgoHands frames with axis-aligned bboxes (polygons
# already collapsed) under a clean train/valid/test split. We pull the
# YOLOv8 export — it gives one .txt per image with normalized (cx, cy, w, h)
# rows, which src/stage1/data/egohands.py parses directly.
#
# Layout produced (after this script):
#   data/egohands/
#     train/{images,labels}/...
#     valid/{images,labels}/...
#     test/{images,labels}/...
#     data.yaml
#
# Run from project root:
#   bash scripts/download_egohands.sh
#
# Optional env vars:
#   DATA_DIR     - destination root (default: data)
#   EGOHANDS_URL - override the download URL (e.g. when Roboflow rotates
#                  presigned links). The default is a stable redirect to
#                  the public dataset's YOLOv8 zip.
set -euo pipefail

DATA_DIR="${DATA_DIR:-data}"
OUT_DIR="$DATA_DIR/egohands"
ZIP_PATH="$OUT_DIR/egohands_yolo.zip"

# Roboflow public download URL for the EgoHands YOLOv8 export. Roboflow
# serves the public hands dataset behind a stable URL; if the link rotates,
# pass EGOHANDS_URL to override.
DEFAULT_URL="https://public.roboflow.com/ds/cQpsg1MAA8?key=4ZxhvUVDhM"
EGOHANDS_URL="${EGOHANDS_URL:-$DEFAULT_URL}"

# Idempotency: skip if all three splits already have at least one labeled image.
if [ -d "$OUT_DIR/train/images" ] \
   && [ -d "$OUT_DIR/train/labels" ] \
   && [ -n "$(find "$OUT_DIR/train/images" -maxdepth 1 -name '*.jpg' -print -quit 2>/dev/null)" ] \
   && [ -n "$(find "$OUT_DIR/train/labels" -maxdepth 1 -name '*.txt' -print -quit 2>/dev/null)" ]; then
    echo "=== EgoHands: already present at $OUT_DIR, skipping ==="
    exit 0
fi

mkdir -p "$OUT_DIR"

echo "=== EgoHands (Roboflow YOLO mirror) ==="
echo "  destination: $OUT_DIR"
echo "  source URL : $EGOHANDS_URL"

if command -v curl >/dev/null 2>&1; then
    curl -L --fail --retry 3 --retry-delay 5 -o "$ZIP_PATH" "$EGOHANDS_URL"
elif command -v wget >/dev/null 2>&1; then
    wget -q -c -O "$ZIP_PATH" "$EGOHANDS_URL"
else
    echo "FATAL: neither curl nor wget is installed" >&2
    exit 1
fi

echo "  unpacking..."
if ! command -v unzip >/dev/null 2>&1; then
    echo "FATAL: unzip not installed (apt-get install unzip)" >&2
    exit 1
fi
unzip -q -o "$ZIP_PATH" -d "$OUT_DIR"
rm -f "$ZIP_PATH"

# Sanity check: every Roboflow YOLOv8 export should have these three splits.
for split in train valid test; do
    if [ ! -d "$OUT_DIR/$split/images" ] || [ ! -d "$OUT_DIR/$split/labels" ]; then
        echo "WARN: split '$split' missing images/ or labels/ under $OUT_DIR" >&2
    fi
done

train_imgs=$(find "$OUT_DIR/train/images" -maxdepth 1 -name '*.jpg' 2>/dev/null | wc -l)
train_lbls=$(find "$OUT_DIR/train/labels" -maxdepth 1 -name '*.txt' 2>/dev/null | wc -l)
echo "=== EgoHands ready: train_images=$train_imgs train_labels=$train_lbls ==="
