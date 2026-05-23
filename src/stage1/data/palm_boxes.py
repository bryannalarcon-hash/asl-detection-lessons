"""Derive palm bounding boxes from labeled hand keypoints (BlazePalm-style).

Used by:
- Net 2 (palm detector) training: GT bbox per labeled hand
- Net 3 (hand landmark) training: crop region per labeled hand
- Inference time: Net 2's predicted bbox feeds Net 3's crop

BlazePalm trains on the *palm* (wrist + 5 MCPs), not the full hand. This is
more stable across hand poses than a tight box around all 21 keypoints
(fingertips spread vs. closed changes the bbox dramatically).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.stage1.data import schema as S


PALM_KP_LOCAL = [0, 1, 5, 9, 13, 17]  # wrist + thumb-CMC + 4 finger-MCPs


@dataclass
class HandBBox:
    x: float          # top-left x in image pixels
    y: float
    w: float
    h: float
    side: str         # "right" or "left"

    def to_xywh(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.w, self.h

    def to_xyxy(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.x + self.w, self.y + self.h

    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2


def palm_bbox(
    coords: np.ndarray,
    visible: np.ndarray,
    side: str,
    pad: float = 0.5,
    square: bool = True,
) -> HandBBox | None:
    """Derive a palm bbox from one hand's 21 keypoints.

    coords: (21, 2) array of (x, y) for ONE hand in image pixel coords.
    visible: (21,) array of 0/1.
    pad: fractional padding of the longest side (0.5 = +50%).

    Returns None if fewer than 3 palm landmarks visible.
    """
    palm_pts = []
    for idx in PALM_KP_LOCAL:
        if visible[idx]:
            palm_pts.append(coords[idx])
    if len(palm_pts) < 3:
        return None
    pts = np.asarray(palm_pts, dtype=np.float32)
    x_min, y_min = float(pts[:, 0].min()), float(pts[:, 1].min())
    x_max, y_max = float(pts[:, 0].max()), float(pts[:, 1].max())
    w, h = x_max - x_min, y_max - y_min
    if w <= 0 or h <= 0:
        return None
    cx, cy = (x_min + x_max) / 2, (y_min + y_max) / 2
    long_side = max(w, h)
    half = long_side * (1 + pad) / 2
    new_x = cx - half
    new_y = cy - half
    new_w = new_h = 2 * half
    if not square:
        # Keep aspect of palm pts but apply pad uniformly to both axes.
        half_w = w * (1 + pad) / 2
        half_h = h * (1 + pad) / 2
        new_x = cx - half_w
        new_y = cy - half_h
        new_w = 2 * half_w
        new_h = 2 * half_h
    return HandBBox(new_x, new_y, new_w, new_h, side=side)


def palm_bbox_for_each_hand(coords: np.ndarray, visible: np.ndarray,
                            pad: float = 0.5) -> list[HandBBox]:
    """Wrapper: return up to 2 bboxes (right + left) for a 49-kpt sample."""
    out: list[HandBBox] = []
    right_coords = coords[S.RIGHT_HAND_START:S.RIGHT_HAND_START + 21]
    right_vis = visible[S.RIGHT_HAND_START:S.RIGHT_HAND_START + 21]
    box = palm_bbox(right_coords, right_vis, side="right", pad=pad)
    if box is not None:
        out.append(box)
    left_coords = coords[S.LEFT_HAND_START:S.LEFT_HAND_START + 21]
    left_vis = visible[S.LEFT_HAND_START:S.LEFT_HAND_START + 21]
    box = palm_bbox(left_coords, left_vis, side="left", pad=pad)
    if box is not None:
        out.append(box)
    return out


def jitter_bbox(box: HandBBox, shift_frac: float = 0.1,
                scale_frac: float = 0.15, rng: np.random.Generator | None = None
                ) -> HandBBox:
    """Randomly jitter a bbox for Net 3 training-time robustness.

    shift_frac and scale_frac are relative to the bbox size.
    """
    rng = rng or np.random.default_rng()
    sx = float(rng.uniform(-shift_frac, shift_frac)) * box.w
    sy = float(rng.uniform(-shift_frac, shift_frac)) * box.h
    s = 1 + float(rng.uniform(-scale_frac, scale_frac))
    cx, cy = box.center()
    new_w = box.w * s
    new_h = box.h * s
    new_x = cx + sx - new_w / 2
    new_y = cy + sy - new_h / 2
    return HandBBox(new_x, new_y, new_w, new_h, side=box.side)


def iou(box_a: HandBBox, box_b: HandBBox) -> float:
    ax1, ay1, ax2, ay2 = box_a.to_xyxy()
    bx1, by1, bx2, by2 = box_b.to_xyxy()
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter = inter_w * inter_h
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0
