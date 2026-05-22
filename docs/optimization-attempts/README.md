# Stage 1 v3 — Optimization Attempts Log

Chronological record of data-path / throughput optimizations attempted during
the v3 training run on a rented RTX 5090. Each entry includes what was tried,
the measured outcome, and why we kept or reverted.

The frozen file snapshots live in `v3-state-pre-cuda-graphs/` so we can diff
against future work.

## Baseline (cv2.imread + 16 workers + no cache)

- Net 2 epoch 0: 487 s (= 4.67 it/s sustained, batch 256)
- Net 3: not measured (we hit gates before it ran)
- GPU util: ~16% (CPU JPEG decode is the wall)

## 1. `num_workers: 16 → 32` ✅ kept

- Result: 4.67 → 6.8 it/s (+45%)
- Reason it worked: 32 effective CPU cores, more parallel JPEG decode
- Cost: 0 dev time. Already in code base, just config change.

## 2. GPU JPEG decode + per-image GPU resize/letterbox/warp ❌ reverted

- Files affected: `gpu_decode.py` (new), `detector_dataset.py`, `landmark_dataset.py`, `train_v3_*.py`
- Idea: replace `cv2.imread → cv2.resize` with `torchvision.io.decode_jpeg(device='cuda') + GPU resize`
- Result: 6.8 → 4.7 it/s (−31%) on Net 2
- Why it didn't work: per-image GPU resize/letterbox in a Python loop adds
  ~150 ms of CUDA kernel launch overhead per batch. Each `F.interpolate` call
  costs ~100–200 μs of launch + sync overhead × 256 images = 38+ ms wasted.
  Bigger than the cv2 decode it replaced.
- Lesson: GPU NVJPEG decode is real, but doing **per-image** GPU work in a
  Python loop is a regression — you need fully batched ops to beat CPU.

## 3. Decoded npy mmap cache for HaGRID + COCO ✅ kept

- Files: `scripts/build_net2_cache.py` (new), `data/detector_dataset.py` (cache lookup path)
- Pre-decode + pre-letterbox all HaGRID (500K) + COCO (37K) images to a single
  mmap'd binary file per source. Loader reads with `mmap[i]` instead of
  cv2.imread.
- Build cost: ~11 min one-time at first (single-threaded); ~1 min later with
  ProcessPoolExecutor (32 workers).
- Disk cost: +55 GB (HaGRID 42 GB + COCO 13 GB).
- Measured: cv2 = 569 imgs/sec per worker; mmap = 201,185 imgs/sec per worker.
- Training: Net 2 epoch 0 went 487 s → 287 s (−41%).
- Why it worked: removed the entire 1.76 ms/image JPEG decode + resize cost.
  The next bottleneck (anchor matching, model compute) became visible.
- Why it's not applied to Net 3: InterHand at full-res cache would be ~600 GB,
  doesn't fit on the 200 GB disk. Per-sample crops also rule it out.

## 4. DALI integration (parallel callback via ThreadPool) ✅ kept

- Files: `data/dali_pipelines.py` (new), `train_v3_*.py` (`--use-dali` flag),
  `requirements.txt` (nvidia-dali-cuda120)
- Replaced `DataLoader` with DALI pipeline doing batched NVJPEG decode +
  resize/letterbox / per-sample warp_affine + normalize on GPU.
- Standalone bench (Net 3 workload, no model): DALI single proc = 8000 imgs/sec
  vs cv2 single-thread = 1073 imgs/sec (7.5× faster).
- In real training: Net 2 = 10 it/s, Net 3 = 15 it/s sustained.
- Parallel callback (A): `_jpeg_callback` reads JPEGs across an 8-thread pool
  inside DALI's external_source — cv2/PIL release the GIL so threads work.
- Why it's "only" 20–50% faster than cache+cv2: model compute + anchor matching
  + Python overhead in the data path are the next bottlenecks (see #5).

## 5. GPU anchor matching (`build_targets_gpu`) ❌ reverted

- Files: `models/anchors.py` (`build_targets_gpu` added)
- Idea: move the 26 ms/batch numpy IoU + assignment + encode_box loop to GPU.
- Result: 10 → 3.5 it/s on Net 2 (−65%, big regression)
- Why it failed: Python `for b in range(256): <10 small GPU ops>` =
  2560 CUDA kernel launches × ~50 μs = ~128 ms of pure launch overhead per
  batch. The numpy "26 ms anchor matching" was actually CHEAPER than the
  small-op GPU launch overhead.
- Lesson: small GPU ops in a Python loop are SLOWER than equivalent numpy on
  CPU when batch counts are small. Either fully batch the ops (pad GTs to
  max count) or keep CPU.
- Code kept in `anchors.py` for reference; trainer reverted to numpy.

## 6. Synthetic-input model ceiling bench (instrumentation, not optimization)

- Files: `scripts/bench_model_ceiling.py` (new)
- Synthesized zero tensors → model + loss + backward + optimizer (no data path)
- Net 2 ceiling (model only): 39.5 it/s. + anchor matching: 19.4 it/s.
- Net 3 ceiling (model only): 54.9 it/s. + kornia aug: 34.9 it/s.
- Observed (DALI training): Net 2 ~10 it/s, Net 3 ~15 it/s.
- Diagnosis: ~50 ms/batch Net 2 and ~38 ms/batch Net 3 of overhead lives
  *between* DALI data delivery and the model step (Python glue + per-launch
  overhead in the training loop).

## What's actually capping us (state after #4)

| Stage | Observed | Model+aux ceiling | Hidden gap |
|---|---|---|---|
| Net 2 | 10 it/s (100 ms/batch) | 19.4 it/s (51 ms/batch) | 50 ms/batch — Python glue + DALI→torch + numpy anchor work |
| Net 3 | 15 it/s (67 ms/batch) | 34.9 it/s (29 ms/batch) | 38 ms/batch — Python glue + DALI→torch + heatmap render |

## Next: CUDA Graphs + DALI `fn.box_encoder`

The pattern of "small ops + Python glue + per-launch overhead" is best killed
by:

1. **CUDA Graphs** — capture the model forward + loss + backward + optimizer
   step once, replay per batch. Eliminates per-iteration Python and launch
   overhead inside the training step. Requires fixed shapes (we have them).

2. **DALI `fn.box_encoder`** — Net 2's anchor matching moves from numpy CPU
   into the data pipeline as a GPU operator. Eliminates the 26 ms/batch
   numpy work plus the cpu→gpu transfer of cls/box targets.

These are the "v4 architectural moves" referenced in v3-plan.md, applied
mid-run because the training math made the wall-clock unworkable.

## Files in this directory

- `v3-state-pre-cuda-graphs/` — frozen copies of trainer + DALI loader + helpers
  immediately before the CUDA Graphs + box_encoder work. Diff against the live
  files to see the change.
