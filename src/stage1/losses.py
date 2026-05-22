"""Loss functions for heatmap-based keypoint detection."""
from __future__ import annotations

import torch
from torch import nn


class HeatmapMSELoss(nn.Module):
    """Per-keypoint MSE, masked by visibility.

    Loss = mean over visible keypoints of MSE between predicted and target
    heatmap pixels. Invisible keypoints contribute zero gradient.
    """

    def __init__(self) -> None:
        super().__init__()

    def forward(self, pred: torch.Tensor, target: torch.Tensor,
                vis_mask: torch.Tensor) -> torch.Tensor:
        # pred, target: (B, K, H, W); vis_mask: (B, K)
        B, K, H, W = pred.shape
        per_kp = ((pred - target) ** 2).mean(dim=(-1, -2))  # (B, K)
        weighted = per_kp * vis_mask
        n_visible = vis_mask.sum().clamp(min=1.0)
        return weighted.sum() / n_visible
