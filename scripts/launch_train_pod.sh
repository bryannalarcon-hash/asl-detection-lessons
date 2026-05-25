#!/usr/bin/env bash
# Launch one training phase on a rented RunPod 5090.
#
#   scripts/launch_train_pod.sh <net2|net3>
#
# Provisions a pod (community first, secure fallback), validates SSH + GPU +
# torch, ships the code, writes secrets to the pod's .remote_env, kicks off
# scripts/_remote_train.sh <role> in a detached tmux, records the pod to
# .round_env, then EXITS leaving the pod running. The cron health check
# (scripts/round_health.sh) mirrors artifacts + detects completion; teardown
# is driven by the cron / operator (python3 scripts/runpod_provision.py
# destroy <id>). The pod is destroyed automatically ONLY if provisioning /
# SSH / GPU validation fails before training starts.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
ROLE="${1:?usage: launch_train_pod.sh <net2|net3>}"

[ -f .env.local ] || { echo "[FATAL] .env.local missing"; exit 2; }
set -a; . ./.env.local; set +a
: "${RUNPOD_API:?RUNPOD_API not set}"
: "${KAGGLE_API:?KAGGLE_API not set}"

KEY="${NET_SSH_KEY:-$HOME/.ssh/vast_v3}"
# runpod/pytorch images run sshd + inject PUBLIC_KEY on boot (the plain
# pytorch/pytorch image does not, so SSH never comes up). This 2.8.0/cu128
# tag is native Blackwell (sm_120) — validated torch kernels run on the 5090.
IMAGE="${RUNPOD_IMAGE:-runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04}"
PROV="python3 scripts/runpod_provision.py"

case "$ROLE" in
  net2) DISK="${POD_DISK:-80}";  CKPT="checkpoints/stage1_v3_detector_kpt/stage_b" ;;
  net3) DISK="${POD_DISK:-130}"; CKPT="checkpoints/stage1_v3_landmark_reg" ;;
  *) echo "[FATAL] role must be net2 or net3"; exit 2 ;;
esac

deploy() {  # $1 = "" (community) or "--secure"
    $PROV deploy --name "asl-$ROLE" --disk "$DISK" --image "$IMAGE" $1 2>/tmp/dep_$ROLE.err
}
echo "[1/6] provisioning $ROLE pod (disk=${DISK}GB)"
POD_ID=""
for try in 1 2 3; do
    POD_ID=$(deploy "" || true); [ -n "$POD_ID" ] && { echo "  community pod $POD_ID"; break; }
    echo "  community attempt $try: $(tr -d '\n' </tmp/dep_$ROLE.err | tail -c 160)"; sleep 8
done
if [ -z "$POD_ID" ]; then
    echo "  community unavailable; trying secure cloud (~\$0.99/hr)"
    POD_ID=$(deploy "--secure" || true)
    [ -n "$POD_ID" ] && echo "  secure pod $POD_ID"
fi
[ -n "$POD_ID" ] || { echo "[FATAL] deploy failed: $(cat /tmp/dep_$ROLE.err)"; exit 4; }

# Destroy on ANY failure until training is launched.
trap 'echo "[cleanup] destroying $POD_ID"; '"$PROV"' destroy "'"$POD_ID"'" || true' EXIT

echo "[2/6] waiting for SSH endpoint"
read -r HOST PORT < <(timeout 420 $PROV ssh "$POD_ID" || true)
[ -n "${PORT:-}" ] || { echo "[FATAL] SSH endpoint never came up"; exit 5; }
SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no \
     -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=30 \
     -o ConnectTimeout=20 -p "$PORT" "root@$HOST")
SCP=(scp -i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no \
     -o UserKnownHostsFile=/dev/null -P "$PORT")
echo "  ssh root@$HOST:$PORT"

echo "[3/6] validating GPU + torch"
"${SSH[@]}" 'nvidia-smi -L && python -c "import torch; assert torch.cuda.is_available(), \"cuda not available\""' \
    || { echo "[FATAL] GPU/torch sanity failed"; exit 6; }

echo "[4/6] shipping code"
"${SSH[@]}" 'mkdir -p /workspace/asl/logs'
TAR="/tmp/asl_${ROLE}_$$.tar.gz"
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.log' \
    -czf "$TAR" -C "$REPO_ROOT" src configs scripts requirements.txt
"${SCP[@]}" "$TAR" "root@$HOST:/workspace/asl_code.tar.gz"
rm -f "$TAR"
"${SSH[@]}" 'tar -xzf /workspace/asl_code.tar.gz -C /workspace/asl && rm /workspace/asl_code.tar.gz'

echo "[5/6] writing remote secrets + launching training in tmux"
# Build .remote_env locally (KAGGLE token + S3 presigned URLs), scp, then rm.
ENVF="/tmp/remote_env_${ROLE}_$$"
{
    echo "export KAGGLE_API_TOKEN='${KAGGLE_API}'"
    bash scripts/aws_presign_datasets.sh 2>/dev/null || true
} > "$ENVF"
"${SCP[@]}" "$ENVF" "root@$HOST:/workspace/asl/.remote_env"
rm -f "$ENVF"
# Detach with setsid (no tmux on the image). Wrap in `timeout`: some images
# keep the SSH channel open even with redirects + disown, hanging the client
# indefinitely. setsid means the remote process survives the client being
# killed by the timeout, so a timed-out launch ssh is still a successful start.
timeout 60 "${SSH[@]}" "cd /workspace/asl && chmod +x scripts/_remote_train.sh && \
    setsid bash scripts/_remote_train.sh $ROLE >logs/remote_$ROLE.log 2>&1 </dev/null & \
    disown; echo launched" \
    || echo "  (launch ssh closed via timeout; setsid process persists)"

echo "[6/6] recording pod to .round_env"
# Record + clear the destroy-trap BEFORE any verification, so a flaky verify
# SSH can never wrongly tear down a pod that is already training.
# .round_env line: POD <role> <pod_id> <host> <port> <remote_ckpt_dir>
touch "$REPO_ROOT/.round_env"
grep -v "^POD $ROLE " "$REPO_ROOT/.round_env" > "$REPO_ROOT/.round_env.tmp" 2>/dev/null || true
mv "$REPO_ROOT/.round_env.tmp" "$REPO_ROOT/.round_env" 2>/dev/null || true
echo "POD $ROLE $POD_ID $HOST $PORT $CKPT" >> "$REPO_ROOT/.round_env"
trap - EXIT   # pod is recorded; never auto-destroy from here

# Best-effort liveness (log-based; never destroys — the cron catches real
# failures). pgrep would self-match the SSH shell, so grep the log instead.
sleep 6
if timeout 30 "${SSH[@]}" "grep -q 'installing system tools' /workspace/asl/logs/remote_$ROLE.log 2>/dev/null"; then
    echo "  remote training confirmed (log is writing)"
else
    echo "  [warn] could not confirm log yet; pod recorded, cron will monitor"
fi
echo "[done] $ROLE training launched on pod $POD_ID (ssh root@$HOST:$PORT)"
echo "       monitor: bash scripts/round_health.sh   destroy: $PROV destroy $POD_ID"
