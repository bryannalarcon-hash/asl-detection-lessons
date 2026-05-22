"""DALI-backed loaders for Net 2 (detector) and Net 3 (landmark).

Replaces PyTorch DataLoader with a NVIDIA DALI pipeline that does:
  - Read raw JPEG bytes in Python (cheap)
  - Batched NVJPEG decode on GPU (hardware-accelerated)
  - Letterbox (Net 2) or per-sample warp_affine (Net 3) on GPU
  - Normalize + CHW transpose on GPU

Both loaders yield dicts compatible with the existing trainers so the change
is local to the data layer.

Benchmarked vs cv2: ~4-7x speedup for the Net 3 workload (NVJPEG + warp_affine
batched on GPU eliminates the per-sample CPU decode + cv2.warpAffine loop).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Iterator

import numpy as np
import torch
from PIL import Image

from nvidia.dali import pipeline_def, fn, types

from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.hagrid import HaGRIDDataset, hagrid_bboxes_to_pixel
from src.stage1.data.interhand import InterHand26MDataset
from src.stage1.data import schema as S
from src.stage1.data.hand_crops import project_kpts
from src.stage1.data.palm_boxes import (
    HandBBox, palm_bbox, palm_bbox_for_each_hand, jitter_bbox,
)


# ===== Helpers =====

def _normalize_bbox_to_input(box: HandBBox, img_w: int, img_h: int,
                             input_size: int) -> HandBBox:
    scale = input_size / max(img_w, img_h)
    new_w = img_w * scale
    new_h = img_h * scale
    dx = (input_size - new_w) / 2
    dy = (input_size - new_h) / 2
    return HandBBox(
        x=box.x * scale + dx, y=box.y * scale + dy,
        w=box.w * scale, h=box.h * scale, side=box.side,
    )


def _build_landmark_affine(box: HandBBox, out_size: int,
                           rotation_deg: float) -> np.ndarray:
    cx, cy = box.center()
    scale = out_size / max(box.w, box.h)
    angle_rad = np.deg2rad(rotation_deg)
    cos_a = np.cos(angle_rad) * scale
    sin_a = np.sin(angle_rad) * scale
    return np.array([
        [cos_a, -sin_a, out_size / 2 - cos_a * cx + sin_a * cy],
        [sin_a, cos_a, out_size / 2 - sin_a * cx - cos_a * cy],
    ], dtype=np.float32)


def _read_jpeg_with_dims(path: str) -> tuple[np.ndarray, int, int] | None:
    """Read raw JPEG bytes + (w, h) without decoding pixels."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        if not data:
            return None
        with Image.open(BytesIO(data)) as im:
            w, h = im.size
        return np.frombuffer(data, dtype=np.uint8), w, h
    except Exception:
        return None


# ===== Net 2 (detector) =====

