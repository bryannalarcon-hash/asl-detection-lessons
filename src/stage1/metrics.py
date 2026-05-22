"""PCK (Percentage of Correct Keypoints) for pose estimation."""
from __future__ import annotations

import torch

from src.stage1.data import schema as S
from src.stage1.models.detector import soft_argmax_2d


def pck_at_threshold(
    pred_coords: torch.Tensor,
    gt_coords: torch.Tensor,
    vis_mask: torch.Tensor,
    threshold_px: float,
) -> torch.Tensor:
    """Per-keypoint PCK: fraction of visible kp predictions within threshold.

    Returns a tensor of shape (K,) with the PCK for each keypoint over the
    batch dim. Use compute_pck for aggregated subgroup scores.
    """
    diffs = (pred_coords - gt_coords).norm(dim=-1)  # (B, K)
    correct = (diffs <= threshold_px).float()  # (B, K)
    weighted = correct * vis_mask
    counts = vis_mask.sum(dim=0).clamp(min=1.0)
    return weighted.sum(dim=0) / counts


def compute_pck(
    pred_heatmaps: torch.Tensor,
    gt_coords_image: torch.Tensor,
    vis_mask: torch.Tensor,
    image_size: int,
    heatmap_size: int,
    threshold_frac: float = 0.05,
) -> dict[str, float]:
    """Compute PCK in image-pixel space, grouped by body region.

    pred_heatmaps: (B, K, hm_H, hm_W)
    gt_coords_image: (B, K, 2) in 0..image_size
    vis_mask: (B, K)
    threshold_frac: PCK threshold as a fraction of image_size (0.05 = "PCK@0.05")
    """
    # Predict in heatmap coords, then rescale to image coords.
    pred_hm = soft_argmax_2d(pred_heatmaps)  # (B, K, 2)
    scale = image_size / heatmap_size
    pred_image = pred_hm * scale

    threshold_px = threshold_frac * image_size
    per_kp = pck_at_threshold(pred_image, gt_coords_image, vis_mask, threshold_px)

    return {
        "pck_overall": float(per_kp.mean().item()),
        "pck_hands": float(per_kp[S.HAND_INDICES_RIGHT + S.HAND_INDICES_LEFT].mean().item()),
        "pck_face": float(per_kp[S.FACE_INDICES].mean().item()),
        "pck_body": float(per_kp[S.BODY_INDICES].mean().item()),
    }
