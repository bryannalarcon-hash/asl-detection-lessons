"""Build a mmap'd decoded-image cache for Net 2 (palm detector) training.

Pre-decodes JPEGs to (input_size, input_size, 3) uint8 letterboxed arrays,
stored in a single per-source binary file with a JSON index. Eliminates
~99% of CPU image-load time at training (cv2.imread ~1.76 ms → mmap slice
~5 µs per image, validated by benchmark).

Multi-process: workers each open the pre-allocated mmap, decode their
assigned paths, and write to disjoint row indices.

Layout:
  cache_root/hagrid/images.bin   uint8 (N, S, S, 3)
  cache_root/hagrid/index.json   {input_size, shape, index: {abspath: {row, source_w, source_h}}}
  cache_root/coco/...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# Make `src` importable when running this file as a script (not via `python -m`).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import cv2
import numpy as np
from tqdm import tqdm

# Avoid contention between cv2's internal thread pool and our process pool.
cv2.setNumThreads(1)
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

from src.stage1.data.coco_wholebody import CocoWholeBodyDataset
from src.stage1.data.egohands import EgoHandsDataset
from src.stage1.data.freihand import FreiHANDDataset
from src.stage1.data.hagrid import HaGRIDDataset
from src.stage1.data.synthetic_composite import SyntheticCompositeDataset


def collect_unique_paths(dataset, max_samples: int | None = None) -> list[str]:
    """Walk the dataset and return absolute paths deduplicated by image."""
    seen: set[str] = set()
    out: list[str] = []
    n = len(dataset) if max_samples is None else min(max_samples, len(dataset))
    print(f"  scanning {n:,} dataset entries for unique image paths...")
    for i in tqdm(range(n)):
        try:
            s = dataset[i]
        except Exception:
            continue
        p = str(Path(s["image_path"]).resolve())
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


# Worker-side state. ProcessPoolExecutor uses fork on Linux by default, so
# the child inherits these globals AFTER they're set in main().
_WORKER_BIN = ""
_WORKER_N = 0
_WORKER_S = 0
_WORKER_ARR: np.ndarray | None = None


def _init_worker(bin_path: str, n: int, input_size: int) -> None:
    """Open the mmap once per worker process. Called via ProcessPoolExecutor initializer."""
    global _WORKER_BIN, _WORKER_N, _WORKER_S, _WORKER_ARR
    _WORKER_BIN = bin_path
    _WORKER_N = n
    _WORKER_S = input_size
    _WORKER_ARR = np.memmap(bin_path, dtype="uint8", mode="r+",
                            shape=(n, input_size, input_size, 3))
    cv2.setNumThreads(1)


def _decode_one(row_and_path: tuple[int, str]) -> tuple[str, int, int, int, bool]:
    """Decode one image, write to its row. Returns (path, row, source_w, source_h, ok)."""
    row, path = row_and_path
    img = cv2.imread(path)
    if img is None:
        return (path, row, 0, 0, False)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = img.shape[:2]
    s = _WORKER_S / max(h, w)
    nh = max(1, int(h * s))
    nw = max(1, int(w * s))
    rz = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((_WORKER_S, _WORKER_S, 3), dtype=np.uint8)
    dy = (_WORKER_S - nh) // 2
    dx = (_WORKER_S - nw) // 2
    canvas[dy:dy + nh, dx:dx + nw] = rz
    _WORKER_ARR[row] = canvas
    return (path, row, int(w), int(h), True)


def build_cache(paths: list[str], out_dir: Path, input_size: int,
                workers: int) -> None:
    N = len(paths)
    out_dir.mkdir(parents=True, exist_ok=True)
    bin_path = out_dir / "images.bin"
    idx_path = out_dir / "index.json"

    print(f"  allocating {N:,} x {input_size}x{input_size}x3 bytes = "
          f"{N * input_size * input_size * 3 / 1024 / 1024 / 1024:.2f} GB")
    arr = np.memmap(bin_path, dtype="uint8", mode="w+",
                    shape=(N, input_size, input_size, 3))
    arr.flush()
    del arr  # close so workers can re-open r+

    print(f"  decoding with {workers} workers...")
    t0 = time.time()
    decoded = 0
    skipped = 0
    index: dict[str, dict] = {}
    args_iter = list(enumerate(paths))

    with ProcessPoolExecutor(max_workers=workers,
                             initializer=_init_worker,
                             initargs=(str(bin_path), N, input_size)) as ex:
        for path, row, sw, sh, ok in tqdm(
                ex.map(_decode_one, args_iter, chunksize=64),
                total=N):
            if ok:
                index[path] = {"row": row, "source_w": sw, "source_h": sh}
                decoded += 1
            else:
                skipped += 1

    elapsed = time.time() - t0
    print(f"  done: {decoded:,} decoded, {skipped:,} skipped, "
          f"{elapsed:.1f}s ({decoded / max(elapsed, 1e-6):.0f} imgs/sec)")

    with idx_path.open("w") as f:
        json.dump({
            "input_size": input_size,
            "shape": [N, input_size, input_size, 3],
            "n_valid": decoded,
            "index": index,
        }, f)
    print(f"  wrote {bin_path} ({bin_path.stat().st_size / 1024 / 1024 / 1024:.2f} GB)")
    print(f"  wrote {idx_path} ({idx_path.stat().st_size / 1024:.1f} KB)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-root", default="data/net2_cache")
    ap.add_argument("--input-size", type=int, default=192)
    ap.add_argument("--sources", default="hagrid,coco",
                    help="Comma-separated subset of "
                         "{hagrid,coco,freihand,egohands,synthetic}.")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--max-samples", type=int, default=None)
    ap.add_argument("--workers", type=int,
                    default=max(1, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()

    cache_root = Path(args.cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    for src in sources:
        out_dir = cache_root / src
        bin_p = out_dir / "images.bin"
        idx_p = out_dir / "index.json"
        if bin_p.exists() and idx_p.exists():
            with idx_p.open() as f:
                meta = json.load(f)
            if int(meta.get("input_size", -1)) == args.input_size:
                print(f"[{src}] cache already present at input_size={args.input_size}, "
                      f"skipping (n={meta.get('n_valid', '?'):,})")
                continue

        print(f"\n=== {src} ===")
        try:
            if src == "hagrid":
                ds = HaGRIDDataset(f"{args.data_root}/hagrid", split="train")
            elif src == "coco":
                ds = CocoWholeBodyDataset(
                    ann_file=f"{args.data_root}/coco/annotations/coco_wholebody_train_v1.0.json",
                    image_root=f"{args.data_root}/coco/train2017",
                )
            elif src == "freihand":
                ds = FreiHANDDataset(f"{args.data_root}/FreiHAND_pub_v2")
            elif src == "egohands":
                ds = EgoHandsDataset(f"{args.data_root}/egohands", split="train")
            elif src == "synthetic":
                ds = SyntheticCompositeDataset(f"{args.data_root}/synthetic_hands")
            else:
                print(f"  unknown source: {src}", file=sys.stderr)
                continue
        except (FileNotFoundError, OSError) as e:
            print(f"  [warn] {src} unavailable, skipping cache build: {e}",
                  file=sys.stderr)
            continue

        paths = collect_unique_paths(ds, max_samples=args.max_samples)
        build_cache(paths, out_dir, args.input_size, workers=args.workers)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
