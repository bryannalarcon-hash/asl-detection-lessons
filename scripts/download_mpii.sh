#!/usr/bin/env bash
# Pull MPII Human Pose v1.0 images + a JSON-port annotation file.
# Run on the rented GPU instance, not your laptop.
#
# License: MPII Human Pose Dataset is released for research use under the
# terms posted at http://human-pose.mpi-inf.mpg.de/#download
#   "You may use this dataset for the purpose of non-commercial scientific
#    research." Andriluka et al., CVPR 2014. Manual crowd annotations; no
#    MediaPipe / pseudo-labels — safe for our Req 7 constraint.
#
# Layout produced (under $DATA_DIR/mpii/):
#   images/<image_filename>.jpg                     ~25K files, ~12 GB extracted
#   annotations/mpii_annotations.json                JSON port (16-joint layout)
#   annotations/mpii_human_pose_v1_u12_1.mat         original .mat (fallback)
#
# JSON port note: the official MPII archive ships annotations only as
# .mat. Reading .mat in Python pulls in scipy.io + heavy struct parsing
# that's brittle across MATLAB versions. We mirror a community JSON port
# that mirrors the same 16-joint layout. Two mirrors are tried in order;
# if both fail, the .mat file is left in place for an offline converter
# (`scipy.io.loadmat` on `RELEASE.annolist[i].annorect[j].annopoints`).
#
# Required tools: wget, tar, unzip, curl. Optional: gdown (for fallback).

set -euo pipefail

DATA_DIR="${DATA_DIR:-data}"
MPII_DIR="$DATA_DIR/mpii"
IMG_DIR="$MPII_DIR/images"
ANN_DIR="$MPII_DIR/annotations"

mkdir -p "$IMG_DIR" "$ANN_DIR"

# ----- Images (official mirror) -----
if [ -n "$(find "$IMG_DIR" -maxdepth 1 -name '*.jpg' -print -quit 2>/dev/null)" ]; then
    echo "=== MPII images: already present, skipping ==="
else
    echo "=== MPII Human Pose v1.0 images (~12 GB) ==="
    IMAGES_TGZ="$MPII_DIR/mpii_human_pose_v1.tar.gz"
    IMAGES_URL="https://datasets.d2.mpi-inf.mpg.de/andriluka14cvpr/mpii_human_pose_v1.tar.gz"
    wget -q --show-progress -c -O "$IMAGES_TGZ" "$IMAGES_URL"

    echo "  extracting images tarball..."
    # Archive's top-level dir is 'images/' so we extract one level above.
    tar -xzf "$IMAGES_TGZ" -C "$MPII_DIR"
    rm -f "$IMAGES_TGZ"

    IMG_COUNT=$(find "$IMG_DIR" -maxdepth 1 -name '*.jpg' | wc -l)
    echo "  extracted $IMG_COUNT MPII images"
    if [ "$IMG_COUNT" -lt 20000 ]; then
        echo "FATAL: MPII extraction yielded only $IMG_COUNT images (expected ~25K)"
        exit 1
    fi
fi

# ----- Original .mat annotations (official mirror, ~12 MB) -----
if [ -f "$ANN_DIR/mpii_human_pose_v1_u12_1.mat" ]; then
    echo "=== MPII .mat annotations: already present, skipping ==="
else
    echo "=== MPII original .mat annotations ==="
    MAT_ZIP="$MPII_DIR/mpii_human_pose_v1_u12_2.zip"
    MAT_URL="https://datasets.d2.mpi-inf.mpg.de/andriluka14cvpr/mpii_human_pose_v1_u12_2.zip"
    wget -q --show-progress -c -O "$MAT_ZIP" "$MAT_URL"
    unzip -q -o "$MAT_ZIP" -d "$ANN_DIR"
    # The zip wraps the .mat in an extra folder; flatten if needed.
    NESTED_MAT=$(find "$ANN_DIR" -mindepth 2 -name 'mpii_human_pose_v1_u12_*.mat' -print -quit || true)
    if [ -n "$NESTED_MAT" ]; then
        mv -f "$NESTED_MAT" "$ANN_DIR/mpii_human_pose_v1_u12_1.mat"
    fi
    rm -f "$MAT_ZIP"
