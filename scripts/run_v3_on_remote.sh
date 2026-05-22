#!/usr/bin/env bash
# Bootstrap + launch v3 inside a tmux session so it survives ssh drops.
# Runs on the rented instance only.
set -euo pipefail

cd /workspace/asl-learning

# Source env so KAGGLE_* + VAST_API + INTERHAND_ANN_GDRIVE_FOLDER are visible.
source /root/.bashrc 2>/dev/null || true
export KAGGLE_KEY KAGGLE_USERNAME VAST_API INTERHAND_ANN_GDRIVE_FOLDER

apt-get update -qq
apt-get install -y -qq unzip tmux

# Raise fd budget for PyTorch DataLoader's shm-backed tensor sharing.
# With num_workers=32 + persistent + prefetch=4 + variable-length JPEG bytes,
# the default 1024 fd ceiling is blown immediately.
ulimit -n 65536
echo "ulimit -n: $(ulimit -n)"

# Kick off the full pipeline in tmux. Output to logs/launch.log so we can tail.
mkdir -p logs
tmux kill-session -t v3 2>/dev/null || true
# setsid detaches tmux from the SSH controlling tty so it survives logout.
# Without it, vast's minimal pytorch container kills the tmux server when ssh exits.
setsid tmux new-session -d -s v3 -x 200 -y 50 \
    "bash scripts/launch_v3.sh 2>&1 | tee logs/launch.log; sleep 86400"

echo "tmux session 'v3' started. Attach with: tmux attach -t v3"
echo "Tail log: tail -F /workspace/asl-learning/logs/launch.log"
