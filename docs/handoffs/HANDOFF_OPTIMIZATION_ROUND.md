# Handoff — Stage 1 v3 Optimization Round (2026-05-22) — SUPERSEDED

> **NOTE: This document is historical** (the 3-hour optimization sweep on the rented 5090).
> **Current state is in `docs/handoffs/HANDOFF_POST_TRAIN.md`.** Read that first.
> This file is kept for reference on what was tried/measured during the optimization round (anchor matcher numba, DALI cache, precompute pickles, channels_last/fused_adamw experiments).

You are continuing work on the ASL Learning project's Stage 1 v3 training pipeline.

## 1. What's running RIGHT NOW

### Persistent Monitor (task `bcpit5tox`)
A persistent background SSH tail watching the remote training log + metrics files. Will fire `<task-notification>` events on:
- new lines in `checkpoints/stage1_v3_detector/metrics.jsonl`
- new lines in `checkpoints/stage1_v3_landmark/metrics.jsonl`
- pattern matches in `logs/launch.log` (epoch lines, Traceback, FATAL, CUDA OOM, `[4/8]`/`[6/8]`/`[7/8]`/`[8/8]` step markers, `resumed from`, `palm AP`, gate triggers)

**Do NOT TaskStop this unless you confirm the rental is being destroyed.** Use TaskList to verify it's still alive when you pick up.

### Active cron (`693264f0`)
- `*/10 * * * *` — every 10 minutes, fires a "health check" prompt asking you to ssh to the instance and report a short status table.
- Stop conditions in the cron prompt are non-actionable (just report-and-surface) — you do NOT need to keep this running. Delete with CronDelete if it's noise.

## 2. The rented GPU

- **Vast contract**: `37347023`
- **SSH**: `ssh -i ~/.ssh/vast_v3 -o StrictHostKeyChecking=no -p 27022 root@ssh9.vast.ai`
- **GPU**: RTX 5090 32 GB, Blackwell, US-Utah datacenter
- **Rate**: ~$1.27/hr
- **Wall-clock elapsed at handoff**: ~6.7 hr
- **Hard kill (per HANDOFF_STAGE1.md)**: $20 v3 spend OR 14 wall-clock hours
- **API key**: `.env.local` has `VAST_API` and `KAGGLE_API` — DO NOT echo or commit
- **Working dir on remote**: `/workspace/asl-learning`
- **Tmux session name**: `v3` (currently NOT running; production training paused)

### Data state on the remote (all confirmed present)
```
/workspace/asl-learning/data/
  coco/        ~20 GB   COCO-WholeBody (118K imgs train + val + test ann)
  FreiHAND_pub_v2/  5 GB
  hagrid/      ~14 GB   413,584 train + 24,698 val + 21,385 test
  interhand/   ~80 GB   1,361,062 train + 380K val + 849K test images + ann
  net2_cache/  55 GB   pre-decoded letterboxed npy mmap (HaGRID + COCO at 192²)
```

Disk: 174/200 GB used (87%). Tight but stable.

## 3. Current state of training

**PAUSED.** Net 2 was running with the proven-fastest config (DALI + cache + parallel callback + BF16) when the user pivoted to optimization work.

### Last completed Net 2 epoch (in `checkpoints/stage1_v3_detector/metrics.jsonl`)
```
{"epoch": 8, "epoch_secs": 300.6, "train_loss": 0.185, "cls_loss": 0.145, "box_loss": 0.040, "lr": 4.88e-4}
```

### Net 2 resume checkpoint
**`/workspace/asl-learning/checkpoints/stage1_v3_detector/best_epoch8_pre_dali.pt`** (2.5 MB)
- Saved as a backup before the optimization rabbit hole
- This is the EMA weights from epoch 8
- Use `--resume-from <this path>` to continue Net 2 from epoch 9

### Net 3 has NOT been trained yet
- Net 3 P1 (70 epochs × ~25 min ≈ 29 hr) — not feasible inside the 14h kill budget no matter what
- Plan: Net 3 likely deferred to a future rental, OR run with capped epochs

## 4. The optimization round — context

User goal (now CLEARED with `/goal clear`): "get the optimizations working. Don't abandon them unless ran through with me. I want to see smoke like the estimates you gave and ideal is sub hour training."

