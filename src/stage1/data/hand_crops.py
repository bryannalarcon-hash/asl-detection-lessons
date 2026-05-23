"""Hand-region cropping: image → 224x224 hand crop with transform tracking.

Used by:
- Net 3 training (crop labeled hand region for landmark learning)
- Inference time (after Net 2 predicts palm bbox)

The transform matrix is returned so we can unproject Net 3's predicted
keypoints (in 224x224 crop space) back to the original frame.
"""
from __future__ import annotations

import numpy as np
import cv2

from src.stage1.data.palm_boxes import HandBBox


def crop_hand(
    image: np.ndarray,
    box: HandBBox,
    out_size: int = 224,
    rotation_deg: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Crop a hand region from image, optionally rotating.

    Args:
        image: (H, W, 3) numpy array.
        box: source bbox in image-pixel coords.
        out_size: output crop is (out_size, out_size, 3).
        rotation_deg: rotate the crop by this many degrees (positive = CCW).

    Returns:
        (crop, M) where M is the (2, 3) affine matrix mapping image coords
        → crop coords. To go the other way, use cv2.invertAffineTransform(M).
    """
    cx, cy = box.center()
    # Build affine: shift bbox center to crop center, scale to out_size, rotate.
    scale = out_size / max(box.w, box.h)
    # M takes image pixels → crop pixels.
    angle_rad = np.deg2rad(rotation_deg)
    cos_a = np.cos(angle_rad) * scale
    sin_a = np.sin(angle_rad) * scale
    M = np.array([
        [cos_a, -sin_a, out_size / 2 - cos_a * cx + sin_a * cy],
        [sin_a, cos_a, out_size / 2 - sin_a * cx - cos_a * cy],
    ], dtype=np.float32)
    crop = cv2.warpAffine(
        image, M, (out_size, out_size),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )
    return crop, M


def project_kpts(kpts: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Apply 2x3 affine to (N, 2) points. Used to bring labeled kpts into crop space."""
    n = kpts.shape[0]
    aug = np.concatenate([kpts, np.ones((n, 1), dtype=kpts.dtype)], axis=-1)
    return aug @ M.T  # (n, 2)


def unproject_kpts(crop_kpts: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Inverse: crop pixels → original image pixels."""
    M_inv = cv2.invertAffineTransform(M)
    return project_kpts(crop_kpts, M_inv)
