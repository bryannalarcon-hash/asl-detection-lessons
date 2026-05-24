#!/usr/bin/env bash
# Net 2 v3.1 launcher — vast.ai RTX 5090.
#
# Provisions a 5090 instance, rsyncs the repo + Net 2 datasets, runs the
# two-stage curriculum (stage_a hagrid-only -> stage_b balanced mix) in tmux,
# tails epoch lines back to the dev box, pulls best.pt when done, destroys
# the instance.
#
# Requires .env.local with VAST_API set. Never commit secrets, never push.
# Re-running the script while an instance is already up is a no-op (no
# double-spawn).
#
# One-time setup: register the public key on the vast account so the
# instance authorizes the launcher's ssh calls. Run once per dev box:
#   vastai create ssh-key "$(cat ~/.ssh/vast_v3.pub)"
# And add to ~/.ssh/config so all ssh invocations pick up the right
# identity even without -i:
#   Host *.vast.ai
#       IdentityFile ~/.ssh/vast_v3
#       IdentitiesOnly yes
# Newly provisioned instances pull keys from account on boot. If the
# key is uploaded after provisioning, attach it explicitly:
#   vastai attach ssh <instance_id> "$(cat ~/.ssh/vast_v3.pub)"
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

# --- Load secrets WITHOUT echoing them. -----------------------------------
if [ ! -f .env.local ]; then
    echo "[ERR] .env.local missing — needs VAST_API=..." >&2
    exit 2
fi
# shellcheck disable=SC1091
set -a
. .env.local
set +a
: "${VAST_API:?VAST_API not set in .env.local}"

VAST_LABEL="asl-net2-v3-1"
LOCAL_LOG="/tmp/net2_v3_1.log"
REMOTE_TMUX="net2v31"
REMOTE_LOG="/workspace/asl/logs/train_v3_1.log"
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=30"

# vast CLI must be installed. Prefer the .local pip install.
export PATH="$HOME/.local/bin:$PATH"
if ! command -v vastai >/dev/null; then
    echo "[setup] installing vastai cli (pip --user)"
    pip install --user --quiet vastai
fi
vastai set api-key "$VAST_API" >/dev/null

