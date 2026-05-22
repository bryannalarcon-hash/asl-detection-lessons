#!/usr/bin/env bash
# Runs on the NJ instance. Waits for data download, then runs:
#   1. v1 resume from v1_best.pt → checkpoints/stage1_resumed/
#   2. v2 preprocess cache
#   3. v2 fresh training from scratch with optimized pipeline
set -e
cd /workspace/asl-learning

# Wait for data ready signal.
until grep -q "ALL DATA READY" logs_setup.log 2>/dev/null; do
  sleep 10
done
echo "[orchestrate] data ready, starting v1 resume"

# 1. v1 resume
python -m src.stage1.train \
  --config configs/stage1_resume_v1.yaml \
  --resume checkpoints/stage1/v1_best.pt \
  > logs/resume_v1.log 2>&1 || echo "[orchestrate] v1 resume exited"
echo "[orchestrate] v1 resume done"

# 2. v2 preprocess
mkdir -p logs
python scripts/preprocess_cache.py \
  --config configs/stage1_v2.yaml --out data/cache/stage1 \
  > logs/preprocess.log 2>&1 || echo "[orchestrate] preprocess exited"
echo "[orchestrate] preprocess done"

# 3. v2 fresh training
python -m src.stage1.train_v2 \
  --config configs/stage1_v2.yaml \
  --cache-root data/cache/stage1 \
  > logs/train_v2.log 2>&1 || echo "[orchestrate] v2 training exited"
echo "[orchestrate] all done"
