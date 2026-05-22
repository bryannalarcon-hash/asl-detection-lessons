"""Palm detector — Net 2 of the v3 pipeline.

Architecture (BlazePalm-inspired, from scratch):
  Input 192x192 RGB
    → stem (Conv s2, BN, ReLU)
    → 5 stages of depthwise-separable blocks (s2 each)
    → 3 feature maps tapped at strides 8, 16, 32 (sizes 24, 12, 6)
    → SSD-style detection head per scale
  Outputs: classification logits + box deltas per anchor, plus an optional
  small auxiliary head for keypoint offsets (wrist + middle-MCP) used to
  estimate hand rotation at inference. We keep the aux head as zero-cost
  optional; not required for the bbox-only loss path.
"""
from __future__ import annotations

import torch
from torch import nn


def _conv_bn_relu(in_ch: int, out_ch: int, k: int = 3, stride: int = 1) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(in_ch, out_ch, k, stride=stride, padding=k // 2, bias=False),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
    )


class _DWSepBlock(nn.Module):
    """Depthwise 3x3 + pointwise 1x1 + BN/ReLU + optional residual."""

    def __init__(self, in_ch: int, out_ch: int, stride: int = 1):
        super().__init__()
        self.use_residual = (stride == 1 and in_ch == out_ch)
        self.dw = nn.Conv2d(in_ch, in_ch, 3, stride=stride, padding=1,
                            groups=in_ch, bias=False)
        self.bn1 = nn.BatchNorm2d(in_ch)
        self.pw = nn.Conv2d(in_ch, out_ch, 1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_ch)
        self.act = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = x
        out = self.act(self.bn1(self.dw(x)))
        out = self.act(self.bn2(self.pw(out)))
        if self.use_residual:
            out = out + identity
        return out


class PalmDetector(nn.Module):
    """3-scale SSD-style palm detector. ~460K params."""

    def __init__(self, n_anchors_per_cell: int = 3, n_aux_kpts: int = 0):
        super().__init__()
        self.n_anchors = n_anchors_per_cell
        self.n_aux_kpts = n_aux_kpts

        # Stem: 192 → 96
        self.stem = _conv_bn_relu(3, 24, stride=2)
        # Stage 1: 96 → 48
        self.stage1 = nn.Sequential(_DWSepBlock(24, 32, stride=2),
                                    _DWSepBlock(32, 32))
        # Stage 2 (P1 24x24): 48 → 24
        self.stage2 = nn.Sequential(_DWSepBlock(32, 64, stride=2),
                                    _DWSepBlock(64, 64),
                                    _DWSepBlock(64, 64))
        # Stage 3 (P2 12x12): 24 → 12
        self.stage3 = nn.Sequential(_DWSepBlock(64, 96, stride=2),
                                    _DWSepBlock(96, 96),
                                    _DWSepBlock(96, 96))
        # Stage 4 (P3 6x6): 12 → 6
        self.stage4 = nn.Sequential(_DWSepBlock(96, 128, stride=2),
                                    _DWSepBlock(128, 128))

        # Detection heads (shared structure, separate weights per scale).
        kpt_out = 2 * n_aux_kpts
        self.head_p1 = self._make_head(64, kpt_out)
        self.head_p2 = self._make_head(96, kpt_out)
        self.head_p3 = self._make_head(128, kpt_out)

        self._init_weights()

    def _make_head(self, in_ch: int, kpt_out: int) -> nn.ModuleDict:
        return nn.ModuleDict({
            "cls": nn.Sequential(
                _conv_bn_relu(in_ch, in_ch),
                nn.Conv2d(in_ch, self.n_anchors, 1),
            ),
            "box": nn.Sequential(
                _conv_bn_relu(in_ch, in_ch),
                nn.Conv2d(in_ch, self.n_anchors * 4, 1),
            ),
            **({"kpt": nn.Sequential(
                _conv_bn_relu(in_ch, in_ch),
                nn.Conv2d(in_ch, self.n_anchors * kpt_out, 1),
            )} if kpt_out > 0 else {}),
        })

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1.0)
                nn.init.constant_(m.bias, 0.0)
        # Bias init for focal loss stability: prior_p = 0.01 → bias = -log((1-p)/p)
        prior = 0.01
        for head in (self.head_p1, self.head_p2, self.head_p3):
            cls_conv = head["cls"][-1]
            nn.init.constant_(cls_conv.bias, -torch.log(torch.tensor((1 - prior) / prior)).item())

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        x = self.stem(x)
        x = self.stage1(x)
        p1 = self.stage2(x)
        p2 = self.stage3(p1)
        p3 = self.stage4(p2)
        outs = {"cls": [], "box": [], "kpt": []}
        for feat, head in ((p1, self.head_p1), (p2, self.head_p2), (p3, self.head_p3)):
            cls = head["cls"](feat)            # (B, A, H, W)
            box = head["box"](feat)            # (B, A*4, H, W)
            outs["cls"].append(self._flatten(cls, 1))
            outs["box"].append(self._flatten(box, 4))
            if "kpt" in head:
                kpt = head["kpt"](feat)
                outs["kpt"].append(self._flatten(kpt, 2 * self.n_aux_kpts))
        # Concatenate across scales in the same order as anchor generation
        # (P1 → P2 → P3) so anchor index aligns with output index.
        result = {
            "cls": torch.cat(outs["cls"], dim=1),  # (B, N_anchors)
            "box": torch.cat(outs["box"], dim=1),  # (B, N_anchors, 4)
        }
        if self.n_aux_kpts > 0:
            result["kpt"] = torch.cat(outs["kpt"], dim=1)  # (B, N, 2*kpts)
        return result

    @staticmethod
    def _flatten(t: torch.Tensor, per_anchor: int) -> torch.Tensor:
        B, C, H, W = t.shape
        return (t.permute(0, 2, 3, 1).contiguous()
                 .view(B, H * W * (C // per_anchor), per_anchor)
                 .squeeze(-1) if per_anchor == 1 else
                 t.permute(0, 2, 3, 1).contiguous()
                  .view(B, H * W * (C // per_anchor), per_anchor))


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
