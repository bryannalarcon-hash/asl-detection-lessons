"""Net 2 (palm detector) training dataset.

Combines COCO-WholeBody + FreiHAND + HaGRID. Each sample emits:
  - 192x192 letterboxed uint8 image tensor (normalized to [-1, 1])
  - GT palm bboxes in letterboxed-input coords

If a decoded image cache exists at `cache_root/{source_tag}/{images.bin,index.json}`,
the worker reads pre-decoded letterboxed arrays from a memory-mapped file
instead of decoding JPEGs at training time. This eliminates the ~1.7 ms
per-image cv2.imread + cvtColor + resize cost (validated benchmark:
~570 imgs/sec → ~200K imgs/sec, 350× speedup).
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.hagrid import HaGRIDDataset, hagrid_bboxes_to_pixel
from src.stage1.data.palm_boxes import (
    HandBBox, palm_bbox_for_each_hand,
)


def _normalize_bbox_to_input(box: HandBBox, img_w: int, img_h: int,
                             input_size: int) -> HandBBox:
    """Scale a box from source image dims to network input dims (letterboxed)."""
    scale = input_size / max(img_w, img_h)
    new_w = img_w * scale
    new_h = img_h * scale
    dx = (input_size - new_w) / 2
    dy = (input_size - new_h) / 2
    return HandBBox(
        x=box.x * scale + dx, y=box.y * scale + dy,
        w=box.w * scale, h=box.h * scale, side=box.side,
    )


def _source_tag_for(ds: Dataset) -> str:
    if isinstance(ds, HaGRIDDataset):
        return "hagrid"
    if isinstance(ds, CocoWholeBodyDataset):
        return "coco"
    if isinstance(ds, FreiHANDDataset):
        return "freihand"
    return type(ds).__name__.lower()


class _ImageCache:
    """Memory-mapped cache of pre-decoded letterboxed uint8 images.

    Layout:
      cache_root/{source_tag}/images.bin   uint8 mmap of shape (N, S, S, 3)
      cache_root/{source_tag}/index.json   {"input_size": S, "shape": [N,S,S,3],
                                            "index": {abspath: {row, source_w, source_h}}}
    """

    def __init__(self, cache_root: Path, source_tag: str, expected_input_size: int):
        self.ok = False
        self.idx: dict[str, dict] = {}
        self.input_size = expected_input_size
        meta_p = cache_root / source_tag / "index.json"
        bin_p = cache_root / source_tag / "images.bin"
        if not (meta_p.exists() and bin_p.exists()):
            return
        with meta_p.open() as f:
            meta = json.load(f)
        if int(meta.get("input_size", -1)) != expected_input_size:
            return
        shape = tuple(meta["shape"])
        self.mmap = np.memmap(bin_p, dtype="uint8", mode="r", shape=shape)
        self.idx = meta["index"]
        self.ok = True

    def get(self, path: str) -> tuple[np.ndarray, int, int] | None:
        entry = self.idx.get(path)
        if entry is None:
            return None
        return self.mmap[entry["row"]], int(entry["source_w"]), int(entry["source_h"])


class DetectorTrainDataset(Dataset):
    """Unifies three sources into a single (image, bboxes) stream."""

    def __init__(self, coco_train: CocoWholeBodyDataset,
                 freihand_train: FreiHANDDataset,
                 hagrid_train: HaGRIDDataset | None,
                 input_size: int = 192,
                 padding_frac: float = 0.5,
                 cache_root: str | Path | None = None):
        super().__init__()
        self.sources: list[Dataset] = [coco_train, freihand_train]
        if hagrid_train is not None:
            self.sources.append(hagrid_train)
        self.input_size = input_size
        self.padding_frac = padding_frac
        self._lengths = [len(s) for s in self.sources]
        self._cumlen = np.cumsum(self._lengths).tolist()

        self._caches: dict[int, _ImageCache] = {}
        if cache_root:
            cache_root = Path(cache_root)
            for i, src in enumerate(self.sources):
                tag = _source_tag_for(src)
                c = _ImageCache(cache_root, tag, input_size)
                if c.ok:
                    self._caches[i] = c
                    print(f"[cache] using mmap cache for source {tag}: "
                          f"{len(c.idx):,} images")

    def __len__(self) -> int:
        return self._cumlen[-1]

    def _resolve(self, idx: int) -> tuple[int, Dataset, int]:
        for i, end in enumerate(self._cumlen):
            if idx < end:
                start = self._cumlen[i - 1] if i > 0 else 0
                return i, self.sources[i], idx - start
        raise IndexError(idx)

    def __getitem__(self, idx: int) -> dict:
        src_i, source, local = self._resolve(idx)
        sample = source[local]
        path = str(sample["image_path"])

        # Try cache first.
        cached = None
        if src_i in self._caches:
            cached = self._caches[src_i].get(path)
        if cached is not None:
            canvas, img_w, img_h = cached
            canvas = canvas  # already (S, S, 3) uint8, letterboxed
        else:
            img = cv2.imread(path)
            if img is None:
                return self._empty(idx)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_h, img_w = img.shape[:2]
            scale = self.input_size / max(img_w, img_h)
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)
            resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            canvas = np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8)
            dy = (self.input_size - new_h) // 2
            dx = (self.input_size - new_w) // 2
            canvas[dy:dy + new_h, dx:dx + new_w] = resized

        # Derive GT bboxes per source type (in source-pixel coords).
        if isinstance(source, HaGRIDDataset):
            boxes = hagrid_bboxes_to_pixel(sample["norm_bboxes"], img_w, img_h,
                                           leading_hand=sample.get("leading_hand", "right"))
        else:
            boxes = palm_bbox_for_each_hand(sample["keypoints"], sample["visible"],
                                            pad=self.padding_frac)

        boxes_in_input = [
            _normalize_bbox_to_input(b, img_w, img_h, self.input_size) for b in boxes
        ]

        img_tensor = torch.from_numpy(canvas.copy()).permute(2, 0, 1).float() / 255.0
        img_tensor = (img_tensor - 0.5) / 0.5

        boxes_arr = np.zeros((len(boxes_in_input), 4), dtype=np.float32)
        for i, b in enumerate(boxes_in_input):
            boxes_arr[i] = [b.x + b.w / 2, b.y + b.h / 2, b.w, b.h]

        return {
            "image": img_tensor,
            "boxes": torch.from_numpy(boxes_arr),
            "image_id": sample.get("image_id", idx),
        }

    def _empty(self, idx: int) -> dict:
        return {
            "image": torch.zeros(3, self.input_size, self.input_size),
            "boxes": torch.zeros(0, 4),
            "image_id": idx,
        }


def detector_collate(batch: list[dict]) -> dict:
    """Variable bbox count per sample → list, not stacked."""
    return {
        "image": torch.stack([b["image"] for b in batch]),
        "boxes": [b["boxes"] for b in batch],
        "image_id": [b["image_id"] for b in batch],
    }
