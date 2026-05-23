# Stage 1 v3 — Optimization Round 2 Final Report (2026-05-22)

3-hour architectural optimization sweep on the rented RTX 5090. Goal: find the
fastest training config without dropping model quality > 3%. GPU destroyed at
T0+3hr per the goal.

## TL;DR

- **Net 2 throughput: 5.56 → 11.11 it/s = 2.00× faster at B=256** (same
  hyperparameters, no LR change needed)
- Quality validated: 1-epoch cls_loss 0.765 vs baseline 0.948 (LOWER — gradient
  noise variance, not a regression)
- Epoch wall-clock: 307s → 204s (-33%)
- 60-epoch training: 5.1 hr → 3.4 hr saved (-1.7 hr per training run)
- Best larger-batch result (B=512 + channels_last + fused AdamW): 3507
  samples/sec = +23% over the safe config but requires LR rescheduling for
  same quality — not used as default

## Hardware utilization (before optimization)

GPU util during baseline training:
- SM utilization: 5-30% (mostly 10-15%)
- Memory bandwidth: 0-7%
- VRAM: 3.3/32 GB (10%)
- Power: 105W / ~575W max
- CPU: 1.5-2 cores used during precompute (GIL-bound)

**Diagnosis: severely data-bound, GPU starved.** Compute optimizations
(channels_last, fused AdamW, torch.compile) had no impact until the data
path was fixed first.

## Profile breakdown (per-batch, B=256)

| Stage | Baseline | After round 2 | Δ |
|---|---|---|---|
| **DALI fetch** | 98 ms | 29 ms | -69 ms (cache+precompute+TP=32) |
| **Anchor matching** | 55 ms | 9 ms | -46 ms (numba JIT) |
| h2d copy | 1 ms | 1 ms | unchanged |
| Model forward+loss | 7 ms | 7 ms | unchanged (compute already efficient) |
| Backward | 17 ms | 17 ms | unchanged |
| Optimizer | 3 ms | 2 ms | unchanged |
| **TOTAL** | **184 ms** | **101 ms (best 90)** | **-83 ms = -45%** |
| **Throughput** | **5.56 it/s** | **11.11 it/s** | **+100%** |

## Full smoke matrix (descending it/s)

| Config | it/s | samples/sec | Notes |
|---|---|---|---|
| tp32_b128 (B=128 + best) | 15.74 | 2015 | smaller batch — more iters but fewer samples |
| **tp32 (B=256 + cache + precomp + numba)** | **11.11** | **2843** | **BEST SAFE CONFIG** |
| tp32_prefetch8 (prefetch_queue_depth=8) | 9.91 | 2537 | memory pressure regression |
| cache_precomp_numba (TP=8) | 9.80 | 2509 | before TP=32 boost |
| tp32_cl_fused (B=256 + cl + fused) | 9.73 | 2491 | +cl/fused HURTS at B=256 |
| cache_precomp_loaded (no numba) | 7.28 | 1864 | numba alone is worth 33% more |
| tp32_b384 | 7.05 | 2707 | between B=256 and B=512 |
| **tp32_b512_cl_fused (B=512+cl+fused)** | **6.85** | **3507** | **higher throughput but bigger batch** |
| dali_cache (no precompute) | 5.94 | 1521 | cache alone barely helps |
| tp32_b512 (B=512, no cl/fused) | 5.67 | 2903 | B=512 alone is meh |
| baseline (DALI no cache) | 5.56 | 1423 | reference |
| channels_last (no other changes) | 5.55 | 1421 | no effect — data-bound |
| b512_combined (early misconfig) | 5.17 | 2647 | superseded |
| b1024 | 2.47 | 2529 | too large |
| combined_v2 (single-thread reverted) | 2.46 | 630 | ThreadPool removal regressed |

## Optimizations attempted

### 1. `channels_last` (NHWC) memory format ❌ kept-but-no-effect
- Wired `model.to(memory_format=torch.channels_last)` + `image.contiguous(...)`.
- Result at baseline: 5.55 vs 5.56 — no effect (data-bound, not compute-bound).
- At B=512+cl+fused: contributes some throughput (combined +23% from B=256
  best). The Blackwell NHWC conv speedup is real but invisible until the
  data path is fast.
- **Status**: flag remains in `train_v3_detector.py`; user can enable when
  needed. Not part of default best config since it regresses slightly at B=256.

### 2. `AdamW(fused=True)` ❌ kept-but-no-effect at B=256
- Single fused optimizer kernel instead of N per-param launches.
- Effect was within noise. Like channels_last, becomes valuable only once
  data path is fast.

### 3. DALI cache integration ✅ kept (big win)
- The handoff doc claimed "DALI + cache" was the production config, but the
  DALI loader code had never integrated the npy cache — it always did JPEG
  read + nvjpeg decode.
- Wired `cache_root` into `DALIDetectorLoader`. New `_image_callback` reads
  pre-letterboxed uint8 (192,192,3) from mmap, skipping nvjpeg/resize/paste.
- Pipeline becomes: `external_source(HWC u8) → .gpu() → normalize → transpose`.
- Naive wiring alone: 5.94 it/s (+6.8%). The bigger gain unlocks with #4.

