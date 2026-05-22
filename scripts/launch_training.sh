#!/usr/bin/env bash
# Orchestrates the Stage 1 launch sequence on a freshly rented GPU instance.
#   1. install deps
#   2. smoke test (no data needed; verifies the pipeline)
#   3. download datasets
#   4. data sanity check (renders keypoints onto sample images)
#   5. local smoke training run on 200 samples
#   6. full training run
#
# Each step is gated — exit non-zero if anything fails. The expensive step
# (full training) only fires if everything above it passed.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "================================================================"
echo "[1/6] Installing dependencies"
echo "================================================================"
pip install -r requirements.txt

echo ""
echo "================================================================"
echo "[2/6] Pipeline smoke test (synthetic data, ~30s)"
echo "================================================================"
python scripts/smoke_test.py

echo ""
echo "================================================================"
echo "[3/6] Downloading datasets (~3-5 min on a GPU host)"
echo "================================================================"
bash scripts/download_data.sh

echo ""
echo "================================================================"
echo "[4/6] Data sanity check (renders samples to /tmp/data_check)"
echo "================================================================"
python scripts/check_data.py --config configs/stage1_baseline.yaml

echo ""
echo "================================================================"
echo "[5/6] Smoke training run (~5 min on small subset)"
echo "================================================================"
python -m src.stage1.train --config configs/stage1_smoke.yaml --data-limit 200

echo ""
echo "================================================================"
echo "[6/6] Full training run (~3-5 hours)"
echo "================================================================"
echo "About to start full training. Press Ctrl-C in the next 10s to abort."
sleep 10
python -m src.stage1.train --config configs/stage1_baseline.yaml

echo ""
echo "Training complete. Checkpoint: checkpoints/stage1/best.pt"
echo "Run: python -m src.stage1.eval --config configs/stage1_baseline.yaml \\"
echo "       --checkpoint checkpoints/stage1/best.pt \\"
echo "       --render-dir /tmp/stage1_renders"
