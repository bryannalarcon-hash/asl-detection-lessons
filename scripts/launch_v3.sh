#!/usr/bin/env bash
# Full v3 training orchestrator.
# Runs on the rented GPU instance.
#
#   1. install deps
#   2. download all datasets
#   3. smoke test (synthetic, ~30s — verifies torch + kornia work)
#   4. train Net 2 (palm detector)
#   5. generate Net 2 predictions over Net 3 training set
#   6. train Net 3 Phase 1 (GT bboxes + jitter)
#   7. train Net 3 Phase 2 (Net 2 predictions mixed in, fine-tune from Phase 1 best)
#   8. eval end-to-end pipeline
set -euo pipefail

cd "$(dirname "$0")/.."

echo "================================================================"
echo "[1/8] install deps"
echo "================================================================"
apt-get install -y -qq unzip
pip install -q -r requirements.txt
# Blackwell GPUs need a newer torch; install if 5090/B200 detected.
if nvidia-smi --query-gpu=compute_cap --format=csv,noheader | grep -qE "1[12]\."; then
    pip install -q --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu128
fi

echo ""
echo "================================================================"
echo "[2/8] download datasets"
echo "================================================================"
bash scripts/download_v3_data.sh

echo ""
echo "================================================================"
echo "[3/8] synthetic smoke test"
echo "================================================================"
python -u scripts/smoke_test_v3.py

echo ""
echo "================================================================"
echo "[3b/8] build Net 2 image cache (one-time, parallel)"
echo "================================================================"
# Cap workers to match vast's effective CPU allocation (host nproc lies).
python -u scripts/build_net2_cache.py --cache-root data/net2_cache --input-size 192 --sources hagrid,coco --workers 32

echo ""
echo "================================================================"
echo "[4/8] train Net 2 (palm detector)"
echo "================================================================"
mkdir -p logs
python -u -m src.stage1.train_v3_detector --config configs/stage1_v3_detector.yaml \
    2>&1 | tee logs/train_v3_detector.log

echo ""
echo "================================================================"
echo "[5/8] generate Net 2 bboxes for Phase 2"
echo "================================================================"
python -u scripts/predict_bboxes_for_phase2.py \
    --palm checkpoints/stage1_v3_detector/best.pt \
    --out data/cache/net2_predictions.json

echo ""
echo "================================================================"
echo "[6/8] train Net 3 Phase 1 (~5 hr)"
echo "================================================================"
python -u -m src.stage1.train_v3_landmark \
    --config configs/stage1_v3_landmark_phase1.yaml \
    2>&1 | tee logs/train_v3_landmark_phase1.log

echo ""
echo "================================================================"
echo "[7/8] train Net 3 Phase 2 fine-tune (~1 hr)"
echo "================================================================"
python -u -m src.stage1.train_v3_landmark \
    --config configs/stage1_v3_landmark_phase2.yaml \
    2>&1 | tee logs/train_v3_landmark_phase2.log

echo ""
echo "================================================================"
echo "[8/8] end-to-end eval"
echo "================================================================"
python -u -m src.stage1.eval_v3 \
    --v2 results/v2/best.pt \
    --palm checkpoints/stage1_v3_detector/best.pt \
    --landmark checkpoints/stage1_v3_landmark/best.pt \
    --out results/v3/eval.json

echo ""
echo "All done. Pull artifacts:"
echo "  results/v3/eval.json"
echo "  checkpoints/stage1_v3_detector/best.pt"
echo "  checkpoints/stage1_v3_landmark/best.pt"
