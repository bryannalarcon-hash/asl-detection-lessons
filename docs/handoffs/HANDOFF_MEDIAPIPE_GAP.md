# Handoff — MediaPipe gap-closing round (2026-05-24)

Read this first. Self-contained resume point after context compaction. Covers
what this session did, the committed/uncommitted state, and the full action
plan (the user has greenlit ALL the MediaPipe-gap fixes below).

---

## 1. TL;DR — where we are

- **Net 3 v2 trained + landed** (Vast 5090, ~$4.75): `results/v3/net3_v2/best.pt`,
  **val_pck_05=0.321 / val_pck_10=0.604 / val_pck_20=0.796**. Slightly *below*
  v1 (0.353) — the aggressive ±180° rotation aug + fingertip weighting
  underperformed. This is the weak link and the main target below.
- **Diagnosis from live demo testing**: Net 2 box now OK after fixes; **Net 3
  keypoints are "wildly off" even on a still hand** → Net 3 is genuinely weak
  (0.32 PCK) + no temporal smoothing + heatmap architecture is wrong for the
  param budget.
- **A 3-agent swarm mapped the MediaPipe gap** → ranked action plan in §4. User
  said: "we'll be doing all of those."
- **Net 4 still ≈ chance** (top-3 0.059). Root cause = body-relative feature
  normalization burying handshape. Fix is the per-hand normalization (staged,
  uncommitted — see §3).

---

## 2. What this session accomplished

1. **Handoff reorg** (committed `aed2e47`, `27dd4de`): all handoffs moved to
   `docs/handoffs/`. This file is the newest.
2. **Net 3 v2 retrain** (committed `273856d`, `6b9f534`): multi-threshold PCK
   wired into trainer; `scripts/mirror_net3_local.sh` for cross-host artifact
   pull. Trained on a Vast 5090 with the NEW stack (below), pulled, destroyed.
3. **Infra learnings** (committed `13a7203`):
   - **Use `pytorch/pytorch:2.7.0-cuda12.8-cudnn9-devel`** on Blackwell (5090).
     The old handoff's `vastai/pytorch:2.4.0-cuda-12.1.1-base` is a DEAD image
     AND lacks sm_120 support. The new stack ~2× the 5090's throughput
     (1.27 min/epoch vs the old ~2.8). cuDNN 9 + CUDA 12.8 = native Blackwell.
   - **RunPod works via GraphQL API** (`RUNPOD_API` in `.env.local`). Community
     5090 = $0.69/hr (~30% under Vast). Provision with `PUBLIC_KEY` env so the
     `runpod/pytorch:*` image injects our SSH key (`~/.ssh/vast_v3`). SSH with
     `-i ~/.ssh/vast_v3 -o IdentitiesOnly=yes`. Balance: **$6.40**.
   - **FFCV** is the fix for the I/O-bound training ceiling (Net 2 trained at
     ~6.7 it/s on a 5090 = pure data-loading bottleneck).
4. **Net 2 ablation sprint** (6 ablations, ~$3.56, results in
   `results/v3/net2_ablations/`): `focal_alpha=0.5` REGRESSES (reject, keep
   0.25); `focal_gamma=4` is a safe mild gain. Loss alone can't rank across
   gamma (no AP eval in pipeline). EgoHands download soft-failed (egohands=0) —
   the ego ablations were confounded.
5. **Net 4 data sourcing** (`docs/handoffs/net4_data_sourcing.md`): verified via
   metadata (no bulk download) that an **~85-word PopSign-drawn ASL-1
   vocabulary has ≥500 real clips/word** (95/96 words clear it; only `icecream`
   short at 439 → swap to `snack`). PopSign spans 6 sub-splits (game+non-game ×
   train/test/val) — `game/train` alone is only ~150/word. Numbers, WH-words,
   and greeting phrases are ABSENT from PopSign (need self-capture if required).
6. **Demo upgrades** (all in `playground/realtime_demo/app.py` — GITIGNORED,
   local-only, live sliders): see §5.

---

## 3. UNCOMMITTED / staged changes (decide before committing)

`git status` shows these modified-but-uncommitted (intentional, experimental):