**Conclusion reached**: sub-hour Net 2 at current quality is **mathematically impossible** on this 5090 with this model architecture. Synthetic-input model ceiling is 19.4 it/s (with anchor matching) or 39.5 it/s (model+loss only) = absolute floor of ~57 min for 60 epochs of Net 2. Net 3 ceiling is ~5.6 hours.

User's latest directive (just before compaction): use remaining ~1.5 hr of GPU time PURELY for optimization smoke testing (NOT training). Find the optimal training setup. Then ship to a separate run.

## 5. Bench data — what we measured

Smokes done on the remote (numbers are **sustained it/s** for Net 2, batch 256, input 192²):

| Config | it/s | Notes |
|---|---|---|
| Original cv2 + 16 workers | 5.5 | starting baseline |
| cv2 + 32 workers | 6.8 | num_workers helped |
| cv2 + cache + 32 workers | 8.2 | **+ npy cache** |
| **DALI + ThreadPool + cache + BF16** | **10.0** | **current best, used for production** |
| GPU JPEG decode in workers | 4.7 | regression (per-image Python loop) |
| DALI + GPU anchor matcher (Python loop) | 3.5 | regression |
| DALI + GPU anchor matcher (batched padding) | 6.0 | still regression (bandwidth-bound) |
| DALI + DALI box_encoder | 7-9 | marginal regression (DALI op is CPU) |
| DALI + raw cuda graph | 5.8 | AccumulateGrad stream mismatch |
| DALI + `make_graphed_callables` | 6.2 | same stream mismatch |
| DALI + `torch.compile(reduce-overhead)` | 6.1 | same |

**Pattern**: every CUDA-graph variant ~40% SLOWER than eager DALI. The eager autograd machinery in PyTorch 2.11 is faster than the captured equivalents we can build on this model/loss structure.

### Synthetic model ceiling (no data path, just zero tensors)
- Net 2 model + loss only: **39.5 it/s** (25 ms/batch)
- + numpy anchor matching: **19.4 it/s** (51 ms/batch; anchor matching costs 26 ms)
- + observed in DALI: **10 it/s** (100 ms/batch; ~50 ms hidden glue overhead)
- Net 3 model + loss only: 54.9 it/s (18.2 ms)
- + kornia aug: **34.9 it/s** (28.6 ms)
- + observed in DALI: **15 it/s** (66.7 ms)

## 6. Plan you were in the middle of when compaction hit

Smoke matrix to find the optimal training setup using the remaining ~1.5 hr GPU budget:

| # | Optimization | Why | Expected gain | Status |
|---|---|---|---|---|
| 1 | **`channels_last` memory format (NHWC)** | Blackwell convs are 1.2-1.5× faster on NHWC | +20-40% | **IN PROGRESS — flag added but not yet wired into model.to() / inputs** |
| 2 | **`AdamW(fused=True)`** | Single fused optimizer kernel, removes ~600 launches/step | +3-7% | flag added, not yet wired |
| 3 | `torch.compile(model, mode='default')` (no reduce-overhead) | JIT kernel fusion WITHOUT cuda-graphs | uncertain | not yet started |
| 4 | Batched numpy IoU in `_build_targets` | Replace `for b in range(B)` with vectorized | +5-15% | not yet started |
| 5 | Combined best | Stack winners | — | not yet started |
| 6 | DALI prefetch_queue_depth=8 (currently 4) | More batches in flight | marginal | not yet started |
| 7 | Final 2-epoch validation | Confirm stable rate | — | not yet started |

### Where you were exactly

I had just added `--channels-last` and `--fused-adamw` CLI flags to `train_v3_detector.py` (lines ~95-103). The flag-handling code in `main()` and the actual `model.to(memory_format=torch.channels_last)` + `.contiguous(memory_format=...)` on inputs + `AdamW(..., fused=True)` wiring was NOT done yet.

## 7. Key files (purposes + recent changes)

### Trainers
- **`src/stage1/train_v3_detector.py`** — Net 2 (PalmDetector, 615K params, batch 256, input 192²). Flags: `--use-dali`, `--use-dali-box-encoder`, `--use-cuda-graphs`, `--use-gpu-anchor-matcher`, `--resume-from`, `--data-limit`, `--device`, `--channels-last` (added but not wired), `--fused-adamw` (added but not wired). BF16 mixed precision (no GradScaler). cudnn.benchmark=True globally.
- **`src/stage1/train_v3_landmark.py`** — Net 3 (HandLandmarkNet, 1.27M params, batch 128, input 224²). Same flags except no `--resume-from`, no `--use-dali-box-encoder`, no `--use-gpu-anchor-matcher`. Has `--use-dali`, `--use-cuda-graphs`. BF16.

