#!/usr/bin/env bash
# Phase: Net 2 detection-AP comparison (new keypoint detector vs net2_v3_1) on
# COCO-WholeBody val. Run inside a rented pod by launch_eval_net2.sh. Downloads
# the wholebody train ann, splits a val set, fetches ONLY the N val images it
# will score (by URL, ~120MB not 18GB), then runs eval_net2_ap.py on both
# checkpoints (pushed to results/v3/net2_v3_1/best.pt and results/v3/net2/best.pt).
set -uo pipefail
cd /workspace/asl
[ -f .remote_env ] && { set -a; . ./.remote_env; set +a; }
export PYTHONUNBUFFERED=1
N="${EVAL_N:-800}"
mkdir -p data/coco/annotations data/coco/train2017 logs

echo "[eval] $(date -u) deps"
apt-get update -qq >/dev/null 2>&1 || true
apt-get install -y -qq unzip wget curl >/dev/null 2>&1 || true
pip install -q -r requirements.txt
pip install -q --upgrade gdown >/dev/null 2>&1 || true

if [ ! -f data/coco/annotations/coco_wholebody_val_v1.0.json ]; then
    echo "[eval] downloading + splitting COCO-WholeBody annotations"
    ( cd data/coco/annotations && gdown 1thErEToRbmM9uLNi1JXXfOsaS5VK2FXf -O coco_wholebody_train_v1.0.json )
    python3 scripts/split_train_val.py \
        --in data/coco/annotations/coco_wholebody_train_v1.0.json \
        --train-out data/coco/annotations/coco_wholebody_train_v1.0.json \
        --val-out data/coco/annotations/coco_wholebody_val_v1.0.json
fi

echo "[eval] fetching the $N val images this run will score"
python3 - "$N" <<'PY'
import sys, os, urllib.request
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
N = int(sys.argv[1])
ds = CocoWholeBodyDataset("data/coco/annotations/coco_wholebody_val_v1.0.json",
                          "data/coco/train2017")
N = min(N, len(ds))
got = miss = 0
for i in range(N):
    p = ds[i]["image_path"]
    if os.path.exists(p):
        got += 1; continue
    fn = os.path.basename(p)
    try:
        urllib.request.urlretrieve(
            f"http://images.cocodataset.org/train2017/{fn}", p)
        got += 1
    except Exception:
        miss += 1
    if (i + 1) % 100 == 0:
        print(f"  fetched {i+1}/{N} (ok={got} miss={miss})", flush=True)
print(f"[eval] images ready: ok={got} miss={miss}")
PY

for ck in results/v3/net2_v3_1/best.pt results/v3/net2/best.pt; do
    if [ ! -s "$ck" ]; then echo "[eval] MISSING $ck — skip"; continue; fi
    echo "===== EVAL $ck ====="
    python3 scripts/eval_net2_ap.py --checkpoint "$ck" \
        --coco-ann data/coco/annotations/coco_wholebody_val_v1.0.json \
        --coco-img data/coco/train2017 --limit "$N" --conf 0.5 \
        2>&1 | tee -a logs/eval_net2.log
done
touch .eval_done
echo "[eval] DONE $(date -u)"
