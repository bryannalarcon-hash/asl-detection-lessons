"""Keypoint-aware augmentation built on albumentations."""
from __future__ import annotations

import numpy as np
import albumentations as A
import cv2

from src.stage1.data import schema as S


_IMAGENET_LIKE_MEAN = (0.5, 0.5, 0.5)
_IMAGENET_LIKE_STD = (0.5, 0.5, 0.5)


def _hflip_remap_indices() -> np.ndarray:
    """Index permutation that swaps left/right keypoints after hflip."""
    perm = np.arange(S.NUM_KEYPOINTS)
    for a, b in S.FLIP_PAIRS:
        perm[a], perm[b] = perm[b], perm[a]
    return perm


HFLIP_REMAP = _hflip_remap_indices()


def build_train_transform(image_size: int, color_jitter: float = 0.2) -> A.Compose:
    """Train-time pipeline: aggressive geometric + photometric augmentation.

    Note: albumentations updates keypoint coords for geometric ops. We handle
    left/right-side swapping for hflip ourselves via HFLIP_REMAP.
    """
    return A.Compose(
        [
            A.LongestMaxSize(max_size=int(image_size * 1.3)),
            A.PadIfNeeded(min_height=int(image_size * 1.3),
                          min_width=int(image_size * 1.3),
                          border_mode=cv2.BORDER_CONSTANT, value=0),
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
            A.OneOf([
                A.MotionBlur(blur_limit=5),
                A.GaussianBlur(blur_limit=5),
                A.GaussNoise(var_limit=(5, 25)),
            ], p=0.3),
            A.Normalize(mean=_IMAGENET_LIKE_MEAN, std=_IMAGENET_LIKE_STD),
        ],
        keypoint_params=A.KeypointParams(
            format="xy", remove_invisible=False, label_fields=["kp_visible"],
        ),
    )


def build_val_transform(image_size: int) -> A.Compose:
    """Val/test pipeline: deterministic letterbox + normalize."""
    return A.Compose(
        [
            A.LongestMaxSize(max_size=image_size),
            A.PadIfNeeded(min_height=image_size, min_width=image_size,
                          border_mode=cv2.BORDER_CONSTANT, value=0,
                          position="center"),
            A.Normalize(mean=_IMAGENET_LIKE_MEAN, std=_IMAGENET_LIKE_STD),
        ],
        keypoint_params=A.KeypointParams(
            format="xy", remove_invisible=False, label_fields=["kp_visible"],
        ),
    )


def apply_transform(transform: A.Compose, image: np.ndarray,
                    keypoints: np.ndarray, visible: np.ndarray,
                    image_size: int) -> dict:
    """Apply transform; handle hflip's left/right index swap by detection.

    albumentations doesn't tell us whether HorizontalFlip fired, so we infer
    it by checking which side has more x > image_width/2 keypoints before vs
    after. Cleaner option: subclass HorizontalFlip to set a flag — for now
    this heuristic is reliable when at least one keypoint is visible.
    """
    out = transform(
        image=image,
        keypoints=[(float(x), float(y)) for x, y in keypoints],
        kp_visible=list(visible.tolist()),
    )

    out_kps = np.array(out["keypoints"], dtype=np.float32)
    out_vis = np.array(out["kp_visible"], dtype=np.int64)

    # Mark keypoints that landed outside the cropped frame as not-visible.
    in_frame = (
        (out_kps[:, 0] >= 0) & (out_kps[:, 0] < image_size)
        & (out_kps[:, 1] >= 0) & (out_kps[:, 1] < image_size)
    )
    out_vis = out_vis & in_frame.astype(np.int64)

    # Heuristic hflip detection: if the x-centroid of visible body kpts moved
    # across the midline, treat it as a flip and remap.
    if _looks_flipped(keypoints, visible, out_kps, out_vis, image_size):
        out_kps = out_kps[HFLIP_REMAP]
        out_vis = out_vis[HFLIP_REMAP]

    return {
        "image": out["image"],
        "keypoints": out_kps,
        "visible": out_vis,
    }


def _looks_flipped(in_kps: np.ndarray, in_vis: np.ndarray,
                   out_kps: np.ndarray, out_vis: np.ndarray,
                   image_size: int) -> bool:
    """Detect hflip by comparing left-vs-right shoulder positions."""
    ls, rs = S.LEFT_SHOULDER, S.RIGHT_SHOULDER
    if not (in_vis[ls] and in_vis[rs] and out_vis[ls] and out_vis[rs]):
        return False
    in_sign = in_kps[ls, 0] - in_kps[rs, 0]
    out_sign = out_kps[ls, 0] - out_kps[rs, 0]
    return (in_sign > 0) != (out_sign > 0)
