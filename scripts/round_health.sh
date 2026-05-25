#!/usr/bin/env bash
# Training-round health check + artifact mirror (cron target, every ~10 min).
#
# Reads pods from .round_env (written by scripts/launch_train_pod.sh), one
# line each:  POD <role> <pod_id> <host> <port> <remote_ckpt_dir>
# For each pod it pulls best.pt / last.pt / newest epoch_*.pt / metrics.jsonl
# into results/v3/<role>/, reports the latest epoch + headline metric, and
# prints a HEALTH verdict (trainer alive? done marker?). Log-and-continue so
# a single unreachable pod (busy / rebooting) does not abort the others.
#
# Exit: 0 pulled something | 2 no pods configured | 3 nothing new yet.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
KEY="${NET_SSH_KEY:-${HOME}/.ssh/vast_v3}"
ROUND_ENV="${REPO_ROOT}/.round_env"
LOG_DIR="${REPO_ROOT}/logs"; mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/round_health.log"
ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { printf '[%s] %s\n' "$(ts)" "$*" | tee -a "${LOG_FILE}"; }

[ -f "${ROUND_ENV}" ] || { log "no .round_env — no pods to monitor"; exit 2; }

pulled=0
while read -r tag role pod_id host port rdir; do
    [ "${tag:-}" = "POD" ] || continue
    # .round_env stores the ckpt dir relative to the remote repo root; make it
    # absolute so ls/scp work without a remote `cd` (they run from /root).
    case "${rdir}" in /*) : ;; *) rdir="/workspace/asl/${rdir}" ;; esac
    ldir="${REPO_ROOT}/results/v3/${role}"
    mkdir -p "${ldir}"
    # -n redirects ssh stdin from /dev/null: without it, ssh consumes the
    # while-read loop's stdin (the .round_env file) and the loop processes
    # only the first pod.
    SSH=(ssh -n -i "${KEY}" -o IdentitiesOnly=yes -o ConnectTimeout=12 -o BatchMode=yes
         -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p "${port}" "root@${host}")
    scp_pull() { scp -i "${KEY}" -o IdentitiesOnly=yes -o ConnectTimeout=12 \
                 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
                 -P "${port}" "root@${host}:$1" "$2" >>"${LOG_FILE}" 2>&1; }

    if ! "${SSH[@]}" 'echo ok' >/dev/null 2>&1; then
        log "[${role}] pod ${pod_id} unreachable (busy/rebooting) host=${host}:${port}"
        continue
    fi
    # Filter to real python trainer processes; the [p]ython trick + grep avoids
    # the pgrep shell self-matching its own pattern string and reporting a
    # false "alive" while the pod is only downloading.
    procs=$("${SSH[@]}" "pgrep -af 'train_v3_detector|train_v3_landmark_reg|extract_keypoints|train_v4_classifier' | grep -E '[p]ython -u -m' | head -1" 2>/dev/null || true)
    markers=$("${SSH[@]}" "ls -1 /workspace/asl/.*_done 2>/dev/null | tr '\n' ' '" 2>/dev/null || true)
    if [ -n "${procs}" ]; then
        log "[${role}] HEALTH alive: ${procs}"
    else
        log "[${role}] HEALTH no trainer process (between stages / done / crashed). markers: ${markers:-none}"
    fi

    listing=$("${SSH[@]}" "ls -1t ${rdir}/best.pt ${rdir}/last.pt ${rdir}/metrics.jsonl ${rdir}/epoch_*.pt 2>/dev/null" 2>/dev/null || true)
    if [ -z "${listing}" ]; then
        log "[${role}] no artifacts in ${rdir} yet"
        continue
    fi
    for name in best.pt last.pt metrics.jsonl; do
        case "${listing}" in *"${rdir}/${name}"*)
            scp_pull "${rdir}/${name}" "${ldir}/${name}" && pulled=$((pulled+1)) ;;
        esac
    done
    newest_epoch=$(echo "${listing}" | grep -E "/epoch_[0-9]+\.pt$" | head -1 || true)
    [ -n "${newest_epoch}" ] && scp_pull "${newest_epoch}" "${ldir}/$(basename "${newest_epoch}")" && pulled=$((pulled+1))

    if [ -f "${ldir}/metrics.jsonl" ]; then
        tail -n 1 "${ldir}/metrics.jsonl" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    ks = [k for k in ('val_pck_05','val_pck_10','val_pck_20','top1','top3','val_acc','mAP','train_loss','cls_loss','box_loss','kpt_loss') if k in d]
    print('METRIC ${role} epoch=' + str(d.get('epoch','?')) + ' ' + ' '.join(f'{k}={d[k]}' for k in ks))
except Exception as e:
    print('METRIC ${role} parse_error: ' + str(e))" | tee -a "${LOG_FILE}"
    fi
done < "${ROUND_ENV}"

[ "${pulled}" -gt 0 ] && exit 0 || exit 3
