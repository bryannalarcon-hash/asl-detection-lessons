"""Synthetic hand-in-scene composite loader for the palm detector.

Reads composites produced by ``scripts/build_synthetic_composites.py``: a
256x256 PNG canvas of a non-person background with a small (10-30 px)
FreiHAND hand crop alpha-feathered onto it, plus a JSONL annotation file
with the pixel bbox.

Alpha-feathering at composite time avoids hard rectangular boundaries
around the inserted hand, which would otherwise become a trivial cue for
the detector and degrade transfer to real photos.

The dataset covers the small-hand-in-context regime: tight hand-only
crops never expose, and full-frame interaction images underrepresent.
Mixing it into the training pool broadens box-scale and background
diversity at the low end without manual annotation cost.

Interface contract: same shape as ``coco_wholebody.py`` — each
``__getitem__`` returns a dict with ``image_path``, ``image_id``,
``image_width``, ``image_height``, plus a ``bboxes_xyxy`` array
``(N, 4)`` already in canvas pixel coords. No keypoints are emitted;
this loader is detector-only, so the downstream collator passes the
pre-computed boxes through verbatim rather than re-deriving palm boxes
from landmarks.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from torch.utils.data import Dataset


CANVAS_SIZE = 256


class SyntheticCompositeDataset(Dataset):
    """Loads (image_path, palm_bboxes) tuples from a synthetic-composite dump.

    Args:
        root: Directory produced by build_synthetic_composites.py. Must contain
              `anno.jsonl` and an `img/` subdirectory.
        min_bbox_px: Drop annotations whose longer bbox edge is below this.
                     Default 4 catches degenerate crops without filtering the
                     intended 10-30 px range.
        max_samples: Optional cap for debugging / smoke runs.
    """

    def __init__(self, root: str | Path, min_bbox_px: float = 4.0,
                 max_samples: int | None = None) -> None:
        super().__init__()
        self.root = Path(root)
        anno_path = self.root / "anno.jsonl"
        if not anno_path.exists():
            raise FileNotFoundError(
                f"synthetic composites annotation missing: {anno_path} "
                "(run scripts/build_synthetic_composites.py first)"
            )

        self.samples: list[dict] = []
        with anno_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                bbox = rec.get("bbox_xyxy")
                if bbox is None or len(bbox) != 4:
                    continue
                x1, y1, x2, y2 = bbox
                if max(x2 - x1, y2 - y1) < min_bbox_px:
                    continue
                self.samples.append(rec)
                if max_samples is not None and len(self.samples) >= max_samples:
                    break

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        rec = self.samples[idx]
        image_path = self.root / rec["image_path"]
        x1, y1, x2, y2 = rec["bbox_xyxy"]
        bboxes = np.array([[float(x1), float(y1), float(x2), float(y2)]],
                          dtype=np.float32)
        return {
            "image_path": str(image_path),
            "image_id": int(rec["image_id"]),
            "image_width": CANVAS_SIZE,
            "image_height": CANVAS_SIZE,
            "bboxes_xyxy": bboxes,
            "side": rec.get("side", "right"),
            "frei_id": int(rec.get("frei_id", -1)),
            "coco_id": int(rec.get("coco_id", -1)),
        }


def synthetic_bboxes_to_handbbox(bboxes_xyxy: np.ndarray, side: str = "right"):
    """Convert this dataset's xyxy bboxes into HandBBox objects for the detector.

    Mirrors the role of `hagrid_bboxes_to_pixel` in detector_dataset.py — gives
    the trainer a uniform HandBBox stream regardless of source.
    """
    from src.stage1.data.palm_boxes import HandBBox

    out: list[HandBBox] = []
    for box in bboxes_xyxy:
        x1, y1, x2, y2 = box
        out.append(HandBBox(
            x=float(x1), y=float(y1),
            w=float(x2 - x1), h=float(y2 - y1),
            side=side,
        ))
    return out
