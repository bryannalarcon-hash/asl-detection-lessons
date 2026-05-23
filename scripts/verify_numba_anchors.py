"""Verify numba anchor matcher matches numpy output element-by-element."""
import sys, time
sys.path.insert(0, ".")
import numpy as np
import torch
from src.stage1.models.anchors import get_anchors, match_anchors_to_gt, xywh_to_xyxy, encode_box
from src.stage1.models.anchors_numba import build_targets_numba

ANCHORS = get_anchors(192)
N = ANCHORS.shape[0]
pos_iou, neg_iou = 0.5, 0.4

def numpy_build(boxes_per_image):
    anchors_xyxy = xywh_to_xyxy(ANCHORS)
    B = len(boxes_per_image)
    cls = np.zeros((B, N), dtype=np.int64)
    boxr = np.zeros((B, N, 4), dtype=np.float32)
    for b, boxes in enumerate(boxes_per_image):
        if boxes.shape[0] == 0:
            continue
        gt_xywh = boxes.cpu().numpy() if hasattr(boxes, "cpu") else np.asarray(boxes)
        gt_xyxy = xywh_to_xyxy(gt_xywh)
        assignment, _ = match_anchors_to_gt(anchors_xyxy, gt_xyxy, pos_iou=pos_iou, neg_iou=neg_iou)
        row = np.zeros(N, dtype=np.int64)
        row[assignment == -2] = -1
        row[assignment >= 0] = 1
        pos_idx = np.where(assignment >= 0)[0]
        if pos_idx.size > 0:
            gt_for_pos = gt_xywh[assignment[pos_idx]]
            boxr[b, pos_idx] = encode_box(gt_for_pos, ANCHORS[pos_idx])
        cls[b] = row
    return cls, boxr

# Sample batch: 8 samples with mixed 0/1/2/3 boxes
rng = np.random.default_rng(123)
boxes_per_image = []
for _ in range(8):
    M = rng.integers(0, 4)
    if M == 0:
        boxes_per_image.append(torch.zeros((0, 4), dtype=torch.float32))
    else:
        b = rng.uniform(20, 150, size=(M, 4)).astype(np.float32)
        boxes_per_image.append(torch.from_numpy(b))

cls_np, box_np = numpy_build(boxes_per_image)
cls_nb, box_nb = build_targets_numba(boxes_per_image, ANCHORS, pos_iou=pos_iou, neg_iou=neg_iou)
cls_nb = cls_nb.numpy(); box_nb = box_nb.numpy()

ok = True
if not np.array_equal(cls_np, cls_nb):
    diff = np.sum(cls_np != cls_nb)
    print(f"FAIL cls mismatch: {diff} positions differ (out of {cls_np.size})")
    ok = False
else:
    print("PASS cls exact match")
if not np.allclose(box_np, box_nb, atol=1e-5):
    diff = np.abs(box_np - box_nb).max()
    print(f"FAIL box max diff = {diff}")
    ok = False
else:
    print("PASS box numerically equivalent")

# Timing
import statistics
ts_np = []
for _ in range(10):
    t0 = time.perf_counter()
    numpy_build(boxes_per_image)
    ts_np.append((time.perf_counter() - t0) * 1000)
ts_nb = []
for _ in range(10):
    t0 = time.perf_counter()
    build_targets_numba(boxes_per_image, ANCHORS, pos_iou=pos_iou, neg_iou=neg_iou)
    ts_nb.append((time.perf_counter() - t0) * 1000)
print(f"numpy: median={statistics.median(ts_np):.2f}ms")
print(f"numba: median={statistics.median(ts_nb):.2f}ms ({statistics.median(ts_np)/statistics.median(ts_nb):.1f}x speedup)")

# Also batch size 256
boxes_256 = boxes_per_image * 32
ts_nb_256 = []
for _ in range(5):
    t0 = time.perf_counter()
    build_targets_numba(boxes_256, ANCHORS, pos_iou=pos_iou, neg_iou=neg_iou)
    ts_nb_256.append((time.perf_counter() - t0) * 1000)
print(f"numba B=256: median={statistics.median(ts_nb_256):.2f}ms")
sys.exit(0 if ok else 1)
