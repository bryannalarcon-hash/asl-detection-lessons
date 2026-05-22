"""GPU-side smoke test. Run this AS THE FIRST THING on a rented instance,
before downloading datasets or kicking off a real training run.

Exercises the entire pipeline with synthetic in-memory data:
- Builds the model (verifies torch + CUDA work)
- Generates a few synthetic batches matching the dataset interface
- Runs a few forward/backward passes
- Verifies loss decreases and metrics compute without errors

Takes ~30 seconds. If it fails, do not proceed to data download or training.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import torch
from torch.optim import AdamW

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.stage1.data import schema as S
from src.stage1.losses import HeatmapMSELoss
from src.stage1.metrics import compute_pck
from src.stage1.models.detector import KeypointDetector, count_params, soft_argmax_2d


def _synthetic_batch(batch_size: int, image_size: int, heatmap_size: int,
                     num_kp: int, device: str) -> dict:
    """Random image + keypoints + heatmaps with consistent geometry."""
    image = torch.randn(batch_size, 3, image_size, image_size, device=device)
    # Random keypoints in image coords.
    keypoints = torch.rand(batch_size, num_kp, 2, device=device) * image_size
    visible = (torch.rand(batch_size, num_kp, device=device) > 0.2).float()

    # Heatmap target: gaussian at each visible keypoint, in heatmap coords.
    scale = heatmap_size / image_size
    hm = torch.zeros(batch_size, num_kp, heatmap_size, heatmap_size, device=device)
    ys = torch.arange(heatmap_size, device=device).view(1, 1, heatmap_size, 1)
    xs = torch.arange(heatmap_size, device=device).view(1, 1, 1, heatmap_size)
    sigma = 2.0
    for b in range(batch_size):
        for k in range(num_kp):
            if visible[b, k] < 0.5:
                continue
            cx = float(keypoints[b, k, 0]) * scale
            cy = float(keypoints[b, k, 1]) * scale
            hm[b, k] = torch.exp(
                -((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * sigma ** 2)
            )

    return {
        "image": image, "heatmaps": hm.squeeze(0) if False else hm,
        "visible": visible, "keypoints": keypoints,
    }


def main() -> None:
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    print(f"[smoke] device={device}")
    if device == "cuda":
        print(f"[smoke] gpu={torch.cuda.get_device_name(0)} "
              f"vram={torch.cuda.get_device_properties(0).total_memory/1e9:.1f}GB")

    image_size = 384
    heatmap_size = 96
    batch_size = 4

    model = KeypointDetector(num_keypoints=S.NUM_KEYPOINTS).to(device)
    print(f"[smoke] params={count_params(model):,}")

    loss_fn = HeatmapMSELoss()
    optimizer = AdamW(model.parameters(), lr=1e-3)

    losses = []
    model.train()
    t0 = time.time()
    for step in range(8):
        batch = _synthetic_batch(batch_size, image_size, heatmap_size,
                                 S.NUM_KEYPOINTS, device)
        optimizer.zero_grad(set_to_none=True)
        pred = model(batch["image"])
        assert pred.shape == (batch_size, S.NUM_KEYPOINTS, heatmap_size, heatmap_size), \
            f"unexpected output shape: {pred.shape}"
        loss = loss_fn(pred, batch["heatmaps"], batch["visible"])
        loss.backward()
        optimizer.step()
        losses.append(float(loss.item()))
        print(f"[smoke] step={step}  loss={loss.item():.6f}")
    elapsed = time.time() - t0
    print(f"[smoke] {len(losses)} steps in {elapsed:.1f}s "
          f"({elapsed / len(losses) * 1000:.0f}ms/step)")

    assert losses[-1] < losses[0] * 1.5, \
        f"loss did not move favorably: start={losses[0]} end={losses[-1]}"

    # Eval-mode metric path.
    model.eval()
    with torch.no_grad():
        batch = _synthetic_batch(batch_size, image_size, heatmap_size,
                                 S.NUM_KEYPOINTS, device)
        pred = model(batch["image"])
        m = compute_pck(pred, batch["keypoints"], batch["visible"],
                        image_size=image_size, heatmap_size=heatmap_size)
        print(f"[smoke] metrics: {m}")

        # soft-argmax sanity.
        sa = soft_argmax_2d(pred)
        assert sa.shape == (batch_size, S.NUM_KEYPOINTS, 2)
        assert torch.isfinite(sa).all()

    print("\n[smoke] PASSED — model, loss, metrics, optimizer all wire together.")


if __name__ == "__main__":
    main()
