"""MPII Human Pose v1.0 loader mapped into our 49-keypoint schema.

MPII Human Pose (Andriluka et al., CVPR 2014) provides ~25K images with
~40K annotated people across 410 activities. Annotations are manual
crowdsourced keypoints — pre-MediaPipe, no pseudo-labels. Public research
license, hosted at http://human-pose.mpi-inf.mpg.de/.

We use the JSON port (rather than the original ``mpii_human_pose_v1_u12_1.mat``
file) because it is easier to consume and ships with the same 16-joint
layout. The expected JSON is a flat list of person annotations with the
following per-entry fields, matching the layout used by
``princeton-vl/pytorch_stacked_hourglass`` and most downstream MPII
benchmarks::

    {
      "image":      "099890470.jpg",
      "joints":     [[x0, y0], ..., [x15, y15]],   # 16 entries, may contain 0/-1 placeholders
      "joints_vis": [v0, ..., v15],                # 16 entries, 0/1 visibility
      "center":     [cx, cy],                      # optional, not used here
      "scale":      s,                             # optional, not used here
      "isValidation": 0 or 1                       # optional split flag
    }

Several JSON ports omit ``joints_vis`` and instead encode invisible joints
as ``[0, 0]`` or ``[-1, -1]``. Both encodings are accepted.

MPII 16-joint layout (canonical; from Andriluka 2014 / mpii_human_pose_v1_u12_1.mat)::

      0  r_ankle
      1  r_knee
      2  r_hip
      3  l_hip
      4  l_knee
      5  l_ankle
      6  pelvis
      7  thorax                  (~ chest_center)
      8  upper_neck              (~ neck)
      9  head_top
     10  r_wrist
     11  r_elbow
     12  r_shoulder              -> our RIGHT_SHOULDER (47)
     13  l_shoulder              -> our LEFT_SHOULDER  (46)
     14  l_elbow
     15  l_wrist

Spec note: the build brief stated "MPII 13 = right shoulder, MPII 12 = left
shoulder". That is inverted relative to the canonical MPII documentation
and every open-source MPII loader (Andriluka 2014, the official
mpii_human_pose_v1_u12_1.mat, AlphaPose, HRNet, pytorch_stacked_hourglass).
We follow the canonical convention (12=r_shoulder, 13=l_shoulder) so the
keypoints align anatomically with the COCO-WholeBody loader, which is the
source of our Net 1 majority data. This is documented in the SendMessage
reply to lead.

MPII -> our 49-kpt schema:
  - MPII 12  (r_shoulder)  -> 47 (RIGHT_SHOULDER)
  - MPII 13  (l_shoulder)  -> 46 (LEFT_SHOULDER)
  - MPII 7   (thorax)      -> 45 (CHEST_CENTER)         direct, when visible
  - MPII 8   (upper_neck)  -> 48 (NECK)                 direct, when visible
  - everything else        -> not assigned (mask = 0)

If MPII thorax/upper_neck are missing but both shoulders are present, we
derive CHEST_CENTER as the shoulder midpoint, matching the
``coco_wholebody.py`` convention. NECK is left unset in that case (no
nose available to anchor the midpoint derivation, since MPII does not
provide nose).

Face indices (NOSE=42, CHIN=43, FOREHEAD=44) are intentionally left
not-visible: MPII has no facial landmarks (head_top is the back of the
skull and a poor proxy for forehead). The training loss masks ignored
keypoints, so these unused slots cost nothing.

Hands (indices 0-41) are also left not-visible. MPII annotates only the
wrist as a single point; we never assign it to the hand block because
that would teach the model to mis-locate the wrist as kpt 0 (wrist of a
21-point hand) when only a body annotation exists.

The canonical class is ``MPIIHumanPoseDataset``. ``MPIIDataset`` is a
module-level alias kept so callers using the short name resolve to the
same implementation (avoids ImportError without forcing every consumer
to learn the full canonical name).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np
from torch.utils.data import Dataset

from src.stage1.data import schema as S


# MPII joint indices.
MPII_R_SHOULDER = 12
MPII_L_SHOULDER = 13
MPII_THORAX = 7
MPII_UPPER_NECK = 8
MPII_NUM_JOINTS = 16


class MPIIHumanPoseDataset(Dataset):
    """Loads MPII Human Pose v1.0 (JSON port) into our 49-keypoint schema.

    Yields one sample per labeled person. Multi-person images contribute
    multiple samples, matching how COCO-WholeBody is consumed.

    Args:
      ann_file: path to the JSON-port annotation file (list of per-person
        dicts). Typical filenames are ``train.json`` / ``valid.json`` /
        ``mpii_annotations.json``.
      image_root: directory containing MPII ``images/`` (each file matches
        the entry's ``image`` field, with no subdir nesting).
      split: optional filter against ``isValidation`` flag:
        - "train"     -> drop entries where isValidation == 1
        - "val"       -> keep only entries where isValidation == 1
        - "all"       -> keep everything (default)
        Entries lacking the field are kept regardless of the split filter.
      require_shoulder: if True (default), drop annotations with neither
        shoulder visible. Those teach the body keypoint detector nothing
        and the brief targets shoulder articulation.
    """

    def __init__(
        self,
        ann_file: str | Path,
        image_root: str | Path,
        split: str = "all",
        require_shoulder: bool = True,
    ) -> None:
        super().__init__()
        self.image_root = Path(image_root)
        ann_path = Path(ann_file)
        if not ann_path.exists():
            raise FileNotFoundError(f"MPII annotation file not found: {ann_path}")
        if split not in {"train", "val", "all"}:
            raise ValueError(f"unknown split: {split!r}")

        with ann_path.open() as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            raise ValueError(
                f"MPII JSON port expected to be a list of person entries; "
                f"got {type(raw).__name__} at {ann_path}"
            )

        self.samples: list[dict] = []
        for entry in raw:
            if not _matches_split(entry, split):
                continue
            joints, vis = _parse_joints(entry)
            if joints is None:
                continue
            if require_shoulder:
                if vis[MPII_R_SHOULDER] == 0 and vis[MPII_L_SHOULDER] == 0:
                    continue
            img_name = entry.get("image")
            if not img_name:
                continue
            self.samples.append({
                "image_path": self.image_root / img_name,
                "image_name": img_name,
                "joints": joints,
                "vis": vis,
            })

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        s = self.samples[idx]
        joints: np.ndarray = s["joints"]  # (16, 2)
        vis: np.ndarray = s["vis"]        # (16,)

        coords = np.zeros((S.NUM_KEYPOINTS, 2), dtype=np.float32)
        visible = np.zeros(S.NUM_KEYPOINTS, dtype=np.int64)

        if vis[MPII_R_SHOULDER] > 0:
            coords[S.RIGHT_SHOULDER] = joints[MPII_R_SHOULDER]
            visible[S.RIGHT_SHOULDER] = 1
        if vis[MPII_L_SHOULDER] > 0:
            coords[S.LEFT_SHOULDER] = joints[MPII_L_SHOULDER]
            visible[S.LEFT_SHOULDER] = 1

        # Prefer MPII's thorax for chest_center; fall back to shoulder midpoint.
        if vis[MPII_THORAX] > 0:
            coords[S.CHEST_CENTER] = joints[MPII_THORAX]
            visible[S.CHEST_CENTER] = 1
        elif visible[S.LEFT_SHOULDER] > 0 and visible[S.RIGHT_SHOULDER] > 0:
            coords[S.CHEST_CENTER] = (
                coords[S.LEFT_SHOULDER] + coords[S.RIGHT_SHOULDER]
            ) / 2.0
            visible[S.CHEST_CENTER] = 1

        if vis[MPII_UPPER_NECK] > 0:
            coords[S.NECK] = joints[MPII_UPPER_NECK]
            visible[S.NECK] = 1

        return {
            "image_path": str(s["image_path"]),
            "image_id": s["image_name"],
            "image_width": 0,   # MPII JSON port lacks dims; consumer reads from disk
            "image_height": 0,
            "keypoints": coords,
            "visible": visible,
        }


def _matches_split(entry: dict, split: str) -> bool:
    if split == "all":
        return True
    flag = entry.get("isValidation")
    if flag is None:
        return True
    is_val = bool(flag)
    if split == "val":
        return is_val
    return not is_val  # "train"


def _parse_joints(entry: dict) -> tuple[np.ndarray | None, np.ndarray]:
    """Extract a (16, 2) joints array + (16,) visibility array from one entry.

    Returns (None, ...) if the entry is malformed. Visibility falls back
    to "missing if coords are exactly (0,0) or any negative" when the JSON
    port omits joints_vis.
    """
    raw_joints = entry.get("joints")
    if raw_joints is None:
        return None, np.zeros(MPII_NUM_JOINTS, dtype=np.int64)
    joints = np.asarray(raw_joints, dtype=np.float32)
    if joints.ndim != 2 or joints.shape[0] != MPII_NUM_JOINTS or joints.shape[1] < 2:
        return None, np.zeros(MPII_NUM_JOINTS, dtype=np.int64)
    joints = joints[:, :2]

    vis_raw: Sequence[float] | None = entry.get("joints_vis")
    if vis_raw is not None:
        vis_arr = np.asarray(vis_raw, dtype=np.float32).reshape(-1)
        if vis_arr.shape[0] != MPII_NUM_JOINTS:
            vis = _infer_vis_from_coords(joints)
        else:
            vis = (vis_arr > 0).astype(np.int64)
    else:
        vis = _infer_vis_from_coords(joints)

    return joints, vis


def _infer_vis_from_coords(joints: np.ndarray) -> np.ndarray:
    """Treat (0,0) or any negative coordinate as a missing joint."""
    nonzero = (joints[:, 0] != 0) | (joints[:, 1] != 0)
    nonneg = (joints[:, 0] >= 0) & (joints[:, 1] >= 0)
    return (nonzero & nonneg).astype(np.int64)


# Short-name alias; see module docstring.
MPIIDataset = MPIIHumanPoseDataset
