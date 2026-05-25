"""Palm detector - Net 2 of the v3 pipeline.

Two architecture variants share the same depthwise-separable backbone:

  Backbone (both variants, ~615K params at 192 input):
    Input HxH RGB
      -> stem (Conv s2, BN, ReLU)
      -> 4 stages of depthwise-separable blocks (s2 each)
      -> feature maps tapped at strides 8, 16, 32

  Variant A (use_fpn=False, legacy SSDLite-style):
    Three separate detection heads, one per scale (P1 64-ch, P2 96-ch,
    P3 128-ch). Each emits cls + box deltas at A anchors per cell.

  Variant B (use_fpn=True, mini-FPN top-down lateral):
    1x1 lateral conv reduces each scale to a common FPN channel count.
    Top-down: P3 lateral is upsampled and added to P2 lateral; the merged
    map is upsampled and added to P1 lateral. Each merged map is smoothed
    by a 3x3 depthwise-separable block. A SINGLE shared prediction head
    (one cls conv + one box conv) is applied to all three FPN maps. Anchor
    counts at the three strides must match the caller's anchor generator.

  Output (both variants): concatenated cls (B, N) and box (B, N, 4)
  tensors with N anchors stitched in P1 -> P2 -> P3 order. Optional aux
  keypoint regression head when ``n_aux_kpts > 0`` (legacy variant only).

  Per-anchor keypoint regression (FPN variant) when ``n_kpts > 0``: each
  FPN head grows a third "kpt" conv emitting ``a * n_kpts * 2`` channels per
  cell, and the forward returns an extra ``"kpt"`` key of shape
  (B, N, n_kpts * 2) stitched in the same P1 -> P2 -> P3 order as cls/box.
  Keypoints are encoded as offsets from the anchor center normalized by
  anchor size — the same convention as the box-center deltas (see
  ``anchors.encode_kpts`` / ``anchors.decode_kpts``).
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
    """3-scale palm detector with optional top-down FPN lateral path.

    Args:
        n_anchors_per_cell: legacy interface - number of anchors per cell
            when ``anchors_per_scale`` is None. With FPN the prediction
            head is shared across scales so all three scales emit the
            same number of anchors per cell.
        n_aux_kpts: optional auxiliary keypoint regression (legacy variant
            only; ignored when ``use_fpn=True``).
        use_fpn: enable the mini-FPN top-down lateral path with a shared
            prediction head. Default False keeps the legacy architecture
            byte-for-byte parameter-compatible with prior checkpoints.
        fpn_channels: lateral channel count for the FPN path. 64 keeps the
            head under the 1.5M total-param budget.
        anchors_per_scale: optional tuple of length 3 giving (a_p1, a_p2,
            a_p3) - the per-scale anchor count. When set, the legacy path
            uses these to size each scale's head; the FPN path emits all
            three at the shared head but the caller is responsible for
            matching the head's anchor count to ``a_p1 == a_p2 == a_p3``
            (since the head is shared). If the per-scale counts differ
            the FPN constructor falls back to per-scale heads at the
            FPN channel width.
        n_kpts: per-anchor keypoint regression count for the FPN variant.
            When >0 (and ``use_fpn``), each FPN head grows a "kpt" conv
            emitting ``a * n_kpts * 2`` channels and the forward returns a
            ``"kpt"`` key of shape (B, N, n_kpts * 2). Works with both the
            shared head (all anchors_per_scale equal) and the per-scale
            fallback. Ignored for the legacy non-FPN path, which keeps the
            separate ``n_aux_kpts`` aux-keypoint head for back-compat.
    """

    def __init__(self,
                 n_anchors_per_cell: int = 3,
                 n_aux_kpts: int = 0,
                 use_fpn: bool = False,
                 fpn_channels: int = 64,
                 anchors_per_scale: tuple[int, int, int] | None = None,
                 n_kpts: int = 0):
        super().__init__()
        self.n_anchors = n_anchors_per_cell
        self.n_aux_kpts = n_aux_kpts
        self.use_fpn = use_fpn
        self.fpn_channels = fpn_channels
        self.n_kpts = n_kpts
        if anchors_per_scale is None:
            anchors_per_scale = (n_anchors_per_cell,) * 3
        if len(anchors_per_scale) != 3:
            raise ValueError("anchors_per_scale must be length 3 (P1, P2, P3)")
        self.anchors_per_scale = tuple(int(a) for a in anchors_per_scale)

        # Backbone (identical for both variants).
        self.stem = _conv_bn_relu(3, 24, stride=2)
        self.stage1 = nn.Sequential(_DWSepBlock(24, 32, stride=2),
                                    _DWSepBlock(32, 32))
        self.stage2 = nn.Sequential(_DWSepBlock(32, 64, stride=2),
                                    _DWSepBlock(64, 64),
                                    _DWSepBlock(64, 64))
        self.stage3 = nn.Sequential(_DWSepBlock(64, 96, stride=2),
                                    _DWSepBlock(96, 96),
                                    _DWSepBlock(96, 96))
        self.stage4 = nn.Sequential(_DWSepBlock(96, 128, stride=2),
                                    _DWSepBlock(128, 128))

        if use_fpn:
            self._init_fpn_heads()
        else:
            self._init_legacy_heads()

        self._init_weights()

    # ------------------------------------------------------------------
    # Head construction
    # ------------------------------------------------------------------
    def _init_legacy_heads(self) -> None:
        kpt_out = 2 * self.n_aux_kpts
        a_p1, a_p2, a_p3 = self.anchors_per_scale
        self.head_p1 = self._make_head(64, kpt_out, a_p1)
        self.head_p2 = self._make_head(96, kpt_out, a_p2)
        self.head_p3 = self._make_head(128, kpt_out, a_p3)

    def _init_fpn_heads(self) -> None:
        c = self.fpn_channels
        # Lateral 1x1 to a common channel count.
        self.lat_p1 = nn.Conv2d(64, c, 1, bias=False)
        self.lat_p2 = nn.Conv2d(96, c, 1, bias=False)
        self.lat_p3 = nn.Conv2d(128, c, 1, bias=False)
        # Lateral norms stabilize the top-down addition. BN over c channels.
        self.lat_bn_p1 = nn.BatchNorm2d(c)
        self.lat_bn_p2 = nn.BatchNorm2d(c)
        self.lat_bn_p3 = nn.BatchNorm2d(c)
        # Post-merge smoothing - one DWSep block per scale.
        self.smooth_p1 = _DWSepBlock(c, c)
        self.smooth_p2 = _DWSepBlock(c, c)
        self.smooth_p3 = _DWSepBlock(c, c)

        # Shared prediction head - one cls conv and one box conv applied to
        # every FPN map. The shared head only works if all three scales emit
        # the same anchors-per-cell count; otherwise fall back to per-scale
        # heads at the FPN channel width.
        if len(set(self.anchors_per_scale)) == 1:
            a = self.anchors_per_scale[0]
            modules: dict[str, nn.Module] = {
                "stem": _conv_bn_relu(c, c),
                "cls": nn.Conv2d(c, a, 1),
                "box": nn.Conv2d(c, a * 4, 1),
            }
            if self.n_kpts > 0:
                # Per-anchor keypoint offsets: a anchors x n_kpts x 2 coords.
                modules["kpt"] = nn.Conv2d(c, a * self.n_kpts * 2, 1)
            self.shared_head = nn.ModuleDict(modules)
            self.fpn_shared_head = True
        else:
            # Per-scale FPN heads at the (smaller) FPN channel width. The
            # per-anchor keypoint regression head is added here too (kpt_out
            # = n_kpts * 2 channels per anchor); n_aux_kpts is the legacy
            # per-cell aux-kpt path and stays at 0 in the FPN variant.
            kpt_out = 2 * self.n_kpts
            self.head_p1 = self._make_head(c, kpt_out, self.anchors_per_scale[0])
            self.head_p2 = self._make_head(c, kpt_out, self.anchors_per_scale[1])
            self.head_p3 = self._make_head(c, kpt_out, self.anchors_per_scale[2])
            self.fpn_shared_head = False

    def _make_head(self, in_ch: int, kpt_out: int, n_anchors: int) -> nn.ModuleDict:
        modules: dict[str, nn.Module] = {
            "cls": nn.Sequential(
                _conv_bn_relu(in_ch, in_ch),
                nn.Conv2d(in_ch, n_anchors, 1),
            ),
            "box": nn.Sequential(
                _conv_bn_relu(in_ch, in_ch),
                nn.Conv2d(in_ch, n_anchors * 4, 1),
            ),
        }
        if kpt_out > 0:
            modules["kpt"] = nn.Sequential(
                _conv_bn_relu(in_ch, in_ch),
                nn.Conv2d(in_ch, n_anchors * kpt_out, 1),
            )
        return nn.ModuleDict(modules)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1.0)
                nn.init.constant_(m.bias, 0.0)
        # Bias init for focal loss stability: prior_p = 0.01 -> bias = -log((1-p)/p)
        prior = 0.01
        focal_bias = -torch.log(torch.tensor((1 - prior) / prior)).item()
        if self.use_fpn and self.fpn_shared_head:
            nn.init.constant_(self.shared_head["cls"].bias, focal_bias)
            if "kpt" in self.shared_head:
                # Regression head: small-std weights + zero bias so initial
                # keypoint offsets sit near the anchor center.
                nn.init.normal_(self.shared_head["kpt"].weight, std=0.01)
                nn.init.constant_(self.shared_head["kpt"].bias, 0.0)
        else:
            for head in (self.head_p1, self.head_p2, self.head_p3):
                cls_conv = head["cls"][-1]
                nn.init.constant_(cls_conv.bias, focal_bias)
                if "kpt" in head:
                    # Per-scale FPN kpt head: small-std final conv + zero bias.
                    kpt_conv = head["kpt"][-1]
                    nn.init.normal_(kpt_conv.weight, std=0.01)
                    nn.init.constant_(kpt_conv.bias, 0.0)

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------
    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        x = self.stem(x)
        x = self.stage1(x)
        p1 = self.stage2(x)   # stride 8
        p2 = self.stage3(p1)  # stride 16
        p3 = self.stage4(p2)  # stride 32

        if self.use_fpn:
            f1, f2, f3 = self._fpn_forward(p1, p2, p3)
            return self._head_forward([(f1, "p1"), (f2, "p2"), (f3, "p3")])
        return self._legacy_head_forward(p1, p2, p3)

    def _fpn_forward(self, p1: torch.Tensor, p2: torch.Tensor, p3: torch.Tensor
                     ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        # Lateral 1x1 + BN to a common channel count.
        l1 = self.lat_bn_p1(self.lat_p1(p1))
        l2 = self.lat_bn_p2(self.lat_p2(p2))
        l3 = self.lat_bn_p3(self.lat_p3(p3))
        # Top-down: upsample-then-add. Bilinear upsample because nearest can
        # tile-stripe small palms.
        up3 = nn.functional.interpolate(l3, size=l2.shape[-2:],
                                        mode="bilinear", align_corners=False)
        m2 = l2 + up3
        up2 = nn.functional.interpolate(m2, size=l1.shape[-2:],
                                        mode="bilinear", align_corners=False)
        m1 = l1 + up2
        # Per-scale smoothing.
        f1 = self.smooth_p1(m1)
        f2 = self.smooth_p2(m2)
        f3 = self.smooth_p3(l3)
        return f1, f2, f3

    def _head_forward(self, feats: list[tuple[torch.Tensor, str]]
                      ) -> dict[str, torch.Tensor]:
        cls_chunks: list[torch.Tensor] = []
        box_chunks: list[torch.Tensor] = []
        kpt_chunks: list[torch.Tensor] = []
        emit_kpt = self.n_kpts > 0
        kpt_per_anchor = self.n_kpts * 2
        if self.use_fpn and self.fpn_shared_head:
            head = self.shared_head
            for feat, _name in feats:
                t = head["stem"](feat)
                cls_chunks.append(self._flatten(head["cls"](t), 1))
                box_chunks.append(self._flatten(head["box"](t), 4))
                if emit_kpt:
                    kpt_chunks.append(self._flatten(head["kpt"](t), kpt_per_anchor))
        else:
            heads = {"p1": self.head_p1, "p2": self.head_p2, "p3": self.head_p3}
            for feat, name in feats:
                h = heads[name]
                cls_chunks.append(self._flatten(h["cls"](feat), 1))
                box_chunks.append(self._flatten(h["box"](feat), 4))
                if emit_kpt:
                    kpt_chunks.append(self._flatten(h["kpt"](feat), kpt_per_anchor))
        result = {
            "cls": torch.cat(cls_chunks, dim=1),  # (B, N_anchors)
            "box": torch.cat(box_chunks, dim=1),  # (B, N_anchors, 4)
        }
        if emit_kpt:
            result["kpt"] = torch.cat(kpt_chunks, dim=1)  # (B, N_anchors, n_kpts*2)
        return result

    def _legacy_head_forward(self, p1: torch.Tensor, p2: torch.Tensor,
                             p3: torch.Tensor) -> dict[str, torch.Tensor]:
        outs: dict[str, list[torch.Tensor]] = {"cls": [], "box": [], "kpt": []}
        for feat, head in ((p1, self.head_p1), (p2, self.head_p2), (p3, self.head_p3)):
            cls = head["cls"](feat)
            box = head["box"](feat)
            outs["cls"].append(self._flatten(cls, 1))
            outs["box"].append(self._flatten(box, 4))
            if "kpt" in head:
                kpt = head["kpt"](feat)
                outs["kpt"].append(self._flatten(kpt, 2 * self.n_aux_kpts))
        result = {
            "cls": torch.cat(outs["cls"], dim=1),
            "box": torch.cat(outs["box"], dim=1),
        }
        if self.n_aux_kpts > 0:
            result["kpt"] = torch.cat(outs["kpt"], dim=1)
        return result

    @staticmethod
    def _flatten(t: torch.Tensor, per_anchor: int) -> torch.Tensor:
        B, C, H, W = t.shape
        if per_anchor == 1:
            return (t.permute(0, 2, 3, 1).contiguous()
                     .view(B, H * W * (C // per_anchor), per_anchor)
                     .squeeze(-1))
        return (t.permute(0, 2, 3, 1).contiguous()
                 .view(B, H * W * (C // per_anchor), per_anchor))


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def _smoke() -> None:
    """CPU smoke: build the FPN keypoint variant and print output shapes."""
    from src.stage1.models.anchors import get_anchors

    input_size = 256
    scales = [[0.05, 0.10], [0.20, 0.35], [0.55]]
    strides = [8, 16, 32]
    anchors = get_anchors(input_size, scales_per_stride=scales, strides=strides)

    for n_kpts in (0, 2):
        model = PalmDetector(use_fpn=True, n_kpts=n_kpts,
                             anchors_per_scale=(2, 2, 1))
        model.eval()
        with torch.no_grad():
            out = model(torch.randn(2, 3, input_size, input_size))
        n = out["cls"].shape[1]
        assert n == anchors.shape[0], (n, anchors.shape[0])
        assert out["box"].shape == (2, n, 4)
        keys = sorted(out.keys())
        if n_kpts > 0:
            assert out["kpt"].shape == (2, n, n_kpts * 2)
        print(f"[smoke] n_kpts={n_kpts} params={count_params(model):,} "
              f"N_anchors={n} keys={keys} "
              f"cls={tuple(out['cls'].shape)} box={tuple(out['box'].shape)}"
              + (f" kpt={tuple(out['kpt'].shape)}" if n_kpts > 0 else ""))

    # Legacy path still works.
    legacy = PalmDetector(use_fpn=False, n_anchors_per_cell=3)
    with torch.no_grad():
        lout = legacy(torch.randn(1, 3, 192, 192))
    print(f"[smoke] legacy params={count_params(legacy):,} "
          f"keys={sorted(lout.keys())} cls={tuple(lout['cls'].shape)}")


if __name__ == "__main__":
    _smoke()
