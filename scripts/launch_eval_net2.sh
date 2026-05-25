#!/usr/bin/env bash
# Launch the Net 2 AP comparison (new keypoint detector vs net2_v3_1) on a
# small pod. Ships code + both checkpoints, runs _remote_eval_net2.sh detached.
# Prints pod id + ssh; poll logs/eval_net2.log then destroy. NOT added to
# .round_env (it's a one-off, not cron-monitored training).
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
set -a; . ./.env.local; set +a
: "${RUNPOD_API:?}"
KEY="${NET_SSH_KEY:-$HOME/.ssh/vast_v3}"
IMAGE="${RUNPOD_IMAGE:-runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04}"
PROV="python3 scripts/runpod_provision.py"
DISK="${POD_DISK:-30}"

for f in results/v3/net2/best.pt results/v3/net2_v3_1/best.pt; do
    [ -s "$f" ] || { echo "[FATAL] missing $f"; exit 3; }
done
echo "[1/5] provisioning eval pod (disk=${DISK}GB)"
deploy() { $PROV deploy --name asl-evalnet2 --disk "$DISK" --image "$IMAGE" $1 2>/tmp/dep_eval.err; }
POD_ID=""
for try in 1 2 3; do POD_ID=$(deploy "" || true); [ -n "$POD_ID" ] && break; sleep 8; done
[ -n "$POD_ID" ] || POD_ID=$(deploy "--secure" || true)
[ -n "$POD_ID" ] || { echo "[FATAL] deploy failed: $(cat /tmp/dep_eval.err)"; exit 4; }
echo "  pod $POD_ID"
trap 'echo "[cleanup] destroying $POD_ID"; '"$PROV"' destroy "'"$POD_ID"'" || true' EXIT

echo "[2/5] waiting for SSH"
read -r HOST PORT < <(timeout 420 $PROV ssh "$POD_ID" || true)
[ -n "${PORT:-}" ] || { echo "[FATAL] no SSH"; exit 5; }
SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=30 -o ConnectTimeout=20 -p "$PORT" "root@$HOST")
SCP=(scp -i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -P "$PORT")
echo "  ssh root@$HOST:$PORT"

echo "[3/5] GPU sanity"
"${SSH[@]}" 'nvidia-smi -L && python -c "import torch; assert torch.cuda.is_available()"' || { echo "[FATAL] gpu"; exit 6; }

echo "[4/5] ship code + both net2 checkpoints"
"${SSH[@]}" 'mkdir -p /workspace/asl/logs /workspace/asl/results/v3/net2 /workspace/asl/results/v3/net2_v3_1'
TAR="/tmp/asl_eval_$$.tar.gz"
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.log' -czf "$TAR" -C "$REPO_ROOT" src configs scripts requirements.txt
"${SCP[@]}" "$TAR" "root@$HOST:/workspace/asl_code.tar.gz"; rm -f "$TAR"
"${SSH[@]}" 'tar -xzf /workspace/asl_code.tar.gz -C /workspace/asl && rm /workspace/asl_code.tar.gz'
"${SCP[@]}" "$REPO_ROOT/results/v3/net2/best.pt" "root@$HOST:/workspace/asl/results/v3/net2/best.pt"
"${SCP[@]}" "$REPO_ROOT/results/v3/net2_v3_1/best.pt" "root@$HOST:/workspace/asl/results/v3/net2_v3_1/best.pt"

echo "[5/5] launch eval (detached)"
timeout 60 "${SSH[@]}" "cd /workspace/asl && chmod +x scripts/_remote_eval_net2.sh && \
    setsid bash scripts/_remote_eval_net2.sh >logs/remote_eval.log 2>&1 </dev/null & disown; echo launched" \
    || echo "  (timeout; setsid persists)"
trap - EXIT
echo "EVAL_POD $POD_ID $HOST $PORT" > "$REPO_ROOT/.eval_pod"
echo "[done] eval launched on $POD_ID (ssh root@$HOST:$PORT). Poll: logs/eval_net2.log; destroy when .eval_done."