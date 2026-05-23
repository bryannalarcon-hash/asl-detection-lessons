"""Rendered Hand Pose Dataset (RHD) loader.

RHD is a fully synthetic, renderer-grounded 21-keypoint hand dataset from
Freiburg (Zimmermann & Brox, ICCV 2017). It ships ~41,258 training and
~2,728 evaluation frames at 320 x 320 resolution. Because labels come from
the renderer, they are clean of any MediaPipe-derived bias and satisfy
Req 7 (no MediaPipe-derived data, no pretrained weights).

Each sample may contain a left hand, a right hand, or both. Two hands are
common; we emit each labeled hand into its corresponding RIGHT_HAND or
LEFT_HAND slot of the unified 49-keypoint schema.

Expected layout on disk (created by `scripts/download_rhd.sh`):
    data/RHD_published_v2/
        training/
            color/00000.png ... 00041257.png
            mask/00000.png  ...
            depth/00000.png ...
            anno_training.pickle
        evaluation/
            color/00000.png ... 00002727.png
            mask/...
            depth/...
            anno_evaluation.pickle

Annotation pickle format (per sample, keyed by int id):
    {
        "uv_vis": np.ndarray (42, 3),     # (u, v, vis) per keypoint
                                           # rows 0..20  = LEFT hand
                                           # rows 21..41 = RIGHT hand
        "xyz":    np.ndarray (42, 3),     # 3D camera coords (mm)
        "K":      np.ndarray (3, 3),      # intrinsics
    }

The 21 in-hand keypoints in RHD follow the order
    0   wrist
    1-4   thumb  (tip, DIP-equivalent, PIP-equivalent, MCP)  -- tip-to-root
    5-8   index  (tip, DIP, PIP, MCP)
    9-12  middle (tip, DIP, PIP, MCP)
    13-16 ring   (tip, DIP, PIP, MCP)
    17-20 pinky  (tip, DIP, PIP, MCP)
which is tip-to-root within each finger. Our schema uses MediaPipe-style
root-to-tip ordering, so each finger group is reversed via `RHD_TO_MP`.

Sample contract (matches `src/stage1/data/freihand.py`):
    {
        "image_path": str,
        "image_id":   int,
        "image_width":  320,
        "image_height": 320,
        "keypoints": np.ndarray (49, 2) float32,  # image-pixel coords
        "visible":   np.ndarray (49,)   int64,    # 0/1
    }
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from torch.utils.data import Dataset

from src.stage1.data import schema as S


_IMAGE_SIZE = 320  # RHD ships at fixed 320 x 320

# Reverse each finger group; wrist stays put. RHD orders tip-to-root within
# every finger, our schema orders root-to-tip.
RHD_TO_MP: list[int] = [0] + [
    base + offset
    for base in (1, 5, 9, 13, 17)
    for offset in (3, 2, 1, 0)
]
assert len(RHD_TO_MP) == 21
assert sorted(RHD_TO_MP) == list(range(21))


class RHDDataset(Dataset):
    """Rendered Hand Pose Dataset adapter.

    Emits unified 49-keypoint schema samples. Both hands populated when
    both are labeled visible by the renderer.

    Args:
        root: dataset root containing `training/` and `evaluation/`.
        split: "training" or "evaluation".
        min_visible_per_hand: drop hands with fewer than this many visible
            keypoints. A hand with 0 visible keypoints is unlabeled in this
            frame and must be left out of the unified-schema slot so the
            consumer treats it as not-visible rather than as a noisy
            all-zeros target.
    """

    def __init__(
        self,
        root: str | Path,
        split: str = "training",
        min_visible_per_hand: int = 3,
    ) -> None:
        super().__init__()
        if split not in ("training", "evaluation"):
            raise ValueError(f"unknown RHD split: {split!r}")
        self.root = Path(root)
        self.split = split
        self.min_visible_per_hand = int(min_visible_per_hand)
        self.image_dir = self.root / split / "color"
        anno_path = self.root / split / f"anno_{split}.pickle"
        if not self.image_dir.exists():
            raise FileNotFoundError(f"RHD images not found at {self.image_dir}")
        if not anno_path.exists():
            raise FileNotFoundError(f"RHD annotations not found at {anno_path}")

        with anno_path.open("rb") as f:
            raw = pickle.load(f)

        # Keep only frames with at least one usable hand. Sort by id so
        # iteration order is deterministic across runs.
        self.sample_ids: list[int] = []
        self.samples_by_id: dict[int, dict] = {}
        for sid in sorted(raw.keys()):
            entry = raw[sid]
            uv_vis = np.asarray(entry["uv_vis"], dtype=np.float32)
            # Shape sanity: must be (42, 3).
            if uv_vis.shape != (42, 3):
                continue
            left_vis_count = int(uv_vis[:21, 2].sum())
            right_vis_count = int(uv_vis[21:, 2].sum())
            if (left_vis_count < self.min_visible_per_hand
                    and right_vis_count < self.min_visible_per_hand):
                continue
            self.sample_ids.append(int(sid))
            self.samples_by_id[int(sid)] = {
                "uv_vis": uv_vis,
                "left_ok": left_vis_count >= self.min_visible_per_hand,
                "right_ok": right_vis_count >= self.min_visible_per_hand,
            }

    def __len__(self) -> int:
        return len(self.sample_ids)

    def __getitem__(self, idx: int) -> dict:
        sid = self.sample_ids[idx]
        s = self.samples_by_id[sid]
        uv_vis = s["uv_vis"]

        # Per-hand chunks. RHD packs LEFT first then RIGHT.
        left_uv = uv_vis[:21, :2]
        left_vis = uv_vis[:21, 2]
        right_uv = uv_vis[21:, :2]
        right_vis = uv_vis[21:, 2]

        # Reorder each finger group from tip-to-root (RHD) to root-to-tip (MP).
        left_uv_mp = left_uv[RHD_TO_MP]
        left_vis_mp = left_vis[RHD_TO_MP]
        right_uv_mp = right_uv[RHD_TO_MP]
        right_vis_mp = right_vis[RHD_TO_MP]

        coords = np.zeros((S.NUM_KEYPOINTS, 2), dtype=np.float32)
        visible = np.zeros(S.NUM_KEYPOINTS, dtype=np.int64)
        if s["right_ok"]:
            coords[S.RIGHT_HAND_START:S.RIGHT_HAND_START + 21] = right_uv_mp
            visible[S.RIGHT_HAND_START:S.RIGHT_HAND_START + 21] = (
                right_vis_mp > 0.5
            ).astype(np.int64)
        if s["left_ok"]:
            coords[S.LEFT_HAND_START:S.LEFT_HAND_START + 21] = left_uv_mp
            visible[S.LEFT_HAND_START:S.LEFT_HAND_START + 21] = (
                left_vis_mp > 0.5
            ).astype(np.int64)

        image_path = self.image_dir / f"{sid:05d}.png"

        return {
            "image_path": str(image_path),
            "image_id": sid,
            "image_width": _IMAGE_SIZE,
            "image_height": _IMAGE_SIZE,
            "keypoints": coords,
            "visible": visible,
        }
