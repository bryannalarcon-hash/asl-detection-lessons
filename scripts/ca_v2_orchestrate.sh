#!/usr/bin/env bash
# Runs on the CA 4090. Pulls data, preprocesses to npy cache, runs v2 training.
set -e
cd /workspace/asl-learning
mkdir -p data/coco/annotations logs

echo "=== gdown COCO annotations ==="
( cd data/coco/annotations && gdown 1thErEToRbmM9uLNi1JXXfOsaS5VK2FXf -O coco_wholebody_train_v1.0.json )
python scripts/split_train_val.py \
  --in data/coco/annotations/coco_wholebody_train_v1.0.json \
  --train-out data/coco/annotations/coco_wholebody_train_v1.0.json \
  --val-out data/coco/annotations/coco_wholebody_val_v1.0.json

echo "=== COCO images ==="
( cd data/coco && wget -q -c http://images.cocodataset.org/zips/train2017.zip && unzip -q -o train2017.zip && rm train2017.zip )

echo "=== FreiHAND (kaggle) ==="
kaggle datasets download danieldelro/freihand -p data/ --unzip
mkdir -p data/FreiHAND_pub_v2
mv data/training* data/evaluation* data/FreiHAND_pub_v2/ 2>/dev/null || true

echo "=== ALL DATA READY ==="
ls data/coco/train2017 | wc -l
ls data/FreiHAND_pub_v2/ | head -5

echo "=== Preprocessing to npy cache ==="
python scripts/preprocess_cache.py --config configs/stage1_v2.yaml --out data/cache/stage1

echo "=== V2 training ==="
python -u -m src.stage1.train_v2 \
  --config configs/stage1_v2.yaml \
  --cache-root data/cache/stage1

echo "=== V2 done ==="
