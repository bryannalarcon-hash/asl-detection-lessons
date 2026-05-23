"""Combined dataset and heatmap target generation.

The unified dataset:
- Wraps COCO-WholeBody and FreiHAND loaders.
- Applies keypoint-aware augmentation.
- Generates Gaussian heatmaps at the configured heatmap resolution.
- Returns tensors ready for a training step.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

from src.stage1.augment.transforms import apply_transform
from src.stage1.data import schema as S


class UnifiedKeypointDataset(Dataset):
    """Concatenated source datasets emitting model-ready training tensors.

    Each source dataset must return:
      {image_path, keypoints (K,2), visible (K,)}.
    """

    def __init__(
        self,
        sources: list[Dataset],
        transform,
        image_size: int,
        heatmap_size: int,
        heatmap_sigma: float = 2.0,
    ) -> None:
        super().__init__()
        self.sources = sources
        self.transform = transform
        self.image_size = image_size
        self.heatmap_size = heatmap_size
        self.heatmap_sigma = heatmap_sigma
        self._lengths = [len(s) for s in sources]
        self._cumlen = np.cumsum(self._lengths).tolist()

    def __len__(self) -> int:
        return self._cumlen[-1] if self._cumlen else 0

    def _resolve(self, idx: int) -> tuple[Dataset, int]:
        for i, end in enumerate(self._cumlen):
            if idx < end:
                start = self._cumlen[i - 1] if i > 0 else 0
                return self.sources[i], idx - start
        raise IndexError(idx)

    def __getitem__(self, idx: int) -> dict:
        source, local_idx = self._resolve(idx)
        sample = source[local_idx]

        img = np.array(Image.open(sample["image_path"]).convert("RGB"))
        keypoints = sample["keypoints"]
        visible = sample["visible"]

        out = apply_transform(
            self.transform, img, keypoints, visible, self.image_size,
        )

        image_tensor = torch.from_numpy(out["image"]).permute(2, 0, 1).float()
        heatmaps, vis_mask = _generate_heatmaps(
            out["keypoints"], out["visible"],
            self.image_size, self.heatmap_size, self.heatmap_sigma,
        )

        return {
            "image": image_tensor,
            "heatmaps": heatmaps,
            "visible": vis_mask,
            "keypoints": torch.from_numpy(out["keypoints"]).float(),
        }


def _generate_heatmaps(
    keypoints: np.ndarray,
    visible: np.ndarray,
    image_size: int,
    heatmap_size: int,
    sigma: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Render Gaussian peaks at each visible keypoint.

    keypoints are in image-pixel coords (0..image_size). We downsample by
    image_size/heatmap_size to get heatmap-pixel coords.
    """
    K = keypoints.shape[0]
    scale = heatmap_size / image_size
    heatmaps = np.zeros((K, heatmap_size, heatmap_size), dtype=np.float32)
    vis_mask = np.zeros(K, dtype=np.float32)
    tmp_size = sigma * 3

    for k in range(K):
        if not visible[k]:
            continue
        x = keypoints[k, 0] * scale
        y = keypoints[k, 1] * scale
        if x < 0 or x >= heatmap_size or y < 0 or y >= heatmap_size:
            continue

        ul_x = int(np.floor(x - tmp_size))
        ul_y = int(np.floor(y - tmp_size))
        br_x = int(np.floor(x + tmp_size + 1))
        br_y = int(np.floor(y + tmp_size + 1))
        if ul_x >= heatmap_size or ul_y >= heatmap_size or br_x < 0 or br_y < 0:
            continue

        size = 2 * tmp_size + 1
        grid_x, grid_y = np.meshgrid(np.arange(size), np.arange(size))
        g = np.exp(-((grid_x - tmp_size) ** 2 + (grid_y - tmp_size) ** 2)
                   / (2 * sigma ** 2)).astype(np.float32)

        g_x_lo = max(0, -ul_x)
        g_y_lo = max(0, -ul_y)
        g_x_hi = min(int(size), heatmap_size - ul_x)
        g_y_hi = min(int(size), heatmap_size - ul_y)
        img_x_lo = max(0, ul_x)
        img_y_lo = max(0, ul_y)
        img_x_hi = min(heatmap_size, br_x)
        img_y_hi = min(heatmap_size, br_y)

        # Defensive: when float→int rounding diverges between bounds,
        # the dest slice can be 1px wider/taller than the src slice.
        # Take the min of both to guarantee a valid assignment.
        dst_h = img_y_hi - img_y_lo
        dst_w = img_x_hi - img_x_lo
        src = g[g_y_lo:g_y_hi, g_x_lo:g_x_hi]
        h = min(dst_h, src.shape[0])
        w = min(dst_w, src.shape[1])
        if h <= 0 or w <= 0:
            continue
        heatmaps[k, img_y_lo:img_y_lo + h, img_x_lo:img_x_lo + w] = src[:h, :w]
        vis_mask[k] = 1.0

    return torch.from_numpy(heatmaps), torch.from_numpy(vis_mask)
