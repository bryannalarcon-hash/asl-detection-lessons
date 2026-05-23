"""HaGRID loader (v1, 512px version).

HaGRID provides hand bounding boxes + gesture class labels, annotated by
Yandex Toloka crowdworkers. No keypoint annotations, so this dataset is
ONLY used for Net 2 (palm detector) training, NOT Net 3.

We deliberately do NOT use HaGRID v2's 21-keypoint annotations because those
are derived from MediaPipe (pseudo-labels), which would violate Req 7.

Expected directory layout after extracting the 512px archive:
  data/hagrid/
    images/
      call/ABCD.jpg
      dislike/...
      ...18 gesture folders...
    annotations/
      train.json
      val.json
      test.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from torch.utils.data import Dataset

from src.stage1.data import schema as S
from src.stage1.data.palm_boxes import HandBBox


class HaGRIDDataset(Dataset):
    """HaGRID samples emit (image_path, palm_bboxes).

    Each annotation entry in HaGRID's JSON contains a list of bboxes per
    image with handedness ("right" / "left"). We pass them through as
    HandBBox objects in absolute image-pixel coords. Keypoint slots in
    the returned sample are all marked not-visible.
    """

    def __init__(self, root: str | Path, split: str = "train"):
        super().__init__()
        self.root = Path(root)
        ann_path = self.root / "annotations" / f"{split}.json"
        if not ann_path.exists():
            raise FileNotFoundError(f"HaGRID annotation file missing: {ann_path}")
        with ann_path.open() as f:
            data = json.load(f)
        self.samples: list[dict] = []
        # HaGRID JSON has one key per image filename → metadata dict with
        # "bboxes" (list of [x, y, w, h] in 0..1 normalized coords) and
        # "leading_hand" ("right" / "left") fields.
        for img_id, meta in data.items():
            boxes = meta.get("bboxes", [])
            if not boxes:
                continue
            label = meta.get("labels", [""])[0]
            image_path = self.root / "images" / label / f"{img_id}.jpg"
            self.samples.append({
                "image_id": img_id,
                "image_path": image_path,
                "norm_bboxes": boxes,
                "leading_hand": meta.get("leading_hand", "right"),
                "gesture": label,
            })

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        s = self.samples[idx]
        # We don't know image dims without reading; defer that to the consumer.
        # HaGRID stores normalized bboxes (0..1) so the consumer must multiply
        # by image dims before constructing pixel HandBBox.
        return {
            "image_path": str(s["image_path"]),
            "image_id": s["image_id"],
            "norm_bboxes": s["norm_bboxes"],  # list of [x, y, w, h] normalized
            "leading_hand": s["leading_hand"],
            "gesture": s["gesture"],
            # Keypoints unknown for HaGRID — emit empty so downstream code
            # can stitch with FreiHAND/COCO samples uniformly.
            "keypoints": np.zeros((S.NUM_KEYPOINTS, 2), dtype=np.float32),
            "visible": np.zeros(S.NUM_KEYPOINTS, dtype=np.int64),
        }


def hagrid_bboxes_to_pixel(norm_bboxes: list[list[float]],
                           img_w: int, img_h: int,
                           leading_hand: str = "right",
                           ) -> list[HandBBox]:
    """Convert HaGRID's normalized [x, y, w, h] to HandBBox pixel coords."""
    out: list[HandBBox] = []
    for i, (nx, ny, nw, nh) in enumerate(norm_bboxes):
        # When there are 2 boxes, the leading_hand convention from HaGRID
        # tells us which is the dominant hand; the other is the non-dominant.
        side = leading_hand if i == 0 else ("left" if leading_hand == "right" else "right")
        out.append(HandBBox(
            x=nx * img_w, y=ny * img_h, w=nw * img_w, h=nh * img_h, side=side,
        ))
    return out
