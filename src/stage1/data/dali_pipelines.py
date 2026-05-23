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
from src.stage1.data.detector_dataset import _ImageCache, _source_tag_for
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.hagrid import HaGRIDDataset, hagrid_bboxes_to_pixel
from src.stage1.data.interhand import InterHand26MDataset
from src.stage1.data import schema as S
from src.stage1.data.hand_crops import project_kpts
from src.stage1.data.palm_boxes import (
    HandBBox, palm_bbox, palm_bbox_for_each_hand, jitter_bbox,
)
from src.stage1.models.anchors import generate_anchors

import cv2


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

    Two modes, gated by `use_box_encoder`:

    1. `use_box_encoder=False` (default; back-compat):
       Yields {"image": (B, 3, S, S) GPU FloatTensor in [-1,1],
               "boxes": list[Tensor(N_i, 4)] cxcywh in letterboxed pixel coords,
               "image_id": list}. The trainer then runs `_build_targets` on CPU.

    2. `use_box_encoder=True` (DALI SSD-style anchor matching):
       Yields {"image": (B, 3, S, S) GPU FloatTensor in [-1,1],
               "cls_target": (B, N_anchors) int32 on CPU,
               "box_target": (B, N_anchors, 4) float32 deltas on CPU,
               "image_id": list}. The trainer skips `_build_targets` entirely.
       Anchors are pre-baked from `generate_anchors(input_size)`. GT boxes are
       fed to DALI as xyxy normalized [0,1] alongside int32 labels (all `1` —
       single foreground class "palm").

       Math equivalence with `encode_box` in `src/stage1/models/anchors.py`:
         DALI `box_encoder(offset=True, stds=[1,1,1,1], means=[0,0,0,0])`
         emits, for positive anchors:
             dx = (gt_cx - a_cx) / a_w
             dy = (gt_cy - a_cy) / a_h
             dw = log(gt_w / a_w)
             dh = log(gt_h / a_h)
         which is *exactly* `encode_box`.

       TRADE-OFF (quality):
         Our `match_anchors_to_gt` uses BOTH `pos_iou=0.5` and `neg_iou=0.4`:
         anchors in `[neg_iou, pos_iou)` get cls=-1 (ignored by focal loss).
         DALI's `box_encoder` has only ONE threshold (`criteria`); anchors below
         it are marked cls=0 (background) and contribute as real negatives.
         This is a mild regularization shift — slightly more anchors push the
         loss as negatives — but `FocalClassificationLoss` is already designed
         for the long-tailed pos/neg ratio that focal handles. The forced
         "best-IoU anchor per GT" positive assignment is preserved (DALI
         `box_encoder` always assigns each GT to its best-overlap anchor).

       SPEEDUP: removes the ~26 ms/batch numpy IoU + assignment loop (and the
       CPU→GPU transfer of cls/box targets) from `_build_targets`.
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
                 seed: int = 42,
                 use_box_encoder: bool = False,
                 pos_iou: float = 0.5,
                 cache_root: str | Path | None = None):
        self.sources: list = [coco, frei] + ([hagrid] if hagrid is not None else [])
        self._lengths = [len(s) for s in self.sources]
        self._cumlen = np.cumsum(self._lengths).tolist()
        self.input_size = input_size
        self.batch_size = batch_size
        self.padding_frac = padding_frac
        self.shuffle = shuffle
        self.drop_last = drop_last
        self.use_box_encoder = use_box_encoder
        self.pos_iou = pos_iou
        self.rng = np.random.default_rng(seed)
        # mmap caches per source. If provided, the pipeline skips nvjpeg and
        # uploads pre-letterboxed uint8 (H,W,3) arrays directly. Cuts the
        # ~98ms/batch JPEG read+decode bottleneck.
        self._caches: dict[int, _ImageCache] = {}
        self.cache_root = Path(cache_root) if cache_root else None
        if self.cache_root is not None:
            for i, src in enumerate(self.sources):
                tag = _source_tag_for(src)
                c = _ImageCache(self.cache_root, tag, input_size)
                if c.ok:
                    self._caches[i] = c
                    print(f"[dali-cache] source {tag}: {len(c.idx):,} cached images",
                          flush=True)
        self._use_cache = len(self._caches) > 0
        # Per-sample box derivation is deterministic (no augmentation for Net 2).
        # Precomputed once at __init__ and persisted to a pickle in cache_root.
        # Hot-path callback becomes mmap read + array lookup (~10-15ms vs the
        # original ~70ms inline). Cold-start cost: ~3 min for ~580K samples.
        self._precomputed_boxes_cxcywh: list[np.ndarray] = []
        self._precomputed_ids: list = []
        self._precomputed_path: list[str] = []
        self._precomputed_src_idx: list[int] = []
        if self._use_cache:
            self._precompute_boxes()
        # State carried between _jpeg_callback / _boxes_callback /
        # _labels_callback / __next__. Each entry is a dict with parallel
        # per-sample box arrays in two representations:
        #   "cxcywh"     — (M_i, 4) in letterboxed PIXEL coords (legacy path)
        #   "xyxy_norm"  — (M_i, 4) in normalized [0, 1] coords (box_encoder)
        self._pending_boxes: list[dict] = []
        self._pending_ids: list[list] = []
        self._order: np.ndarray = np.arange(len(self))
        self._cursor: int = 0
        self._epoch: int = 0
        # ThreadPool for parallel per-sample mmap page-fault servicing + box
        # derivation. Boosted from 8 → 32 workers since cache-mode threading
        # is now I/O-bound on page faults rather than CPU-bound on JPEG decode.
        self._pool = ThreadPoolExecutor(max_workers=32)
        self._reshuffle()

        # Pre-compute anchors in normalized xyxy form for fn.box_encoder.
        # generate_anchors returns (N, 4) cxcywh in PIXEL coords for input_size.
        # box_encoder requires xyxy in normalized [0, 1] form.
        # Some anchors at the grid edges extend outside [0, 1] (e.g. corner
        # anchors of the 24x24 grid at scale 0.10 have x1 ≈ -0.029, x2 ≈ 0.071).
        # We DO NOT clip these for two reasons:
        #   (a) An unclipped xyxy normalized anchor has cx = (x1+x2)/2 and
        #       w = x2-x1 that match the original (cxcywh) anchor exactly.
        #       Clipping would shrink the anchor, change its cx/w, and create
        #       a train/inference mismatch since `decode_box` at inference
        #       time uses the ORIGINAL (unclipped) anchors from get_anchors().
        #   (b) For IoU, GT boxes are clipped to [0, 1] (see _prepare_one)
        #       so the intersection of (negative-x1 anchor) ∩ (clipped GT) is
        #       still well-defined. The IoU drops by at most the unclipped
        #       sliver of the anchor — a tiny effect that does not change
        #       which GT a given anchor matches in practice.
        anchors_xywh_px = generate_anchors(input_size=input_size)
        anchors_xyxy_px = np.stack([
            anchors_xywh_px[:, 0] - anchors_xywh_px[:, 2] * 0.5,
            anchors_xywh_px[:, 1] - anchors_xywh_px[:, 3] * 0.5,
            anchors_xywh_px[:, 0] + anchors_xywh_px[:, 2] * 0.5,
            anchors_xywh_px[:, 1] + anchors_xywh_px[:, 3] * 0.5,
        ], axis=1).astype(np.float32)
        anchors_xyxy_norm = (anchors_xyxy_px / float(input_size)).astype(np.float32)
        self._anchors_xyxy_norm = anchors_xyxy_norm
        self._n_anchors = anchors_xyxy_norm.shape[0]
        # DALI expects anchors as a flat list of floats, length = 4 * N.
        self._anchors_flat = anchors_xyxy_norm.reshape(-1).tolist()

        print(f"[init] DALIDetectorLoader: box_encoder={use_box_encoder} "
              f"n_anchors={self._n_anchors} input_size={input_size}",
              flush=True)
        if use_box_encoder:
            print(f"[init] DALIDetectorLoader using box_encoder "
                  f"(CPU anchor matching disabled, criteria={pos_iou}). "
                  f"NOTE: neg_iou ignore-zone trade-off — anchors with IoU < "
                  f"{pos_iou} are negatives (no -1 ignore zone).",
                  flush=True)

        if use_box_encoder:
            @pipeline_def(batch_size=batch_size, num_threads=num_threads,
                          device_id=device_id, prefetch_queue_depth=prefetch)
            def _pipe():
                # Single multi-output callback returns (jpegs, gt_boxes, gt_labels)
                # so all three outputs share the same _prepare_batch tick — no
                # ordering / pending-queue races between separate callbacks.
                jpegs, gt_boxes, gt_labels = fn.external_source(
                    source=self._multi_callback,
                    num_outputs=3,
                    batch=True,
                    dtype=[types.UINT8, types.FLOAT, types.INT32],
                    name="jpegs_boxes_labels",
                )
                img = fn.decoders.image(jpegs, device="mixed", output_type=types.RGB)
                resized = fn.resize(img, resize_longer=input_size,
                                    interp_type=types.INTERP_LINEAR)
                padded = fn.paste(resized, paste_x=0.5, paste_y=0.5, ratio=1.0,
                                  min_canvas_size=input_size, fill_value=0)
                normed = fn.normalize(padded, mean=127.5, stddev=127.5,
                                      dtype=types.FLOAT)
                chw = fn.transpose(normed, perm=[2, 0, 1])
                # box_encoder runs on CPU. `criteria` is the positive IoU.
                # `offset=True` returns encoded deltas (gt - anchor) / anchor.
                # stds=[1,1,1,1] disables std normalization so the math matches
                # our `encode_box` 1:1 (dx,dy,dw,dh as defined above).
                enc_boxes, enc_labels = fn.box_encoder(
                    gt_boxes, gt_labels,
                    anchors=self._anchors_flat,
                    criteria=float(pos_iou),
                    offset=True,
                    stds=[1.0, 1.0, 1.0, 1.0],
                    means=[0.0, 0.0, 0.0, 0.0],
                )
                return chw, enc_boxes, enc_labels
        elif self._use_cache:
            # Cache fast-path: external_source returns pre-letterboxed uint8
            # (H,W,3) arrays. We skip nvjpeg + resize + paste entirely — the
            # cache already holds letterboxed images at `input_size`. The only
            # GPU work is .gpu() upload + normalize + transpose.
            @pipeline_def(batch_size=batch_size, num_threads=num_threads,
                          device_id=device_id, prefetch_queue_depth=prefetch)
            def _pipe():
                imgs = fn.external_source(source=self._image_callback, batch=True,
                                          dtype=types.UINT8, name="imgs",
                                          layout="HWC")
                gpu_imgs = imgs.gpu()
                normed = fn.normalize(gpu_imgs, mean=127.5, stddev=127.5,
                                      dtype=types.FLOAT)
                chw = fn.transpose(normed, perm=[2, 0, 1])
                return chw
        else:
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

    def _prepare_one(self, i: int) -> tuple:
        """Worker function: load + derive boxes for one sample.

        Returns:
            (jpeg_bytes, boxes_cxcywh_px, boxes_xyxy_norm, image_id)
            - boxes_cxcywh_px: (M, 4) float32 in letterboxed PIXEL coords
              (cx, cy, w, h). Used by the non-encoder code path (`_build_targets`).
            - boxes_xyxy_norm: (M, 4) float32 xyxy in NORMALIZED [0, 1] coords,
              clipped to [0, 1] so DALI's box_encoder sees in-range inputs.
              Used by the `use_box_encoder=True` code path.
            Both are derived from the same letterboxed bbox so the two paths are
            semantically identical (modulo the clip — see note below).
        """
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
        boxes_cxcywh = np.zeros((len(boxes_in_input), 4), dtype=np.float32)
        for k, b in enumerate(boxes_in_input):
            boxes_cxcywh[k] = [b.x + b.w / 2, b.y + b.h / 2, b.w, b.h]
        # xyxy normalized [0,1] for DALI's box_encoder. We CLIP GTs to [0,1]
        # because a GT box that extends outside the image canvas is not
        # physically meaningful (the visible content is bounded by the
        # letterbox). Anchors are NOT clipped (see __init__ note) since their
        # role is to match objects regardless of canvas overlap.
        if len(boxes_in_input) > 0:
            inv = 1.0 / float(self.input_size)
            x1 = (boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] * 0.5) * inv
            y1 = (boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] * 0.5) * inv
            x2 = (boxes_cxcywh[:, 0] + boxes_cxcywh[:, 2] * 0.5) * inv
            y2 = (boxes_cxcywh[:, 1] + boxes_cxcywh[:, 3] * 0.5) * inv
            boxes_xyxy_norm = np.stack([
                np.clip(x1, 0.0, 1.0),
                np.clip(y1, 0.0, 1.0),
                np.clip(x2, 0.0, 1.0),
                np.clip(y2, 0.0, 1.0),
            ], axis=1).astype(np.float32)
            # Drop degenerate boxes (width or height <= 0 after clip).
            keep = (boxes_xyxy_norm[:, 2] > boxes_xyxy_norm[:, 0]) & \
                   (boxes_xyxy_norm[:, 3] > boxes_xyxy_norm[:, 1])
            boxes_xyxy_norm = boxes_xyxy_norm[keep]
        else:
            boxes_xyxy_norm = np.zeros((0, 4), dtype=np.float32)
        return jpeg_bytes, boxes_cxcywh, boxes_xyxy_norm, sample.get("image_id", int(i))

    def _precompute_boxes(self) -> None:
        """One-time precompute of palm boxes for every sample.

        Net 2 has no per-sample augmentation, so boxes are deterministic given
        the source dataset annotations. Storing them once eliminates the
        per-batch palm_bbox/keypoint-geometry work (was ~1.6ms/sample, the
        callback's dominant cost).
        """
        import time as _time
        import pickle
        t0 = _time.time()
        N = len(self)
        # Disk cache for the precomputed boxes — they never change.
        ds_sig = "_".join(str(l) for l in self._lengths) + f"_{self.input_size}"
        cache_pkl = self.cache_root / f"box_precompute_{ds_sig}.pkl" \
            if self.cache_root else None
        if cache_pkl is not None and cache_pkl.exists():
            print(f"[dali-cache] loading precomputed boxes from {cache_pkl} ...", flush=True)
            with open(cache_pkl, "rb") as f:
                data = pickle.load(f)
            self._precomputed_boxes_cxcywh = data["boxes"]
            self._precomputed_src_idx = data["src_idx"]
            self._precomputed_path = data["path"]
            self._precomputed_ids = data["ids"]
            print(f"[dali-cache] loaded {len(self._precomputed_ids):,} entries in "
                  f"{_time.time()-t0:.1f}s", flush=True)
            return

        def _one(idx: int) -> tuple[np.ndarray, int, str, int]:
            source, local = self._resolve(int(idx))
            sample = source[local]
            path = str(sample["image_path"])
            src_i, _ = self._resolve_src_idx(int(idx))
            # We need img_w/img_h. If the cache has this sample, use the cached
            # source dims; otherwise probe via PIL (rare on cv2-fallback samples).
            cache = self._caches.get(src_i)
            if cache is not None and cache.idx.get(path) is not None:
                entry = cache.idx[path]
                img_w = int(entry["source_w"])
                img_h = int(entry["source_h"])
            else:
                ji = _read_jpeg_with_dims(path)
                if ji is None:
                    return (np.zeros((0, 4), dtype=np.float32), src_i, path,
                            int(sample.get("image_id", idx)))
                _, img_w, img_h = ji

            if isinstance(source, HaGRIDDataset):
                boxes = hagrid_bboxes_to_pixel(sample["norm_bboxes"], img_w, img_h,
                                               leading_hand=sample.get("leading_hand", "right"))
            else:
                boxes = palm_bbox_for_each_hand(sample["keypoints"], sample["visible"],
                                                pad=self.padding_frac)
            boxes_in_input = [
                _normalize_bbox_to_input(b, img_w, img_h, self.input_size) for b in boxes
            ]
            boxes_cxcywh = np.zeros((len(boxes_in_input), 4), dtype=np.float32)
            for k, b in enumerate(boxes_in_input):
                boxes_cxcywh[k] = [b.x + b.w / 2, b.y + b.h / 2, b.w, b.h]
            # Image IDs are heterogeneous: COCO int, HaGRID UUID string, FreiHAND int.
            return boxes_cxcywh, src_i, path, sample.get("image_id", idx)

        print(f"[dali-cache] precomputing boxes for {N:,} samples...", flush=True)
        # Single-process; palm_bbox / hagrid_bboxes_to_pixel are numpy-heavy
        # and release the GIL well enough that threading helps; but spawning
        # process pool here would require pickling source datasets which is
        # expensive. Falling back to single-thread serial is fast enough
        # at ~1.6ms/sample × 581K = ~15min worst case, much better cached.
        from concurrent.futures import ThreadPoolExecutor as _TPool
        with _TPool(max_workers=16) as pool:
            results = list(pool.map(_one, range(N), chunksize=512))
        self._precomputed_boxes_cxcywh = [r[0] for r in results]
        self._precomputed_src_idx = [r[1] for r in results]
        self._precomputed_path = [r[2] for r in results]
        self._precomputed_ids = [r[3] for r in results]
        dt = _time.time() - t0
        print(f"[dali-cache] box precompute done in {dt:.1f}s "
              f"({N/max(dt,1e-6):,.0f} samples/sec)", flush=True)
        if cache_pkl is not None:
            try:
                with open(cache_pkl, "wb") as f:
                    pickle.dump({
                        "boxes": self._precomputed_boxes_cxcywh,
                        "src_idx": self._precomputed_src_idx,
                        "path": self._precomputed_path,
                        "ids": self._precomputed_ids,
                    }, f, protocol=pickle.HIGHEST_PROTOCOL)
                print(f"[dali-cache] saved precompute to {cache_pkl}", flush=True)
            except Exception as e:
                print(f"[dali-cache] WARN failed to save precompute: {e}", flush=True)

    def _prepare_one_decoded(self, i: int) -> tuple:
        """Cache-path counterpart of `_prepare_one`.

        Returns (decoded_uint8_HWC, boxes_cxcywh_px, boxes_xyxy_norm, image_id).
        The image is already letterboxed at `input_size` (cache provides it pre-decoded).
        Cache miss falls back to cv2.imread + letterbox in this worker thread.
        """
        source, local = self._resolve(int(i))
        sample = source[local]
        path = str(sample["image_path"])
        src_i, _ = self._resolve_src_idx(int(i))
        cache = self._caches.get(src_i)
        decoded = cache.get(path) if cache is not None else None
        if decoded is not None:
            img_hwc, img_w, img_h = decoded
            # mmap view → contiguous copy (safe to feed to DALI which expects
            # a complete buffer). Cost: 28KB memcpy per sample = ~7MB/batch.
            img_arr = np.ascontiguousarray(img_hwc)
        else:
            # Cache miss → cv2 imread + letterbox to input_size.
            img = cv2.imread(path)
            if img is None:
                # Fallback to a black placeholder + zero boxes.
                img_arr = np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8)
                empty = np.zeros((0, 4), dtype=np.float32)
                return img_arr, empty, empty, sample.get("image_id", int(i))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_h, img_w = img.shape[:2]
            scale = self.input_size / max(img_w, img_h)
            new_w = int(img_w * scale); new_h = int(img_h * scale)
            resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            canvas = np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8)
            dy = (self.input_size - new_h) // 2
            dx = (self.input_size - new_w) // 2
            canvas[dy:dy + new_h, dx:dx + new_w] = resized
            img_arr = canvas

        # Box derivation (mirror of _prepare_one)
        if isinstance(source, HaGRIDDataset):
            boxes = hagrid_bboxes_to_pixel(sample["norm_bboxes"], img_w, img_h,
                                           leading_hand=sample.get("leading_hand", "right"))
        else:
            boxes = palm_bbox_for_each_hand(sample["keypoints"], sample["visible"],
                                            pad=self.padding_frac)
        boxes_in_input = [
            _normalize_bbox_to_input(b, img_w, img_h, self.input_size) for b in boxes
        ]
        boxes_cxcywh = np.zeros((len(boxes_in_input), 4), dtype=np.float32)
        for k, b in enumerate(boxes_in_input):
            boxes_cxcywh[k] = [b.x + b.w / 2, b.y + b.h / 2, b.w, b.h]
        if len(boxes_in_input) > 0:
            inv = 1.0 / float(self.input_size)
            x1 = (boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] * 0.5) * inv
            y1 = (boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] * 0.5) * inv
            x2 = (boxes_cxcywh[:, 0] + boxes_cxcywh[:, 2] * 0.5) * inv
            y2 = (boxes_cxcywh[:, 1] + boxes_cxcywh[:, 3] * 0.5) * inv
            boxes_xyxy_norm = np.stack([
                np.clip(x1, 0.0, 1.0), np.clip(y1, 0.0, 1.0),
                np.clip(x2, 0.0, 1.0), np.clip(y2, 0.0, 1.0),
            ], axis=1).astype(np.float32)
            keep = (boxes_xyxy_norm[:, 2] > boxes_xyxy_norm[:, 0]) & \
                   (boxes_xyxy_norm[:, 3] > boxes_xyxy_norm[:, 1])
            boxes_xyxy_norm = boxes_xyxy_norm[keep]
        else:
            boxes_xyxy_norm = np.zeros((0, 4), dtype=np.float32)
        return img_arr, boxes_cxcywh, boxes_xyxy_norm, sample.get("image_id", int(i))

    def _resolve_src_idx(self, idx: int) -> tuple[int, int]:
        for i, end in enumerate(self._cumlen):
            if idx < end:
                start = self._cumlen[i - 1] if i > 0 else 0
                return i, idx - start
        raise IndexError(idx)

    def _read_one_cached(self, i: int) -> np.ndarray:
        """Fast hot-path: precomputed path/src_idx + mmap read. No box work."""
        path = self._precomputed_path[i]
        src_i = self._precomputed_src_idx[i]
        cache = self._caches.get(src_i)
        if cache is not None:
            decoded = cache.get(path)
            if decoded is not None:
                return np.ascontiguousarray(decoded[0])
        # Cache miss → cv2 letterbox. Rare (FreiHAND only).
        img = cv2.imread(path)
        if img is None:
            return np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_h, img_w = img.shape[:2]
        scale = self.input_size / max(img_w, img_h)
        new_w = int(img_w * scale); new_h = int(img_h * scale)
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8)
        dy = (self.input_size - new_h) // 2
        dx = (self.input_size - new_w) // 2
        canvas[dy:dy + new_h, dx:dx + new_w] = resized
        return canvas

    def _image_callback(self) -> list[np.ndarray]:
        """Cache-mode external_source callback.

        Uses precomputed boxes/ids + ThreadPool for mmap page-fault parallelism.
        Tried single-threaded with preallocated buffer; was 6x slower because
        the 8 threads pipeline page faults across the 45GB mmap'd cache.
        """
        if self._cursor + self.batch_size > len(self._order):
            self._epoch += 1
            self._reshuffle()
        idxs = self._order[self._cursor:self._cursor + self.batch_size]
        self._cursor += self.batch_size
        idxs_list = idxs.tolist()
        imgs = list(self._pool.map(self._read_one_cached, idxs_list))
        batch_boxes_cxcywh = [self._precomputed_boxes_cxcywh[i] for i in idxs_list]
        batch_ids = [self._precomputed_ids[i] for i in idxs_list]
        self._pending_boxes.append({
            "cxcywh": batch_boxes_cxcywh,
            "xyxy_norm": [],
        })
        self._pending_ids.append(batch_ids)
        return imgs

    def _jpeg_callback(self) -> list[np.ndarray]:
        """Called by DALI before each batch — returns a list[batch_size] of jpeg byte arrays.

        Per-sample JPEG file read + dimension probe + box derivation is done in
        parallel via a ThreadPoolExecutor (cv2/PIL release the GIL during the
        heavy work). This was the dominant Python-side cost when sequential.

        We also stash the per-sample box arrays + image ids on `self._pending_*`
        for the box/label callbacks (box_encoder mode) and the consumer
        (`__next__`) to pick up in the same batch tick. DALI invokes the
        external_source callbacks in declaration order each batch.
        """
        if self._cursor + self.batch_size > len(self._order):
            self._epoch += 1
            self._reshuffle()
        idxs = self._order[self._cursor:self._cursor + self.batch_size]
        self._cursor += self.batch_size

        # Parallel per-sample work
        results = list(self._pool.map(self._prepare_one, idxs.tolist()))
        jpegs = [r[0] for r in results]
        batch_boxes_cxcywh = [r[1] for r in results]
        batch_boxes_xyxy_norm = [r[2] for r in results]
        batch_ids = [r[3] for r in results]

        # Stash for the consumer to pick up alongside the GPU tensor.
        # Note: in box_encoder mode we also need _boxes_callback /
        # _labels_callback to pull from this same queue entry; we use a
        # parallel list keyed by call order.
        self._pending_boxes.append({
            "cxcywh": batch_boxes_cxcywh,
            "xyxy_norm": batch_boxes_xyxy_norm,
        })
        self._pending_ids.append(batch_ids)
        return jpegs

    def _boxes_callback(self) -> list[np.ndarray]:
        """Legacy: only used if the pipeline ever calls per-output sources.
        The current box_encoder pipeline uses `_multi_callback` instead."""
        return self._pending_boxes[-1]["xyxy_norm"]

    def _labels_callback(self) -> list[np.ndarray]:
        """Legacy: see `_boxes_callback`."""
        return [
            np.ones(boxes.shape[0], dtype=np.int32)
            for boxes in self._pending_boxes[-1]["xyxy_norm"]
        ]

    def _multi_callback(self) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
        """Single multi-output callback used by the box_encoder pipeline.

        Returns (jpegs, gt_boxes_xyxy_norm, gt_labels_int32) in one tick, so
        DALI gets all three outputs from the same _prepare_one call — no
        cross-callback ordering races.
        """
        if self._cursor + self.batch_size > len(self._order):
            self._epoch += 1
            self._reshuffle()
        idxs = self._order[self._cursor:self._cursor + self.batch_size]
        self._cursor += self.batch_size
        results = list(self._pool.map(self._prepare_one, idxs.tolist()))
        jpegs = [r[0] for r in results]
        batch_boxes_cxcywh = [r[1] for r in results]
        batch_boxes_xyxy_norm = [r[2] for r in results]
        batch_ids = [r[3] for r in results]
        batch_labels = [np.ones(b.shape[0], dtype=np.int32)
                        for b in batch_boxes_xyxy_norm]
        # Stash for __next__ to pick up alongside the GPU tensor.
        self._pending_boxes.append({
            "cxcywh": batch_boxes_cxcywh,
            "xyxy_norm": batch_boxes_xyxy_norm,
        })
        self._pending_ids.append(batch_ids)
        return jpegs, batch_boxes_xyxy_norm, batch_labels

    def __next__(self) -> dict:
        out = self._pipeline.run()
        from nvidia.dali.plugin.pytorch import feed_ndarray
        # out[0] = (B, 3, S, S) GPU image tensor — always present.
        img_t = torch.empty((self.batch_size, 3, self.input_size, self.input_size),
                            dtype=torch.float32, device="cuda")
        feed_ndarray(out[0].as_tensor(), img_t)
        pending = self._pending_boxes.pop(0)
        ids_batch = self._pending_ids.pop(0)

        if self.use_box_encoder:
            # out[1] = encoded box targets, out[2] = encoded class labels.
            # box_encoder runs on CPU, so out[1]/out[2] are TensorListCPU
            # with uniform per-sample shape: (N_anchors, 4) float32 and
            # (N_anchors,) int32 respectively. `.as_tensor()` collapses the
            # list into a single dense tensor (B, ...) since shapes are uniform.
            # `np.array(tensor)` triggers DALI's __array_interface__ for a
            # zero-copy view; we then copy via `torch.from_numpy(arr.copy())`
            # because the underlying DALI buffer is recycled on the next run.
            enc_boxes_t = out[1].as_tensor()       # TensorCPU (B, N, 4) float32
            enc_labels_t = out[2].as_tensor()      # TensorCPU (B, N) int32
            box_target_np = np.array(enc_boxes_t, copy=True)            # (B, N, 4)
            cls_target_np = np.array(enc_labels_t, copy=True)           # (B, N)
            # Focal loss expects (B, N) with values in {0, 1} for our single-
            # class case. box_encoder returns labels as int32; we cast to
            # int64 because the trainer compares with `targets >= 0` then
            # casts to float, and downstream code uses .long() indexing.
            box_target_t = torch.from_numpy(box_target_np)               # float32
            cls_target_t = torch.from_numpy(cls_target_np.astype(np.int64))
            return {
                "image": img_t,
                "cls_target": cls_target_t,
                "box_target": box_target_t,
                "image_id": ids_batch,
            }

        return {
            "image": img_t,
            "boxes": [torch.from_numpy(b) for b in pending["cxcywh"]],
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
