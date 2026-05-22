"""Hand landmark regressor — Net 3 of the v3 pipeline.

Architecture (MobileNet-style, from scratch):
  Input 224x224 RGB hand crop
    → stem (Conv s2)
    → 5 stages of depthwise-separable blocks (each ending in stride 2)
    → 2 deconv stages (stride 2 each, restoring to 56x56)
    → 1x1 head → 21 heatmaps at 56x56

Output stride 4, params ~1.8M.
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


class _DeconvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.deconv = nn.ConvTranspose2d(in_ch, out_ch, 4, stride=2, padding=1, bias=False)
        self.bn = nn.BatchNorm2d(out_ch)
        self.act = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.act(self.bn(self.deconv(x)))


class HandLandmarkNet(nn.Module):
    """21-keypoint heatmap regressor on cropped hand input. ~1.8M params.

    Designed for input 224x224 → 56x56 heatmaps (stride 4).
    Run separately on each hand crop produced by Net 2.
    """

    def __init__(self, num_keypoints: int = 21, heatmap_channels: int = 128):
        super().__init__()
        # Stem: 224 → 112
        self.stem = _conv_bn_relu(3, 32, stride=2)
        # Stage 1: 112 → 56
        self.stage1 = nn.Sequential(_DWSepBlock(32, 48, stride=2),
                                    _DWSepBlock(48, 48))
        # Stage 2: 56 → 28
        self.stage2 = nn.Sequential(_DWSepBlock(48, 96, stride=2),
                                    _DWSepBlock(96, 96),
                                    _DWSepBlock(96, 96))
        # Stage 3: 28 → 14
        self.stage3 = nn.Sequential(_DWSepBlock(96, 160, stride=2),
                                    _DWSepBlock(160, 160),
                                    _DWSepBlock(160, 160))
        # Stage 4: 14 → 7
        self.stage4 = nn.Sequential(_DWSepBlock(160, 256, stride=2),
                                    _DWSepBlock(256, 256))

        # Decoder: 7 → 14 → 28 → 56
        self.deconv1 = _DeconvBlock(256, heatmap_channels)
        self.deconv2 = _DeconvBlock(heatmap_channels, heatmap_channels)
        self.deconv3 = _DeconvBlock(heatmap_channels, heatmap_channels)

        self.head = nn.Conv2d(heatmap_channels, num_keypoints, 1)
        self._init_weights()

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, (nn.Conv2d, nn.ConvTranspose2d)):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1.0)
                nn.init.constant_(m.bias, 0.0)
        nn.init.normal_(self.head.weight, std=0.001)
        nn.init.constant_(self.head.bias, 0.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.stem(x)
        x = self.stage1(x)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.stage4(x)
        x = self.deconv1(x)
        x = self.deconv2(x)
        x = self.deconv3(x)
        return self.head(x)


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
