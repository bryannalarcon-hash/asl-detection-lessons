"""Break down `_image_callback` into resolve / sample-load / cache-lookup / memcpy / boxes."""
import time, statistics, sys
import numpy as np
sys.path.insert(0, ".")
from src.common.v3_config import deep_get, load_v3_config
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.hagrid import HaGRIDDataset, hagrid_bboxes_to_pixel
from src.stage1.data.dali_pipelines import DALIDetectorLoader, _normalize_bbox_to_input
from src.stage1.data.palm_boxes import palm_bbox_for_each_hand

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

# Build a static list of 256 random indices for repeatable bench
rng = np.random.default_rng(0)
N = len(loader)
test_idxs = rng.integers(0, N, size=256).tolist()

# Single-thread loops — gives us per-sample cost without thread contention
def time_part(label, fn, repeats=10):
    ts = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        for i in test_idxs:
            fn(i)
        ts.append((time.perf_counter() - t0) * 1000)
    return f"  {label:<22} median={statistics.median(ts):6.2f}ms  mean={statistics.mean(ts):6.2f}ms"

def part_resolve(i):
    return loader._resolve(int(i))
def part_resolve_src(i):
    return loader._resolve_src_idx(int(i))
def part_sample_load(i):
    src, local = loader._resolve(int(i))
    return src[local]
def part_cache_lookup(i):
    src, local = loader._resolve(int(i))
    sample = src[local]
    path = str(sample["image_path"])
    src_i, _ = loader._resolve_src_idx(int(i))
    cache = loader._caches.get(src_i)
    decoded = None
    if cache:
        decoded = cache.get(path)
    return decoded
def part_memcpy(i):
    src, local = loader._resolve(int(i))
    sample = src[local]
    path = str(sample["image_path"])
    src_i, _ = loader._resolve_src_idx(int(i))
    cache = loader._caches.get(src_i)
    if cache:
        decoded = cache.get(path)
        if decoded:
            return np.ascontiguousarray(decoded[0])
    return None
def part_full(i):
    return loader._prepare_one_decoded(i)

print("Per-batch (256 samples) cost, single-threaded:")
print(time_part("resolve", part_resolve))
print(time_part("resolve_src_idx", part_resolve_src))
print(time_part("sample_load", part_sample_load))
print(time_part("cache_lookup", part_cache_lookup))
print(time_part("memcpy", part_memcpy))
print(time_part("prepare_one_decoded", part_full))

# Now time _image_callback itself which uses ThreadPool
ts = []
for _ in range(15):
    t0 = time.perf_counter()
    imgs = loader._image_callback()
    ts.append((time.perf_counter() - t0) * 1000)
print(f"\n[image_callback (8-thread)] median={statistics.median(ts):.2f}ms mean={statistics.mean(ts):.2f}ms")
