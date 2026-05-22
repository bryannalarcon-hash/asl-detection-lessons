"""From-scratch keypoint detector.

Architecture: a SimpleBaseline-style network — ResNet-like encoder with three
deconv stages to upsample back to a heatmap resolution.

  input  (3, H, W)
    │ stem        3 → 32,  H → H/2
    │ stage2     32 → 64,  H/2 → H/4
    │ stage3     64 → 128, H/4 → H/8
    │ stage4    128 → 256, H/8 → H/16
    │ stage5    256 → 384, H/16 → H/32
    │ deconv1   384 → 256, H/32 → H/16
    │ deconv2   256 → 256, H/16 → H/8
    │ deconv3   256 → 256, H/8 → H/4
    │ head 1×1  256 → K
  output (K, H/4, W/4)

At input H=384 the heatmap is 96×96, matching our config. ~8M params trained
fully from scratch — no pretrained weights at any layer.
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


class _BasicBlock(nn.Module):
    """ResNet-style residual block, no bottleneck."""

    def __init__(self, channels: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, 3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(channels)
        self.act = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = x
        out = self.act(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out = out + identity
        return self.act(out)


class _DownStage(nn.Module):
    """Downsample 2× then refine with two BasicBlocks."""

    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.down = _conv_bn_relu(in_ch, out_ch, k=3, stride=2)
        self.refine = nn.Sequential(_BasicBlock(out_ch), _BasicBlock(out_ch))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.refine(self.down(x))


class _DeconvBlock(nn.Module):
    """Transposed conv to upsample 2× + BN + ReLU."""

    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.deconv = nn.ConvTranspose2d(
            in_ch, out_ch, kernel_size=4, stride=2, padding=1, bias=False,
        )
        self.bn = nn.BatchNorm2d(out_ch)
        self.act = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.act(self.bn(self.deconv(x)))


class KeypointDetector(nn.Module):
    """Whole-frame keypoint detector with heatmap output."""

    def __init__(
        self,
        num_keypoints: int = 49,
        backbone_channels: tuple[int, ...] = (32, 64, 128, 256, 384),
        heatmap_channels: int = 256,
    ) -> None:
        super().__init__()
        c1, c2, c3, c4, c5 = backbone_channels

        # Stem: 1× downsample 2.
        self.stem = nn.Sequential(
            _conv_bn_relu(3, c1, k=3, stride=2),
            _BasicBlock(c1),
        )
        # Backbone: 4× downsample (cumulative 32×).
        self.stage2 = _DownStage(c1, c2)
        self.stage3 = _DownStage(c2, c3)
        self.stage4 = _DownStage(c3, c4)
        self.stage5 = _DownStage(c4, c5)

        # Head: 3 deconv stages → cumulative 8× upsample.
        # Cumulative downsample 32× ÷ 8× = output stride 4.
        self.deconv1 = _DeconvBlock(c5, heatmap_channels)
        self.deconv2 = _DeconvBlock(heatmap_channels, heatmap_channels)
        self.deconv3 = _DeconvBlock(heatmap_channels, heatmap_channels)
        self.final = nn.Conv2d(heatmap_channels, num_keypoints, 1)

        self._init_weights()

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, (nn.Conv2d, nn.ConvTranspose2d)):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1.0)
                nn.init.constant_(m.bias, 0.0)
        # Final layer: small init helps early training stability for heatmap regression.
        nn.init.normal_(self.final.weight, std=0.001)
        nn.init.constant_(self.final.bias, 0.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.stem(x)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.stage4(x)
        x = self.stage5(x)
        x = self.deconv1(x)
        x = self.deconv2(x)
        x = self.deconv3(x)
        return self.final(x)


def soft_argmax_2d(heatmaps: torch.Tensor) -> torch.Tensor:
    """Convert heatmaps (B, K, H, W) → (B, K, 2) in heatmap-pixel coords.

    Uses a softmax-weighted spatial expectation. Smoother than argmax and
    differentiable, which is useful if we ever add an auxiliary coord-regression
    loss; for inference we use a sharpening temperature.
    """
    B, K, H, W = heatmaps.shape
    # Sharpen the heatmaps before softmax for cleaner argmax-like behavior.
    flat = heatmaps.view(B, K, -1)
    flat = flat - flat.max(dim=-1, keepdim=True).values
    probs = torch.softmax(flat * 10.0, dim=-1)
    probs = probs.view(B, K, H, W)

    ys = torch.arange(H, device=heatmaps.device, dtype=heatmaps.dtype)
    xs = torch.arange(W, device=heatmaps.device, dtype=heatmaps.dtype)
    grid_y, grid_x = torch.meshgrid(ys, xs, indexing="ij")

    x_coord = (probs * grid_x[None, None]).sum(dim=(-1, -2))
    y_coord = (probs * grid_y[None, None]).sum(dim=(-1, -2))
    return torch.stack([x_coord, y_coord], dim=-1)


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
