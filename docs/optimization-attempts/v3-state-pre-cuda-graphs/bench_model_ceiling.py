"""Find the per-batch model+loss ceiling — what is the GPU actually capable of?

Feeds synthetic zero tensors directly to the model (skipping data loading
entirely). Measures forward + loss + backward + optimizer step.

Compares against observed training throughput to isolate where the real
bottleneck lives:
  - If model ceiling ≈ observed → we're model-bound (DALI did all it can)
  - If model ceiling >> observed → we're data-bound or CPU-bound (anchor
    matching, kornia aug, DALI overhead, _build_targets, etc.)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np
import torch
from torch.optim import AdamW
from torch.optim.swa_utils import AveragedModel, get_ema_multi_avg_fn


def bench_detector(batch_size: int, input_size: int, n_steps: int,
                   include_anchor_matching: bool) -> dict:
    """Net 2: PalmDetector + DetectorLoss + (optional) anchor matching."""
    from src.stage1.models.palm_detector import PalmDetector
    from src.stage1.losses_v3 import DetectorLoss
    from src.stage1.models.anchors import get_anchors, match_anchors_to_gt, xywh_to_xyxy, encode_box

    device = "cuda"
    model = PalmDetector(n_anchors_per_cell=3, n_aux_kpts=0).to(device)
    loss_fn = DetectorLoss(alpha=0.25, gamma=2.0, box_weight=1.0, beta=0.11)
    optimizer = AdamW(model.parameters(), lr=5e-4, weight_decay=1e-4)
    ema = AveragedModel(model, multi_avg_fn=get_ema_multi_avg_fn(0.9998))
    scaler = torch.amp.GradScaler(device=device)
    anchors_xywh = get_anchors(input_size)
    n_anchors = anchors_xywh.shape[0]

    # Fake input + fake targets (cls/box already encoded — skip _build_targets unless asked).
    x = torch.zeros(batch_size, 3, input_size, input_size, device=device)
    cls_t = torch.zeros(batch_size, n_anchors, dtype=torch.long, device=device)
    cls_t[:, :10] = 1  # pretend 10 anchors per sample are positive
    box_t = torch.zeros(batch_size, n_anchors, 4, dtype=torch.float, device=device)

    # Optional: simulate per-step anchor matching cost (the _build_targets work).
    anchors_xyxy = xywh_to_xyxy(anchors_xywh)
    fake_gts_per_sample = [np.array([[100, 100, 50, 50]], dtype=np.float32)] * batch_size

    # Warmup
    for _ in range(5):
        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
            out = model(x)
            losses = loss_fn(out["cls"], out["box"], cls_t, box_t)
        scaler.scale(losses["loss"]).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(optimizer); scaler.update()
        ema.update_parameters(model)
    torch.cuda.synchronize()

    t0 = time.time()
    for _ in range(n_steps):
        if include_anchor_matching:
            cls_arr = np.zeros((batch_size, n_anchors), dtype=np.int64)
            box_arr = np.zeros((batch_size, n_anchors, 4), dtype=np.float32)
            for b in range(batch_size):
                gt_xywh = fake_gts_per_sample[b]
                gt_xyxy = xywh_to_xyxy(gt_xywh)
                assignment, _ = match_anchors_to_gt(anchors_xyxy, gt_xyxy,
                                                    pos_iou=0.5, neg_iou=0.4)
                cls_arr[b, assignment >= 0] = 1
                pos = np.where(assignment >= 0)[0]
                if pos.size > 0:
                    box_arr[b, pos] = encode_box(gt_xywh[assignment[pos]], anchors_xywh[pos])
            cls_t_l = torch.from_numpy(cls_arr).to(device)
            box_t_l = torch.from_numpy(box_arr).to(device)
        else:
            cls_t_l, box_t_l = cls_t, box_t

        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
            out = model(x)
            losses = loss_fn(out["cls"], out["box"], cls_t_l, box_t_l)
        scaler.scale(losses["loss"]).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(optimizer); scaler.update()
        ema.update_parameters(model)
    torch.cuda.synchronize()
    elapsed = time.time() - t0
    return {
        "name": f"Net 2 detector (anchor_match={include_anchor_matching})",
        "it_per_sec": n_steps / elapsed,
        "samples_per_sec": (n_steps * batch_size) / elapsed,
        "ms_per_batch": elapsed * 1000 / n_steps,
        "elapsed": elapsed,
    }


def bench_landmark(batch_size: int, crop_size: int, hm_size: int, n_steps: int,
                   include_kornia_aug: bool) -> dict:
    """Net 3: HandLandmarkNet + LandmarkLoss + (optional) kornia GPU aug."""
    from src.stage1.models.landmark_net import HandLandmarkNet
    from src.stage1.losses_v3 import LandmarkLoss
    from src.stage1.augment.transforms_v3 import GPUAugmentation
    from src.stage1.train_v3_landmark import _gpu_render_heatmaps

    device = "cuda"
    model = HandLandmarkNet(num_keypoints=21, heatmap_channels=128).to(device)
    loss_fn = LandmarkLoss(awing_alpha=2.1, awing_omega=14.0, awing_epsilon=1.0,
                           awing_theta=0.5, coord_weight=0.1, coord_ramp_epochs=5)
    optimizer = AdamW(model.parameters(), lr=5e-4, weight_decay=1e-4)
    ema = AveragedModel(model, multi_avg_fn=get_ema_multi_avg_fn(0.9998))
    scaler = torch.amp.GradScaler(device=device)
    gpu_aug = GPUAugmentation(image_size=crop_size) if include_kornia_aug else None

    image = torch.zeros(batch_size, 3, crop_size, crop_size, device=device)
    coords = torch.rand(batch_size, 21, 2, device=device) * crop_size
    visible = torch.ones(batch_size, 21, device=device)

    # Warmup
    for _ in range(5):
        if gpu_aug is not None:
            with torch.no_grad():
                x_aug, c_aug = gpu_aug(image, coords)
                if c_aug is None: c_aug = coords
                hm, vis_mask, c_hm = _gpu_render_heatmaps(c_aug, visible, crop_size, hm_size, 2.0)
        else:
            x_aug, c_aug, vis_mask = image, coords, visible
            hm, _, c_hm = _gpu_render_heatmaps(c_aug, visible, crop_size, hm_size, 2.0)
        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
            pred = model(x_aug)
            out = loss_fn(pred, hm, c_hm, vis_mask, epoch=10)
        scaler.scale(out["loss"]).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(optimizer); scaler.update()
        ema.update_parameters(model)
    torch.cuda.synchronize()

    t0 = time.time()
    for _ in range(n_steps):
        if gpu_aug is not None:
            with torch.no_grad():
                x_aug, c_aug = gpu_aug(image, coords)
                if c_aug is None: c_aug = coords
                hm, vis_mask, c_hm = _gpu_render_heatmaps(c_aug, visible, crop_size, hm_size, 2.0)
        else:
            x_aug, c_aug, vis_mask = image, coords, visible
            hm, _, c_hm = _gpu_render_heatmaps(c_aug, visible, crop_size, hm_size, 2.0)
        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
            pred = model(x_aug)
            out = loss_fn(pred, hm, c_hm, vis_mask, epoch=10)
        scaler.scale(out["loss"]).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(optimizer); scaler.update()
        ema.update_parameters(model)
    torch.cuda.synchronize()
    elapsed = time.time() - t0
    return {
        "name": f"Net 3 landmark (kornia_aug={include_kornia_aug})",
        "it_per_sec": n_steps / elapsed,
        "samples_per_sec": (n_steps * batch_size) / elapsed,
        "ms_per_batch": elapsed * 1000 / n_steps,
        "elapsed": elapsed,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=100)
    ap.add_argument("--net2-batch", type=int, default=256)
    ap.add_argument("--net2-input", type=int, default=192)
    ap.add_argument("--net3-batch", type=int, default=128)
    ap.add_argument("--net3-crop", type=int, default=224)
    ap.add_argument("--net3-hm", type=int, default=56)
    args = ap.parse_args()

    print(f"\n=== Net 2 model ceiling (batch={args.net2_batch}, input={args.net2_input}) ===")
    r1 = bench_detector(args.net2_batch, args.net2_input, args.steps, False)
    print(f"  no anchor matching:  {r1['it_per_sec']:6.1f} it/s  ({r1['ms_per_batch']:.1f} ms/batch, {r1['samples_per_sec']:.0f} samples/sec)")
    r2 = bench_detector(args.net2_batch, args.net2_input, args.steps, True)
    print(f"  + anchor matching:   {r2['it_per_sec']:6.1f} it/s  ({r2['ms_per_batch']:.1f} ms/batch, {r2['samples_per_sec']:.0f} samples/sec)")
    print(f"  anchor matching cost: {r2['ms_per_batch'] - r1['ms_per_batch']:.1f} ms/batch")

    print(f"\n=== Net 3 model ceiling (batch={args.net3_batch}, crop={args.net3_crop}) ===")
    r3 = bench_landmark(args.net3_batch, args.net3_crop, args.net3_hm, args.steps, False)
    print(f"  no kornia aug:       {r3['it_per_sec']:6.1f} it/s  ({r3['ms_per_batch']:.1f} ms/batch, {r3['samples_per_sec']:.0f} samples/sec)")
    r4 = bench_landmark(args.net3_batch, args.net3_crop, args.net3_hm, args.steps, True)
    print(f"  + kornia aug:        {r4['it_per_sec']:6.1f} it/s  ({r4['ms_per_batch']:.1f} ms/batch, {r4['samples_per_sec']:.0f} samples/sec)")
    print(f"  kornia aug cost:     {r4['ms_per_batch'] - r3['ms_per_batch']:.1f} ms/batch")

    print(f"\n=== Comparison vs observed training ===")
    print(f"  Net 2 observed (DALI):    ~10 it/s × {args.net2_batch} = ~{args.net2_batch * 10} samples/sec")
    print(f"  Net 2 model ceiling:      {r2['it_per_sec']:.1f} it/s — gap = {r2['it_per_sec']/10:.1f}× more capacity")
    print(f"  Net 3 observed (DALI):    ~15 it/s × {args.net3_batch} = ~{args.net3_batch * 15} samples/sec")
    print(f"  Net 3 model ceiling:      {r4['it_per_sec']:.1f} it/s — gap = {r4['it_per_sec']/15:.1f}× more capacity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
