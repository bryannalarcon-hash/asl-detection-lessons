"""Trigger box precomputation + pickle to data/net2_cache/box_precompute_*.pkl.

Idempotent — exits immediately if the cache file exists.
"""
import sys
sys.path.insert(0, ".")
from pathlib import Path
from src.common.v3_config import deep_get, load_v3_config
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.hagrid import HaGRIDDataset
from src.stage1.data.dali_pipelines import DALIDetectorLoader

cfg = load_v3_config("configs/stage1_v3_detector.yaml")
coco = CocoWholeBodyDataset(
    ann_file=deep_get(cfg, "data.coco_ann_file"),
    image_root=f"{deep_get(cfg, 'data.coco_root')}/{deep_get(cfg, 'data.coco_train_images')}",
)
frei = FreiHANDDataset(deep_get(cfg, "data.freihand_root"))
h_root = deep_get(cfg, "data.hagrid_root")
hagrid = HaGRIDDataset(h_root, split="train") if h_root else None
print(f"sources: coco={len(coco)}, freihand={len(frei)}, hagrid={len(hagrid) if hagrid else 0}", flush=True)
loader = DALIDetectorLoader(
    coco=coco, frei=frei, hagrid=hagrid,
    input_size=192, batch_size=256, padding_frac=0.5,
    num_threads=8, prefetch=4, shuffle=True, drop_last=True, seed=42,
    use_box_encoder=False, pos_iou=0.5,
    cache_root=deep_get(cfg, "data.cache_root"),
)
print(f"loader done; precomputed {len(loader._precomputed_ids):,} sample entries", flush=True)
