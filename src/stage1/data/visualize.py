"""Render keypoints onto images for visual sanity-checking the loaders."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from src.stage1.data import schema as S


_COLOR_RIGHT_HAND = (255, 60, 60)
_COLOR_LEFT_HAND = (60, 60, 255)
_COLOR_FACE = (60, 220, 60)
_COLOR_BODY = (255, 220, 0)


def draw_keypoints(
    image_path: str | Path,
    keypoints: np.ndarray,
    visible: np.ndarray,
    out_path: str | Path,
    radius: int = 4,
) -> None:
    """Render the unified-schema keypoints on top of the source image."""
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    for i in range(S.NUM_KEYPOINTS):
        if not visible[i]:
            continue
        x, y = float(keypoints[i, 0]), float(keypoints[i, 1])
        color = _color_for(i)
        draw.ellipse(
            [(x - radius, y - radius), (x + radius, y + radius)],
            outline=color,
            width=2,
        )
        # Index label, small.
        draw.text((x + radius + 2, y - radius), str(i), fill=color)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def _color_for(idx: int) -> tuple[int, int, int]:
    if idx in S.HAND_INDICES_RIGHT:
        return _COLOR_RIGHT_HAND
    if idx in S.HAND_INDICES_LEFT:
        return _COLOR_LEFT_HAND
    if idx in S.FACE_INDICES:
        return _COLOR_FACE
    return _COLOR_BODY