class DALIDetectorLoader:
    """DALI-backed iterable for Net 2 training.

    Yields dicts {"image": (B, 3, S, S) GPU FloatTensor in [-1,1],
                  "boxes": list[Tensor(N_i, 4)] of GT bboxes in letterboxed coords,
                  "image_id": list[int]} — matches the cv2 path's collate output.
    """

    def __init__(self,
                 coco: CocoWholeBodyDataset,
                 frei: FreiHANDDataset,
                 hagrid: HaGRIDDataset | None,
                 input_size: int,
                 batch_size: int,
                 padding_frac: float = 0.5,
                 device_id: int = 0,
                 num_threads: int = 8,
                 prefetch: int = 2,
                 shuffle: bool = True,
                 drop_last: bool = True,
                 seed: int = 42):
        self.sources: list = [coco, frei] + ([hagrid] if hagrid is not None else [])
        self._lengths = [len(s) for s in self.sources]
        self._cumlen = np.cumsum(self._lengths).tolist()
        self.input_size = input_size
        self.batch_size = batch_size
        self.padding_frac = padding_frac
        self.shuffle = shuffle
        self.drop_last = drop_last
        self.rng = np.random.default_rng(seed)
        # State carried between _jpeg_callback and the consumer of pipeline batches
        self._pending_boxes: list[list[np.ndarray]] = []
        self._pending_ids: list[list] = []
        self._order: np.ndarray = np.arange(len(self))
        self._cursor: int = 0
        self._epoch: int = 0
        # ThreadPool for parallel per-sample JPEG read + box derivation.
        # cv2 + PIL release the GIL during decode, so threads parallelize well.
        self._pool = ThreadPoolExecutor(max_workers=8)
        self._reshuffle()

        @pipeline_def(batch_size=batch_size, num_threads=num_threads,
                      device_id=device_id, prefetch_queue_depth=prefetch)
        def _pipe():
            jpegs = fn.external_source(source=self._jpeg_callback, batch=True,
                                       dtype=types.UINT8, name="jpegs")
            img = fn.decoders.image(jpegs, device="mixed", output_type=types.RGB)
            # Letterbox: scale so longest side = input_size, keep aspect, then center-pad.
            resized = fn.resize(img, resize_longer=input_size,
                                interp_type=types.INTERP_LINEAR)
            padded = fn.paste(resized, paste_x=0.5, paste_y=0.5, ratio=1.0,
                              min_canvas_size=input_size, fill_value=0)
            normed = fn.normalize(padded, mean=127.5, stddev=127.5,
                                  dtype=types.FLOAT)
            chw = fn.transpose(normed, perm=[2, 0, 1])
            return chw

        self._pipeline = _pipe()
        self._pipeline.build()

    def __len__(self) -> int:
        return self._cumlen[-1]

    def __iter__(self) -> Iterator[dict]:
        return self

    def _reshuffle(self) -> None:
        if self.shuffle:
            self.rng.shuffle(self._order)
        self._cursor = 0

    def _resolve(self, idx: int) -> tuple[object, int]:
        for i, end in enumerate(self._cumlen):
            if idx < end:
                start = self._cumlen[i - 1] if i > 0 else 0
                return self.sources[i], idx - start
        raise IndexError(idx)

    def _prepare_one(self, i: int) -> tuple[np.ndarray, np.ndarray, object]:
        """Worker function: load + derive boxes for one sample."""
        source, local = self._resolve(int(i))
        sample = source[local]
        path = str(sample["image_path"])
        jpeg_info = _read_jpeg_with_dims(path)
        if jpeg_info is None:
            jpeg_info = _read_jpeg_with_dims(str(self.sources[0][0]["image_path"]))
            if jpeg_info is None:
                raise RuntimeError(f"Cannot read placeholder JPEG; main path={path}")
        jpeg_bytes, img_w, img_h = jpeg_info
        # Box derivation (in source-pixel coords)
        if isinstance(source, HaGRIDDataset):
            boxes = hagrid_bboxes_to_pixel(sample["norm_bboxes"], img_w, img_h,
                                           leading_hand=sample.get("leading_hand", "right"))
        else:
            boxes = palm_bbox_for_each_hand(sample["keypoints"], sample["visible"],
                                            pad=self.padding_frac)
        boxes_in_input = [
            _normalize_bbox_to_input(b, img_w, img_h, self.input_size) for b in boxes
        ]
        boxes_arr = np.zeros((len(boxes_in_input), 4), dtype=np.float32)
        for k, b in enumerate(boxes_in_input):
            boxes_arr[k] = [b.x + b.w / 2, b.y + b.h / 2, b.w, b.h]
        return jpeg_bytes, boxes_arr, sample.get("image_id", int(i))

    def _jpeg_callback(self) -> list[np.ndarray]:
        """Called by DALI before each batch — returns a list[batch_size] of jpeg byte arrays.

        Per-sample JPEG file read + dimension probe + box derivation is done in
        parallel via a ThreadPoolExecutor (cv2/PIL release the GIL during the
        heavy work). This was the dominant Python-side cost when sequential.
        """
        if self._cursor + self.batch_size > len(self._order):
            self._epoch += 1
            self._reshuffle()
        idxs = self._order[self._cursor:self._cursor + self.batch_size]
        self._cursor += self.batch_size

        # Parallel per-sample work
        results = list(self._pool.map(self._prepare_one, idxs.tolist()))
        jpegs = [r[0] for r in results]
        batch_boxes = [r[1] for r in results]
        batch_ids = [r[2] for r in results]

        # Stash for the consumer to pick up alongside the GPU tensor
        self._pending_boxes.append(batch_boxes)
        self._pending_ids.append(batch_ids)
        return jpegs

    def __next__(self) -> dict:
        out = self._pipeline.run()
        # `out[0]` is the GPU tensor (B, 3, S, S) float32. Convert to torch.
        gpu = out[0].as_tensor()  # TensorGPU
        # DALI 2.x: use `.as_tensor()` then `torch.utils.dlpack` if needed; simpler is .as_cpu().
        # We want a torch GPU tensor — use the standard plugin conversion:
        from nvidia.dali.plugin.pytorch import feed_ndarray
        img_t = torch.empty((self.batch_size, 3, self.input_size, self.input_size),
                            dtype=torch.float32, device="cuda")
        feed_ndarray(gpu, img_t)
        boxes_batch = self._pending_boxes.pop(0)
        ids_batch = self._pending_ids.pop(0)
        return {
            "image": img_t,
            "boxes": [torch.from_numpy(b) for b in boxes_batch],
            "image_id": ids_batch,
        }

    def num_batches_per_epoch(self) -> int:
        if self.drop_last:
            return len(self) // self.batch_size
        return (len(self) + self.batch_size - 1) // self.batch_size


