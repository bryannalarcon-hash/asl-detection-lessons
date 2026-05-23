"""Cached dataset: reads pre-decoded .npy images written by preprocess_cache.py.

Pairs with build_train_transform_v2 / build_val_transform_v2 in augment/transforms_v2.py
which omit JPEG decode and the initial resize (already done at cache time).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

from src.stage1.augment.transforms import apply_transform


class CachedKeypointDataset(Dataset):
    """Reads (.npy image, keypoints, visibility) tuples from a cache directory.

    Cache layout (written by preprocess_cache.py):
        {cache_root}/{name}/
            images/0000000.npy
            images/0000001.npy
            ...
            keypoints.npy   (N, 49, 2)
            visible.npy     (N, 49)
            meta.json
    """

    def __init__(
        self,
        cache_root: str | Path,
        name: str,
        transform,
        image_size: int,
    ) -> None:
        super().__init__()
        self.root = Path(cache_root) / name
        self.img_dir = self.root / "images"
        if not self.img_dir.exists():
            raise FileNotFoundError(f"cache not found: {self.img_dir}")
        self.keypoints = np.load(self.root / "keypoints.npy")  # (N, 49, 2)
        self.visible = np.load(self.root / "visible.npy")      # (N, 49) int8
        self.transform = transform
        self.image_size = image_size
        # Build the file list from what's actually on disk.
        self.files = sorted(self.img_dir.glob("*.npy"))

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, idx: int) -> dict:
        img = np.load(self.files[idx])  # (H, W, 3) uint8
        # The keypoints file was indexed by dataset-source index, which equals
        # the integer prefix of the npy filename.
        kp_idx = int(self.files[idx].stem)
        kp = self.keypoints[kp_idx]
        vis = self.visible[kp_idx].astype(np.int64)

        out = apply_transform(self.transform, img, kp, vis, self.image_size)
        image_tensor = torch.from_numpy(out["image"]).permute(2, 0, 1).float()
        return {
            "image": image_tensor,
            "keypoints": torch.from_numpy(out["keypoints"]).float(),
            "visible": torch.from_numpy(out["visible"]).float(),
        }


def gpu_render_heatmaps(
    keypoints: torch.Tensor,
    visible: torch.Tensor,
    image_size: int,
    heatmap_size: int,
    sigma: float = 2.0,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Render Gaussian heatmaps on the GPU.

    keypoints: (B, K, 2) in image-pixel coords (0..image_size)
    visible:   (B, K) float, 1 for visible, 0 for not
    Returns:
      heatmaps: (B, K, H, W)
      vis_mask: (B, K)
    """
    B, K, _ = keypoints.shape
    device = keypoints.device
    scale = heatmap_size / image_size
    coords = keypoints * scale  # (B, K, 2)

    ys = torch.arange(heatmap_size, device=device).view(1, 1, heatmap_size, 1)
    xs = torch.arange(heatmap_size, device=device).view(1, 1, 1, heatmap_size)
    cx = coords[..., 0:1].unsqueeze(-1)  # (B, K, 1, 1)
    cy = coords[..., 1:2].unsqueeze(-1)  # (B, K, 1, 1)

    heatmaps = torch.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * sigma * sigma))

    # Zero out invisible keypoints.
    heatmaps = heatmaps * visible.view(B, K, 1, 1)
    # Mask out keypoints that landed outside the heatmap.
    out_of_frame = (
        (coords[..., 0] < 0) | (coords[..., 0] >= heatmap_size)
        | (coords[..., 1] < 0) | (coords[..., 1] >= heatmap_size)
    )
    vis_mask = visible.clone()
    vis_mask[out_of_frame] = 0
    heatmaps = heatmaps * vis_mask.view(B, K, 1, 1)
    return heatmaps, vis_mask
