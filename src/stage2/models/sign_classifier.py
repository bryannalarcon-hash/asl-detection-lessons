"""Net 4 — isolated sign classifier.

Port of the hoyso48 Kaggle ISLR 1st-place architecture (2023) into PyTorch.
Original recipe documented in `docs/hoyso-architecture.md`. Their TF model:

  Input (T, C) -> Mask(PAD)
    -> Dense(192) stem -> BN
    -> [3 x Conv1DBlock(k=17) -> 1 x TransformerBlock] x 2
    -> Dense(384) -> GAP1D
    -> LateDropout(0.8) -> Dense(num_classes)

Per-frame channel dim C: we feed (x, y, visibility) for our 49-kpt schema
(face+body 7 + right hand 21 + left hand 21) + lag-1 and lag-2 motion deltas
on coords. With visibility included we end up at C = 49*3 + 49*2 + 49*2 = 343
by default, but the model is agnostic to the actual C — first Dense projects
into the 192 inner dim.

We rely on `key_padding_mask` to ignore PADded time steps inside attention.
Pad value is hard-coded to 0.0 here; callers pad with zeros + supply a mask.
"""
from __future__ import annotations

from typing import Optional

import torch
from torch import nn


def _drop_path(x: torch.Tensor, drop_prob: float, training: bool) -> torch.Tensor:
    if drop_prob == 0.0 or not training:
        return x
    keep = 1.0 - drop_prob
    shape = (x.shape[0],) + (1,) * (x.ndim - 1)
    rand = keep + torch.rand(shape, dtype=x.dtype, device=x.device)
    return x.div(keep) * rand.floor()


class DropPath(nn.Module):
    def __init__(self, p: float = 0.0):
        super().__init__()
        self.p = float(p)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return _drop_path(x, self.p, self.training)


class Conv1DBlock(nn.Module):
    """Depthwise-separable causal Conv1D + GELU + residual + DropPath.

    Causal padding keeps lag features time-aligned with their source frame.
    """

    def __init__(self, dim: int, kernel: int = 17, drop_path: float = 0.2):
        super().__init__()
        self.causal_pad = kernel - 1
        self.dw = nn.Conv1d(dim, dim, kernel_size=kernel, groups=dim, padding=0)
        self.pw = nn.Conv1d(dim, dim, kernel_size=1)
        self.norm = nn.BatchNorm1d(dim)
        self.act = nn.GELU()
        self.drop_path = DropPath(drop_path)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, C). Conv1d expects (B, C, T).
        residual = x
        h = x.transpose(1, 2)
        h = nn.functional.pad(h, (self.causal_pad, 0))
        h = self.dw(h)
        h = self.pw(h)
        h = self.norm(h)
        h = self.act(h)
        h = h.transpose(1, 2)
        return residual + self.drop_path(h)


class TransformerBlock(nn.Module):
    """Pre-norm MHA + 2x expand MLP + DropPath. 4 heads default."""

    def __init__(self, dim: int, num_heads: int = 4, expand: int = 2,
                 drop_path: float = 0.2):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.attn = nn.MultiheadAttention(dim, num_heads=num_heads,
                                          batch_first=True, dropout=0.0)
        self.dp1 = DropPath(drop_path)
        self.norm2 = nn.LayerNorm(dim)
        self.mlp = nn.Sequential(
            nn.Linear(dim, dim * expand),
            nn.GELU(),
            nn.Linear(dim * expand, dim),
        )
        self.dp2 = DropPath(drop_path)

    def forward(self, x: torch.Tensor,
                key_padding_mask: Optional[torch.Tensor] = None
                ) -> torch.Tensor:
        h = self.norm1(x)
        a, _ = self.attn(h, h, h, key_padding_mask=key_padding_mask,
                         need_weights=False)
        x = x + self.dp1(a)
        x = x + self.dp2(self.mlp(self.norm2(x)))
        return x


