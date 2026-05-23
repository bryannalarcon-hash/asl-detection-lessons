"""COCO-WholeBody loader mapped into our 49-keypoint schema."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np
from torch.utils.data import Dataset

from src.stage1.data import schema as S


class CocoWholeBodyDataset(Dataset):
    """Loads COCO-WholeBody and emits (image_path, keypoints_xy, visible).

    Multi-person images: we keep the annotation with the largest bbox area,
    matching the "primary subject" assumption for our learner-webcam use case.

    Each sample is one annotation. We filter annotations that have neither
    valid hands nor a valid face, since those teach the detector nothing.
    """

    def __init__(
        self,
        ann_file: str | Path,
        image_root: str | Path,
        require_face_or_hand: bool = True,
    ) -> None:
        super().__init__()
        self.image_root = Path(image_root)
        ann_path = Path(ann_file)
        if not ann_path.exists():
            raise FileNotFoundError(f"COCO annotation file not found: {ann_path}")

        with ann_path.open() as f:
            data = json.load(f)

        images_by_id = {img["id"]: img for img in data["images"]}

        # Pick the largest annotation per image.
        per_image: dict[int, dict] = {}
        for ann in data["annotations"]:
            if ann.get("num_keypoints", 0) == 0:
                continue
            if require_face_or_hand and not (
                ann.get("face_valid", False)
                or ann.get("lefthand_valid", False)
                or ann.get("righthand_valid", False)
            ):
                continue
            area = ann.get("bbox", [0, 0, 0, 0])[2] * ann.get("bbox", [0, 0, 0, 0])[3]
            if area <= 0:
                continue
            existing = per_image.get(ann["image_id"])
            if existing is None or area > existing["_area"]:
                ann["_area"] = area
                per_image[ann["image_id"]] = ann

        self.samples: list[dict] = []
        for img_id, ann in per_image.items():
            img_meta = images_by_id.get(img_id)
            if img_meta is None:
                continue
            self.samples.append({
                "image_path": self.image_root / img_meta["file_name"],
                "ann": ann,
                "image_id": img_id,
                "width": img_meta["width"],
                "height": img_meta["height"],
            })

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        sample = self.samples[idx]
        ann = sample["ann"]

        coords = np.zeros((S.NUM_KEYPOINTS, 2), dtype=np.float32)
        visible = np.zeros(S.NUM_KEYPOINTS, dtype=np.int64)

        body = _read_kpts(ann["keypoints"], 17)
        right_hand = _read_kpts(ann.get("righthand_kpts", []), 21)
        left_hand = _read_kpts(ann.get("lefthand_kpts", []), 21)
        face = _read_kpts(ann.get("face_kpts", []), 68)

        # Hands map directly (same MediaPipe-style ordering).
        if ann.get("righthand_valid", False) and right_hand is not None:
            _assign_block(coords, visible, S.RIGHT_HAND_START, right_hand)
        if ann.get("lefthand_valid", False) and left_hand is not None:
            _assign_block(coords, visible, S.LEFT_HAND_START, left_hand)

        # Face/body anchors.
        if body is not None:
            _assign_one(coords, visible, S.NOSE, body[0])
            _assign_one(coords, visible, S.LEFT_SHOULDER, body[5])
            _assign_one(coords, visible, S.RIGHT_SHOULDER, body[6])
            # Derived: chest_center = midpoint of shoulders.
            if body[5, 2] > 0 and body[6, 2] > 0:
                mid = (body[5, :2] + body[6, :2]) / 2.0
                coords[S.CHEST_CENTER] = mid
                visible[S.CHEST_CENTER] = 1
                # Derived: neck = midpoint of nose and chest_center.
                if body[0, 2] > 0:
                    neck = (body[0, :2] + mid) / 2.0
                    coords[S.NECK] = neck
                    visible[S.NECK] = 1

        if ann.get("face_valid", False) and face is not None:
            # chin = face_landmark[8] (bottom of jaw contour)
            _assign_one(coords, visible, S.CHIN, face[8])
            # forehead = midpoint of innermost eyebrows (idx 21 and 22)
            if face[21, 2] > 0 and face[22, 2] > 0:
                forehead = (face[21, :2] + face[22, :2]) / 2.0
                coords[S.FOREHEAD] = forehead
                visible[S.FOREHEAD] = 1

        return {
            "image_path": str(sample["image_path"]),
            "image_id": sample["image_id"],
            "image_width": sample["width"],
            "image_height": sample["height"],
            "keypoints": coords,
            "visible": visible,
        }


def _read_kpts(flat: Sequence[float], expected: int) -> np.ndarray | None:
    """Parse COCO-style flat keypoint list [x1,y1,v1,x2,y2,v2,...]."""
    if not flat:
        return None
    arr = np.array(flat, dtype=np.float32).reshape(-1, 3)
    if arr.shape[0] != expected:
        return None
    return arr


def _assign_block(coords: np.ndarray, visible: np.ndarray, start: int,
                  block: np.ndarray) -> None:
    n = block.shape[0]
    coords[start:start + n] = block[:, :2]
    visible[start:start + n] = (block[:, 2] > 0).astype(np.int64)


def _assign_one(coords: np.ndarray, visible: np.ndarray, idx: int,
                kp: np.ndarray) -> None:
    if kp[2] > 0:
        coords[idx] = kp[:2]
        visible[idx] = 1
