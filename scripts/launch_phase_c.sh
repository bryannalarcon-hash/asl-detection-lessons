#!/usr/bin/env bash
# Phase C launcher: PopSign extraction -> Net 4 -> e2e pipeline.
#
#   scripts/launch_phase_c.sh
#
# Provisions one pod, ships code + the trained Net1/2/3 checkpoints, and kicks
# off scripts/_remote_phase_c.sh detached. Records the pod to .round_env as
# role "phasec" (ckpt dir = the Net 4 checkpoint dir) so the cron monitors it.
# Pre-req: results/v3/net1_v3_1/best_export.pt, results/v3/net2/best.pt,
# results/v3/net3/best.pt all present locally (verified below).
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

[ -f .env.local ] || { echo "[FATAL] .env.local missing"; exit 2; }
set -a; . ./.env.local; set +a
: "${RUNPOD_API:?RUNPOD_API not set}"

KEY="${NET_SSH_KEY:-$HOME/.ssh/vast_v3}"
IMAGE="${RUNPOD_IMAGE:-runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04}"
PROV="python3 scripts/runpod_provision.py"
DISK="${POD_DISK:-60}"
CKPT="checkpoints/stage2_v4_classifier_popsign"
# ROLE lets a second (parallel) pod run a disjoint slice without clobbering the
# baseline pod's .round_env line / logs. Extraction knobs (OFFSET, MAX_PER_SIGN,
# BATCHED, TRAIN_NET4) are passed through to the remote via a shipped .remote_env.
ROLE="${ROLE:-phasec}"
LOG="logs/remote_${ROLE}.log"
GPU="${RUNPOD_GPU:-NVIDIA GeForce RTX 5090}"

N1=results/v3/net1_v3_1/best_export.pt
N2=results/v3/net2_v3_1/best.pt   # stronger detector; Net 3 self-orients (2-pass)
N3=results/v3/net3/best.pt
for f in "$N1" "$N2" "$N3"; do
    [ -s "$REPO_ROOT/$f" ] || { echo "[FATAL] missing local checkpoint: $f"; exit 3; }
done
echo "[0/6] checkpoints present: net1=$(stat -c%s "$N1") net2=$(stat -c%s "$N2") net3=$(stat -c%s "$N3")"

deploy() { $PROV deploy --name "asl-$ROLE" --gpu "$GPU" --disk "$DISK" --image "$IMAGE" $1 2>/tmp/dep_$ROLE.err; }
echo "[1/6] provisioning $ROLE pod (disk=${DISK}GB)"
POD_ID=""
for try in 1 2 3; do POD_ID=$(deploy "" || true); [ -n "$POD_ID" ] && { echo "  community pod $POD_ID"; break; }; sleep 8; done
[ -n "$POD_ID" ] || { echo "  community unavailable; secure"; POD_ID=$(deploy "--secure" || true); }
[ -n "$POD_ID" ] || { echo "[FATAL] deploy failed: $(cat /tmp/dep_$ROLE.err)"; exit 4; }
trap 'echo "[cleanup] destroying $POD_ID"; '"$PROV"' destroy "'"$POD_ID"'" || true' EXIT

echo "[2/6] waiting for SSH"
read -r HOST PORT < <(timeout 420 $PROV ssh "$POD_ID" || true)
[ -n "${PORT:-}" ] || { echo "[FATAL] no SSH"; exit 5; }
SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=30 -o ConnectTimeout=20 -p "$PORT" "root@$HOST")
SCP=(scp -i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -P "$PORT")
echo "  ssh root@$HOST:$PORT"

echo "[3/6] validating GPU + torch"
"${SSH[@]}" 'nvidia-smi -L && python -c "import torch; assert torch.cuda.is_available()"' \
    || { echo "[FATAL] GPU/torch sanity failed"; exit 6; }

echo "[4/6] shipping code + checkpoints"
"${SSH[@]}" 'mkdir -p /workspace/asl/logs /workspace/asl/results/v3/net1_v3_1 /workspace/asl/results/v3/net2_v3_1 /workspace/asl/results/v3/net3'
TAR="/tmp/asl_phasec_$$.tar.gz"
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.log' -czf "$TAR" -C "$REPO_ROOT" src configs scripts requirements.txt
"${SCP[@]}" "$TAR" "root@$HOST:/workspace/asl_code.tar.gz"; rm -f "$TAR"
"${SSH[@]}" 'tar -xzf /workspace/asl_code.tar.gz -C /workspace/asl && rm /workspace/asl_code.tar.gz'
"${SCP[@]}" "$REPO_ROOT/$N1" "root@$HOST:/workspace/asl/$N1"
"${SCP[@]}" "$REPO_ROOT/$N2" "root@$HOST:/workspace/asl/$N2"
"${SCP[@]}" "$REPO_ROOT/$N3" "root@$HOST:/workspace/asl/$N3"

# Ship extraction knobs via .remote_env (sourced by _remote_phase_c.sh).
"${SSH[@]}" "cat > /workspace/asl/.remote_env <<EOF
OFFSET=${OFFSET:-0}
MAX_PER_SIGN=${MAX_PER_SIGN:-40}
BATCHED=${BATCHED:-0}
TRAIN_NET4=${TRAIN_NET4:-1}
EOF"

echo "[5/6] launching $ROLE (detached)"
timeout 60 "${SSH[@]}" "cd /workspace/asl && chmod +x scripts/_remote_phase_c.sh && \
    setsid bash scripts/_remote_phase_c.sh >$LOG 2>&1 </dev/null & disown; echo launched" \
    || echo "  (launch ssh closed via timeout; setsid persists)"

echo "[6/6] recording pod to .round_env"
touch "$REPO_ROOT/.round_env"
grep -v "^POD $ROLE " "$REPO_ROOT/.round_env" > "$REPO_ROOT/.round_env.tmp" 2>/dev/null || true
mv "$REPO_ROOT/.round_env.tmp" "$REPO_ROOT/.round_env" 2>/dev/null || true
echo "POD $ROLE $POD_ID $HOST $PORT $CKPT" >> "$REPO_ROOT/.round_env"
trap - EXIT
sleep 6
if timeout 30 "${SSH[@]}" "grep -q 'phasec' /workspace/asl/$LOG 2>/dev/null"; then
    echo "  $ROLE confirmed running"
else
    echo "  [warn] could not confirm log yet; pod recorded, cron will monitor"
fi
echo "[done] $ROLE launched on pod $POD_ID (ssh root@$HOST:$PORT)"