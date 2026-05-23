"""Unified 35-style keypoint schema used by Stage 1.

The detector learns to predict K keypoints in a fixed order. Every source
dataset is mapped into this layout at load time so the rest of the pipeline
sees a single tensor shape.

Layout (49 keypoints):
  0  – 20 : right hand (MediaPipe-style ordering — wrist + 4 per finger × 5)
  21 – 41 : left hand  (same ordering as right)
  42      : nose
  43      : chin
  44      : forehead   (derived: midpoint of inner eyebrows)
  45      : chest_center (derived: midpoint of shoulders)
  46      : left_shoulder
  47      : right_shoulder
  48      : neck       (derived: midpoint of nose and chest_center)

Hand keypoint ordering (within each hand, 0–20):
  0  wrist
  1–4   thumb       (CMC, MCP, IP, tip)
  5–8   index       (MCP, PIP, DIP, tip)
  9–12  middle      (MCP, PIP, DIP, tip)
  13–16 ring        (MCP, PIP, DIP, tip)
  17–20 pinky       (MCP, PIP, DIP, tip)
"""
from __future__ import annotations

from dataclasses import dataclass

NUM_KEYPOINTS = 49

RIGHT_HAND_START = 0
LEFT_HAND_START = 21
NOSE = 42
CHIN = 43
FOREHEAD = 44
CHEST_CENTER = 45
LEFT_SHOULDER = 46
RIGHT_SHOULDER = 47
NECK = 48

HAND_INDICES_RIGHT = list(range(RIGHT_HAND_START, RIGHT_HAND_START + 21))
HAND_INDICES_LEFT = list(range(LEFT_HAND_START, LEFT_HAND_START + 21))
FACE_INDICES = [NOSE, CHIN, FOREHEAD]
BODY_INDICES = [CHEST_CENTER, LEFT_SHOULDER, RIGHT_SHOULDER, NECK]

# Symmetric pairs for horizontal-flip augmentation.
# When the image is flipped horizontally, these pairs must be swapped.
FLIP_PAIRS: list[tuple[int, int]] = [
    # right_hand[i] <-> left_hand[i]
    *[(RIGHT_HAND_START + i, LEFT_HAND_START + i) for i in range(21)],
    # left/right shoulder
    (LEFT_SHOULDER, RIGHT_SHOULDER),
]

KEYPOINT_NAMES = (
    [f"right_hand_{i}" for i in range(21)]
    + [f"left_hand_{i}" for i in range(21)]
    + ["nose", "chin", "forehead", "chest_center", "left_shoulder",
       "right_shoulder", "neck"]
)
assert len(KEYPOINT_NAMES) == NUM_KEYPOINTS

# --------------------------------------------------------------------------
# Mappings from source datasets.
# --------------------------------------------------------------------------

# COCO-WholeBody (133 keypoints): body[0-16] + foot[17-22] + face[23-90] +
# left_hand[91-111] + right_hand[112-132].
#
# In COCO's body skeleton, "left" and "right" refer to the PERSON's left/right
# (their actual anatomy). We keep that convention: our LEFT_HAND_START holds
# the person's left hand, etc.
COCO_WB_BODY_OFFSET = 0
COCO_WB_FACE_OFFSET = 23
COCO_WB_LEFT_HAND_OFFSET = 91
COCO_WB_RIGHT_HAND_OFFSET = 112

# COCO-WholeBody face follows the 68-point iBUG layout (offset within face):
#   0–16  jawline (contour); index 8 is chin
#   17–21 right eyebrow      (5 pts)
#   22–26 left eyebrow       (5 pts)
#   27–35 nose
#   36–41 right eye
#   42–47 left eye
#   48–59 outer mouth
#   60–67 inner mouth
COCO_WB_FACE_CHIN = COCO_WB_FACE_OFFSET + 8
COCO_WB_FACE_RIGHT_BROW_INNER = COCO_WB_FACE_OFFSET + 21   # innermost right brow
COCO_WB_FACE_LEFT_BROW_INNER = COCO_WB_FACE_OFFSET + 22    # innermost left brow

COCO_WB_BODY_NOSE = COCO_WB_BODY_OFFSET + 0
COCO_WB_BODY_LEFT_SHOULDER = COCO_WB_BODY_OFFSET + 5
COCO_WB_BODY_RIGHT_SHOULDER = COCO_WB_BODY_OFFSET + 6


# --------------------------------------------------------------------------
# FreiHAND (21 keypoints, single right hand per image).
# FreiHAND uses MANO ordering; our hand layout is MediaPipe-style. Define the
# permutation here so the (torch-free) tests can verify it.
# mediapipe[i] = mano[MANO_TO_MP[i]]
# --------------------------------------------------------------------------
MANO_TO_MP = [
    0,                          # wrist
    17, 18, 19, 20,             # thumb  (CMC, MCP, IP, tip)
    1, 2, 3, 4,                 # index  (MCP, PIP, DIP, tip)
    5, 6, 7, 8,                 # middle (MCP, PIP, DIP, tip)
    13, 14, 15, 16,             # ring   (MCP, PIP, DIP, tip)
    9, 10, 11, 12,              # pinky  (MCP, PIP, DIP, tip)
]
assert len(MANO_TO_MP) == 21


@dataclass
class KeypointSet:
    """A single sample's keypoints in our unified schema.

    coords: (NUM_KEYPOINTS, 2) array of (x, y) in image pixel coordinates.
    visible: (NUM_KEYPOINTS,) array; 0 = not labeled, 1 = labeled.
    """
    coords: list[tuple[float, float]]
    visible: list[int]

    def __post_init__(self):
        assert len(self.coords) == NUM_KEYPOINTS
        assert len(self.visible) == NUM_KEYPOINTS


def empty_keypoints() -> KeypointSet:
    return KeypointSet(
        coords=[(0.0, 0.0)] * NUM_KEYPOINTS,
        visible=[0] * NUM_KEYPOINTS,
    )