class LateDropout(nn.Module):
    """Dropout that activates only after `start_step` global training steps.

    Lets the model fit aggressively early, then heavily regularises once
    overfitting starts. The buffer keeps step state under DataParallel.
    """

    def __init__(self, p: float = 0.8, start_step: int = 0):
        super().__init__()
        self.p = float(p)
        self.start_step = int(start_step)
        self.register_buffer("step", torch.zeros(1, dtype=torch.long),
                             persistent=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.training:
            self.step += 1
            if int(self.step.item()) >= self.start_step:
                return nn.functional.dropout(x, p=self.p, training=True)
        return x


class SignClassifier(nn.Module):
    """Hoyso48 ISLR stack adapted for our 49-kpt input.

    Args:
        in_channels: per-frame feature dim (coords + visibility + lag deltas).
        num_classes: usually 75 for the pilot vocabulary.
        dim: inner channel width. 192 in the original.
        kernel: Conv1D kernel. 17 in the original.
        drop_path: stochastic depth rate (shared across blocks).
        late_dropout_p: final-layer dropout magnitude.
        late_dropout_start_step: global step at which late dropout switches on.
    """

    def __init__(self,
                 in_channels: int,
                 num_classes: int = 75,
                 dim: int = 192,
                 kernel: int = 17,
                 drop_path: float = 0.2,
                 late_dropout_p: float = 0.8,
                 late_dropout_start_step: int = 5000):
        super().__init__()
        self.stem = nn.Linear(in_channels, dim, bias=False)
        self.stem_bn = nn.BatchNorm1d(dim, momentum=0.05)

        def conv_stack() -> nn.ModuleList:
            return nn.ModuleList([
                Conv1DBlock(dim, kernel=kernel, drop_path=drop_path)
                for _ in range(3)
            ])

        self.conv_block_1 = conv_stack()
        self.tfm_block_1 = TransformerBlock(dim, num_heads=4, expand=2,
                                            drop_path=drop_path)
        self.conv_block_2 = conv_stack()
        self.tfm_block_2 = TransformerBlock(dim, num_heads=4, expand=2,
                                            drop_path=drop_path)

        self.top = nn.Linear(dim, dim * 2)
        self.late_dropout = LateDropout(p=late_dropout_p,
                                        start_step=late_dropout_start_step)
        self.classifier = nn.Linear(dim * 2, num_classes)

    def _apply_convs(self, x: torch.Tensor, blocks: nn.ModuleList,
                     mask: Optional[torch.Tensor]) -> torch.Tensor:
        # Zero out PADded positions before the depthwise conv so they don't
        # leak energy into adjacent frames through the causal kernel.
        for blk in blocks:
            if mask is not None:
                x = x * (~mask).unsqueeze(-1).to(x.dtype)
            x = blk(x)
        return x

    def forward(self, x: torch.Tensor,
                key_padding_mask: Optional[torch.Tensor] = None
                ) -> torch.Tensor:
        """Args:
            x: (B, T, in_channels) per-frame features (already lag-augmented).
            key_padding_mask: (B, T) bool tensor, True where padded.

        Returns:
            (B, num_classes) class logits.
        """
        x = self.stem(x)
        # BN1d expects (B, C, T)
        x = self.stem_bn(x.transpose(1, 2)).transpose(1, 2)

        x = self._apply_convs(x, self.conv_block_1, key_padding_mask)
        x = self.tfm_block_1(x, key_padding_mask=key_padding_mask)
        x = self._apply_convs(x, self.conv_block_2, key_padding_mask)
        x = self.tfm_block_2(x, key_padding_mask=key_padding_mask)

        x = self.top(x)
        # Masked global average pool.
        if key_padding_mask is not None:
            valid = (~key_padding_mask).unsqueeze(-1).to(x.dtype)
            x = (x * valid).sum(dim=1) / valid.sum(dim=1).clamp(min=1.0)
        else:
            x = x.mean(dim=1)
        x = self.late_dropout(x)
        return self.classifier(x)


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == "__main__":
    # Smoke test
    m = SignClassifier(in_channels=343, num_classes=75)
    print(f"Params: {count_params(m):,}")
    x = torch.randn(2, 64, 343)
    mask = torch.zeros(2, 64, dtype=torch.bool)
    mask[0, 40:] = True  # first sample has 40 valid frames
    out = m(x, key_padding_mask=mask)
    print(f"Output: {out.shape}")
