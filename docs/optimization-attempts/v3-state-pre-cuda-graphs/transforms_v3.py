"""v3 augmentation: cheap CPU per-sample prep + heavy GPU per-batch augmentation.

Architecture choice:
- CPU side: just decode the cached npy + apply rare heavy augs (HandOnCOCO,
  JPEG compression) when their stochastic flag fires. Outputs raw tensors.
- GPU side: kornia-based affine + color + blur + noise applied per batch.

This split keeps GPU utilization high while preserving augmentation diversity.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn

try:
    import kornia.augmentation as K
    _HAS_KORNIA = True
except ImportError:
    _HAS_KORNIA = False


_NORM_MEAN = (0.5, 0.5, 0.5)
_NORM_STD = (0.5, 0.5, 0.5)


# --------------------------------------------------------------------------
# CPU-side: light per-sample prep (called from Dataset.__getitem__)
# --------------------------------------------------------------------------

def cpu_prep(image: np.ndarray, normalize: bool = True) -> torch.Tensor:
    """Convert cached uint8 numpy image → float tensor (C, H, W).

    Normalization to [-1, 1] happens here. The expensive random aug runs
    later on the GPU.
    """
    t = torch.from_numpy(image).permute(2, 0, 1).float()
    if normalize:
        t = t / 255.0
        for c in range(3):
            t[c] = (t[c] - _NORM_MEAN[c]) / _NORM_STD[c]
    return t


def hand_on_coco_composite(hand_crop: np.ndarray, background: np.ndarray,
                           mask: np.ndarray | None = None,
                           rng: np.random.Generator | None = None) -> np.ndarray:
    """Composite a tight hand crop over a COCO background image.

    Operates on uint8 numpy arrays. If `mask` is None, uses skin-color
    heuristic; otherwise paste the masked region.
    """
    rng = rng or np.random.default_rng()
    h, w = hand_crop.shape[:2]
    bg = cv2.resize(background, (w, h), interpolation=cv2.INTER_AREA)
    if mask is None:
        # Skin-color YCbCr mask (rough heuristic — only used at p=0.3 so
        # imperfect mask is acceptable).
        ycrcb = cv2.cvtColor(hand_crop, cv2.COLOR_RGB2YCrCb)
        cr, cb = ycrcb[..., 1], ycrcb[..., 2]
        skin = ((cr > 135) & (cr < 180) & (cb > 85) & (cb < 135)).astype(np.float32)
        # Smooth the mask
        mask = cv2.GaussianBlur(skin, (5, 5), 0)[..., None]
    else:
        mask = mask.astype(np.float32)[..., None]
    return (hand_crop * mask + bg * (1 - mask)).astype(np.uint8)


# --------------------------------------------------------------------------
# GPU-side: batched augmentation via kornia
# --------------------------------------------------------------------------

class GPUAugmentation(nn.Module):
    """Batched augmentation that runs on the device the input is already on.

    Applied AFTER batching, BEFORE the model forward. All ops are differentiable
    but we typically wrap this in `with torch.no_grad():` because we don't
    backprop into augmentation parameters.

    Usage in training loop:
        batch = batch.to(device)
        with torch.no_grad():
            batch = gpu_aug(batch)
        pred = model(batch)
    """

    def __init__(self, image_size: int = 256,
                 rotate_deg: float = 30.0, scale_range: tuple[float, float] = (0.75, 1.25),
                 shift_frac: float = 0.08, hflip_p: float = 0.5,
                 brightness: float = 0.3, contrast: float = 0.3,
                 saturation: float = 0.3, hue: float = 0.1,
                 blur_p: float = 0.2, noise_p: float = 0.2):
        super().__init__()
        if not _HAS_KORNIA:
            raise RuntimeError("kornia is required for GPUAugmentation; "
                               "add `kornia` to requirements.txt")
        # Kornia 0.7+ requires AugmentationSequential for keypoint-aware composition.
        # Geometric ops (affine + flip) move kpts; color/blur/noise don't.
        self.geom = K.AugmentationSequential(
            K.RandomAffine(
                degrees=rotate_deg,
                translate=(shift_frac, shift_frac),
                scale=scale_range,
                p=0.9, same_on_batch=False,
            ),
            K.RandomHorizontalFlip(p=hflip_p, same_on_batch=False),
            data_keys=["input", "keypoints"],
            same_on_batch=False,
        )
        # Photometric stack — image-only, doesn't touch keypoints.
        self.photo = nn.Sequential(
            K.ColorJitter(
                brightness=brightness, contrast=contrast,
                saturation=saturation, hue=hue, p=0.8, same_on_batch=False,
            ),
            K.RandomGaussianBlur(
                kernel_size=(5, 5), sigma=(0.5, 2.0), p=blur_p, same_on_batch=False,
            ),
            K.RandomGaussianNoise(mean=0.0, std=0.05, p=noise_p, same_on_batch=False),
        )

    def forward(self, batch_imgs: torch.Tensor,
                keypoints: torch.Tensor | None = None,
                ) -> tuple[torch.Tensor, torch.Tensor | None]:
        """Apply augmentation. If keypoints provided, returns transformed kpts too.

        batch_imgs: (B, 3, H, W), in normalized [-1, 1] space (we de-normalize for
                    color ops, then re-normalize at the end).
        keypoints:  (B, K, 2) in image-pixel coords, or None.
        """
        # Convert to [0, 1] for color ops + most kornia primitives.
        x = batch_imgs * 0.5 + 0.5
        if keypoints is not None:
            x, keypoints_out = self.geom(x, keypoints)
        else:
            # When no kpts, just apply geom on input alone via the same sequential.
            # AugmentationSequential with data_keys=['input','keypoints'] requires
            # both; sidestep by using K.RandomAffine + K.RandomHorizontalFlip directly.
            x = self.geom.transforms[0](x)
            x = self.geom.transforms[1](x)
            keypoints_out = None
        x = self.photo(x)
        x = x.clamp(0, 1)
        x = (x - 0.5) / 0.5
        return x, keypoints_out


# --------------------------------------------------------------------------
# Hand-side index swap helper for keypoints after a horizontal flip.
# --------------------------------------------------------------------------

def swap_hand_indices_on_flip(keypoints: torch.Tensor, vis_mask: torch.Tensor
                              ) -> tuple[torch.Tensor, torch.Tensor]:
    """For samples that were horizontally flipped, swap right/left hand kpts.

    Net 3 trains on single-hand crops, so this mostly applies to Net 2's
    full-frame inputs. Caller decides whether to invoke based on flip flag.
    """
    # Net 3 hand crop case: 21 kpts — flipping doesn't swap left↔right,
    # it just mirrors finger positions. Caller handles by NOT calling this.
    # Net 2 case: 49 kpts — swap right hand [0:21] with left hand [21:42].
    K = keypoints.shape[-2]
    if K != 49:
        return keypoints, vis_mask
    kp_out = keypoints.clone()
    vis_out = vis_mask.clone()
    kp_out[..., 0:21, :] = keypoints[..., 21:42, :]
    kp_out[..., 21:42, :] = keypoints[..., 0:21, :]
    vis_out[..., 0:21] = vis_mask[..., 21:42]
    vis_out[..., 21:42] = vis_mask[..., 0:21]
    return kp_out, vis_out
