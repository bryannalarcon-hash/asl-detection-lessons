#!/usr/bin/env bash
# Training-round health check + artifact mirror (cron target, every ~10 min).
#
# Generalizes mirror_net3_local.sh to the multi-net sequential round
# (Net2 -> Net3 -> extract -> Net4) on one RunPod box. For each configured
# remote checkpoint dir it pulls best.pt, last.pt, the newest epoch_*.pt
# (the "every 10" snapshot) and metrics.jsonl, reports the latest epoch +
# headline metric, and prints a HEALTH verdict: is a python trainer alive,
# and did metrics.jsonl advance since last pull.
#
# Config (env; sourced from .env.local if present):
#   NET_SSH_HOST   pod public IP            (from runpod_provision.py ssh <id>)
#   NET_SSH_PORT   pod public SSH port
#   NET_SSH_KEY    private key path         (default ~/.ssh/vast_v3)
#   ROUND_DIRS     space/semicolon list of "remote_dir=>local_dir" pairs.
#                  Defaults cover the three trainers' checkpoint_dir values.
#
# Exit codes: 0 pulled something | 2 host unreachable | 3 nothing new yet.
# Failure mode is "log and exit non-zero" so cron keeps retrying across the
# brief windows where the box is busy or rebooting.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ -f "${REPO_ROOT}/.env.local" ]; then
    set -a; . "${REPO_ROOT}/.env.local"; set +a
fi

HOST="${NET_SSH_HOST:-}"
PORT="${NET_SSH_PORT:-}"
KEY="${NET_SSH_KEY:-${HOME}/.ssh/vast_v3}"
REMOTE_BASE="/workspace/asl/checkpoints"

# Default dir map: remote checkpoint_dir => local results dir. Matches the
# configs the build round produces (stage_b for Net2's curriculum).
DEFAULT_DIRS="\
${REMOTE_BASE}/stage1_v3_detector_kpt/stage_b=>results/v3/net2_kpt \
${REMOTE_BASE}/stage1_v3_landmark_reg=>results/v3/net3_reg \
${REMOTE_BASE}/stage2_v4_classifier_popsign=>results/v3/net4_popsign"
ROUND_DIRS="${ROUND_DIRS:-$DEFAULT_DIRS}"

LOG_DIR="${REPO_ROOT}/logs"; mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/round_health.log"
ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { printf '[%s] %s\n' "$(ts)" "$*" | tee -a "${LOG_FILE}"; }

if [ -z "${HOST}" ] || [ -z "${PORT}" ]; then
    log "FATAL config: NET_SSH_HOST and NET_SSH_PORT must be set (run: python3 scripts/runpod_provision.py ssh <podId>)"
    exit 1
fi

SSH=(ssh -i "${KEY}" -o IdentitiesOnly=yes -o ConnectTimeout=12 \
     -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
     -p "${PORT}" "root@${HOST}")
scp_pull() {  # remote_path local_path
    scp -i "${KEY}" -o IdentitiesOnly=yes -o ConnectTimeout=12 \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -P "${PORT}" "root@${HOST}:$1" "$2" >>"${LOG_FILE}" 2>&1
}

if ! "${SSH[@]}" 'echo ok' >/dev/null 2>&1; then
    log "WARN host unreachable (host=${HOST} port=${PORT}) — box busy/rebooting?"
    exit 2
fi

# HEALTH: is a trainer/extractor process alive, and what stage marker exists.
PROCS=$("${SSH[@]}" "pgrep -af 'train_v3_detector|train_v3_landmark_reg|extract_keypoints|train_v4_classifier' | head -3" 2>/dev/null || true)
MARKERS=$("${SSH[@]}" "ls -1 /workspace/asl/.*_done 2>/dev/null" 2>/dev/null || true)
if [ -n "${PROCS}" ]; then
    log "HEALTH alive: $(echo "${PROCS}" | sed 's/  */ /g' | tr '\n' ';')"
else
    log "HEALTH no trainer process running (between stages, finished, or crashed)"
fi
[ -n "${MARKERS}" ] && log "MARKERS: $(echo ${MARKERS} | tr '\n' ' ')"

pulled=0
# Normalize separators (allow ';' or whitespace between pairs).
for pair in $(echo "${ROUND_DIRS}" | tr ';' ' '); do
    rdir="${pair%%=>*}"; ldir="${pair##*=>}"
    [ "${rdir}" = "${pair}" ] && continue   # skip malformed
    abs_ldir="${REPO_ROOT}/${ldir}"; mkdir -p "${abs_ldir}"
    # Newest epoch snapshot + the fixed names.
    listing=$("${SSH[@]}" "ls -1t ${rdir}/best.pt ${rdir}/last.pt ${rdir}/metrics.jsonl ${rdir}/epoch_*.pt 2>/dev/null" 2>/dev/null || true)
    [ -z "${listing}" ] && { log "INFO ${rdir}: no artifacts yet"; continue; }
    # Fixed-name files.
    for name in best.pt last.pt metrics.jsonl; do
        case "${listing}" in *"${rdir}/${name}"*)
            scp_pull "${rdir}/${name}" "${abs_ldir}/${name}" && pulled=$((pulled+1)) ;;
        esac
    done
    # Newest epoch_*.pt only (the "every 10" snapshot) to avoid pulling all.
    newest_epoch=$(echo "${listing}" | grep -E "/epoch_[0-9]+\.pt$" | head -1 || true)
    if [ -n "${newest_epoch}" ]; then
        scp_pull "${newest_epoch}" "${abs_ldir}/$(basename "${newest_epoch}")" && pulled=$((pulled+1))
    fi
    # Report latest epoch + metric from the mirrored metrics.jsonl.
    if [ -f "${abs_ldir}/metrics.jsonl" ]; then
        tail -n 1 "${abs_ldir}/metrics.jsonl" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    ks = [k for k in ('val_pck_05','val_pck_10','val_pck_20','top1','top3','val_acc','train_loss') if k in d]
    m = ' '.join(f'{k}={d[k]}' for k in ks)
    print(f'METRIC ${ldir} epoch={d.get(\"epoch\",\"?\")} {m}')
except Exception as e:
    print(f'METRIC ${ldir} parse_error: {e}')" | tee -a "${LOG_FILE}"
    fi
done

[ "${pulled}" -gt 0 ] && exit 0 || exit 3
