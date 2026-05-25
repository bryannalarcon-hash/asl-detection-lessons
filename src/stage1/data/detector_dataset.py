"""Net 2 (palm detector) training dataset.

Combines COCO-WholeBody + FreiHAND + HaGRID. Each sample emits:
  - 192x192 letterboxed uint8 image tensor (normalized to [-1, 1])
  - GT palm bboxes in letterboxed-input coords
  - per-box keypoints (wrist, middle-MCP) in the same letterboxed-input
    coords plus a per-box valid flag (1 where the source supplied hand
    keypoints, 0 otherwise)

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

from src.stage1.data import schema as S
from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.egohands import EgoHandsDataset, egohands_bboxes_to_pixel
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.hagrid import HaGRIDDataset, hagrid_bboxes_to_pixel
from src.stage1.data.palm_boxes import (
    HandBBox, palm_bbox_for_each_hand,
)
from src.stage1.data.synthetic_composite import (
    SyntheticCompositeDataset, synthetic_bboxes_to_handbbox,
)


# Wrist + middle-MCP indices within one 21-pt hand (standard hand ordering).
_KPT_LOCAL = (0, 9)  # [wrist, middle_MCP]
# Per-hand starts in the unified 49-kpt schema (see schema.py).
_HAND_STARTS = {"right": S.RIGHT_HAND_START, "left": S.LEFT_HAND_START}


def _letterbox_params(img_w: int, img_h: int,
                      input_size: int) -> tuple[float, float, float]:
    """Return (scale, dx, dy) for the letterbox transform used everywhere."""
    scale = input_size / max(img_w, img_h)
    dx = (input_size - img_w * scale) / 2
    dy = (input_size - img_h * scale) / 2
    return scale, dx, dy


def _normalize_bbox_to_input(box: HandBBox, img_w: int, img_h: int,
                             input_size: int) -> HandBBox:
    """Scale a box from source image dims to network input dims (letterboxed)."""
    scale, dx, dy = _letterbox_params(img_w, img_h, input_size)
    return HandBBox(
        x=box.x * scale + dx, y=box.y * scale + dy,
        w=box.w * scale, h=box.h * scale, side=box.side,
    )


def _normalize_point_to_input(pt: np.ndarray, scale: float, dx: float,
                              dy: float) -> np.ndarray:
    """Apply the same letterbox transform to a (..., 2) point array."""
    out = pt.astype(np.float32) * scale
    out[..., 0] += dx
    out[..., 1] += dy
    return out


def _box_kpts_from_sample(sample: dict, box: HandBBox, scale: float,
                          dx: float, dy: float) -> tuple[np.ndarray, int]:
    """Extract the (wrist, middle-MCP) keypoints for one palm box.

    Returns ((2, 2) float32 in letterboxed-input coords, valid flag). For
    sources that carry a 49-kpt `keypoints`/`visible` array (COCO, FreiHAND),
    the points come from the box's hand slot. For box-only sources the caller
    never reaches here (handled with zeros + valid=0 upstream).
    """
    kpts = sample.get("keypoints")
    visible = sample.get("visible")
    start = _HAND_STARTS.get(box.side)
    if kpts is None or visible is None or start is None:
        return np.zeros((2, 2), dtype=np.float32), 0
    idx = [start + i for i in _KPT_LOCAL]
    if any(int(visible[i]) == 0 for i in idx):
        return np.zeros((2, 2), dtype=np.float32), 0
    pts = np.asarray(kpts, dtype=np.float32)[idx]  # (2, 2) source-pixel coords
    return _normalize_point_to_input(pts, scale, dx, dy), 1


def _source_tag_for(ds: Dataset) -> str:
    if isinstance(ds, HaGRIDDataset):
        return "hagrid"
    if isinstance(ds, CocoWholeBodyDataset):
        return "coco"
    if isinstance(ds, FreiHANDDataset):
        return "freihand"
    if isinstance(ds, EgoHandsDataset):
        return "egohands"
    if isinstance(ds, SyntheticCompositeDataset):
        return "synthetic"
    return type(ds).__name__.lower()


# Canonical mix-config names. The cache uses short tags (coco, hagrid, ...)
# but the v3.1 target_mix YAML keys are the dataset's published names.
# This mapping lets the sampler read either form from the config.
_MIX_NAME_ALIASES = {
    "coco": "coco_wholebody",
    "coco_wholebody": "coco_wholebody",
    "hagrid": "hagrid",
    "freihand": "freihand",
    "egohands": "egohands",
    "synthetic": "synthetic",
}


def mix_name_for(ds: Dataset) -> str:
    """Return the canonical target_mix YAML key for a source dataset."""
    return _MIX_NAME_ALIASES.get(_source_tag_for(ds), _source_tag_for(ds))


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

    def __init__(self, coco_train: CocoWholeBodyDataset | None,
                 freihand_train: FreiHANDDataset | None,
                 hagrid_train: HaGRIDDataset | None,
                 input_size: int = 192,
                 padding_frac: float = 0.5,
                 cache_root: str | Path | None = None,
                 egohands_train: EgoHandsDataset | None = None,
                 synthetic_train: SyntheticCompositeDataset | None = None):
        super().__init__()
        self.sources: list[Dataset] = []
        if coco_train is not None:
            self.sources.append(coco_train)
        if freihand_train is not None:
            self.sources.append(freihand_train)
        if hagrid_train is not None:
            self.sources.append(hagrid_train)
        if egohands_train is not None:
            self.sources.append(egohands_train)
        if synthetic_train is not None:
            self.sources.append(synthetic_train)
        if not self.sources:
            raise ValueError(
                "DetectorTrainDataset needs at least one source dataset")
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

        # Derive GT bboxes per source type (in source-pixel coords). Only
        # keypoint sources (COCO, FreiHAND) carry a 49-kpt array we can read
        # wrist + middle-MCP from; box-only sources emit zeros + valid=0.
        has_hand_kpts = False
        if isinstance(source, HaGRIDDataset):
            boxes = hagrid_bboxes_to_pixel(sample["norm_bboxes"], img_w, img_h,
                                           leading_hand=sample.get("leading_hand", "right"))
        elif isinstance(source, EgoHandsDataset):
            boxes = egohands_bboxes_to_pixel(sample["norm_bboxes"], img_w, img_h)
        elif isinstance(source, SyntheticCompositeDataset):
            # Synthetic canvas pixel coords are already in the final input
            # space (canvas size == input_size). _normalize_bbox_to_input
            # below is a no-op when img_w == img_h == input_size.
            boxes = synthetic_bboxes_to_handbbox(
                sample["bboxes_xyxy"], side=sample.get("side", "right"))
        else:
            boxes = palm_bbox_for_each_hand(sample["keypoints"], sample["visible"],
                                            pad=self.padding_frac)
            has_hand_kpts = True

        scale, dx, dy = _letterbox_params(img_w, img_h, self.input_size)
        boxes_in_input = [
            _normalize_bbox_to_input(b, img_w, img_h, self.input_size) for b in boxes
        ]

        img_tensor = torch.from_numpy(canvas.copy()).permute(2, 0, 1).float() / 255.0
        img_tensor = (img_tensor - 0.5) / 0.5

        M = len(boxes_in_input)
        boxes_arr = np.zeros((M, 4), dtype=np.float32)
        kpts_arr = np.zeros((M, 2, 2), dtype=np.float32)
        kpts_valid = np.zeros((M,), dtype=np.float32)
        for i, (b_src, b_in) in enumerate(zip(boxes, boxes_in_input)):
            boxes_arr[i] = [b_in.x + b_in.w / 2, b_in.y + b_in.h / 2,
                            b_in.w, b_in.h]
            if has_hand_kpts:
                pts, valid = _box_kpts_from_sample(sample, b_src, scale, dx, dy)
                kpts_arr[i] = pts
                kpts_valid[i] = valid

        return {
            "image": img_tensor,
            "boxes": torch.from_numpy(boxes_arr),
            "kpts": torch.from_numpy(kpts_arr),
            "kpts_valid": torch.from_numpy(kpts_valid),
            "image_id": sample.get("image_id", idx),
        }

    def _empty(self, idx: int) -> dict:
        return {
            "image": torch.zeros(3, self.input_size, self.input_size),
            "boxes": torch.zeros(0, 4),
            "kpts": torch.zeros(0, 2, 2),
            "kpts_valid": torch.zeros(0),
            "image_id": idx,
        }


def detector_collate(batch: list[dict]) -> dict:
    """Variable bbox count per sample → list, not stacked.

    `kpts` ((M, 2, 2) per sample) and `kpts_valid` ((M,)) are carried as
    parallel lists alongside `boxes`, so the i-th element of each list
    describes the same sample's GT boxes.
    """
    return {
        "image": torch.stack([b["image"] for b in batch]),
        "boxes": [b["boxes"] for b in batch],
        "kpts": [b["kpts"] for b in batch],
        "kpts_valid": [b["kpts_valid"] for b in batch],
        "image_id": [b["image_id"] for b in batch],
    }


def build_mix_sample_weights(ds: "DetectorTrainDataset",
                             target_mix: dict[str, float],
                             ) -> tuple[np.ndarray, dict[str, float]]:
    """Build per-sample weights so a WeightedRandomSampler draws each source
    at the target_mix proportion.

    A sample's weight is `target_share / source_size`. The sampler is
    instantiated with `num_samples = len(ds)` so each epoch sees the same
    total step count as the unweighted run (matching existing
    steps_per_epoch / cosine schedule assumptions).

    Sources present in `ds.sources` but absent from `target_mix` get a
    proportional zero weight (they will never be sampled). Sources in
    `target_mix` but absent from `ds.sources` are dropped from the active
    mix and the remaining weights renormalize to sum to 1.0. The effective
    active mix is returned for logging.

    Args:
        ds: a DetectorTrainDataset instance.
        target_mix: {canonical_name: float} from cfg["data"]["target_mix"].

    Returns:
        weights: (len(ds),) float32 numpy array, normalized so it sums to 1.
        active_mix: the renormalized mix actually applied (for logging).
    """
    if not target_mix:
        raise ValueError("target_mix must be a non-empty dict")

    present: dict[str, int] = {}
    for src_i, source in enumerate(ds.sources):
        name = mix_name_for(source)
        present[name] = src_i

    active: dict[str, float] = {n: float(s) for n, s in target_mix.items()
                                if n in present and s > 0}
    total = sum(active.values())
    if total <= 0:
        raise ValueError(
            f"target_mix has no overlap with loaded sources. "
            f"target_mix keys={list(target_mix)} loaded={list(present)}"
        )
    active = {n: s / total for n, s in active.items()}

    weights = np.zeros(len(ds), dtype=np.float32)
    starts = [0] + list(ds._cumlen)
    for src_i, source in enumerate(ds.sources):
        name = mix_name_for(source)
        share = active.get(name, 0.0)
        n = ds._lengths[src_i]
        if n <= 0 or share <= 0:
            continue
        # Per-sample weight = target_share / n. After sampling, the expected
        # share-of-batch for this source equals `share`.
        per_sample = share / n
        weights[starts[src_i]:starts[src_i] + n] = per_sample

    s = float(weights.sum())
    if s <= 0:
        raise ValueError("all sample weights are zero; check target_mix vs sources")
    weights /= s
    return weights, active
