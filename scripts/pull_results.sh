#!/usr/bin/env bash
# Pull the trained Stage 1 artifacts back from the vast instance to local.
#   ./scripts/pull_results.sh [host_alias_or_ip] [port] [remote_path] [local_dst]
set -euo pipefail

HOST="${1:-ssh9.vast.ai}"
PORT="${2:-12446}"
REMOTE_BASE="${3:-/workspace/asl-learning}"
LOCAL_DST="${4:-./results}"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/vast_asl}"
mkdir -p "$LOCAL_DST"

echo "[pull] checkpoints..."
rsync -azP -e "ssh -i $SSH_KEY -p $PORT" \
  "root@$HOST:$REMOTE_BASE/checkpoints/" "$LOCAL_DST/checkpoints/" || true

echo "[pull] renders..."
rsync -azP -e "ssh -i $SSH_KEY -p $PORT" \
  "root@$HOST:/tmp/stage1_renders/" "$LOCAL_DST/renders/" || true
rsync -azP -e "ssh -i $SSH_KEY -p $PORT" \
  "root@$HOST:/tmp/data_check/" "$LOCAL_DST/data_check/" || true

echo ""
echo "[pull] done. Local results in $LOCAL_DST"
du -sh "$LOCAL_DST"/* 2>/dev/null || true
