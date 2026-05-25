#!/usr/bin/env bash
# Pull all v3 datasets to the rented instance.
# Runs on the GPU instance, not your laptop.
#
# Required env / files:
#   - KAGGLE_API env var set (so kaggle CLI can fetch FreiHAND + HaGRID mirrors)
#   - $HOME/.kaggle/kaggle.json present
#   - gdown installed via pip
#   - unzip installed via apt
set -euo pipefail

# --net2-only skips InterHand2.6M (Net-3-only, ~80GB).
# --net3-only fetches ONLY Net 3 sources (FreiHAND + InterHand + RHD) and
#   skips COCO/HaGRID/EgoHands/MPII/synthetic — so a Net-3 pod never aborts on
#   HaGRID's FATAL reorg checks for data it does not need.
NET2_ONLY=0
NET3_ONLY=0
case "${1:-}" in
    --net2-only) NET2_ONLY=1; echo "[download] --net2-only: skipping InterHand2.6M" ;;
    --net3-only) NET3_ONLY=1; echo "[download] --net3-only: FreiHAND + InterHand + RHD only" ;;
esac

DATA_DIR="${DATA_DIR:-data}"
mkdir -p "$DATA_DIR/coco/annotations" "$DATA_DIR/hagrid"

# ----- COCO -----
if [ "$NET3_ONLY" = "1" ]; then
    echo "=== COCO-WholeBody: skipped (--net3-only) ==="
elif [ -f "$DATA_DIR/coco/annotations/coco_wholebody_train_v1.0.json" ] \
   && [ -d "$DATA_DIR/coco/train2017" ] \
   && [ -n "$(find "$DATA_DIR/coco/train2017" -maxdepth 1 -name '*.jpg' -print -quit 2>/dev/null)" ]; then
    echo "=== COCO-WholeBody: already present, skipping ==="
else
    echo "=== COCO-WholeBody annotations (Google Drive) ==="
    ( cd "$DATA_DIR/coco/annotations" && gdown 1thErEToRbmM9uLNi1JXXfOsaS5VK2FXf \
        -O coco_wholebody_train_v1.0.json )
    python scripts/split_train_val.py \
        --in "$DATA_DIR/coco/annotations/coco_wholebody_train_v1.0.json" \
        --train-out "$DATA_DIR/coco/annotations/coco_wholebody_train_v1.0.json" \
        --val-out "$DATA_DIR/coco/annotations/coco_wholebody_val_v1.0.json"

    echo "=== COCO train2017 images (~18 GB) ==="
    ( cd "$DATA_DIR/coco" && wget -q -c http://images.cocodataset.org/zips/train2017.zip \
        && unzip -q -o train2017.zip && rm train2017.zip )
fi

# ----- FreiHAND -----
if [ -d "$DATA_DIR/FreiHAND_pub_v2/training/rgb" ] \
   && [ -n "$(find "$DATA_DIR/FreiHAND_pub_v2/training/rgb" -maxdepth 1 -name '*.jpg' -print -quit 2>/dev/null)" ]; then
    echo "=== FreiHAND: already present, skipping ==="
else
    echo "=== FreiHAND (Kaggle mirror) ==="
    kaggle datasets download danieldelro/freihand -p "$DATA_DIR/" --unzip
    mkdir -p "$DATA_DIR/FreiHAND_pub_v2"
    mv "$DATA_DIR/training" "$DATA_DIR/evaluation" "$DATA_DIR/training_"* "$DATA_DIR/evaluation_"* \
       "$DATA_DIR/FreiHAND_pub_v2/" 2>/dev/null || true
fi

# ----- HaGRID v1 (bbox-only; landmarks are MediaPipe-pseudo, NEVER touched by loader) -----
# Sber S3 mirrors are dead. Reassemble from Kaggle:
#   - bbox annotations: kapitanov/hagrid (~1.7 GB JSONs, human-annotated bboxes)
#   - 384p images:      innominate817/hagrid-sample-500k-384p (13.1 GB, ~500K of 552K)
if [ "$NET3_ONLY" = "1" ]; then
    echo "=== HaGRID: skipped (--net3-only) ==="
elif [ -f "$DATA_DIR/hagrid/annotations/train.json" ] \
   && [ -d "$DATA_DIR/hagrid/images/call" ] \
   && [ -n "$(find "$DATA_DIR/hagrid/images/call" -maxdepth 1 -name '*.jpg' -print -quit 2>/dev/null)" ]; then
    echo "=== HaGRID: already present, skipping ==="
