"""Net 3 regression loss — direct coordinate regression (BlazeHand-style).

Pairs with ``HandLandmarkRegNet``. The model predicts normalized [0, 1] crop
coordinates directly (no heatmaps), so the loss is a masked smooth-L1 (or Wing)
on the xy coordinates, with optional z and presence terms.

All masking is multiplicative (no boolean indexing) so the loss is
CUDA-Graphs-capture-safe, matching the convention in ``losses_v3.py``.
"""
from __future__ import annotations

import torch
from torch import nn


class RegressionLandmarkLoss(nn.Module):
    """Masked smooth-L1 / Wing on regressed keypoint coords.

    Components:
      xy        : masked (smooth-L1 | wing) on normalized [0, 1] xy, weighted
                  per-keypoint (fingertips heavier) via ``keypoint_weights``.
      z         : masked smooth-L1 on z, scaled by ``z_weight`` (default 0 →
                  z is unsupervised; the term contributes nothing and never
                  affects the gradient).
      presence  : optional BCE-with-logits on a per-sample hand-present logit,
                  scaled by ``presence_weight``.

    Args:
        loss_type: "smooth_l1" (default) or "wing".
        beta: smooth-L1 transition point (in normalized coord units).
        wing_omega/wing_epsilon: Wing-loss params (when loss_type="wing").
        z_weight: scale on the z term. 0.0 leaves z unsupervised.
        presence_weight: scale on the BCE presence term.
        keypoint_weights: per-joint weights, length K. None → uniform 1.0.
    """

    def __init__(self, loss_type: str = "smooth_l1", beta: float = 0.04,
                 wing_omega: float = 0.1, wing_epsilon: float = 0.02,
                 z_weight: float = 0.0, presence_weight: float = 0.0,
                 keypoint_weights: list[float] | None = None):
        super().__init__()
        self.loss_type = loss_type
        self.beta = float(beta)
        self.wing_omega = float(wing_omega)
        self.wing_epsilon = float(wing_epsilon)
        self.z_weight = float(z_weight)
        self.presence_weight = float(presence_weight)
        if keypoint_weights is not None:
            w = torch.tensor(keypoint_weights, dtype=torch.float32)
            self.register_buffer("kp_weights", w, persistent=False)
        else:
            self.kp_weights = None

    def _elementwise(self, diff_abs: torch.Tensor) -> torch.Tensor:
        """Per-element penalty on |pred - gt| for the configured loss type."""
        if self.loss_type == "wing":
            # Wing (Feng et al. 2018): log near 0, linear far. C keeps it C0.
            c = self.wing_omega - self.wing_omega * torch.log(
                torch.tensor(1.0 + self.wing_omega / self.wing_epsilon,
                             device=diff_abs.device, dtype=diff_abs.dtype))
            inner = self.wing_omega * torch.log(1.0 + diff_abs / self.wing_epsilon)
            outer = diff_abs - c
            return torch.where(diff_abs < self.wing_omega, inner, outer)
        # smooth-L1 / Huber
        return torch.where(diff_abs < self.beta,
                           0.5 * diff_abs ** 2 / self.beta,
                           diff_abs - 0.5 * self.beta)

    def forward(self, pred_coords: torch.Tensor, gt_coords_norm: torch.Tensor,
                vis_mask: torch.Tensor,
                presence_logit: torch.Tensor | None = None,
                presence_target: torch.Tensor | None = None,
                ) -> dict[str, torch.Tensor]:
        # pred_coords: (B, K, 3) normalized. gt_coords_norm: (B, K, 2 or 3).
        # vis_mask: (B, K). presence_logit/target: (B, 1) or (B,).
        device = pred_coords.device
        dtype = pred_coords.dtype
        vis = vis_mask.to(dtype)

        # --- xy term -----------------------------------------------------
        pred_xy = pred_coords[..., :2]
        gt_xy = gt_coords_norm[..., :2]
        xy_diff = (pred_xy - gt_xy).abs()                      # (B, K, 2)
        xy_pen = self._elementwise(xy_diff).sum(dim=-1)        # (B, K)
        weighted = xy_pen * vis
        if self.kp_weights is not None:
            weighted = weighted * self.kp_weights.to(device).unsqueeze(0)
        n_visible = vis.sum().clamp(min=1.0)
        xy_loss = weighted.sum() / n_visible

        # --- z term (masked, off by default) -----------------------------
        if self.z_weight > 0.0 and gt_coords_norm.shape[-1] >= 3:
            z_diff = (pred_coords[..., 2] - gt_coords_norm[..., 2]).abs()  # (B,K)
            z_pen = self._elementwise(z_diff) * vis
            z_loss = z_pen.sum() / n_visible
        else:
            z_loss = pred_coords.sum() * 0.0  # graph-stable zero tied to graph

        # --- presence term (optional) ------------------------------------
        if (self.presence_weight > 0.0 and presence_logit is not None
                and presence_target is not None):
            pl = presence_logit.view(-1)
            pt = presence_target.view(-1).to(dtype)
            presence_loss = nn.functional.binary_cross_entropy_with_logits(
                pl, pt, reduction="mean")
        else:
            presence_loss = pred_coords.sum() * 0.0

        total = xy_loss + self.z_weight * z_loss + self.presence_weight * presence_loss
        return {
            "loss": total,
            "xy": xy_loss.detach(),
            "z": z_loss.detach(),
            "presence": presence_loss.detach(),
        }
