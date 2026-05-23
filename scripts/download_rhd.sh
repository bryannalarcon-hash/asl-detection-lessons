#!/usr/bin/env bash
# Download Rendered Hand Pose Dataset (RHD) for Net 3 training.
#
# RHD is a fully-synthetic 21-keypoint hand dataset from Freiburg
# (Zimmermann & Brox, ICCV 2017). 41,258 training + 2,728 evaluation
# frames at 320x320, labels come from the renderer (no MediaPipe).
#
# Source listing page:
#   https://lmb.informatik.uni-freiburg.de/data/RenderedHandPose/
#
# Layout produced (after this script):
#   data/RHD_published_v2/
#     training/
#       color/00000.png ... 00041257.png
#       mask/...  depth/...
#       anno_training.pickle
#     evaluation/
#       color/00000.png ... 00002727.png
#       mask/...  depth/...
#       anno_evaluation.pickle
#
# Run from project root:
#   bash scripts/download_rhd.sh
#
# Env vars:
#   DATA_DIR  - destination root (default: data)
#   RHD_URL   - override download URL if Freiburg rotates the link
set -euo pipefail

DATA_DIR="${DATA_DIR:-data}"
OUT_DIR="$DATA_DIR/RHD_published_v2"
ZIP_PATH="$DATA_DIR/RHD_published_v2.zip"
# Freiburg's host went down some time before May 2026 with no Wayback
# snapshot. Verified working mirror: a Google Drive copy preserved by
# strawberryfg/RHDHand on GitHub. Partial-GET probe confirms identical
# zip layout (RHD_published_v2/{training,evaluation}/...), 9.09 GB,
# 2018-06-12 last-modified.
GDRIVE_ID="1ahDGxYb6BmzQxRU_juv_QDFLbpHPMy29"
DEFAULT_URL="https://drive.usercontent.google.com/download?id=${GDRIVE_ID}&export=download&confirm=t"
RHD_URL="${RHD_URL:-$DEFAULT_URL}"

# Idempotency: skip if both splits already have images + annotation pickle.
if [ -f "$OUT_DIR/training/anno_training.pickle" ] \
   && [ -f "$OUT_DIR/evaluation/anno_evaluation.pickle" ] \
   && [ -n "$(find "$OUT_DIR/training/color" -maxdepth 1 -name '*.png' -print -quit 2>/dev/null)" ] \
   && [ -n "$(find "$OUT_DIR/evaluation/color" -maxdepth 1 -name '*.png' -print -quit 2>/dev/null)" ]; then
    echo "=== RHD: already present at $OUT_DIR, skipping ==="
    exit 0
fi

mkdir -p "$DATA_DIR"

echo "=== Rendered Hand Pose Dataset (Freiburg) ==="
echo "  destination: $OUT_DIR"
echo "  source URL : $RHD_URL"

# gdown handles Google Drive's confirm token for files >100MB. Falls
# back to curl on the pre-resolved usercontent URL.
if command -v gdown >/dev/null 2>&1; then
    gdown --fuzzy "https://drive.google.com/file/d/${GDRIVE_ID}/view" -O "$ZIP_PATH"
elif command -v curl >/dev/null 2>&1; then
    curl -L --fail --retry 3 --retry-delay 5 -o "$ZIP_PATH" "$RHD_URL"
elif command -v wget >/dev/null 2>&1; then
    wget -q -c -O "$ZIP_PATH" "$RHD_URL"
else
    echo "FATAL: none of gdown / curl / wget is installed" >&2
    exit 1
fi

if ! command -v unzip >/dev/null 2>&1; then
    echo "FATAL: unzip not installed (apt-get install unzip)" >&2
    exit 1
fi

echo "  unpacking..."
unzip -q -o "$ZIP_PATH" -d "$DATA_DIR"
rm -f "$ZIP_PATH"

# The archive may unpack to a slightly different top-level name depending on
# the Freiburg revision (e.g. `RHD_published_v2/` vs `RHD_v1-1/`). Discover
# the real root and rename it to the canonical `RHD_published_v2/`.
if [ ! -d "$OUT_DIR" ]; then
    FOUND=$(find "$DATA_DIR" -maxdepth 2 -type d -name 'training' -print -quit 2>/dev/null \
            | xargs -r dirname)
    if [ -n "$FOUND" ] && [ "$FOUND" != "$OUT_DIR" ]; then
        mv "$FOUND" "$OUT_DIR"
    fi
fi

# Verification: counts and pickle presence.
train_imgs=$(find "$OUT_DIR/training/color" -maxdepth 1 -name '*.png' 2>/dev/null | wc -l)
eval_imgs=$(find "$OUT_DIR/evaluation/color" -maxdepth 1 -name '*.png' 2>/dev/null | wc -l)
train_pkl="$OUT_DIR/training/anno_training.pickle"
eval_pkl="$OUT_DIR/evaluation/anno_evaluation.pickle"

if [ "$train_imgs" -lt 40000 ]; then
    echo "FATAL: RHD training images = $train_imgs (expected ~41258)" >&2
    exit 1
fi
if [ "$eval_imgs" -lt 2500 ]; then
    echo "FATAL: RHD evaluation images = $eval_imgs (expected ~2728)" >&2
    exit 1
fi
for p in "$train_pkl" "$eval_pkl"; do
    if [ ! -f "$p" ]; then
        echo "FATAL: missing annotation pickle: $p" >&2
        exit 1
    fi
done

echo "=== RHD ready: train_images=$train_imgs eval_images=$eval_imgs ==="
echo "  $train_pkl"
echo "  $eval_pkl"
