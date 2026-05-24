"""Hand landmark regressor — Net 3 of the v3 pipeline.

Architecture (MobileNetV2-lite, from scratch — no pretrained weights):
  Input 224x224 RGB hand crop
    → stem (Conv 3x3 s2)                       : 224 → 112,  3 → 32
    → stage1 (2x DWSep, first s2)              : 112 → 56,  32 → 48
    → stage2 (3x DWSep, first s2)              :  56 → 28,  48 → 96
    → stage3 (3x DWSep, first s2)              :  28 → 14,  96 → 160
    → stage4 (2x DWSep, first s2)              :  14 → 7,  160 → 256
    → deconv head (3x ConvTranspose 4x4 s2)    :   7 → 56,  256 → 128 → 128 → 128
    → 1x1 head                                 : 128 → 21
  Output: (B, 21, 56, 56) heatmaps at output stride 4.

Feeds `AdaptiveWingLoss + SoftArgmaxCoordLoss` from losses_v3.LandmarkLoss.
Param count ~1.27M (under the 1.5M budget). All weights trained from scratch —
no MediaPipe, no ImageNet pretrain, no distillation (Req 7).
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
    """21-keypoint heatmap regressor on cropped hand input. ~1.27M params.

    Input 224x224 RGB hand crop → 56x56 heatmaps (output stride 4).
    Run separately on each hand crop produced by Net 2.

    ``use_unet_skip`` enables U-Net style lateral skips from the encoder
    stages (stride 4, 8, 16) into the matching decoder levels (56, 28, 14).
    Adds ~50K params (1x1 lateral convs) and is consistently +0.03-0.06 PCK
    in the SimpleBaseline pose-estimation ablations.
    """

    def __init__(self, num_keypoints: int = 21, heatmap_channels: int = 128,
                 use_unet_skip: bool = False):
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

        self.use_unet_skip = bool(use_unet_skip)
        if self.use_unet_skip:
            # 1x1 lateral projections from encoder stages into the decoder
            # channel count, summed into the decoder after each up-conv.
            self.lat_stage3 = nn.Conv2d(160, heatmap_channels, 1, bias=False)  # 14×14
            self.lat_stage2 = nn.Conv2d(96, heatmap_channels, 1, bias=False)   # 28×28
            self.lat_stage1 = nn.Conv2d(48, heatmap_channels, 1, bias=False)   # 56×56

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
        s1 = self.stage1(x)            # 56×56, 48 ch
        s2 = self.stage2(s1)           # 28×28, 96 ch
        s3 = self.stage3(s2)           # 14×14, 160 ch
        s4 = self.stage4(s3)           # 7×7,   256 ch
        d1 = self.deconv1(s4)          # 14×14
        if self.use_unet_skip:
            d1 = d1 + self.lat_stage3(s3)
        d2 = self.deconv2(d1)          # 28×28
        if self.use_unet_skip:
            d2 = d2 + self.lat_stage2(s2)
        d3 = self.deconv3(d2)          # 56×56
        if self.use_unet_skip:
            d3 = d3 + self.lat_stage1(s1)
        return self.head(d3)


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == "__main__":
    # Smoke check: confirm param budget and IO contract.
    model = HandLandmarkNet(num_keypoints=21)
    model.eval()
    n_params = count_params(model)
    dummy = torch.randn(2, 3, 224, 224)
    with torch.no_grad():
        out = model(dummy)
    print(f"params: {n_params:,}")
    print(f"input : {tuple(dummy.shape)}")
    print(f"output: {tuple(out.shape)}")
    assert tuple(out.shape) == (2, 21, 56, 56), f"output shape mismatch: {out.shape}"
    assert n_params < 1_500_000, f"param budget exceeded: {n_params:,} >= 1.5M"
