#!/usr/bin/env bash
# Mirror Net 3 v2 artifacts (best.pt + last.pt + metrics.jsonl) from the
# live Vast 5090 down to local results/v3/net3_v2/. Intended for cron at
# */30 * * * *.
#
# Configuration (env vars; can be sourced from .env.local):
#   NET3_VAST_HOST   ssh host, e.g. ssh1.vast.ai
#   NET3_VAST_PORT   ssh port, e.g. 34594
#   NET3_REMOTE_DIR  defaults to /workspace/asl/checkpoints/stage1_v3_landmark_v2
#   NET3_LOCAL_DIR   defaults to results/v3/net3_v2 (resolved against the
#                    repo root one level up from this script)
#
# Exit codes:
#   0  one or more artifacts successfully mirrored
#   1  configuration missing
#   2  scp connection failed (host unreachable / port closed)
#   3  no artifacts present on remote yet
#
# Failure mode is "log and exit non-zero" — cron should keep retrying.
# A connect failure during the brief Vast-reboot window is normal.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Allow .env.local to provide host/port if the caller hasn't already sourced it.
if [ -z "${NET3_VAST_HOST:-}" ] && [ -f "${REPO_ROOT}/.env.local" ]; then
    set -a
    # shellcheck disable=SC1090,SC1091
    . "${REPO_ROOT}/.env.local"
    set +a
fi

HOST="${NET3_VAST_HOST:-}"
PORT="${NET3_VAST_PORT:-}"
REMOTE_DIR="${NET3_REMOTE_DIR:-/workspace/asl/checkpoints/stage1_v3_landmark_v2}"
LOCAL_DIR_DEFAULT="${REPO_ROOT}/results/v3/net3_v2"
LOCAL_DIR="${NET3_LOCAL_DIR:-${LOCAL_DIR_DEFAULT}}"
LOG_DIR="${REPO_ROOT}/logs"
LOG_FILE="${LOG_DIR}/mirror_net3.log"

mkdir -p "${LOCAL_DIR}" "${LOG_DIR}"

ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { printf '[%s] %s\n' "$(ts)" "$*" | tee -a "${LOG_FILE}"; }

if [ -z "${HOST}" ] || [ -z "${PORT}" ]; then
    log "FATAL config: NET3_VAST_HOST and NET3_VAST_PORT must be set"
    exit 1
fi

# Probe connectivity first so we can distinguish "no artifacts yet" from
# "host unreachable". A failed probe is the common case during reboots.
if ! ssh -p "${PORT}" -o ConnectTimeout=10 -o BatchMode=yes \
        -o StrictHostKeyChecking=no \
        "root@${HOST}" "test -d ${REMOTE_DIR}" 2>>"${LOG_FILE}"; then
    log "WARN connection or remote dir missing (host=${HOST} port=${PORT} dir=${REMOTE_DIR})"
    exit 2
fi

# List what's actually on the remote before scp'ing — saves a noisy "No
# such file" stderr line when training hasn't checkpointed yet.
REMOTE_LIST=$(ssh -p "${PORT}" -o ConnectTimeout=10 -o BatchMode=yes \
    -o StrictHostKeyChecking=no \
    "root@${HOST}" \
    "ls ${REMOTE_DIR}/best.pt ${REMOTE_DIR}/last.pt ${REMOTE_DIR}/metrics.jsonl 2>/dev/null" \
    || true)
if [ -z "${REMOTE_LIST}" ]; then
    log "INFO no artifacts on remote yet (training may not have hit the first checkpoint)"
    exit 3
fi

pulled=0
for name in best.pt last.pt metrics.jsonl; do
    case "${REMOTE_LIST}" in
        *"${REMOTE_DIR}/${name}"*)
            if scp -P "${PORT}" -o ConnectTimeout=10 \
                   -o StrictHostKeyChecking=no \
                   "root@${HOST}:${REMOTE_DIR}/${name}" \
                   "${LOCAL_DIR}/${name}" \
                   >>"${LOG_FILE}" 2>&1; then
                pulled=$((pulled + 1))
                size=$(stat -c '%s' "${LOCAL_DIR}/${name}" 2>/dev/null || echo 0)
                log "OK pulled ${name} (${size} bytes)"
            else
                log "WARN scp failed for ${name}"
            fi
            ;;
        *)
            log "INFO ${name} not yet on remote"
            ;;
    esac
done

# Surface the latest val_pck_05 from the mirrored metrics for cron output.
if [ -f "${LOCAL_DIR}/metrics.jsonl" ]; then
    latest=$(tail -n 1 "${LOCAL_DIR}/metrics.jsonl" 2>/dev/null || true)
    if [ -n "${latest}" ]; then
        echo "${latest}" \
            | python3 -c "import sys, json
try:
    d = json.loads(sys.stdin.read())
    ep = d.get('epoch', '?')
    p05 = d.get('val_pck_05', d.get('val_pck', float('nan')))
    p10 = d.get('val_pck_10', float('nan'))
    p20 = d.get('val_pck_20', float('nan'))
    print(f'METRIC epoch={ep} val_pck_05={p05} val_pck_10={p10} val_pck_20={p20}')
except Exception as e:
    print(f'METRIC parse_error: {e}')
" | tee -a "${LOG_FILE}"
    fi
fi

if [ "${pulled}" -gt 0 ]; then
    exit 0
fi
exit 3
