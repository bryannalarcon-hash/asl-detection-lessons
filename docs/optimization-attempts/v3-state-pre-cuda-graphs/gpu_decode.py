"""GPU JPEG decode helper.

Lets DataLoader workers skip CPU JPEG decode entirely. Workers read raw
file bytes; the train loop calls `gpu_decode_and_letterbox` / `gpu_decode_only`
to do hardware NVJPEG decode + downstream resize on the GPU.

Falls back to CPU decode for any JPEG NVJPEG can't handle (progressive,
12-bit, malformed). Bit-for-bit equivalent within libjpeg-turbo tolerance.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F
from torchvision.io import ImageReadMode, decode_jpeg


def _try_gpu_decode_batch(jpeg_bytes_list: list[torch.Tensor],
                          device: torch.device | str) -> list[torch.Tensor | None]:
    """Best-effort batched NVJPEG decode. Returns per-sample tensors or None on failure."""
    out: list[torch.Tensor | None] = [None] * len(jpeg_bytes_list)
    # Filter empty/placeholder entries.
    work_idx = [i for i, b in enumerate(jpeg_bytes_list) if b.numel() > 0]
    if not work_idx:
        return out
    work_bytes = [jpeg_bytes_list[i] for i in work_idx]
    try:
        decoded = decode_jpeg(work_bytes, mode=ImageReadMode.RGB, device=device)
        # torchvision returns a list when given a list
        if isinstance(decoded, torch.Tensor):
            decoded = [decoded]
        for i, t in zip(work_idx, decoded):
            out[i] = t
        return out
    except Exception:
        # Whole-batch GPU decode failed — try one at a time so a single
        # bad JPEG doesn't fail the rest.
        for i, b in zip(work_idx, work_bytes):
            try:
                t = decode_jpeg(b, mode=ImageReadMode.RGB, device=device)
                out[i] = t
            except Exception:
                # CPU fallback
                try:
                    t = decode_jpeg(b, mode=ImageReadMode.RGB).to(device)
                    out[i] = t
                except Exception:
                    out[i] = None
        return out


def gpu_decode_and_letterbox(jpeg_bytes_list: list[torch.Tensor],
                             input_size: int,
                             device: torch.device | str,
                             ) -> torch.Tensor:
    """Decode JPEGs on GPU and letterbox to (B, 3, input_size, input_size).

    Output is float, normalized to [-1, 1]. Aspect ratio preserved; padding
    is zero (matches the prior CPU letterbox).
    """
    B = len(jpeg_bytes_list)
    out = torch.zeros(B, 3, input_size, input_size, device=device, dtype=torch.float32)
    decoded = _try_gpu_decode_batch(jpeg_bytes_list, device)

    for i, img in enumerate(decoded):
        if img is None:
            continue
        _, H, W = img.shape
        scale = input_size / max(H, W)
        new_h = max(1, int(H * scale))
        new_w = max(1, int(W * scale))
        resized = F.interpolate(img.unsqueeze(0).float(),
                                size=(new_h, new_w),
                                mode="bilinear", align_corners=False)[0]
        dy = (input_size - new_h) // 2
        dx = (input_size - new_w) // 2
        out[i, :, dy:dy + new_h, dx:dx + new_w] = resized

    # Normalize uint8 [0,255] → [-1, 1]
    return (out / 255.0 - 0.5) / 0.5


def gpu_decode_full_res(jpeg_bytes_list: list[torch.Tensor],
                        device: torch.device | str,
                        ) -> list[torch.Tensor | None]:
    """Decode JPEGs on GPU, return raw (3, H, W) uint8 tensors (per-image sizes)."""
    return _try_gpu_decode_batch(jpeg_bytes_list, device)


def gpu_decode_and_warp_affine(jpeg_bytes_list: list[torch.Tensor],
                               M_list: list[torch.Tensor],
                               out_size: int,
                               device: torch.device | str,
                               ) -> torch.Tensor:
    """Decode JPEGs on GPU, apply per-sample 2x3 affine warp → (B, 3, out_size, out_size).

    M maps SOURCE pixel coords → OUTPUT pixel coords (same convention as
    cv2.warpAffine without WARP_INVERSE_MAP, and same convention as
    src/stage1/data/hand_crops.py crop_hand).

    Output is float, normalized to [-1, 1].
    """
    B = len(jpeg_bytes_list)
    out = torch.zeros(B, 3, out_size, out_size, device=device, dtype=torch.float32)
    decoded = _try_gpu_decode_batch(jpeg_bytes_list, device)

    for i, img in enumerate(decoded):
        if img is None:
            continue
        _, H, W = img.shape
        # M is the forward (src → dst) map. grid_sample needs the inverse
        # (dst → src) AND in normalized coords [-1, 1]. Compute:
        #   theta = N_src @ inv(M_aug) @ N_dst_inv
        # where N_dst_inv maps grid_sample's normalized output [-1,1] → pixel
        # space, M_aug is M extended to 3x3, inv goes dst → src, and N_src
        # then normalizes back to [-1, 1] in the source frame.
        M = M_list[i].to(device=device, dtype=torch.float32)
        # Build 3x3 from 2x3
        M_aug = torch.eye(3, device=device, dtype=torch.float32)
        M_aug[:2] = M
        M_inv = torch.linalg.inv(M_aug)  # 3x3, dst → src
        # Normalized output (-1..1) → pixel (0..out_size-1)
        N_dst_inv = torch.tensor([
            [out_size / 2.0, 0.0, (out_size - 1) / 2.0],
            [0.0, out_size / 2.0, (out_size - 1) / 2.0],
            [0.0, 0.0, 1.0],
        ], device=device, dtype=torch.float32)
        # Pixel (0..W-1, 0..H-1) → normalized (-1..1) in src
        N_src = torch.tensor([
            [2.0 / (W - 1 if W > 1 else 1), 0.0, -1.0],
            [0.0, 2.0 / (H - 1 if H > 1 else 1), -1.0],
            [0.0, 0.0, 1.0],
        ], device=device, dtype=torch.float32)
        theta = (N_src @ M_inv @ N_dst_inv)[:2]  # (2, 3)

        grid = torch.nn.functional.affine_grid(
            theta.unsqueeze(0), (1, 3, out_size, out_size), align_corners=True,
        )
        sampled = torch.nn.functional.grid_sample(
            img.unsqueeze(0).float(), grid,
            mode="bilinear", padding_mode="zeros", align_corners=True,
        )
        out[i] = sampled[0]

    return (out / 255.0 - 0.5) / 0.5