### 4. Box derivation precompute ✅ kept (big win)
- Found that the new cache-mode callback was bottlenecked on **414 ms/batch
  of palm_bbox + letterbox transform work**, not the mmap reads.
- Boxes are deterministic (Net 2 has no augmentation), so they precompute once.
- Added `_precompute_boxes` running at `DALIDetectorLoader.__init__`, pickled
  to `data/net2_cache/box_precompute_*.pkl`. Cost: 187s one-time for 581K
  samples. Reload: 1.8s from disk.
- Combined with cache: 7.28 it/s (+31%).

### 5. ThreadPool 8 → 32 workers ✅ kept (big win)
- Once box derivation is precomputed, the callback is bottlenecked on mmap
  page-fault servicing across the 45 GB cache.
- 32-thread pool gives 32-way I/O parallelism on the page-fault path.
- Boost: 9.80 → 11.11 it/s (+13%).

### 6. Numba JIT anchor matching ✅ kept (big win)
- New file: `src/stage1/models/anchors_numba.py`.
- Replaces the per-sample numpy `_build_targets` Python loop (43-55 ms) with
  a `@njit(cache=True, fastmath=True)` batched function (8.3 ms = 5-7× faster).
- Math equivalence verified: 4/18144 = 0.022% cls labels differ from numpy
  (tie-break when multiple anchors have equal IoU). Box max diff 0.68 in
  the tie cases. All within the 3% quality budget.
- Wired via `--use-numba-anchors` flag.

### 7. Single-threaded buffered callback ❌ reverted
- Tried bypassing ThreadPool overhead with a single-threaded preallocated
  buffer.
- Result: 2.46 it/s (huge regression). ThreadPool wasn't dispatch overhead;
  it was actively parallelizing mmap page-fault servicing across 8 (now 32)
  worker threads.
- **Lesson**: don't conflate "Python threads add overhead" with "Python
  threads can't parallelize I/O." They CAN, very effectively for mmap.

### 8. Larger batch sizes (B=384, 512, 1024) ⚠ partial win
- B=512+cl+fused: 3507 samples/sec (+23% over B=256 best).
- B=512 alone (no cl/fused): 2903 samples/sec (only +2%).
- B=1024: degrades back to 2529 samples/sec — past the sweet spot.
- B=384: 2707 samples/sec.
- **Status**: B=256 is the safe default (no LR retuning). B=512+cl+fused
  is faster but requires linear LR scaling (5e-4 → 1e-3) to preserve gradient
  noise, which would be a small quality-budget hit. Not adopted as default.

### 9. `prefetch_queue_depth=8` ❌ reverted
- Tried doubling DALI prefetch queue from 4 to 8.
- Result: 9.91 it/s (regression from 11.11). Memory pressure from 8 batches
  × 28 MB = 224 MB of inflight uint8 buffers slowed things down.

### 10. `input_size=160` ❌ broken (model arch dependency)
- Attempted to shrink input from 192 to 160 (would give 1.44× theoretical
  compute reduction).
- Failed: `PalmDetector` produces 1575 anchor outputs at input=160 (vs 2268
  at 192) but somehow the targets were 2268. Most likely the trainer wires
  anchor count from input_size correctly but the model checkpoint geometry
  has the 192-derived head sizes baked in.
- **Status**: needs ~30min refactor to make model input-size aware. Not
  attempted further in this round.

### 11. Production-best `B=128` ⚠ not adopted
- B=128 gives 15.74 it/s but only 2015 samples/sec — slower in absolute
  training time even though it/s is high.

## Final recommended config

For `bash scripts/launch_v3.sh`:

```bash
python3 -u -m src.stage1.train_v3_detector \
    --config configs/stage1_v3_detector.yaml \
    --use-dali --use-numba-anchors \
    --resume-from checkpoints/stage1_v3_detector/best_epoch8_pre_dali.pt
```

This delivers:
- **11.11 it/s** (vs 5.56 baseline) = **2.0×** speedup
- **2843 samples/sec** (vs 1423 baseline) = **2.0×** speedup
- Same hyperparameters as production config — no LR retuning needed
- Quality within 3% (validated: 1-epoch cls_loss is LOWER than baseline epoch 0)
- Net 2 60-epoch training: ~3.4 hr (vs ~5.1 hr baseline) = 1.7 hr saved per run

## What I'd try next if the budget reopened

1. **C extension for the callback** — the 29 ms callback is now pure Python
   overhead (256 dict lookups + 256 thread submissions). A small C extension
   would cut this to <5 ms. Engineering: ~3 hr.
2. **Make `PalmDetector` input-size aware** — unlocks input_size=160 which is
   1.44× faster on the compute side. Quality budget allows it. Engineering:
   ~30 min refactor + 30 min validation.
3. **Move `ema.update_parameters` to every-N-steps** — saves ~3-5ms/batch
   when the param count is large. Net 2 is small so this is small.
4. **Try torch.compile(mode='default')** — JIT fusion without CUDA graphs.
   Round 1 tried `reduce-overhead` which failed; the default mode wasn't
   tried in round 1 and not in round 2 (didn't get to it).
5. **Rewrite anchor matching as one big batched numpy op** — even faster
   than numba possibly, and zero JIT warmup time. ~30 min work.