fi

# ----- JSON port (community mirror) -----
# The widely-cited JSON port matches princeton-vl/pytorch_stacked_hourglass and
# microsoft/human-pose-estimation.pytorch (HRNet repo) — both ship the same
# flat list of person dicts with keys: image, joints, joints_vis, center,
# scale, isValidation. We mirror it from a stable GitHub raw URL with one
# fallback. If both fail, the .mat above is the offline-convert path.
JSON_OUT="$ANN_DIR/mpii_annotations.json"
if [ -f "$JSON_OUT" ] && [ "$(stat -c%s "$JSON_OUT")" -gt 1000000 ]; then
    echo "=== MPII JSON port: already present, skipping ==="
else
    echo "=== MPII JSON port annotations ==="
    JSON_URLS=(
        "https://raw.githubusercontent.com/princeton-vl/pose-hg-train/master/data/mpii/annot/train.json"
        "https://raw.githubusercontent.com/princeton-vl/pose-hg-train/master/data/mpii/annot/valid.json"
    )
    JSON_TRAIN="$ANN_DIR/_train.json"
    JSON_VAL="$ANN_DIR/_valid.json"
    set +e
    wget -q -O "$JSON_TRAIN" "${JSON_URLS[0]}"
    rc_train=$?
    wget -q -O "$JSON_VAL"   "${JSON_URLS[1]}"
    rc_val=$?
    set -e

    if [ $rc_train -eq 0 ] && [ $rc_val -eq 0 ] \
        && [ -s "$JSON_TRAIN" ] && [ -s "$JSON_VAL" ]; then
        echo "  merging train + valid JSON ports..."
        python3 - "$JSON_TRAIN" "$JSON_VAL" "$JSON_OUT" <<'PY'
import json, sys
train_path, val_path, out_path = sys.argv[1:4]
with open(train_path) as f:
    train = json.load(f)
with open(val_path) as f:
    val = json.load(f)
for e in train:
    e.setdefault("isValidation", 0)
for e in val:
    e["isValidation"] = 1
merged = list(train) + list(val)
with open(out_path, "w") as f:
    json.dump(merged, f)
print(f"merged: train={len(train)} val={len(val)} total={len(merged)}")
PY
        rm -f "$JSON_TRAIN" "$JSON_VAL"
    else
        echo "  primary JSON port unreachable (train=$rc_train, val=$rc_val);"
        echo "  trying fallback mirror..."
        FALLBACK="https://raw.githubusercontent.com/bearpaw/pytorch-pose/master/data/mpii/mpii_annotations.json"
        set +e
        wget -q -O "$JSON_OUT" "$FALLBACK"
        rc_fb=$?
        set -e
        if [ $rc_fb -ne 0 ] || [ ! -s "$JSON_OUT" ]; then
            rm -f "$JSON_OUT"
            echo "FATAL: could not fetch MPII JSON port from any mirror."
            echo "  Fix: convert $ANN_DIR/mpii_human_pose_v1_u12_1.mat to JSON via:"
            echo "    python -c \"from scipy.io import loadmat; ...\""
            echo "  Or paste a JSON file matching the schema documented in"
            echo "  src/stage1/data/mpii.py into $JSON_OUT"
            exit 1
        fi
        echo "  fallback mirror OK (single-file JSON)."
    fi

    ENTRY_COUNT=$(python3 -c "import json,sys; print(len(json.load(open('$JSON_OUT'))))")
    echo "  MPII JSON entries: $ENTRY_COUNT"
    if [ "$ENTRY_COUNT" -lt 10000 ]; then
        echo "FATAL: MPII JSON has only $ENTRY_COUNT entries (expected ~28K)"
        exit 1
    fi
fi

echo ""
echo "=== MPII READY ==="
du -sh "$MPII_DIR"/* 2>/dev/null