- **`src/stage2/data/sign_dataset.py`** — `_normalise_frame` rewritten to do
  **per-hand normalization**: face/body keep body-scale; each hand re-normalized
  by its OWN center+span so handshape detail isn't buried. THE Net 4 fix.
  Requires re-extracting Net 4 features + retraining Net 4 to take effect.
  Verified it ~10×-amplifies hand-shape spread (0.1→1.0 of range).
- **`src/stage2/data/extract_keypoints.py`** — `run_net3` expands the Net 2
  bbox 10% before cropping (finger margin). Hardcoded; demo has it on a slider.
- **6 ablation configs** (`configs/ablation_*.yaml`) — Net 2 ablation sprint
  inputs. Keep for reference or delete.
- **`scripts/plot_*.py`, `scripts/convert_egohands_to_yolo.py`** — pre-existing,
  not from this session's core work.

**Note**: `docs/handoffs/net4_data_sourcing.md` is untracked — commit it.

---

## 4. THE ACTION PLAN — MediaPipe gap fixes (all greenlit)

Ranked. All Req-7-safe (technique/architecture, not MediaPipe weights).

| # | Fix | Where | Effort | Why |
|---|---|---|---|---|
| 1 | **Strip optimizer state from exported checkpoints** | wherever `best.pt` is saved (e.g. `modal_apps/train_net1_v3_1.py`) | trivial | Net 1 `best.pt` is 154MB = 53.6MB weights + 107MB Adam state that never ships. Save a separate export ckpt with only `model`/`epoch`/`config`. |
| 2 | **Net 3: heatmap → direct (x,y,z) regression** | `src/stage1/models/landmark_net.py` + trainer | retrain (~$5) | **THE 0.32-PCK fix.** At 1.3M params w/ occlusion, heatmap+soft-argmax is wrong: U-Net decoder eats the budget; occluded joints have no peak to supervise. MediaPipe regresses directly → robust to occlusion (predicts invisible joints). Keep encoder + rotation-norm crop; replace 56×56 heatmap head with a 21×3 FC head; supervise z from FreiHAND/InterHand 3D. |
| 3 | **Rotation-canonicalized crop, train AND infer** | `extract_keypoints.py` + Net 3 training crop | with #2 | Stop training Net 3 to be rotation-INVARIANT (v2's ±180° aug was backwards — it's why v2 < v1). Instead rotate the crop to upright (wrist→middle-MCP vertical) before Net 3, train with MILD aug (±15°). Estimate angle 2-pass (rough Net 3 → re-crop) OR from Net 2 keypoints (#5). |
| 4 | **ROI tracking + presence gating** | demo + inference pipeline | medium | Stop re-detecting every frame. Add a presence scalar head to Net 3; derive next-frame ROI from prev landmarks; only re-run Net 2 when presence < thresh. ~2× fewer detector calls + kills box jitter. |
| 5 | **Net 2: regress wrist+middle-MCP keypoints; square anchors; focal loss; FPN decoder** | `palm_detector.py` + trainer | low-med retrain | Enables the oriented crop (#3) + ROI handoff (#4). BlazePalm = 95.7% AP vs our 0.20. |
| 6 | **Net 4: per-hand normalization** (already staged in `sign_dataset.py`) + **wrist-anchored, scale-normalized coords** | `sign_dataset.py` (done) → re-extract + retrain Net 4 | ~$0.50 | The Net-4-at-chance fix. NOTE: HOyso itself used GLOBAL z-score (not per-hand) but had 94k clips + ensemble; at our data scale per-hand (hand-sized scale denominator) is the safer bet. The bbox crop is *inherently* hand-normalization — we currently throw it away by unprojecting Net 3 output back to frame coords in `extract_keypoints.py:246`. Could alternatively just keep crop-relative coords. |
| 7 | **Per-frame quality gate** (palm score + Net 3 heatmap-peak/presence) | inference | med | Drop junk frames before Net 4's temporal buffer. Serves Req-7 OOD-rejection (≥90%). |
| 8 | **INT8-quantize all 4 nets** for browser | export | low-med | 4× shrink → meets the 25MB bundle budget in `docs/ml-handoff.md`. |
| 9 | **Shrink Net 1 backbone** | `landmark_net`/detector for Net 1 | high | Net 1 = 13.4M params, ~7× MediaPipe's whole hand pipeline. Only net off-budget even post-INT8. MobileNet/BlazePose-style + narrower deconv + 192px. |

**Sequencing**: #1 (trivial) → #6 (cheap Net 4 fix, test the normalization hypothesis) → #2+#3+#5 (the Net 3 regression + oriented-crop + Net 2 keypoints retrain — the big accuracy round) → #4/#7 (tracking + gating) → #8/#9 (deployment).

**Skip for now**: synthetic hand rendering (MANO+Blender) — buildable under Req 7 but multi-week; architecture is the bottleneck, not data.

---

## 5. Demo changes (playground/realtime_demo/app.py — GITIGNORED, local-only)

All live sliders in the sidebar; restart `streamlit run playground/realtime_demo/app.py` to load:
- **Net 2 box expansion** slider (default 10%) — finger margin for Net 3 crop.
- **Net 2 bypass** toggle — feed Net 3 a fixed center crop (diagnostic: tests Net 3 without Net 2).
- **Stable-box filter** (temporal) — suppresses jumpy false-positive boxes via
  IoU-over-time. Defaults overlap=0.30/window=1.5s/min_frac=0.30 (sim-tuned).
  CAVEAT: does NOT catch a *stationary* face-box (it's stable) — that needs
  Net-1-face-keypoint suppression or Net 2 face-negative retrain.
- **Net 3 keypoint smoothing** (one-euro filter, what MediaPipe uses) — default
  min_cutoff=0.5, beta=0.02 (tuned: ~3px→1px jitter, no perceptible lag).
- Net 3 default path updated to `results/v3/net3_v2/best.pt`.

These are demo-only display/eval aids, NOT the deployed pipeline.

---

## 6. Accounts / cost / compute

- **RunPod**: API key `RUNPOD_API` in `.env.local`, balance **$6.40**. Community
  5090 $0.69/hr. Provision via GraphQL `podFindAndDeployOnDemand` with
  `PUBLIC_KEY` env. SSH key `~/.ssh/vast_v3`.
- **Vast**: `~$3.49` balance, key `vast_v3`. `vastai` CLI at `~/.local/bin`.
- **Local box**: WSL, **7.6 GB RAM** (stream-extract only, never load big files),
  but **868 GB disk free** (downloads fit locally if needed).
- **Kaggle**: `KAGGLE_API` (KGAT token) in `.env.local`; use `KAGGLE_API_TOKEN`
  env, not the legacy json (which is just the bare token, missing username/key).
- **AWS**: creds valid; S3 presign via `scripts/aws_presign_datasets.sh`.

---

## 7. Gotchas

1. **playground/ is gitignored** — demo changes are local-only, never committed.
2. **PopSign per-sign counts need all 6 splits** to clear 500; `game/train`
   alone ≈ 150/word. Verify ≥500 before locking the Net 4 vocab.
3. **Don't bulk-download to local** for training — do it on a GPU box (keypoint
   extraction needs GPU; only the small `.npz` come back).
4. **Net 4 normalization change is staged but NOT committed** — committing it
   alone breaks Net 4 inference until Net 4 is retrained on the new features.
5. **The mirror cron / monitors from this session are dead** (session-scoped).
6. **EgoHands download soft-fails** — verify egohands count >0 in any Net 2
   retrain or the mix silently renormalizes without it.

---

## 8. Pointers
- `docs/handoffs/net4_data_sourcing.md` — the ≥500/word PopSign vocabulary + plan
- `docs/handoffs/HANDOFF_NET3_V2.md` — prior Net 3 v2 round
- `results/v3/net2_ablations/` — the 6 Net 2 ablation checkpoints + metrics
- `results/v3/net3_v2/` — Net 3 v2 weights + metrics + train log
- `src/stage2/data/sign_dataset.py` — Net 4 dataset + the staged per-hand norm
- `src/stage2/data/extract_keypoints.py` — Net 1/2/3 → keypoint extraction
- `docs/ml-handoff.md` — CV interface contract, 25MB bundle budget, OOD gate
- `docs/hoyso-architecture.md` — Net 4 classifier reference

Next agent: start at §4 #1 (trivial), then #6 (cheap Net-4 normalization test),
then the big Net 3 regression retrain (#2+#3+#5).