else
    echo "=== HaGRID v1 (Kaggle: kapitanov annotations + innominate 500k images) ==="
    mkdir -p "$DATA_DIR/hagrid/raw_ann" "$DATA_DIR/hagrid/raw_500k"

    echo "  fetching bbox annotations (kapitanov/hagrid, ~1.7 GB)..."
    kaggle datasets download kapitanov/hagrid -p "$DATA_DIR/hagrid/raw_ann" --unzip --force

    echo "  fetching 384p images (innominate817/hagrid-sample-500k-384p, ~13 GB)..."
    kaggle datasets download innominate817/hagrid-sample-500k-384p \
        -p "$DATA_DIR/hagrid/raw_500k" --unzip --force

    # Kaggle preserves an outer dir matching the dataset slug, so the real
    # paths are nested. Discover them with `find` to stay robust.
    ANN_TV_DIR=$(find "$DATA_DIR/hagrid/raw_ann" -type d -name 'ann_train_val' -print -quit)
    ANN_TEST_DIR=$(find "$DATA_DIR/hagrid/raw_ann" -type d -name 'ann_test' -print -quit)
    IMG_TV_PARENT=$(find "$DATA_DIR/hagrid/raw_500k" -type d -name 'hagrid_500k' -print -quit)
    if [ -z "$ANN_TV_DIR" ] || [ -z "$IMG_TV_PARENT" ]; then
        echo "FATAL: HaGRID extraction layout unexpected"
        echo "  ann_train_val=$ANN_TV_DIR"
        echo "  ann_test=$ANN_TEST_DIR"
        echo "  hagrid_500k=$IMG_TV_PARENT"
        find "$DATA_DIR/hagrid" -maxdepth 4 -type d | head -20
        exit 1
    fi
    echo "  discovered ann_train_val=$ANN_TV_DIR"
    echo "  discovered ann_test=$ANN_TEST_DIR"
    echo "  discovered images parent=$IMG_TV_PARENT"

    echo "  reorganizing images into images/<gesture>/<uuid>.jpg ..."
    mkdir -p "$DATA_DIR/hagrid/images"
    n_moved=0
    for d in "$IMG_TV_PARENT"/train_val_*; do
        [ -d "$d" ] || continue
        gesture=$(basename "$d" | sed 's/^train_val_//')
        mkdir -p "$DATA_DIR/hagrid/images/$gesture"
        # Use find+mv since `mv glob` may hit arg-list-too-long.
        find "$d" -maxdepth 1 -name '*.jpg' -exec mv -t "$DATA_DIR/hagrid/images/$gesture/" {} +
        cnt=$(find "$DATA_DIR/hagrid/images/$gesture" -maxdepth 1 -name '*.jpg' | wc -l)
        n_moved=$((n_moved + cnt))
        echo "    $gesture: $cnt images"
    done
    echo "  total images moved: $n_moved"
    if [ "$n_moved" -lt 100000 ]; then
        echo "FATAL: only $n_moved HaGRID images moved (expected ~500K)"
        exit 1
    fi

    # Stage annotation dirs into the layout reorganize.py expects
    STAGE="$DATA_DIR/hagrid/raw_ann_staged"
    rm -rf "$STAGE"
    mkdir -p "$STAGE/ann_train_val" "$STAGE/ann_test"
    find "$ANN_TV_DIR" -maxdepth 1 -name '*.json' -exec cp -t "$STAGE/ann_train_val/" {} +
    if [ -n "$ANN_TEST_DIR" ]; then
        find "$ANN_TEST_DIR" -maxdepth 1 -name '*.json' -exec cp -t "$STAGE/ann_test/" {} +
    fi

    echo "  building merged train/val/test annotation JSONs (bboxes-only)..."
    python scripts/hagrid_reorganize.py \
        --ann-root "$STAGE" \
        --images-root "$DATA_DIR/hagrid/images" \
        --out-root "$DATA_DIR/hagrid/annotations" \
        --val-frac 0.05

    # Verify non-zero entries; abort if reorg silently dropped everything.
    TRAIN_COUNT=$(python3 -c "import json; print(len(json.load(open('$DATA_DIR/hagrid/annotations/train.json'))))")
    if [ "$TRAIN_COUNT" -lt 50000 ]; then
        echo "FATAL: HaGRID train.json has only $TRAIN_COUNT entries (expected ~450K)"
        exit 1
    fi
    echo "  HaGRID train entries: $TRAIN_COUNT"

    rm -rf "$DATA_DIR/hagrid/raw_ann" "$DATA_DIR/hagrid/raw_500k" "$STAGE"
    echo "  HaGRID ready:"
    du -sh "$DATA_DIR/hagrid"/* 2>/dev/null
fi

# ----- InterHand2.6M -----
if [ "${SKIP_INTERHAND:-0}" = "1" ]; then
    echo "=== InterHand2.6M: skipped (SKIP_INTERHAND=1; mix renormalizes to FreiHAND+RHD) ==="
elif [ "$NET2_ONLY" = "1" ]; then
    echo "=== InterHand2.6M: skipped (--net2-only) ==="
elif [ -d "$DATA_DIR/interhand/annotations/train" ] \
   && ls "$DATA_DIR/interhand/annotations/train"/*.json >/dev/null 2>&1; then
    echo "=== InterHand2.6M: already present, skipping ==="
else
    echo "=== InterHand2.6M 5fps (~50 GB split tar parts) ==="
    mkdir -p "$DATA_DIR/interhand"
    INTERHAND_BASE="https://fb-baas-f32eacb9-8abb-11eb-b2b8-4857dd089e15.s3.amazonaws.com/InterHand2.6M/InterHand2.6M.images.5.fps.v1.0"
    # Listing is served at /index.html, and parts are named .tar.partaa..partzz (not .tar.gz.*).
    # The assembled archive is a plain tar (NOT gzipped) — verify with the CHECKSUM file.
    ( cd "$DATA_DIR/interhand" \
        && curl -sSL "${INTERHAND_BASE}/index.html" \
             | grep -oE 'InterHand2\.6M\.images\.5\.fps\.v1\.0\.tar\.part[a-z]+' \
             | sort -u > chunks.txt \
        && echo "  chunks discovered: $(wc -l < chunks.txt)" \
        && xargs -n 1 -P 4 -I {} wget -q -c "${INTERHAND_BASE}/{}" < chunks.txt \
        && echo "  parts on disk: $(ls InterHand2.6M.images.5.fps.v1.0.tar.part* | wc -l)" \
        && (
            # Stream-and-delete: cat each part to the pipe, then rm it immediately,
            # so peak disk = ~85 GB extracted (instead of 84 GB parts + 85 GB
            # extracted = 169 GB which blows the 200 GB disk).
            for part in $(ls InterHand2.6M.images.5.fps.v1.0.tar.part* | sort); do
                cat "$part" || exit 1
                rm "$part" || exit 1
            done
        ) | tar -xf - \
        && rm -f chunks.txt )

    INTERHAND_ANN_GDRIVE_FOLDER="${INTERHAND_ANN_GDRIVE_FOLDER:-12RNG9slv9i_TsXSoZ6pQAq-Fa98eGLoy}"
    echo "=== InterHand2.6M annotations (Google Drive folder) ==="
    (
        cd "$DATA_DIR/interhand"
        mkdir -p annotations_raw
        gdown --folder "$INTERHAND_ANN_GDRIVE_FOLDER" -O annotations_raw
        find annotations_raw -type f \( -name '*.tar.gz' -o -name '*.tgz' \) \
            | while read -r tarball; do
                tar -xzf "$tarball" -C "$(dirname "$tarball")"
                rm "$tarball"
            done
        mkdir -p annotations/train annotations/val annotations/test
        find annotations_raw -type f -name 'InterHand2.6M_train_*.json' \
            -exec mv -f {} annotations/train/ \;
        find annotations_raw -type f -name 'InterHand2.6M_val_*.json' \
            -exec mv -f {} annotations/val/ \;
        find annotations_raw -type f -name 'InterHand2.6M_test_*.json' \
            -exec mv -f {} annotations/test/ \;
        rm -rf annotations_raw
    )
fi

# ----- Auxiliary Net 2 sources (EgoHands, MPII, RHD) -----
# Each helper script is responsible for its own idempotency (skip-if-present).
# We invoke them unconditionally and rely on `set -e` to surface real failures.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$NET3_ONLY" = "1" ]; then
    echo "=== EgoHands / MPII: skipped (--net3-only) ==="
else
    echo "=== EgoHands (S3 presigned if EGOHANDS_S3_PRESIGNED_TAR set, else Wayback mirror) ==="
    timeout 300 bash "$SCRIPT_DIR/download_egohands.sh" || \
        echo "[warn] EgoHands download failed or timed out; v3.1 mix sampler will renormalize without egohands. Continuing."

    echo "=== MPII Human Pose v1.0 ==="
    bash "$SCRIPT_DIR/download_mpii.sh" || \
        echo "[warn] MPII download failed; Net 1 v3.1 mix sampler will renormalize without it"
fi

# RHD is a Net 3 source only; skip on a Net-2-only pod.
if [ "$NET2_ONLY" = "1" ]; then
    echo "=== RHD: skipped (--net2-only) ==="
else
    echo "=== RHD (S3 presigned if RHD_S3_PRESIGNED_URL set, else source) ==="
    timeout 600 bash "$SCRIPT_DIR/download_rhd.sh" || \
        echo "[warn] RHD download failed or timed out; Net 3 mix sampler will renormalize without it"
fi

# ----- Synthetic composites -----
# Depends on FreiHAND + COCO being on disk; both blocks above either
# completed or `set -e` already aborted. Builder script is idempotent.
echo "=== Synthetic hand-in-scene composites ==="
if [ "$NET3_ONLY" = "1" ]; then
    echo "  skipped (--net3-only; needs COCO)"
elif [ -f "$DATA_DIR/synthetic_hands/anno.jsonl" ]; then
    echo "  synthetic_hands/anno.jsonl present, skipping"
else
    python "$SCRIPT_DIR/build_synthetic_composites.py" \
        --frei-root "$DATA_DIR/FreiHAND_pub_v2" \
        --coco-ann "$DATA_DIR/coco/annotations/coco_wholebody_train_v1.0.json" \
        --coco-img "$DATA_DIR/coco/train2017" \
        --out "$DATA_DIR/synthetic_hands"
fi

echo ""
echo "=== ALL DATA READY ==="
du -sh "$DATA_DIR"/* 2>/dev/null
df -h /workspace