# ===== Net 3 (landmark) =====

class DALILandmarkLoader:
    """DALI-backed iterable for Net 3 training.

    Per-sample, one hand crop with per-sample affine M.
    Yields {"image": (B, 3, C, C) GPU tensor in [-1,1],
            "keypoints": (B, 21, 2) in crop coords,
            "visible": (B, 21),
            "hand_side": list[str],
            "image_id": list}.
    """

    def __init__(self,
                 freihand: FreiHANDDataset,
                 interhand: InterHand26MDataset | None,
                 crop_size: int,
                 batch_size: int,
                 padding_frac: float = 0.5,
                 jitter_shift: float = 0.10,
                 jitter_scale: float = 0.15,
                 jitter_rot: float = 10.0,
                 phase2_bbox: dict | None = None,
                 phase2_mix_prob: float = 0.0,
                 device_id: int = 0,
                 num_threads: int = 8,
                 prefetch: int = 2,
                 shuffle: bool = True,
                 drop_last: bool = True,
                 seed: int = 42):
        self.crop_size = crop_size
        self.batch_size = batch_size
        self.padding_frac = padding_frac
        self.jitter_shift = jitter_shift
        self.jitter_scale = jitter_scale
        self.jitter_rot = jitter_rot
        self.phase2_bbox = phase2_bbox or {}
        self.phase2_mix_prob = phase2_mix_prob
        self.shuffle = shuffle
        self.drop_last = drop_last
        self.rng = np.random.default_rng(seed)

        # Build the per-sample item list (same expansion as LandmarkTrainDataset)
        self.items: list[tuple[str, int, str]] = []
        for i in range(len(freihand)):
            self.items.append(("freihand", i, "right"))
        if interhand is not None:
            for i in range(len(interhand)):
                self.items.append(("interhand", i, "right"))
                self.items.append(("interhand", i, "left"))
        self._freihand = freihand
        self._interhand = interhand
        self._order = np.arange(len(self.items))
        self._cursor = 0
        self._epoch = 0
        self._pending: list[dict] = []
        # ThreadPool for parallel JPEG read + M-matrix construction + kpt projection.
        self._pool = ThreadPoolExecutor(max_workers=8)
        self._reshuffle()

        @pipeline_def(batch_size=batch_size, num_threads=num_threads,
                      device_id=device_id, prefetch_queue_depth=prefetch)
        def _pipe():
            jpegs = fn.external_source(source=self._jpeg_callback, batch=True,
                                       dtype=types.UINT8, name="jpegs")
            affines = fn.external_source(source=self._affine_callback, batch=True,
                                         dtype=types.FLOAT, name="affines")
            img = fn.decoders.image(jpegs, device="mixed", output_type=types.RGB)
            warped = fn.warp_affine(img, matrix=affines, size=(crop_size, crop_size),
                                    fill_value=0, interp_type=types.INTERP_LINEAR)
            normed = fn.normalize(warped.gpu(), mean=127.5, stddev=127.5,
                                  dtype=types.FLOAT)
            chw = fn.transpose(normed, perm=[2, 0, 1])
            return chw

        self._pipeline = _pipe()
        self._pipeline.build()

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[dict]:
        return self

    def _reshuffle(self) -> None:
        if self.shuffle:
            self.rng.shuffle(self._order)
        self._cursor = 0

    def _load_sample(self, source: str, local_idx: int) -> dict:
        if source == "freihand":
            return self._freihand[local_idx]
        return self._interhand[local_idx]

    def _prepare_one(self, i: int) -> dict:
        """Worker: per-sample JPEG read + M-matrix + kpt projection."""
        src_tag, local, side = self.items[int(i)]
        sample = self._load_sample(src_tag, local)
        if side == "right":
            slot = slice(S.RIGHT_HAND_START, S.RIGHT_HAND_START + 21)
        else:
            slot = slice(S.LEFT_HAND_START, S.LEFT_HAND_START + 21)
        coords = sample["keypoints"][slot]
        visible = sample["visible"][slot]
        path = str(sample["image_path"])

        def _placeholder():
            ji = _read_jpeg_with_dims(path) or _read_jpeg_with_dims(
                str(self._freihand[0]["image_path"]))
            return {
                "jpeg": ji[0], "M": np.eye(2, 3, dtype=np.float32),
                "kpts": np.zeros((21, 2), dtype=np.float32),
                "vis": np.zeros(21, dtype=np.float32),
                "side": "none",
                "id": int(sample.get("image_id", int(i))),
            }
        if visible.sum() < 3:
            return _placeholder()

        rng_local = np.random.default_rng(int(i) + self._epoch * 1_000_003)
        use_phase2 = (str(sample.get("image_id")) in self.phase2_bbox
                      and rng_local.random() < self.phase2_mix_prob)
        if use_phase2:
            cached = self.phase2_bbox[str(sample["image_id"])]
            box = HandBBox(*cached[:4], side=side)
        else:
            box = palm_bbox(coords, visible, side=side, pad=self.padding_frac)
            if box is None:
                return _placeholder()
            box = jitter_bbox(box, shift_frac=self.jitter_shift,
                              scale_frac=self.jitter_scale, rng=rng_local)
        rot_deg = float(rng_local.uniform(-self.jitter_rot, self.jitter_rot))
        M = _build_landmark_affine(box, self.crop_size, rot_deg)
        kpts_in_crop = project_kpts(coords, M)
        ji = _read_jpeg_with_dims(path) or _read_jpeg_with_dims(
            str(self._freihand[0]["image_path"]))
        return {
            "jpeg": ji[0],
            "M": M,
            "kpts": kpts_in_crop.astype(np.float32),
            "vis": visible.astype(np.float32),
            "side": side,
            "id": int(sample.get("image_id", int(i))),
        }

    def _prepare_batch(self) -> None:
        """Pre-compute the next batch worth of (jpeg, M, kpts, vis, side, id) in parallel."""
        if self._cursor + self.batch_size > len(self._order):
            self._epoch += 1
            self._reshuffle()
        idxs = self._order[self._cursor:self._cursor + self.batch_size]
        self._cursor += self.batch_size
        results = list(self._pool.map(self._prepare_one, idxs.tolist()))
        self._pending.append({
            "jpegs": [r["jpeg"] for r in results],
            "Ms":    [r["M"]    for r in results],
            "kpts":  np.stack([r["kpts"] for r in results]),
            "visible": np.stack([r["vis"] for r in results]),
            "sides": [r["side"] for r in results],
            "ids":   [r["id"]   for r in results],
        })

    def _jpeg_callback(self) -> list[np.ndarray]:
        self._prepare_batch()
        return self._pending[-1]["jpegs"]

    def _affine_callback(self) -> list[np.ndarray]:
        # _prepare_batch has just been called by _jpeg_callback in the same batch tick.
        # We do NOT call _prepare_batch again; just return the affines from the most
        # recent pending entry. DALI calls callbacks in declaration order each batch.
        return self._pending[-1]["Ms"]

    def __next__(self) -> dict:
        out = self._pipeline.run()
        from nvidia.dali.plugin.pytorch import feed_ndarray
        img_t = torch.empty((self.batch_size, 3, self.crop_size, self.crop_size),
                            dtype=torch.float32, device="cuda")
        feed_ndarray(out[0].as_tensor(), img_t)
        batch = self._pending.pop(0)
        return {
            "image": img_t,
            "keypoints": torch.from_numpy(batch["kpts"]).float(),
            "visible": torch.from_numpy(batch["visible"]).float(),
            "hand_side": batch["sides"],
            "image_id": batch["ids"],
        }

    def num_batches_per_epoch(self) -> int:
        if self.drop_last:
            return len(self) // self.batch_size
        return (len(self) + self.batch_size - 1) // self.batch_size