### Data path
- **`src/stage1/data/dali_pipelines.py`** — `DALIDetectorLoader` + `DALILandmarkLoader`. Has multi-output `_multi_callback` (for box_encoder path) + parallel `_jpeg_callback` (ThreadPool, 8 workers). Box encoder pipeline gated on `use_box_encoder` constructor arg.
- **`src/stage1/data/detector_dataset.py`** — fallback cv2 path. Has `_ImageCache` mmap reader + `DetectorTrainDataset` with `cache_root` constructor arg.
- **`src/stage1/data/landmark_dataset.py`** — fallback cv2 path for Net 3. Per-sample crop_hand via cv2.warpAffine.
- **`scripts/build_net2_cache.py`** — multi-process (32 workers) builder for the decoded npy cache. Idempotent (skips if cache exists).

### Models / losses
- **`src/stage1/models/anchors.py`** — has `_build_targets` (numpy, used), `build_targets_gpu` (Python loop, BROKEN, kept for reference), `build_targets_gpu_batched` (padded GPU, BROKEN due to bandwidth — kept gated behind `--use-gpu-anchor-matcher`).
- **`src/stage1/losses_v3.py`** — `DetectorLoss` (focal + smoothL1). **Recently rewritten** to use multiplicative masking instead of boolean indexing (was blocking CUDA Graphs capture). Math equivalence verified.
- **`src/stage1/models/palm_detector.py`** / **`landmark_net.py`** — UNCHANGED. Don't touch.
- **`src/stage1/augment/transforms_v3.py`** — kornia GPUAugmentation. Has a kornia 0.7+ AugmentationSequential fix (uses dummy keypoints for no-kpts branch).

