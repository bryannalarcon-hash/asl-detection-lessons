#!/usr/bin/env bash
# Remote training orchestration for one role, run inside a rented GPU pod's
# detached tmux by scripts/launch_train_pod.sh. Static (no host-side string
# interpolation) so it is safe to ship verbatim. Secrets come from
# /workspace/asl/.remote_env (KAGGLE_API_TOKEN, RHD/EgoHands presigned URLs),
# which the launcher writes and this script sources. Writes a .<role>_done
# marker on success so the cron health check / launcher can detect completion.
#
#   bash scripts/_remote_train.sh <net2|net3>
set -euo pipefail
cd /workspace/asl
ROLE="${1:?usage: _remote_train.sh <net2|net3>}"
[ -f .remote_env ] && { set -a; . ./.remote_env; set +a; }
export PYTHONUNBUFFERED=1
mkdir -p logs checkpoints

echo "[remote:$ROLE] $(date -u) installing system tools"
# The runpod/pytorch image is minimal: no unzip/wget/rsync, which the dataset
# download scripts need (COCO zip, kaggle --unzip, HaGRID, InterHand wget).
apt-get update -qq >/dev/null 2>&1 || true
apt-get install -y -qq unzip wget rsync curl git >/dev/null 2>&1 || true

echo "[remote:$ROLE] $(date -u) installing deps"
pip install -q -r requirements.txt
pip install -q --upgrade kaggle gdown >/dev/null 2>&1 || true
pip install -q nvidia-dali-cuda120 numba >/dev/null 2>&1 || true

# Blackwell (sm_120) needs a cu128 torch build. If the current torch cannot
# actually run a kernel on this GPU, reinstall from the cu128 index.
if ! python - <<'PY' >/dev/null 2>&1
import torch, sys
sys.exit(0 if (torch.cuda.is_available() and float(torch.zeros(1).cuda().add_(1)) == 1.0) else 1)
PY
then
    echo "[remote:$ROLE] torch cannot use this GPU; upgrading to cu128"
    pip install -q --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu128
fi
ulimit -n 65536 || true

case "$ROLE" in
  net2)
    bash scripts/download_v3_data.sh --net2-only 2>&1 | tee -a logs/download.log
    # No mmap cache: at 256px it would be ~127GB (HaGRID alone is 500k images)
    # and overflow any reasonably-sized disk. The dataset falls back to cv2
    # JPEG decode; the forced numpy anchor matcher (n_kpts>0) is the bottleneck
    # anyway, so the cache's I/O speedup is largely moot here.
    echo "[remote:net2] STAGE A (hagrid-only, raw JPEG dataset)"
    python -u -m src.stage1.train_v3_detector \
        --config configs/stage1_v3_detector_kpt.yaml --stage stage_a \
        2>&1 | tee -a logs/train_net2.log
    echo "[remote:net2] STAGE B (balanced mix)"
    python -u -m src.stage1.train_v3_detector \
        --config configs/stage1_v3_detector_kpt.yaml --stage stage_b \
        2>&1 | tee -a logs/train_net2.log
    touch .net2_done ;;
  net3)
    bash scripts/download_v3_data.sh --net3-only 2>&1 | tee -a logs/download.log
    echo "[remote:net3] TRAIN regression landmark"
    python -u -m src.stage1.train_v3_landmark_reg \
        --config configs/stage1_v3_landmark_reg.yaml \
        2>&1 | tee -a logs/train_net3.log
    touch .net3_done ;;
  *) echo "[remote] unknown role: $ROLE" >&2; exit 2 ;;
esac

echo "[remote:$ROLE] DONE $(date -u)"
