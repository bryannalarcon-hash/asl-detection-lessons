"""EgoHands loader (Roboflow YOLO-format mirror).

EgoHands is 4,800 first-person video frames with ~15,053 hand polygon
annotations across four interaction activities (cards, chess, jenga,
puzzle). We use the Roboflow YOLO-formatted mirror at
https://public.roboflow.com/object-detection/hands because its polygons
have been converted to axis-aligned bboxes and the layout is the
standard one-txt-per-image scheme our pipeline can read directly.

Per-image annotation file is a plain text file where every line is:
    class_id  cx  cy  w  h
with all four box terms normalized to [0, 1] of the image dims and
`class_id` always 0 (one "hand" class).

No keypoints are provided; this dataset is used ONLY by Net 2 (palm
detector) — the same role HaGRID plays.

Expected directory layout after `scripts/download_egohands.sh`:
  data/egohands/
    train/
      images/*.jpg
      labels/*.txt
    valid/
      images/...
      labels/...
    test/
      images/...
      labels/...
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from torch.utils.data import Dataset

from src.stage1.data import schema as S
from src.stage1.data.palm_boxes import HandBBox


class EgoHandsDataset(Dataset):
    """EgoHands samples emit (image_path, norm_bboxes).

    The interface mirrors HaGRIDDataset so DetectorTrainDataset can stitch
    it in without source-specific branches: it also exposes `norm_bboxes`
    as a list of [x, y, w, h] in TOP-LEFT normalized coords (the same form
    HaGRID uses), and zero-filled keypoint slots.

    Roboflow YOLO labels store CENTER-based normalized boxes (cx, cy, w, h);
    we convert to top-left here so consumers can rely on a single convention.
    """

    def __init__(self, root: str | Path, split: str = "train") -> None:
        super().__init__()
        self.root = Path(root)
        split_dir = self.root / split
        img_dir = split_dir / "images"
        lbl_dir = split_dir / "labels"
        if not img_dir.exists() or not lbl_dir.exists():
            raise FileNotFoundError(
                f"EgoHands split missing under {split_dir} "
                f"(expected images/ and labels/ subdirs)"
            )

        # Common YOLO image extensions; Roboflow ships .jpg but be liberal.
        image_exts = (".jpg", ".jpeg", ".png")
        self.samples: list[dict] = []
        for img_path in sorted(img_dir.iterdir()):
            if img_path.suffix.lower() not in image_exts:
                continue
            lbl_path = lbl_dir / f"{img_path.stem}.txt"
            if not lbl_path.exists():
                continue
            boxes = _read_yolo_labels(lbl_path)
            if not boxes:
                continue
            self.samples.append({
                "image_id": img_path.stem,
                "image_path": img_path,
                "norm_bboxes": boxes,
            })

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        s = self.samples[idx]
        return {
            "image_path": str(s["image_path"]),
            "image_id": s["image_id"],
            "norm_bboxes": s["norm_bboxes"],
            "leading_hand": "right",
            "gesture": "",
            "keypoints": np.zeros((S.NUM_KEYPOINTS, 2), dtype=np.float32),
            "visible": np.zeros(S.NUM_KEYPOINTS, dtype=np.int64),
        }


def _read_yolo_labels(path: Path) -> list[list[float]]:
    """Parse a Roboflow-style YOLO label file → list of [x, y, w, h] normalized.

    Input lines: class_id cx cy w h (center-based, normalized to [0, 1]).
    Output: top-left [x, y, w, h] normalized — matches HaGRID's convention.

    Malformed or fully-clipped boxes are skipped silently; the dataset is
    a known-good public mirror so we don't fault on individual rows.
    """
    out: list[list[float]] = []
    with path.open() as f:
        for raw in f:
            parts = raw.strip().split()
            if len(parts) < 5:
                continue
            try:
                cx = float(parts[1])
                cy = float(parts[2])
                w = float(parts[3])
                h = float(parts[4])
            except ValueError:
                continue
            if w <= 0 or h <= 0:
                continue
            x = cx - w / 2.0
            y = cy - h / 2.0
            # Clip to image; if any axis collapses fully, drop it.
            x0 = max(0.0, x)
            y0 = max(0.0, y)
            x1 = min(1.0, x + w)
            y1 = min(1.0, y + h)
            if x1 - x0 <= 0 or y1 - y0 <= 0:
                continue
            out.append([x0, y0, x1 - x0, y1 - y0])
    return out


def egohands_bboxes_to_pixel(norm_bboxes: list[list[float]],
                             img_w: int, img_h: int) -> list[HandBBox]:
    """Convert EgoHands normalized [x, y, w, h] to HandBBox pixel coords.

    EgoHands does not label handedness, so all boxes are tagged "right".
    Net 2 ignores the side field (it's a single-class detector), so this
    is the same fallback HaGRID uses for its 2nd box.
    """
    out: list[HandBBox] = []
    for nx, ny, nw, nh in norm_bboxes:
        out.append(HandBBox(
            x=nx * img_w, y=ny * img_h, w=nw * img_w, h=nh * img_h, side="right",
        ))
    return out
