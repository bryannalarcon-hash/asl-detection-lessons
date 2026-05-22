"""GPU-side smoke test for the v3 pipeline.

Run this on the rented instance BEFORE any real training:
    python -u scripts/smoke_test_v3.py

Exercises (on synthetic in-memory tensors):
  - PalmDetector forward + backward
  - HandLandmarkNet forward + backward
  - kornia GPUAugmentation
  - AdaptiveWing + Focal losses
  - Anchor encode/decode/NMS

Total time: ~30 seconds. Catches torch/kornia mismatch + Blackwell driver
issues + per-network shape problems before we burn an hour of GPU on
malformed code.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.optim import AdamW

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.stage1.augment.transforms_v3 import GPUAugmentation
from src.stage1.losses_v3 import DetectorLoss, LandmarkLoss
from src.stage1.models.anchors import (
    decode_box, encode_box, get_anchors, nms, xywh_to_xyxy,
)
from src.stage1.models.landmark_net import HandLandmarkNet, count_params as count_p_lm
from src.stage1.models.palm_detector import PalmDetector, count_params as count_p_pd


def _device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def smoke_palm_detector(device: str) -> None:
    print("\n[Net 2] PalmDetector smoke ----------------------------------")
    model = PalmDetector().to(device)
    print(f"  params: {count_p_pd(model):,}")
    opt = AdamW(model.parameters(), lr=1e-3)
    loss_fn = DetectorLoss()
    B = 4
    img = torch.randn(B, 3, 192, 192, device=device)
    out = model(img)
    print(f"  cls shape: {out['cls'].shape}  box shape: {out['box'].shape}")

    # Build fake anchor targets: half positive, half negative.
    N = out["cls"].shape[1]
    cls_t = torch.zeros(B, N, dtype=torch.long, device=device)
    cls_t[:, :10] = 1
    box_t = torch.zeros(B, N, 4, device=device)
    losses = loss_fn(out["cls"], out["box"], cls_t, box_t)
    losses["loss"].backward()
    opt.step()
    print(f"  loss after 1 step: {losses['loss'].item():.4f}  ✓")


def smoke_landmark_net(device: str) -> None:
    print("\n[Net 3] HandLandmarkNet smoke -------------------------------")
    model = HandLandmarkNet().to(device)
    print(f"  params: {count_p_lm(model):,}")
    opt = AdamW(model.parameters(), lr=1e-3)
    loss_fn = LandmarkLoss()
    B = 4
    img = torch.randn(B, 3, 224, 224, device=device)
    out = model(img)
    print(f"  heatmap shape: {out.shape}")  # (B, 21, 56, 56)

    # Fake target: gaussian centered at random spots.
    H, W = out.shape[-2:]
    coords = torch.rand(B, 21, 2, device=device) * H  # heatmap-space coords
    vis = torch.ones(B, 21, device=device)
    ys = torch.arange(H, device=device).view(1, 1, H, 1).float()
    xs = torch.arange(W, device=device).view(1, 1, 1, W).float()
    gt_hm = torch.exp(
        -((xs - coords[..., 0:1, None]) ** 2 + (ys - coords[..., 1:2, None]) ** 2) / 8
    )
    losses = loss_fn(out, gt_hm, coords, vis, epoch=10)
    losses["loss"].backward()
    opt.step()
    print(f"  loss after 1 step: awing={losses['awing'].item():.4f}  "
          f"coord={losses['coord'].item():.4f}  ✓")


def smoke_gpu_aug(device: str) -> None:
    print("\n[GPU aug] kornia smoke -------------------------------------")
    try:
        aug = GPUAugmentation(image_size=224)
    except RuntimeError as e:
        print(f"  SKIP: {e}")
        return
    B = 4
    img = torch.rand(B, 3, 224, 224, device=device) * 2 - 1
    out, _ = aug(img)
    print(f"  in {img.shape} → out {out.shape}  ✓")


def smoke_anchors(device: str) -> None:
    print("\n[Anchors] encode/decode/NMS smoke ---------------------------")
    anchors = get_anchors(192)
    print(f"  anchors: {anchors.shape}")
    gt = np.array([[80, 80, 40, 40], [120, 60, 50, 50]], dtype=np.float32)
    encoded = encode_box(gt, anchors[:2])
    print(f"  encoded shape: {encoded.shape}")
    anchors_t = torch.from_numpy(anchors).to(device)
    deltas = torch.zeros_like(anchors_t)
    decoded = decode_box(deltas, anchors_t)
    boxes_xyxy = xywh_to_xyxy(decoded.cpu().numpy())
    scores = torch.rand(anchors_t.shape[0], device=device)
    keep = nms(torch.from_numpy(boxes_xyxy).to(device), scores, iou_threshold=0.3, top_k=10)
    print(f"  NMS kept: {keep.numel()}  ✓")


def main() -> None:
    device = _device()
    print(f"[smoke v3] device={device}")
    if device == "cuda":
        print(f"  gpu={torch.cuda.get_device_name(0)}")
    t0 = time.time()
    smoke_palm_detector(device)
    smoke_landmark_net(device)
    smoke_gpu_aug(device)
    smoke_anchors(device)
    print(f"\n[smoke v3] PASSED in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
