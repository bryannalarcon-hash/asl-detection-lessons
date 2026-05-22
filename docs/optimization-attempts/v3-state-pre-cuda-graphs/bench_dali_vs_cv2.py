"""Benchmark DALI vs cv2 for the Net 3 hand-crop workload.

This is the deciding test for whether DALI is worth integrating mid-run.

Workload: 1000 InterHand JPEGs, each goes through:
  1. JPEG decode (~512x334 typical)
  2. Per-sample 2x3 affine warp to (224, 224, 3) — emulates crop_hand
  3. Normalize to [-1, 1]

cv2 path runs single-threaded (to control for worker count); we also report
the projected multi-worker number assuming linear scaling up to 32 workers.

DALI path runs as a single GPU pipeline with batch_size=128. Batched NVJPEG
decode + batched warp_affine + batched normalize, no Python per-image loops.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from pathlib import Path

# Repo path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import cv2
import numpy as np
import torch

# Pin cv2 to 1 thread per process so we measure single-core decode honestly.
cv2.setNumThreads(1)


def random_affine_M(out_size: int = 224) -> np.ndarray:
    """Build a plausible 2x3 affine matrix mimicking crop_hand's output."""
    cx = random.uniform(80, 400)
    cy = random.uniform(80, 250)
    bw = random.uniform(60, 180)
    bh = random.uniform(60, 180)
    scale = out_size / max(bw, bh)
    rot = random.uniform(-10, 10) * np.pi / 180
    cos_a = np.cos(rot) * scale
    sin_a = np.sin(rot) * scale
    return np.array([
        [cos_a, -sin_a, out_size / 2 - cos_a * cx + sin_a * cy],
        [sin_a, cos_a, out_size / 2 - sin_a * cx - cos_a * cy],
    ], dtype=np.float32)


def bench_cv2(paths: list[str], affines: list[np.ndarray],
              out_size: int = 224) -> tuple[float, float]:
    """Single-threaded cv2 path. Returns (samples/sec, total seconds)."""
    # Warm cache
    for p in paths[:50]:
        open(p, "rb").read()
    t0 = time.time()
    for p, M in zip(paths, affines):
        img = cv2.imread(p)
        if img is None:
            continue
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        crop = cv2.warpAffine(img, M, (out_size, out_size),
                              flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        # normalize to [-1, 1]
        crop_f = crop.astype(np.float32) / 255.0
        crop_f = (crop_f - 0.5) / 0.5
        # convert to CHW tensor (matches what the dataset returns)
        _ = torch.from_numpy(crop_f).permute(2, 0, 1)
    elapsed = time.time() - t0
    return len(paths) / elapsed, elapsed


def bench_dali(paths: list[str], affines: list[np.ndarray],
               out_size: int = 224, batch_size: int = 128) -> tuple[float, float]:
    """DALI GPU path. Returns (samples/sec, total seconds)."""
    from nvidia.dali import pipeline_def, fn, types

    n = len(paths)
    n_batches = (n + batch_size - 1) // batch_size

    # Use callable source — DALI invokes it per batch as needed and handles end.
    state = {"i": 0}

    def jpeg_src():
        bi = state["i"] % n_batches
        sl_start = bi * batch_size
        sl_end = min(sl_start + batch_size, n)
        return [np.frombuffer(open(paths[k], "rb").read(), dtype=np.uint8)
                for k in range(sl_start, sl_end)]

    def affine_src():
        bi = state["i"] % n_batches
        sl_start = bi * batch_size
        sl_end = min(sl_start + batch_size, n)
        out = [affines[k].astype(np.float32) for k in range(sl_start, sl_end)]
        state["i"] += 1
        return out

    @pipeline_def(batch_size=batch_size, num_threads=8, device_id=0,
                  prefetch_queue_depth=2)
    def pipe():
        jpegs = fn.external_source(source=jpeg_src, name="jpegs",
                                   dtype=types.UINT8, batch=True)
        affines_t = fn.external_source(source=affine_src, name="affines",
                                       dtype=types.FLOAT, batch=True)
        img = fn.decoders.image(jpegs, device="mixed", output_type=types.RGB)
        warped = fn.warp_affine(img, matrix=affines_t, size=(out_size, out_size),
                                fill_value=0, interp_type=types.INTERP_LINEAR)
        normed = fn.normalize(warped.gpu(), mean=127.5, stddev=127.5,
                              dtype=types.FLOAT)
        chw = fn.transpose(normed, perm=[2, 0, 1])
        return chw

    p = pipe()
    p.build()

    # Warm-up
    _ = p.run()
    state["i"] = 0  # reset counter so we time exactly n_batches batches

    t0 = time.time()
    seen = 0
    for _ in range(n_batches):
        out = p.run()
        # Force device sync by materializing on CPU side
        _ = out[0].as_cpu()
        seen += batch_size
    elapsed = time.time() - t0
    return seen / elapsed, elapsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--out-size", type=int, default=224)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--interhand-root", default="data/interhand/images/train")
    args = ap.parse_args()

    random.seed(7)
    print(f"[setup] sampling {args.n} InterHand train JPEGs...")
    all_paths = []
    # Just take whatever's in train/, walk a sample of capture dirs
    captures = list(Path(args.interhand_root).glob("Capture*"))
    random.shuffle(captures)
    for cap in captures:
        for jpg in cap.rglob("*.jpg"):
            all_paths.append(str(jpg))
            if len(all_paths) >= args.n * 2:
                break
        if len(all_paths) >= args.n * 2:
            break
    random.shuffle(all_paths)
    paths = all_paths[:args.n]
    affines = [random_affine_M(args.out_size) for _ in range(args.n)]
    print(f"  got {len(paths)} paths")

    print(f"\n[cv2] single-threaded baseline...")
    cv2_rate, cv2_sec = bench_cv2(paths, affines, out_size=args.out_size)
    print(f"  cv2: {cv2_rate:7.1f} samples/sec  ({cv2_sec:.1f}s for {args.n} imgs)")

    print(f"\n[dali] GPU pipeline (batch={args.batch}, NVJPEG + warp_affine)...")
    try:
        dali_rate, dali_sec = bench_dali(paths, affines, out_size=args.out_size,
                                         batch_size=args.batch)
        print(f"  dali: {dali_rate:7.1f} samples/sec  ({dali_sec:.1f}s for {args.n} imgs)")
    except Exception as e:
        print(f"  dali FAILED: {type(e).__name__}: {e}")
        return 1

    print()
    print(f"=== RESULTS ===")
    print(f"  cv2 single-thread:    {cv2_rate:7.1f} samples/sec")
    print(f"  cv2 × 32 workers est: {cv2_rate * 32:7.1f} samples/sec (linear scale ceiling)")
    print(f"  dali (single proc):   {dali_rate:7.1f} samples/sec")
    print(f"  dali vs cv2-single:   {dali_rate / cv2_rate:.1f}×")
    print(f"  dali vs cv2-32w est:  {dali_rate / (cv2_rate * 32):.2f}×")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
