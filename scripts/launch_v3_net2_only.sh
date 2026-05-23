#!/usr/bin/env bash
# Net-2-only training launch for the rented GPU. Skips Net 3 phases entirely
# (they account for ~85% of full launch_v3.sh wall-clock).
#
# Steps:
#   1. install deps (upgrade torch to cu128 on Blackwell)
#   2. download Net 2 datasets (COCO, FreiHAND, HaGRID — NO InterHand)
#   3. install DALI + numba
#   4. build npy cache (HaGRID + COCO at 192²)
#   5. ulimit + tmux + run train_v3_detector with --use-dali --use-numba-anchors
#      --resume-from best_epoch8_pre_dali.pt
set -euo pipefail

cd "$(dirname "$0")/.."

echo "================================================================"
echo "[1/5] install deps"
echo "================================================================"
apt-get install -y -qq unzip
pip install -q -r requirements.txt
# Blackwell GPUs need a newer torch; upgrade if compute_cap >= 12.x
if nvidia-smi --query-gpu=compute_cap --format=csv,noheader | grep -qE "1[12]\."; then
    pip install -q --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu128
fi
pip install -q nvidia-dali-cuda120 numba

echo ""
echo "================================================================"
echo "[2/5] download Net 2 datasets (NO InterHand)"
echo "================================================================"
# COCO-WholeBody + FreiHAND + HaGRID. InterHand is Net-3-only — skip it.
mkdir -p data
bash scripts/download_v3_data.sh --net2-only 2>&1 | tee logs/download.log

echo ""
echo "================================================================"
echo "[3/5] synthetic smoke test"
echo "================================================================"
python -u scripts/smoke_test_v3.py

echo ""
echo "================================================================"
echo "[4/5] build npy cache (HaGRID + COCO at 192²)"
echo "================================================================"
mkdir -p data/net2_cache
python -u scripts/build_net2_cache.py 2>&1 | tee logs/build_cache.log

echo ""
echo "================================================================"
echo "[5/5] train Net 2 — DALI + cache + precompute + numba"
echo "================================================================"
mkdir -p logs checkpoints/stage1_v3_detector
RESUME_ARG=""
if [ -f checkpoints/stage1_v3_detector/best_epoch8_pre_dali.pt ]; then
    RESUME_ARG="--resume-from checkpoints/stage1_v3_detector/best_epoch8_pre_dali.pt"
    echo "  resuming from epoch 8 checkpoint"
fi
ulimit -n 65536
python -u -m src.stage1.train_v3_detector --config configs/stage1_v3_detector.yaml \
    --use-dali --use-numba-anchors $RESUME_ARG \
    2>&1 | tee logs/train_v3_detector.log

echo ""
echo "================================================================"
echo "[DONE] Net 2 training complete"
echo "================================================================"
ls -la checkpoints/stage1_v3_detector/
