# Handoff — Post-Training State (2026-05-23)

Read this entirely before doing anything. Supersedes `docs/handoffs/HANDOFF_OPTIMIZATION_ROUND.md` (which is now historical).

## 1. TL;DR

Trained 2 of 3 v3 nets. Net 2 + Net 1 are done with checkpoints local. Net 3 was started on Modal and failed on disk-full during InterHand extract. All paid compute is destroyed. Demo runs at `http://localhost:8501`.

**Headline numbers (held-out COCO val, 2055 samples, eval'd locally on CPU)**:
- **Net 1 (face+body keypoints)**: PCK@0.05 overall = **0.709**, face = 0.781, body = 0.656. **2.26× the v2 baseline (0.314)**, but ~0.18 short of the 0.90 G2 target. Shoulders are the weak point.
- **Net 2 (palm bbox)**: AP@IoU=0.5 = **0.033**, max recall 0.195. Fails the 0.85 G2 target — root cause is HaGRID-dominated training distribution (71% of training mix) causing OOD failure on COCO full-body scenes. See §5 below.
- **Net 3 (hand landmarks)**: not trained.

**Total spend so far**: ~$23.4 (≈$3.85 vast Net 2 + $19.5 Modal Net 1 incl. 3 failed retries).

## 2. Status of all 3 nets

| Net | Status | Final metric | Local artifact path |
|---|---|---|---|
| **Net 2** (palm detector, 615K params, SSDLite) | ✅ DONE | train_loss 0.135 / cls 0.103 / box 0.031 (60 ep) — held-out AP=0.033 (OOD failure) | `results/v3/net2/` (best.pt + epoch_009..059.pt + metrics.jsonl + logs) |
| **Net 1** (face+body keypoints, K=7, 8M params, KeypointDetector w/ deconv head) | ✅ DONE | val pck_overall **0.724 @ e200**, held-out PCK 0.709 (face 0.78, body 0.66) | `results/v3/net1/stage1_v2_facebody/` (best.pt + 21 epoch snapshots + metrics.jsonl) |
| **Net 3** (hand landmark, 1.27M params) | ⏸ NOT STARTED | n/a | n/a — held per your instruction |

Net 1 is K=7 (face+body slice, indices 42-48 of the original 49-kpt schema). The trainer is `src/stage1/train_v2_facebody.py` and the config is `configs/stage1_v2_facebody.yaml`. Net 1's trainer evaluates on COCO val every epoch — final `coco_val/pck_overall = 0.718` at epoch 209, best 0.724 at epoch 200.

## 3. Active infrastructure (all stopped, but residual state exists)

- **Vast.ai**: 0 active instances. Both Net 2's instance (contract 37423131) and the earlier optimization-round instance (37347023) are destroyed.
- **Modal apps**: all `stopped` (4 attempts for Net 1, 1 attempt for Net 3 P1). View at https://modal.com/apps/bryannalarcon/main/
- **Modal volumes still exist** (charges ~$0.20/GB/month — sub-$1 total per month for our footprint):
  - `asl-net1-vol` — has `data/coco/`, `data/FreiHAND_pub_v2/`, `cache/stage1/coco_train`, `coco_val`, **`checkpoints/stage1_v2_facebody/best.pt`** (also pulled to local).
  - `asl-net3-vol` — has partial `data/interhand/` (InterHand .tar.part files + partial extraction). About 80 GB.
- **Modal CLI installed locally** at `~/.local/bin/modal`, authenticated as `bryannalarcon`. Use `export PATH=$HOME/.local/bin:$PATH` to access.
- **Demo running on local**: streamlit at `localhost:8501` (PID 20240). Restart with `streamlit run playground/realtime_demo/app.py --server.headless true --server.port 8501`.

## 4. New files added this session

| File | Purpose |
|---|---|
| `configs/stage1_v2_facebody.yaml` | Net 1 config (K=7 face+body slice, 210 ep, BF16) |
| `src/stage1/train_v2_facebody.py` | Net 1 trainer — fork of train_v2.py with `--keypoint-slice`, BF16, channels_last+fused-adamw flags (latter two DISABLED after Modal Xid 43 crash) |
| `modal_apps/train_net1.py` | Modal app for Net 1 (A100-80GB, asl-net1-vol). Includes setup → preprocess → train. |
| `modal_apps/train_net3.py` | Modal app for Net 3 P1+P2 (A10G). Pre-built but NEVER successfully ran (disk-full on InterHand). |
| `scripts/eval_nets.py` | Held-out eval — Net 1 PCK + Net 2 palm AP on COCO val. Runs in ~3 min on CPU. |
| `scripts/plot_training.py` | matplotlib training-curve plot → `results/v3/training_curves.png` |
| `src/common/config.py` | Extended `TrainConfig` with `use_bf16/channels_last/fused_adamw` + `DataConfig.keypoint_slice` |
| `src/stage1/metrics.py` | Patched `compute_pck` to be slice-aware (handle K<49 models) — fixes Modal CUDA assert |
| `playground/realtime_demo/app.py` | Patched to: (a) recursive checkpoint glob, (b) auto-detect K + slice from ckpt config, (c) add Net 2 palm bbox overlay |
| `data/net2_cache/box_precompute_*.pkl` | 80 MB pickle of precomputed Net 2 box matches (from optimization round). Reusable if you train Net 2 again with the same dataset sizes. |
| `results/v3/eval_summary.json` | Held-out eval numbers |
| `results/v3/training_curves.png` | Training curve plot |

## 5. Why Net 2 fails the AP target — full diagnosis

Net 2 trained cleanly (loss 0.85 → 0.13 over 60 epochs, smooth curve), but held-out **palm AP @ IoU=0.5 = 0.033** vs the 0.85 G2 target. Max recall is 0.195 — at the lowest score threshold the model only finds 1-in-5 of the GT palms.

**Root cause**: training-set composition is HaGRID-dominated:
- HaGRID: 413,584 samples (**71%**) — hand-gesture closeups, hands 60-80 px in 192² letterbox
- FreiHAND: 130,240 (22%) — tight hand crops, hands 80%+ of frame
- COCO-WholeBody: 37,657 (6.5%) — full-body scenes, hands 10-20 px

Net 2 learned "find the prominent hand-shape in a hand-photo" but never generalized to "find a tiny hand in a body scene". The training loss converged because the easy 71% HaGRID samples dominated the focal-loss gradient.

**Secondary issue**: Net 2's smallest anchor is scale 0.10 = 19 px. A 15-px COCO hand barely matches, and a 1-px positional offset on the 24×24 grid (stride 8) tanks the IoU below 0.5. Force-positive matching still assigns one anchor, but the regression target is hard to learn cleanly.

**Tertiary issue (minor)**: Our eval double-resizes 256² → 192² (we used the Net 1 preprocess cache for val data because we never built a separate Net 2 val cache). Cost ~0.02 AP at most.

**Verdict on the demo**: Net 2's bbox overlay shows mostly false positives on webcam. **Disable the "Enable palm bbox overlay" checkbox in the sidebar** if you want a clean demo. Net 1's face/body keypoints are the reliable component.

### Fix options for Net 2 (cost-ranked, see also §8)

| Fix | Compute cost | Expected AP |
|---|---|---|
| Balanced sampling (downsample HaGRID, upsample COCO) | ~$3 | 0.30-0.50 |
| Two-stage: HaGRID pretrain → COCO+FreiHAND finetune | ~$2.40 | 0.50-0.65 |
| Add tiny anchors (scale 0.05 = 10 px) | ~$3 | +0.05-0.10 atop any base |
| Train at 384² input | ~$15-25 | 0.40-0.60 |
| Synthetic hand-in-scene composites (crop FreiHAND → COCO scenes) | $3 compute + eng | 0.60-0.75 |
| All combined | ~$25-30 | 0.70-0.80 |

To actually clear 0.85 will probably need architectural changes (multi-scale FPN, attention head). That's v4.

## 6. Demo — what's running

URL: **http://localhost:8501**

Setup we did this session:
- Bootstrapped pip locally via `get-pip.py` (no system pip / no sudo) → `~/.local/bin/pip`
- Installed: `torch==2.12+cpu`, `torchvision`, `streamlit==1.57`, `streamlit-webrtc`, `av`, `numpy`, `cv2`, `Pillow`, `mediapipe==0.10.35`, `matplotlib==3.10`, `modal==1.4.3`
- MediaPipe task files already present in `playground/realtime_demo/mediapipe_models/` (hand/face/pose `.task`)

The demo:
- **Checkpoint dropdown** is recursive (`**/*.pt` under `results/`). Defaults to `v3/net1/stage1_v2_facebody/best.pt` (auto-detects K=7 + slice [42,49]).
- **Net 2 palm overlay** checkbox (defaults on if `results/v3/net2/best.pt` exists). Pre-fills the path. Adjust palm conf threshold via slider.
- **MediaPipe** renderer modes: `ours` / `mediapipe` / `both` overlaid.

To restart the demo:
```bash
pkill -f "streamlit run"; cd /home/bryann/gauntlet/asl-learning
export PATH=$HOME/.local/bin:$PATH
setsid bash -c 'streamlit run playground/realtime_demo/app.py --server.headless true --server.port 8501 > /tmp/streamlit.log 2>&1' & disown
```

## 7. How to run the held-out eval

```bash
export PATH=$HOME/.local/bin:$PATH
cd /home/bryann/gauntlet/asl-learning
# The val cache is at /tmp/eval_cache/coco_val (pulled from Modal asl-net1-vol).
# If wiped, re-pull: modal volume get asl-net1-vol /cache/stage1/coco_val /tmp/eval_cache/
python3 -m scripts.eval_nets               # full 2055 samples, ~3 min
python3 -m scripts.eval_nets --max-samples 100   # quick smoke
```

Output → `results/v3/eval_summary.json` + console.

## 8. Training-platform analysis (from §11 of this session)

For OUR project specifically:

| Stage | What we paid | Cheapest path | Saved |
|---|---|---|---|
| Net 2 (60 ep, ~2-3 hr) | Vast 5090 $3.85 ✓ | same — Vast wins for short Blackwell runs | optimal |
| Net 1 (210 ep, 4.4 hr + retries) | Modal A100-80 $19.40 | AWS spot A10G or Vast 5090 = $5-8 | ~$12 |
| Net 3 P1 (22 hr, never finished) | Modal A10G ~$24 projected | AWS spot A100-40 = $15-20 | ~$5-10 |

**Rule of thumb**:
- **Iteration / short jobs**: Modal — detach-survives-terminal, per-second billing, fast setup.
- **Locked-in long runs (>6 hr)**: AWS spot — 30-70% cheaper. Pair with checkpointing.
- **Bleeding-edge GPUs (Blackwell 5090)**: Vast only.
- **Multi-node / scale**: AWS or Lambda Labs.

Things we hit on Modal worth remembering:
- **Disk quota** silently caps large extractions (InterHand ~85 GB blew Net 3 volume).
- **Default function disk** isn't volume disk — explicit `disk=` arg in `@app.function` decorator needed for large temp.
- **Xid 43 / device-side assert** struck once during Net 1 training (epoch-0 evaluation) — was actually a `metrics.py` indexing bug exposed by K<49 model, masked as a hardware fault. Fix in `src/stage1/metrics.py`'s `compute_pck` now handles slice-aware K.
- **App image build** takes ~3-5 min on first deploy per app.
- **`modal volume get`** can silently truncate one file in a large pull (we hit this on `0001249.npy` for COCO val). Re-pull individual files to fix.

Things we hit on Vast:
- **200 GB disk cap** per typical RTX 5090 offer — was tight for HaGRID + COCO + cache (174/200 used at peak).
- **No multi-day stability guarantee** — instance can be reclaimed by host. Use `reliability2 >= 0.98` filter.
- **Setup overhead** ~30-60 min per fresh instance (deps + dataset downloads).
- **`setsid tmux new-session -d`** required to survive ssh exit on the bare pytorch container (otherwise tmux dies).

## 9. Ranked next moves

| # | Move | Cost | Time | Value |
|---|---|---|---|---|
| 1 | **Improve Net 2** via balanced sampling + 2-stage + tiny anchors | $5 | ~3 hr | Lifts demo Net 2 from useless to ~0.50 AP |
| 2 | **Train Net 3 P1** on AWS spot A100 (fix the InterHand disk issue with bigger volume) | ~$15-25 | ~20 hr | Unlocks full pipeline + `eval_v3.py` |
| 3 | **Run `eval_v3.py`** end-to-end (needs Net 3) | $0 | 10 min | Real G2/G3/G4 numbers |
| 4 | Improve Net 1 shoulders via dataset rebalance or heavier augmentation | $5-10 | 3-5 hr | 0.66 → 0.75 body PCK |
| 5 | Net 2 architectural rework (FPN, attention) | $30-60 | days | Required to hit 0.85 |

Don't redo Net 1 — at 0.71 PCK it's 2.26× the prior baseline and a clean run. Your earlier instruction was explicit: "don't redo Net 1 or Net 2 if they don't hit the benchmark."

## 10. Open questions

- Should I wipe `asl-net3-vol` to stop the storage charge (~$16/mo at 80 GB)? **You haven't said yes/no.** Default: leave it for ~1 week in case we resume Net 3, then delete.
- Resume Net 3 (on AWS this time)? You said "hold on Net 3" — left held.
- Net 2 retrain? You said "don't redo if doesn't hit benchmark." Net 2 missed by a lot, but failure reason is well-understood (data composition) — open question whether you want to spend $5 to lift it.

## 11. User communication style (preserved for next session)

- Direct + decisive. "Stop now" / "Go" / "Ride it" — take literally.
- Cost-conscious — always tally compute spend, no surprises.
- Doesn't want intermediate updates unless asked. Final reports + clear options.
- Wants tight tables, not paragraphs.
- Prefers labeled `[Dev: …]` scaffolding + explicit overrides over silent mocks.
- Willing to spawn many parallel research/build agents; expects status updates not silent work.
- Build-then-review swarm loop — feature work uses coding swarm + review swarm.
- Commit cadence: after each change. Major immediately, minor batched.
- For non-trivial research: primary → fact-check → tertiary triangulation.
- Latest direction: **demo is the priority right now** (not training more nets).

## 12. Memory entries to update (auto-memory at `~/.claude/projects/-home-bryann-gauntlet-asl-learning/memory/`)

To add or refresh post-compact:
- `reference_modal_setup.md` — modal CLI installed locally at `~/.local/bin/modal`, authenticated as `bryannalarcon`, requires `export PATH=$HOME/.local/bin:$PATH`. Cost: ~3× more than Vast for equivalent GPU.
- `reference_pip_setup.md` — no system pip on this WSL; pip was bootstrapped via `get-pip.py` to `~/.local/bin/pip`.
- `project_v3_training_state.md` — Net 2 + Net 1 done, Net 3 held. PCK Net 1 = 0.71, Net 2 AP = 0.03 (OOD failure on COCO val).
- `feedback_net2_failure_root_cause.md` — Net 2 fails on COCO val because training was 71% HaGRID. Fix is balanced sampling or two-stage train. Don't repeat this composition.
- `reference_modal_pitfalls.md` — Modal volume disk quotas silently cap large extractions; `modal volume get` can truncate one file in a big pull; explicit `disk=` arg needed for large temp; image build ~3-5 min per app.
- `reference_demo_runs_locally.md` — streamlit at `localhost:8501`, port 8501, started via setsid. Deps in `~/.local/lib/python3.10/site-packages/`.

I'll add/update these after writing this handoff so they're available on the next session.
