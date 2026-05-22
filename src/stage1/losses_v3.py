"""v3 loss functions.

Two heads:
- Detector losses (focal classification + smooth-L1 box regression) for Net 2
- Landmark losses (Adaptive Wing + soft-argmax L1 + per-group weights) for Net 3
"""
from __future__ import annotations

import torch
from torch import nn


# --------------------------------------------------------------------------
# Net 2 — detection losses
# --------------------------------------------------------------------------

class FocalClassificationLoss(nn.Module):
    """Focal loss for the single-class palm detector.

    For each anchor: target ∈ {0 (negative), 1 (positive), -1 (ignore)}.
    Positives use focal-weighted BCE; negatives also use focal-weighted BCE
    on logit; ignored anchors contribute 0.
    """

    def __init__(self, alpha: float = 0.25, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, cls_logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # cls_logits: (B, N), targets: (B, N) with values -1 / 0 / 1
        valid = targets >= 0
        cls = cls_logits[valid]
        tgt = targets[valid].float()
        p = torch.sigmoid(cls)
        ce = torch.nn.functional.binary_cross_entropy_with_logits(cls, tgt, reduction="none")
        p_t = p * tgt + (1 - p) * (1 - tgt)
        alpha_t = self.alpha * tgt + (1 - self.alpha) * (1 - tgt)
        focal = alpha_t * (1 - p_t) ** self.gamma * ce
        # Normalize by number of positive anchors as in the focal-loss paper.
        n_pos = (targets == 1).sum().clamp(min=1).float()
        return focal.sum() / n_pos


class SmoothL1BoxLoss(nn.Module):
    """Smooth-L1 on box deltas, computed only over positive anchors."""

    def __init__(self, beta: float = 0.11):
        super().__init__()
        self.beta = beta

    def forward(self, box_pred: torch.Tensor, box_target: torch.Tensor,
                pos_mask: torch.Tensor) -> torch.Tensor:
        # box_pred / box_target: (B, N, 4); pos_mask: (B, N) bool
        if pos_mask.sum() == 0:
            return box_pred.sum() * 0.0
        diff = (box_pred - box_target).abs()
        loss = torch.where(diff < self.beta,
                           0.5 * diff ** 2 / self.beta,
                           diff - 0.5 * self.beta)
        loss = loss[pos_mask]
        return loss.mean()


class DetectorLoss(nn.Module):
    """Combined focal cls + smooth-L1 box."""

    def __init__(self, alpha: float = 0.25, gamma: float = 2.0,
                 box_weight: float = 1.0, beta: float = 0.11):
        super().__init__()
        self.focal = FocalClassificationLoss(alpha=alpha, gamma=gamma)
        self.box = SmoothL1BoxLoss(beta=beta)
        self.box_weight = box_weight

    def forward(self, cls_logits: torch.Tensor, box_pred: torch.Tensor,
                cls_target: torch.Tensor, box_target: torch.Tensor) -> dict[str, torch.Tensor]:
        # cls_target: (B, N) with -1/0/1, box_target: (B, N, 4)
        pos = cls_target == 1
        cls_loss = self.focal(cls_logits, cls_target)
        box_loss = self.box(box_pred, box_target, pos)
        total = cls_loss + self.box_weight * box_loss
        return {"loss": total, "cls": cls_loss.detach(), "box": box_loss.detach()}


# --------------------------------------------------------------------------
# Net 3 — landmark losses
# --------------------------------------------------------------------------

class AdaptiveWingLoss(nn.Module):
    """Adaptive Wing Loss for heatmap regression.

    Wang et al. 2019 — smooth Wing penalty near GT peaks, MSE-like elsewhere.
    Better than vanilla MSE for fine-keypoint localization (fingertips).
    """

    def __init__(self, alpha: float = 2.1, omega: float = 14.0,
                 epsilon: float = 1.0, theta: float = 0.5):
        super().__init__()
        self.alpha = alpha
        self.omega = omega
        self.epsilon = epsilon
        self.theta = theta

    def forward(self, pred: torch.Tensor, target: torch.Tensor,
                vis_mask: torch.Tensor) -> torch.Tensor:
        # pred, target: (B, K, H, W); vis_mask: (B, K)
        diff = (pred - target).abs()
        # Region 1: diff < theta  →  smooth Wing
        # Region 2: diff >= theta →  near-linear C2 extension
        A = self.omega * (1 / (1 + (self.theta / self.epsilon) ** (self.alpha - target))) \
            * (self.alpha - target) * ((self.theta / self.epsilon) ** (self.alpha - target - 1)) \
            * (1 / self.epsilon)
        C = self.theta * A - self.omega * torch.log(
            1 + (self.theta / self.epsilon) ** (self.alpha - target)
        )
        loss_inner = self.omega * torch.log(
            1 + (diff / self.epsilon) ** (self.alpha - target)
        )
        loss_outer = A * diff - C
        per_pixel = torch.where(diff < self.theta, loss_inner, loss_outer)
        per_kp = per_pixel.mean(dim=(-1, -2))            # (B, K)
        weighted = per_kp * vis_mask
        n_visible = vis_mask.sum().clamp(min=1.0)
        return weighted.sum() / n_visible


class SoftArgmaxCoordLoss(nn.Module):
    """Auxiliary L1 between soft-argmax of predicted heatmaps and GT coords."""

    def __init__(self, temperature: float = 10.0):
        super().__init__()
        self.temperature = temperature

    def forward(self, heatmaps: torch.Tensor, gt_coords: torch.Tensor,
                vis_mask: torch.Tensor) -> torch.Tensor:
        B, K, H, W = heatmaps.shape
        flat = heatmaps.view(B, K, -1)
        flat = flat - flat.max(dim=-1, keepdim=True).values
        probs = torch.softmax(flat * self.temperature, dim=-1).view(B, K, H, W)
        ys = torch.arange(H, device=heatmaps.device, dtype=heatmaps.dtype)
        xs = torch.arange(W, device=heatmaps.device, dtype=heatmaps.dtype)
        grid_y, grid_x = torch.meshgrid(ys, xs, indexing="ij")
        coord_x = (probs * grid_x[None, None]).sum(dim=(-1, -2))
        coord_y = (probs * grid_y[None, None]).sum(dim=(-1, -2))
        pred = torch.stack([coord_x, coord_y], dim=-1)   # (B, K, 2)
        diff = (pred - gt_coords).abs().sum(dim=-1)      # (B, K)
        weighted = diff * vis_mask
        n_visible = vis_mask.sum().clamp(min=1.0)
        return weighted.sum() / n_visible


class LandmarkLoss(nn.Module):
    """Composite Net 3 loss: AdaptiveWing + λ × soft-argmax L1.

    Soft-argmax weight ramps from 0 → λ_final over the first ramp_epochs.
    """

    def __init__(self, awing_alpha: float = 2.1, awing_omega: float = 14.0,
                 awing_epsilon: float = 1.0, awing_theta: float = 0.5,
                 coord_weight: float = 0.1, coord_ramp_epochs: int = 5,
                 coord_temperature: float = 10.0):
        super().__init__()
        self.awing = AdaptiveWingLoss(awing_alpha, awing_omega, awing_epsilon, awing_theta)
        self.coord = SoftArgmaxCoordLoss(coord_temperature)
        self.coord_weight = coord_weight
        self.coord_ramp_epochs = coord_ramp_epochs

    def coord_lambda(self, epoch: int) -> float:
        if epoch < self.coord_ramp_epochs:
            return self.coord_weight * (epoch / max(self.coord_ramp_epochs, 1))
        return self.coord_weight

    def forward(self, pred_heatmaps: torch.Tensor, gt_heatmaps: torch.Tensor,
                gt_coords_hm: torch.Tensor, vis_mask: torch.Tensor,
                epoch: int = 0) -> dict[str, torch.Tensor]:
        # gt_coords_hm: (B, K, 2) in HEATMAP coords (not image coords).
        awing = self.awing(pred_heatmaps, gt_heatmaps, vis_mask)
        coord = self.coord(pred_heatmaps, gt_coords_hm, vis_mask)
        lam = self.coord_lambda(epoch)
        total = awing + lam * coord
        return {"loss": total, "awing": awing.detach(), "coord": coord.detach(),
                "coord_lambda": torch.tensor(lam)}
