#!/usr/bin/env bash
# Pull Net 3 artifacts from S3 down to results/v3/net3/.
#
# Reads AWS creds + bucket from the environment. Source .env.local first:
#   source .env.local && bash scripts/aws_pull_net3.sh
#
# Defaults pull best.pt + last.pt + metrics.jsonl. Pass --all to pull
# every checkpoint snapshot in the prefix as well.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
AWS="${AWS_CLI:-$(command -v aws || true)}"
if [ -z "${AWS}" ] || [ ! -x "${AWS}" ]; then
    echo "FATAL: aws CLI not on PATH. Install with: pip install --user awscli" >&2
    exit 2
fi

REGION="${AWS_REGION:-us-east-1}"
BUCKET_NAME="${BUCKET_NAME:-asl-net3-data}"
PREFIX="${S3_PREFIX:-net3/checkpoints}"
DEST="${DEST:-results/v3/net3}"
PULL_ALL=0
for arg in "$@"; do
    case "${arg}" in
        --all) PULL_ALL=1 ;;
        --bucket=*) BUCKET_NAME="${arg#--bucket=}" ;;
        --dest=*) DEST="${arg#--dest=}" ;;
        --prefix=*) PREFIX="${arg#--prefix=}" ;;
        -h|--help)
            cat <<USAGE
Usage: aws_pull_net3.sh [--all] [--bucket=NAME] [--prefix=PATH] [--dest=PATH]
  --all       Also pull all epoch_NNN.pt snapshots (not just best/last).
  --bucket    Override S3 bucket (default: asl-net3-data).
  --prefix    Override S3 key prefix (default: net3/checkpoints).
  --dest      Local destination (default: results/v3/net3).
USAGE
            exit 0 ;;
    esac
done

required_env=(AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY)
missing=()
for v in "${required_env[@]}"; do
    if [ -z "${!v:-}" ]; then missing+=("$v"); fi
done
if [ "${#missing[@]}" -gt 0 ]; then
    echo "FATAL: missing required env: ${missing[*]}" >&2
    echo "Source .env.local first." >&2
    exit 2
fi
export AWS_DEFAULT_REGION="${REGION}"

if ! "${AWS}" s3api head-bucket --bucket "${BUCKET_NAME}" >/dev/null 2>&1; then
    echo "FATAL: bucket s3://${BUCKET_NAME}/ not accessible" >&2
    exit 3
fi

mkdir -p "${DEST}"
echo "[pull] s3://${BUCKET_NAME}/${PREFIX}/ → ${DEST}/"

# Always pull the canonical artifacts.
for name in best.pt last.pt metrics.jsonl; do
    if "${AWS}" s3api head-object --bucket "${BUCKET_NAME}" \
            --key "${PREFIX}/${name}" >/dev/null 2>&1; then
        "${AWS}" s3 cp "s3://${BUCKET_NAME}/${PREFIX}/${name}" \
            "${DEST}/${name}" --only-show-errors
        echo "  ok ${name}"
    else
        echo "  missing ${name} (skip)"
    fi
done

if [ "${PULL_ALL}" -eq 1 ]; then
    echo "[pull] mirroring all snapshots"
    "${AWS}" s3 sync "s3://${BUCKET_NAME}/${PREFIX}/" "${DEST}/" \
        --exclude '*' --include 'epoch_*.pt' --only-show-errors
fi

# Final summary: extract the last line of metrics.jsonl and the best-epoch
# entry. We use python so float formatting is consistent across platforms.
if [ -f "${DEST}/metrics.jsonl" ]; then
    python3 - "${DEST}/metrics.jsonl" <<'PYEOF'
import json, sys, math
p = sys.argv[1]
lines = [json.loads(x) for x in open(p) if x.strip()]
if not lines:
    print("[summary] metrics.jsonl is empty")
    sys.exit(0)
last = lines[-1]
def best(key):
    vals = [(i, d.get(key)) for i, d in enumerate(lines)
            if isinstance(d.get(key), (int, float)) and not math.isnan(d[key])]
    return max(vals, key=lambda kv: kv[1]) if vals else (None, None)
b_idx, b_val = best("val_pck")
print("================================================================")
print(f"[summary] epochs logged   : {len(lines)}")
print(f"[summary] last epoch      : {last.get('epoch')}")
print(f"[summary] last train_loss : {last.get('train_loss'):.4f}"
      if isinstance(last.get('train_loss'), (int, float)) else "[summary] last train_loss : n/a")
print(f"[summary] last val_pck    : {last.get('val_pck')}")
if b_idx is not None:
    be = lines[b_idx]
    print(f"[summary] BEST val_pck    : {b_val:.4f} @ epoch {be.get('epoch')}")
print("================================================================")
PYEOF
else
    echo "[summary] no metrics.jsonl pulled"
fi