### Scripts
- **`scripts/launch_v3.sh`** — orchestrator. Currently calls `--use-dali` only (no graphs/no gpu-matcher/no box_encoder). Has `--resume-from` plumbing that auto-uses `best_epoch8_pre_dali.pt` if present.
- **`scripts/run_v3_on_remote.sh`** — bootstrap (sets ulimit -n 65536, starts tmux with `setsid` for vast's container quirk).
- **`scripts/bench_dali_vs_cv2.py`** — DALI vs cv2 throughput bench (used to validate the DALI path).
- **`scripts/bench_model_ceiling.py`** — synthetic-input model + loss ceiling bench.

### Configs
- **`configs/stage1_v3_detector.yaml`** — Net 2 hparams. Has `data.cache_root: data/net2_cache`, `train.num_workers: 32`, `train.batch_size: 256`, `train.epochs: 60`, `train.mixed_precision: true`, `train.lr: 5e-4`, `train.warmup_epochs: 3`, `train.early_stop_patience: 20`.
- **`configs/stage1_v3_landmark_phase1.yaml`** — Net 3 P1 (70 epochs, batch 128, LR 5e-4, patience 25).
- **`configs/stage1_v3_landmark_phase2.yaml`** — Net 3 P2 (10 epochs, batch 128, LR 1e-5, fine-tune from P1 best).

### Docs
- **`docs/handoffs/HANDOFF_STAGE1.md`** — original project handoff (BEFORE this optimization round). v3 plan, dataset details, conventions.
- **`docs/optimization-attempts/README.md`** — full history of optimizations tried (8 numbered attempts with what worked and what didn't).
- **`docs/optimization-attempts/v3-state-pre-cuda-graphs/`** — frozen snapshots of files before the CUDA Graphs deep-dive.
- **`docs/handoffs/HANDOFF_OPTIMIZATION_ROUND.md`** — THIS file.

## 8. What I'd do next (immediate continuation)

1. **Verify Monitor `bcpit5tox` still alive** — TaskList. If dead, re-arm with the same command from this doc.
2. **Verify cron `693264f0`** — CronList. Delete if it's noise, keep if useful.
3. **Complete the channels_last wiring** in `train_v3_detector.py`:
   ```python
   if args.channels_last:
       model = model.to(memory_format=torch.channels_last)
   # Then in train loop after image is on GPU:
   if channels_last:
       image = image.contiguous(memory_format=torch.channels_last)
   ```
4. **Complete fused AdamW wiring**:
   ```python
   optimizer = AdamW(model.parameters(), ..., fused=args.fused_adamw or False)
   ```
5. **Push + smoke**:
   ```bash
   rsync ... train_v3_detector.py to remote
   ssh ... 'timeout 90 python3 -u -m src.stage1.train_v3_detector \
       --config configs/stage1_v3_detector.yaml --use-dali --channels-last 2>&1 > /tmp/cl.log'
   # extract sustained it/s:
   ssh ... 'tr "\r" "\n" < /tmp/cl.log | grep -E "^epoch 0.*[0-9]+/2271" | tail -3'
   ```
6. If channels_last gives **>= +10%** vs DALI baseline 10 it/s, keep it. If null/regression, drop the flag.
7. Same protocol for fused AdamW, then `torch.compile(model, mode='default')`, then combined best.
8. **Save findings** in `docs/optimization-attempts/README.md` as new numbered attempts.

## 9. Final optimized setup (current best — use if you skip the smoke matrix)

```yaml
Net 2:
  --use-dali --resume-from checkpoints/stage1_v3_detector/best_epoch8_pre_dali.pt

Net 3:
  --use-dali

Config (both):
  mixed_precision: true → BF16
  num_workers: 32
  cache: HaGRID + COCO mmap (Net 2 only)
  cudnn.benchmark: true (global)
```

Measured throughput: **Net 2 = 10 it/s** (~3.8 min/epoch), **Net 3 = 15 it/s** (~25 min/epoch).

To resume training to completion (NOT what user asked for now — they want optimization first):
```bash
ssh -i ~/.ssh/vast_v3 -p 27022 root@ssh9.vast.ai 'bash -s' <<'EOF'
cd /workspace/asl-learning
tmux kill-server 2>/dev/null
source /root/.bashrc; ulimit -n 65536
setsid tmux new-session -d -s v3 -x 200 -y 50 \
  'bash -c "ulimit -n 65536; bash scripts/launch_v3.sh" 2>&1 | tee logs/launch.log; sleep 86400'
EOF
```

## 10. Hazards / gotchas you'll hit

- **DO NOT** commit/echo `.env.local` contents. Use `python3 -c "..."` for credential handling.
- **DO NOT** rsync with `--exclude 'data/'` unanchored — it'll skip `src/stage1/data/` too (we hit this earlier).
- **`set -e` in launch_v3.sh** kills the whole pipeline if any step fails silently. Logs are written via `tee` so check `logs/launch.log` for the actual error.
- **`tmux new-session` without `setsid`** dies when the SSH session exits (vast's pytorch container behavior). The bootstrap script uses `setsid` to detach.
- **`torch.cuda.graph()` capture** has been thoroughly attempted and is genuinely net-slower than eager on this model. Don't re-attempt without a fundamentally new approach (e.g., torch.compile mode='max-autotune' is the only remaining variant).
- **`cudnn.benchmark = True`** must stay set globally — disabling it tanks throughput ~2× (we hit this when trying to make CUDA Graphs work).
- **HaGRID/InterHand image extracts** are on the boundary of disk capacity. Don't add more datasets without freeing space.

## 11. User communication style notes

- Direct. "Stop now" / "Go" / "Ride it" — take literally.
- Cost-conscious. Will pause to ask before exceeding $20.
- Sharp on technical detail. Will catch shortcuts.
- Math-light, ML-newer. Explain architecture choices in plain terms, ground in math when needed.
- Patient on detail when learning, decisive when committing.
- Async-friendly. They run `/loop` and `/schedule` and use the Monitor heavily. Don't ask them to babysit.
- Picked up on: PCK vs train_loss distinction, CUDA stream issues, BF16 vs FP16 trade-offs, the "model-bound vs data-bound" framing.

## 12. Open questions you'll likely need to answer

1. Did Monitor `bcpit5tox` survive the compaction? Check TaskList.
2. Should we keep the 10-min cron, or kill it as noise during this smoke matrix work?
3. After the smoke matrix completes, does the user want to (a) provision a NEW instance and ride to convergence, (b) ride out the remaining budget on THIS instance and ship partial, or (c) destroy and replan from scratch? They haven't decided this yet.

Good luck.