# --- Guard against double-spawn. ------------------------------------------
echo "[1/8] checking for existing instance labelled '$VAST_LABEL'"
EXISTING=$(vastai show instances --raw 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print('\n'.join(str(i['id']) for i in d if i.get('label')=='$VAST_LABEL'))")
if [ -n "$EXISTING" ]; then
    echo "[ERR] instance(s) already running with label '$VAST_LABEL': $EXISTING" >&2
    echo "      destroy first with: vastai destroy instance <id>" >&2
    exit 3
fi

# --- Search offers. -------------------------------------------------------
echo "[2/8] searching offers (RTX 5090, >=200 GB, reliability2>=0.98, Utah/US pref)"
OFFER_QUERY='gpu_name=RTX_5090 disk_space>=200 reliability>0.99 rentable=true verified=true'
# vast search occasionally returns empty under transient rate limits;
# retry up to 5 times with backoff.
OFFER_ID=""
for try in 1 2 3 4 5; do
    OFFERS_RAW=$(vastai search offers "$OFFER_QUERY" -o 'dph_total' --raw 2>/dev/null || true)
    if [ -n "$OFFERS_RAW" ]; then
        OFFER_ID=$(printf '%s' "$OFFERS_RAW" | python3 - <<'PY' 2>/dev/null || true
import json, sys
try:
    data = json.loads(sys.stdin.read())
except Exception:
    sys.exit(0)
if not data:
    sys.exit(0)
prefer = ("UT", "Utah")
us = ("US", "United States")
def score(o):
    geo = (o.get("geolocation") or "") + " " + (o.get("country") or "")
    pri = 2 if any(p in geo for p in prefer) else (1 if any(p in geo for p in us) else 0)
    return (-pri, float(o.get("dph_total", 9.99)))
data.sort(key=score)
print(data[0]["id"])
PY
)
    fi
    [ -n "$OFFER_ID" ] && break
    echo "      attempt $try: empty offers, retrying in $((try * 5))s"
    sleep $((try * 5))
done
if [ -z "$OFFER_ID" ]; then
    echo "[ERR] no 5090 offers after 5 retries" >&2
    exit 4
fi
echo "      picked offer $OFFER_ID"

# --- Provision. -----------------------------------------------------------
echo "[3/8] provisioning instance"
CREATE_JSON=$(vastai create instance "$OFFER_ID" \
    --image pytorch/pytorch:2.7.0-cuda12.8-cudnn9-devel \
    --disk 220 \
    --label "$VAST_LABEL" \
    --onstart-cmd "touch /workspace/.ready" \
    --raw)
INSTANCE_ID=$(python3 -c "import json,sys; print(json.loads('''$CREATE_JSON''')['new_contract'])")
echo "      instance $INSTANCE_ID"

cleanup() {
    echo "[cleanup] destroying instance $INSTANCE_ID"
    yes | vastai destroy instance "$INSTANCE_ID" 2>&1 | head -2 || true
}
trap cleanup EXIT INT TERM

# --- Wait for ssh. --------------------------------------------------------
echo "[4/8] waiting for ssh"
SSH_HOST=""; SSH_PORT=""
for _ in $(seq 1 60); do
    INFO=$(vastai show instance "$INSTANCE_ID" --raw 2>/dev/null || echo "{}")
    PARSED=$(printf '%s' "$INFO" | python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
except Exception:
    print('|||'); sys.exit(0)
print(f\"{d.get('ssh_host','') or ''}|{d.get('ssh_port','') or ''}|{d.get('actual_status','') or ''}\")
")
    SSH_HOST="${PARSED%%|*}"
    rest="${PARSED#*|}"
    SSH_PORT="${rest%%|*}"
    STATUS="${rest#*|}"
    if [ "$STATUS" = "running" ] && [ -n "$SSH_HOST" ] && [ -n "$SSH_PORT" ]; then
        if ssh $SSH_OPTS -p "$SSH_PORT" "root@$SSH_HOST" 'echo ok' >/dev/null 2>&1; then
            break
        fi
    fi
    sleep 10
done
if [ -z "$SSH_HOST" ] || [ -z "$SSH_PORT" ]; then
    echo "[ERR] ssh never came up" >&2
    exit 5
fi
echo "      ssh root@$SSH_HOST:$SSH_PORT"

REMOTE="root@$SSH_HOST"
SCP_OPTS="$SSH_OPTS -P $SSH_PORT"
SSH_CMD=(ssh $SSH_OPTS -p "$SSH_PORT" "$REMOTE")

# --- Rsync code + datasets. -----------------------------------------------
echo "[5/8] rsync code + datasets (scp; no .git, no .env)"
"${SSH_CMD[@]}" "mkdir -p /workspace/asl/logs /workspace/asl/data"

# Code only. Positive-include list keeps the tar under 5 MB even if the
# dev box has venvs / build artifacts / design zips sitting around.
TAR_TMP="/tmp/asl_code_${INSTANCE_ID}.tar.gz"
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.log' \
    -czf "$TAR_TMP" -C "$REPO_ROOT" \
    src configs scripts modal_apps tests requirements.txt
scp $SCP_OPTS "$TAR_TMP" "$REMOTE:/workspace/asl_code.tar.gz"
rm -f "$TAR_TMP"
"${SSH_CMD[@]}" "tar -xzf /workspace/asl_code.tar.gz -C /workspace/asl && rm /workspace/asl_code.tar.gz"

# --- Kick off Stage A then Stage B in detached tmux. ----------------------
echo "[6/8] launching two-stage curriculum (stage_a -> stage_b) in tmux"
REMOTE_SCRIPT='/workspace/asl/scripts/_remote_net2_v3_1.sh'
"${SSH_CMD[@]}" "cat > $REMOTE_SCRIPT" <<'REMOTE_EOF'
#!/usr/bin/env bash
set -euo pipefail
cd /workspace/asl
export PATH="$HOME/.local/bin:$PATH"
mkdir -p logs

echo "[remote] install deps"
apt-get install -y -qq unzip rsync >/dev/null
pip install -q -r requirements.txt
if nvidia-smi --query-gpu=compute_cap --format=csv,noheader | grep -qE "1[12]\."; then
    pip install -q --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu128
fi
pip install -q nvidia-dali-cuda120 numba

echo "[remote] download Net 2 datasets"
bash scripts/download_v3_data.sh --net2-only 2>&1 | tee -a logs/download.log

echo "[remote] build npy cache at 256"
python -u scripts/build_net2_cache.py --cache-root data/net2_cache \
    --input-size 256 --sources hagrid,coco,freihand,egohands,synthetic \
    --workers 32 2>&1 | tee -a logs/build_cache.log

ulimit -n 65536

echo "[remote] STAGE A — hagrid-only pretrain"
python -u -m src.stage1.train_v3_detector \
    --config configs/stage1_v3_detector_v3_1.yaml \
    --stage stage_a \
    --use-numba-anchors 2>&1 | tee -a logs/train_v3_1.log

echo "[remote] STAGE B — balanced finetune"
python -u -m src.stage1.train_v3_detector \
    --config configs/stage1_v3_detector_v3_1.yaml \
    --stage stage_b \
    --use-numba-anchors 2>&1 | tee -a logs/train_v3_1.log

echo "[remote] DONE"
touch /workspace/asl/.train_done
REMOTE_EOF
"${SSH_CMD[@]}" "chmod +x $REMOTE_SCRIPT"
"${SSH_CMD[@]}" "setsid tmux new-session -d -s $REMOTE_TMUX 'bash $REMOTE_SCRIPT'"

# --- Tail epoch lines back to dev box. ------------------------------------
echo "[7/8] streaming epoch lines -> $LOCAL_LOG"
: > "$LOCAL_LOG"
TAIL_PID=""
(
    ssh $SSH_OPTS -p "$SSH_PORT" "$REMOTE" \
        "touch $REMOTE_LOG && tail -n +1 -F $REMOTE_LOG" \
        2>/dev/null | grep --line-buffered -E "^(epoch|\[stage|\[remote)" \
        >> "$LOCAL_LOG" &
    echo $!
) > /tmp/net2_v3_1_tail.pid
TAIL_PID=$(cat /tmp/net2_v3_1_tail.pid)

# Poll for completion marker, with periodic still-alive checks.
echo "      waiting for /workspace/asl/.train_done (poll every 60s)"
while true; do
    if "${SSH_CMD[@]}" 'test -f /workspace/asl/.train_done' 2>/dev/null; then
        echo "      remote signalled DONE"
        break
    fi
    # Detect tmux death — if the session died, fail loud.
    if ! "${SSH_CMD[@]}" "tmux has-session -t $REMOTE_TMUX" >/dev/null 2>&1; then
        echo "[ERR] tmux session died before .train_done appeared" >&2
        kill "$TAIL_PID" 2>/dev/null || true
        exit 6
    fi
    sleep 60
done
kill "$TAIL_PID" 2>/dev/null || true

# --- Pull best.pt back. ---------------------------------------------------
echo "[8/8] pulling best.pt + metrics + log"
mkdir -p "$REPO_ROOT/results/v3/net2_v3_1"
scp $SCP_OPTS "$REMOTE:/workspace/asl/checkpoints/stage1_v3_detector_v3_1/stage_b/best.pt" \
    "$REPO_ROOT/results/v3/net2_v3_1/best.pt"
scp $SCP_OPTS "$REMOTE:/workspace/asl/checkpoints/stage1_v3_detector_v3_1/stage_a/best.pt" \
    "$REPO_ROOT/results/v3/net2_v3_1/stage_a_best.pt" || true
scp $SCP_OPTS "$REMOTE:/workspace/asl/logs/train_v3_1.log" \
    "$REPO_ROOT/results/v3/net2_v3_1/train_v3_1.log" || true
scp $SCP_OPTS "$REMOTE:/workspace/asl/checkpoints/stage1_v3_detector_v3_1/stage_b/metrics.jsonl" \
    "$REPO_ROOT/results/v3/net2_v3_1/metrics.jsonl" || true

echo "[done] artifacts at results/v3/net2_v3_1/"
# trap cleanup destroys the instance.
