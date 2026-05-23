"""InterHand2.6M (5fps subset) loader.

Provides two-hand interaction images with marker-based MoCap 21-kpt
annotations per hand. Used by Net 3 (hand landmark) training to expand
beyond FreiHAND's single-hand right-hand-only coverage.

Expected layout after pulling from Meta's S3 bucket + the annotation Drive:
  data/interhand/
    images/
      train/Capture0/ROM01_No_Interaction_2_Finger/cam400262/image00000.jpg
      ...
    annotations/
      train/InterHand2.6M_train_data.json
      train/InterHand2.6M_train_joint_3d.json
      train/InterHand2.6M_train_camera.json
      train/InterHand2.6M_train_MANO_NeuralAnnot.json
      (and val/test/ equivalents)

InterHand uses MANO keypoint ordering. We remap to our MediaPipe-style
ordering (shared via schema.MANO_TO_MP).

The annotation file marks each frame's `hand_type` as one of:
    "right"        single right hand visible
    "left"         single left hand visible
    "interacting"  both hands interacting (often heavily occluded studio
                   close-ups that don't match the front-of-webcam ASL
                   distribution)

Use `hand_types=("right", "left")` (or the convenience constructor
`InterHand26MDataset.single_hand_subset(...)`) to drop the interacting
subset for Net 3 training.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from torch.utils.data import Dataset

from src.stage1.data import schema as S


ALL_HAND_TYPES: tuple[str, ...] = ("right", "left", "interacting")
SINGLE_HAND_TYPES: tuple[str, ...] = ("right", "left")


class InterHand26MDataset(Dataset):
    """InterHand2.6M loader emitting unified-schema samples.

    Each sample contains: image_path, 49-kpt keypoints (right + left hands
    filled, face/body marked not-visible), visibility flags. Bboxes derived
    from keypoints by the consumer via palm_boxes.palm_bbox_for_each_hand.

    Args:
        root: dataset root containing `images/` and `annotations/`.
        split: "train" / "val" / "test".
        max_samples: cap on number of accepted samples (post-filter).
        hand_types: which `hand_type` values to keep. Defaults to all three;
            pass `SINGLE_HAND_TYPES` to drop interacting-hand frames.
    """

    def __init__(self, root: str | Path, split: str = "train",
                 max_samples: int | None = None,
                 hand_types: tuple[str, ...] = ALL_HAND_TYPES):
        super().__init__()
        self.root = Path(root)
        allowed = set(hand_types)
        unknown = allowed - set(ALL_HAND_TYPES)
        if unknown:
            raise ValueError(
                f"unknown hand_types {sorted(unknown)}; "
                f"expected subset of {ALL_HAND_TYPES}"
            )
        self.hand_types = tuple(sorted(allowed))
        ann_dir = self.root / "annotations" / split
        data_json = ann_dir / f"InterHand2.6M_{split}_data.json"
        joint3d_json = ann_dir / f"InterHand2.6M_{split}_joint_3d.json"
        camera_json = ann_dir / f"InterHand2.6M_{split}_camera.json"
        for p in (data_json, joint3d_json, camera_json):
            if not p.exists():
                raise FileNotFoundError(f"InterHand annotation missing: {p}")

        with data_json.open() as f:
            meta = json.load(f)
        with joint3d_json.open() as f:
            self.joint3d = json.load(f)
        with camera_json.open() as f:
            self.cams = json.load(f)

        # `images` and `annotations` follow COCO-style structure.
        images_by_id = {im["id"]: im for im in meta["images"]}
        self.samples: list[dict] = []
        for ann in meta["annotations"]:
            if max_samples and len(self.samples) >= max_samples:
                break
            hand_type = ann.get("hand_type", "interacting")
            if hand_type not in allowed:
                continue
            img_id = ann["image_id"]
            img = images_by_id.get(img_id)
            if not img:
                continue
            capture_id = str(img["capture"])
            seq_name = img["seq_name"]
            cam_id = img["camera"]
            frame_idx = img["frame_idx"]
            # 3D joints lookup: keyed by capture, then frame_idx.
            joints_3d = (self.joint3d.get(capture_id, {})
                                     .get(str(frame_idx), {}))
            if "world_coord" not in joints_3d:
                continue
            world_coord = np.asarray(joints_3d["world_coord"], dtype=np.float32)
            # world_coord shape: (42, 3) — right hand 0–20, left hand 21–41
            cam_block = (self.cams.get(capture_id, {})
                                  .get("campos", {}).get(str(cam_id)))
            if cam_block is None:
                continue
            R = np.asarray(self.cams[capture_id]["camrot"][str(cam_id)],
                           dtype=np.float32)
            t = np.asarray(self.cams[capture_id]["campos"][str(cam_id)],
                           dtype=np.float32)
            focal = np.asarray(self.cams[capture_id]["focal"][str(cam_id)],
                               dtype=np.float32)
            princpt = np.asarray(self.cams[capture_id]["princpt"][str(cam_id)],
                                 dtype=np.float32)
            # `hand_valid` is the per-hand label-presence flag [right, left].
            # For single-hand frames we still trust hand_valid for the active
            # side; for interacting frames both should be 1.
            hand_valid = ann.get("hand_valid", None)
            if hand_valid is None:
                if hand_type == "right":
                    hand_valid = [1, 0]
                elif hand_type == "left":
                    hand_valid = [0, 1]
                else:
                    hand_valid = [1, 1]
            self.samples.append({
                "image_path": (self.root / "images" / split / f"Capture{capture_id}"
                               / seq_name / f"cam{cam_id}"
                               / f"image{frame_idx:05d}.jpg"),
                "world_coord": world_coord,
                "R": R, "t": t, "focal": focal, "princpt": princpt,
                "image_id": img_id,
                "image_width": img["width"],
                "image_height": img["height"],
                "valid": hand_valid,
                "hand_type": hand_type,
            })

    @classmethod
    def single_hand_subset(
        cls,
        root: str | Path,
        split: str = "train",
        max_samples: int | None = None,
    ) -> "InterHand26MDataset":
        """Factory: load only frames where exactly one hand is visible.

        Drops `hand_type == "interacting"` frames. These are the studio
        two-hand close-ups that don't match our front-of-webcam ASL signing
        distribution and that drag the trained landmark net off-domain.
        """
        return cls(root=root, split=split, max_samples=max_samples,
                   hand_types=SINGLE_HAND_TYPES)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        s = self.samples[idx]
        # Project world → camera → pixel.
        # cam_coord = R @ (world - t)
        rel = s["world_coord"] - s["t"][None]  # (42, 3)
        cam_coord = rel @ s["R"].T            # (42, 3)
        # Pinhole projection.
        z = cam_coord[:, 2:3]
        z = np.where(np.abs(z) < 1e-6, 1e-6, z)
        uv = cam_coord[:, :2] / z * s["focal"][None] + s["princpt"][None]

        coords = np.zeros((S.NUM_KEYPOINTS, 2), dtype=np.float32)
        visible = np.zeros(S.NUM_KEYPOINTS, dtype=np.int64)

        # InterHand: 0–20 right hand (MANO order), 21–41 left hand (MANO order)
        # We need MediaPipe-style ordering. The MANO→MP permutation is the
        # same one used by FreiHAND (defined in schema.MANO_TO_MP).
        right_uv = uv[:21][S.MANO_TO_MP]
        left_uv = uv[21:][S.MANO_TO_MP]

        if s["valid"][0]:
            coords[S.RIGHT_HAND_START:S.RIGHT_HAND_START + 21] = right_uv
            visible[S.RIGHT_HAND_START:S.RIGHT_HAND_START + 21] = 1
        if s["valid"][1]:
            coords[S.LEFT_HAND_START:S.LEFT_HAND_START + 21] = left_uv
            visible[S.LEFT_HAND_START:S.LEFT_HAND_START + 21] = 1

        return {
            "image_path": str(s["image_path"]),
            "image_id": s["image_id"],
            "image_width": s["image_width"],
            "image_height": s["image_height"],
            "keypoints": coords,
            "visible": visible,
        }
