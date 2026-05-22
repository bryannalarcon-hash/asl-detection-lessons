"""Net 3 (hand landmark) training dataset.

Wraps FreiHAND + InterHand2.6M. Each sample is ONE hand crop:
  - 224x224 RGB tensor (rotated padded crop)
  - 21 keypoints in crop-pixel coords
  - visibility mask (21,)

We crop using GROUND-TRUTH bboxes with optional jitter for training-time
bbox-imperfection robustness. Phase 2 (after Net 2 is trained) can mix in
Net 2's predicted bboxes via the prediction cache.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from src.stage1.data import schema as S
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.interhand import InterHand26MDataset
from src.stage1.data.palm_boxes import (
    HandBBox, palm_bbox, jitter_bbox,
)
from src.stage1.data.hand_crops import crop_hand, project_kpts


class LandmarkTrainDataset(Dataset):
    """Per-sample: one hand crop + 21 kpts.

    Expansion factor: each source sample with N labeled hands becomes
    N training samples (we yield per-hand). FreiHAND is always 1 hand;
    InterHand2.6M is up to 2.
    """

    def __init__(self,
                 freihand: FreiHANDDataset,
                 interhand: InterHand26MDataset | None,
                 crop_size: int = 224,
                 padding_frac: float = 0.5,
                 jitter_shift: float = 0.10,
                 jitter_scale: float = 0.15,
                 jitter_rot: float = 10.0,
                 phase2_bbox_cache: str | Path | None = None,
                 phase2_mix_prob: float = 0.5):
        super().__init__()
        self.crop_size = crop_size
        self.padding_frac = padding_frac
        self.jitter_shift = jitter_shift
        self.jitter_scale = jitter_scale
        self.jitter_rot = jitter_rot
        self.items: list[tuple[str, int, str]] = []
        for i in range(len(freihand)):
            self.items.append(("freihand", i, "right"))
        if interhand is not None:
            for i in range(len(interhand)):
                self.items.append(("interhand", i, "right"))
                self.items.append(("interhand", i, "left"))
        self._freihand = freihand
        self._interhand = interhand
        self.phase2_bbox = {}
        if phase2_bbox_cache and Path(phase2_bbox_cache).exists():
            with open(phase2_bbox_cache) as f:
                self.phase2_bbox = json.load(f)
        self.phase2_mix_prob = phase2_mix_prob

    def __len__(self) -> int:
        return len(self.items)

    def _load_sample(self, source: str, local_idx: int) -> dict:
        if source == "freihand":
            return self._freihand[local_idx]
        return self._interhand[local_idx]

    def __getitem__(self, idx: int) -> dict:
        source, local, side = self.items[idx]
        sample = self._load_sample(source, local)

        if side == "right":
            slot = slice(S.RIGHT_HAND_START, S.RIGHT_HAND_START + 21)
        else:
            slot = slice(S.LEFT_HAND_START, S.LEFT_HAND_START + 21)
        coords = sample["keypoints"][slot]
        visible = sample["visible"][slot]
        if visible.sum() < 3:
            return self._empty()

        rng = np.random.default_rng(idx)
        use_phase2 = (str(sample.get("image_id")) in self.phase2_bbox
                      and rng.random() < self.phase2_mix_prob)
        if use_phase2:
            cached = self.phase2_bbox[str(sample["image_id"])]
            box = HandBBox(*cached[:4], side=side)
        else:
            box = palm_bbox(coords, visible, side=side, pad=self.padding_frac)
            if box is None:
                return self._empty()
            box = jitter_bbox(box, shift_frac=self.jitter_shift,
                              scale_frac=self.jitter_scale, rng=rng)

        rot_deg = float(rng.uniform(-self.jitter_rot, self.jitter_rot))

        img = cv2.imread(sample["image_path"])
        if img is None:
            return self._empty()
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        crop, M = crop_hand(img, box, out_size=self.crop_size, rotation_deg=rot_deg)
        kpts_in_crop = project_kpts(coords, M)

        crop_tensor = torch.from_numpy(crop).permute(2, 0, 1).float() / 255.0
        crop_tensor = (crop_tensor - 0.5) / 0.5

        return {
            "image": crop_tensor,
            "keypoints": torch.from_numpy(kpts_in_crop).float(),
            "visible": torch.from_numpy(visible.astype(np.float32)),
            "hand_side": side,
            "image_id": sample.get("image_id", idx),
        }

    def _empty(self) -> dict:
        return {
            "image": torch.zeros(3, self.crop_size, self.crop_size),
            "keypoints": torch.zeros(21, 2),
            "visible": torch.zeros(21),
            "hand_side": "none",
            "image_id": -1,
        }
