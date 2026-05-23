"""Time `_image_callback` (cache path) alone, no DALI.

Tells us if the bottleneck is callback Python work or DALI internals.
"""
import time, statistics, sys
sys.path.insert(0, ".")
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
loader = DALIDetectorLoader(
    coco=coco, frei=frei, hagrid=hagrid,
    input_size=192, batch_size=256, padding_frac=0.5,
    num_threads=8, prefetch=4, shuffle=True, drop_last=True, seed=42,
    use_box_encoder=False, pos_iou=0.5,
    cache_root=deep_get(cfg, "data.cache_root"),
)
# Warmup
for _ in range(5):
    loader._image_callback()
# Time callback alone
ts = []
for _ in range(30):
    t0 = time.perf_counter()
    imgs = loader._image_callback()
    ts.append((time.perf_counter() - t0) * 1000)
print(f"[callback only] median={statistics.median(ts):.2f}ms mean={statistics.mean(ts):.2f}ms p90={sorted(ts)[int(0.9*len(ts))]:.2f}ms n={len(ts)}")
print(f"[callback only] batch returned {len(imgs)} imgs, shape={imgs[0].shape} dtype={imgs[0].dtype}")
