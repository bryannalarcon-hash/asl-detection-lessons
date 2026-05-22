"""Lighter augmentation for the cached pipeline.

Caller provides a pre-letterboxed image (e.g., 320×320). This transform does:
  - random crop to image_size (e.g., 256)
  - shift/scale/rotate (gentle)
  - horizontal flip
  - color jitter
  - normalize

Notably absent: the OneOf{MotionBlur, GaussianBlur, GaussNoise} branch from v1.
JPEG decode and base resize are skipped — already done at cache time.
"""
from __future__ import annotations

import albumentations as A
import cv2

_MEAN = (0.5, 0.5, 0.5)
_STD = (0.5, 0.5, 0.5)


def build_train_transform_v2(image_size: int, color_jitter: float = 0.2) -> A.Compose:
    return A.Compose(
        [
            A.ShiftScaleRotate(
                shift_limit=0.05, scale_limit=0.15, rotate_limit=15,
                border_mode=cv2.BORDER_CONSTANT, value=0, p=0.8,
            ),
            A.RandomCrop(height=image_size, width=image_size, p=1.0),
            A.HorizontalFlip(p=0.5),
            A.ColorJitter(
                brightness=color_jitter, contrast=color_jitter,
                saturation=color_jitter, hue=color_jitter / 2, p=0.8,
            ),
            A.Normalize(mean=_MEAN, std=_STD),
        ],
        keypoint_params=A.KeypointParams(
            format="xy", remove_invisible=False, label_fields=["kp_visible"],
        ),
    )


def build_val_transform_v2(image_size: int) -> A.Compose:
    return A.Compose(
        [
            A.CenterCrop(height=image_size, width=image_size, p=1.0),
            A.Normalize(mean=_MEAN, std=_STD),
        ],
        keypoint_params=A.KeypointParams(
            format="xy", remove_invisible=False, label_fields=["kp_visible"],
        ),
    )
