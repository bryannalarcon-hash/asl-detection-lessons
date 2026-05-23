"""Manually time each section of the Net 2 train loop for 100 iters.

Run: python3 -m scripts.profile_v3_detector --config configs/stage1_v3_detector.yaml
"""
import argparse, time, statistics
from pathlib import Path

import numpy as np
import torch
from torch.optim import AdamW

from src.common.seed import set_seed
from src.common.v3_config import deep_get, load_v3_config
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.hagrid import HaGRIDDataset
from src.stage1.losses_v3 import DetectorLoss
from src.stage1.models.anchors import (
    encode_box, get_anchors, match_anchors_to_gt, xywh_to_xyxy,
)
from src.stage1.models.palm_detector import PalmDetector


def _build_targets(boxes_per_image, anchors_xywh, pos_iou, neg_iou):
    anchors_xyxy = xywh_to_xyxy(anchors_xywh)
    N = anchors_xywh.shape[0]
    batch = len(boxes_per_image)
    cls = np.zeros((batch, N), dtype=np.int64)
    boxr = np.zeros((batch, N, 4), dtype=np.float32)
    for b, boxes in enumerate(boxes_per_image):
        if boxes.shape[0] == 0:
            cls[b] = 0
            continue
        gt_xywh = boxes.cpu().numpy()
        gt_xyxy = xywh_to_xyxy(gt_xywh)
        assignment, _ = match_anchors_to_gt(anchors_xyxy, gt_xyxy, pos_iou=pos_iou, neg_iou=neg_iou)
        cls_row = np.zeros(N, dtype=np.int64)
        cls_row[assignment == -2] = -1
        cls_row[assignment >= 0] = 1
        pos_idx = np.where(assignment >= 0)[0]
        if pos_idx.size > 0:
            gt_for_pos = gt_xywh[assignment[pos_idx]]
            boxr[b, pos_idx] = encode_box(gt_for_pos, anchors_xywh[pos_idx])
        cls[b] = cls_row
    return torch.from_numpy(cls), torch.from_numpy(boxr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--iters", type=int, default=100)
    args = p.parse_args()
    cfg = load_v3_config(args.config)
    set_seed(deep_get(cfg, "train.seed", 42))
    device = "cuda"

    coco = CocoWholeBodyDataset(
        ann_file=deep_get(cfg, "data.coco_ann_file"),
        image_root=f"{deep_get(cfg, 'data.coco_root')}/{deep_get(cfg, 'data.coco_train_images')}",
    )
    frei = FreiHANDDataset(deep_get(cfg, "data.freihand_root"))
    h_root = deep_get(cfg, "data.hagrid_root")
    hagrid = HaGRIDDataset(h_root, split="train") if h_root and (Path(h_root)/"annotations"/"train.json").exists() else None

    from src.stage1.data.dali_pipelines import DALIDetectorLoader
    loader = DALIDetectorLoader(
        coco=coco, frei=frei, hagrid=hagrid,
        input_size=deep_get(cfg, "data.input_size"),
        batch_size=deep_get(cfg, "train.batch_size"),
        padding_frac=deep_get(cfg, "data.padding_frac"),
        num_threads=min(8, deep_get(cfg, "train.num_workers", 8)),
        prefetch=4, shuffle=True, drop_last=True,
        seed=deep_get(cfg, "train.seed", 42),
        use_box_encoder=False,
        pos_iou=deep_get(cfg, "anchors.pos_iou", 0.5),
        cache_root=deep_get(cfg, "data.cache_root"),
    )

    model = PalmDetector(
        n_anchors_per_cell=deep_get(cfg, "model.n_anchors_per_cell", 3),
        n_aux_kpts=deep_get(cfg, "model.n_aux_kpts", 0),
    ).to(device)
    loss_fn = DetectorLoss(
        alpha=deep_get(cfg, "loss.focal_alpha", 0.25),
        gamma=deep_get(cfg, "loss.focal_gamma", 2.0),
        box_weight=deep_get(cfg, "loss.box_weight", 1.0),
        beta=deep_get(cfg, "loss.smoothl1_beta", 0.11),
    )
    optimizer = AdamW(model.parameters(), lr=5e-4, weight_decay=0.0)

    anchors_xywh = get_anchors(deep_get(cfg, "data.input_size"))
    pos_iou = deep_get(cfg, "anchors.pos_iou", 0.5)
    neg_iou = deep_get(cfg, "anchors.neg_iou", 0.4)

    torch.backends.cudnn.benchmark = True
    model.train()

    # Use numba for the anchor matching profile
    from src.stage1.models.anchors_numba import build_targets_numba, warmup as nbwarmup
    nbwarmup(input_size=192)

    # warmup
    dali_iter = iter(loader)
    for _ in range(15):
        batch = next(dali_iter)
        image = batch["image"]
        cls_t, box_t = build_targets_numba(batch["boxes"], anchors_xywh, pos_iou, neg_iou)
        cls_t = cls_t.to(device); box_t = box_t.to(device)
        with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
            out = model(image)
            l = loss_fn(out["cls"], out["box"], cls_t, box_t)
        l["loss"].backward()
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
    torch.cuda.synchronize()

    t_fetch = []
    t_match = []
    t_h2d = []
    t_fwd = []
    t_bwd = []
    t_opt = []
    t_total = []
    iter_start = time.perf_counter()

    for i in range(args.iters):
        torch.cuda.synchronize()
        t0 = time.perf_counter()

        batch = next(dali_iter)
        image = batch["image"]
        torch.cuda.synchronize()
        t1 = time.perf_counter()

        cls_t, box_t = build_targets_numba(batch["boxes"], anchors_xywh, pos_iou, neg_iou)
        t2 = time.perf_counter()

        cls_t = cls_t.to(device, non_blocking=True)
        box_t = box_t.to(device, non_blocking=True)
        torch.cuda.synchronize()
        t3 = time.perf_counter()

        with torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16):
            out = model(image)
            l = loss_fn(out["cls"], out["box"], cls_t, box_t)
        torch.cuda.synchronize()
        t4 = time.perf_counter()

        l["loss"].backward()
        torch.cuda.synchronize()
        t5 = time.perf_counter()

        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        torch.cuda.synchronize()
        t6 = time.perf_counter()

        t_fetch.append((t1 - t0) * 1000)
        t_match.append((t2 - t1) * 1000)
        t_h2d.append((t3 - t2) * 1000)
        t_fwd.append((t4 - t3) * 1000)
        t_bwd.append((t5 - t4) * 1000)
        t_opt.append((t6 - t5) * 1000)
        t_total.append((t6 - t0) * 1000)

    elapsed = time.perf_counter() - iter_start
    its = args.iters / elapsed
    def stats(name, arr):
        return f"  {name:<8} median={statistics.median(arr):6.2f}ms  mean={statistics.mean(arr):6.2f}ms  p90={sorted(arr)[int(0.9*len(arr))]:6.2f}ms  total={sum(arr):.1f}ms"
    print(f"[profile] {args.iters} iters in {elapsed:.2f}s = {its:.2f} it/s")
    print(stats("fetch", t_fetch))
    print(stats("match", t_match))
    print(stats("h2d", t_h2d))
    print(stats("fwd", t_fwd))
    print(stats("bwd", t_bwd))
    print(stats("opt", t_opt))
    print(stats("TOTAL", t_total))

if __name__ == "__main__":
    main()
