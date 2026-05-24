# Project Handoff — ASL Learning, Stage 1 (keypoint detector)

Read this entirely before doing anything. Then read `docs/training-plan.md` and `docs/v3-plan.md`.

## What this project is

A controlled-pilot ASL learning web app. A learner signs a vocabulary word into their webcam; we predict pass/fail with a targeted pedagogical hint. Two ML stages:

- **Stage 1**: whole-body keypoint detector (49 unified keypoints) — *we are here*
- **Stage 2**: temporal sign classifier (hoyso48-style 1D-CNN + Transformer) running on Stage 1's keypoints — not yet started

The spec is `superbuilders-partner-project-asl-learning-with-computer-vision.pdf` in the repo root. Read it. The 15 requirements drive every decision.

**Req 7 is the load-bearing constraint**: no pretrained model weights anywhere in the system — including pretrained backbones, pseudo-label generation, and knowledge distillation from pretrained teachers. We train every weight from scratch. Demo-side MediaPipe (for visual comparison only, not in the deployed system) is fine.

**Req 15**: documentation must include evidence no pretrained models were used.

## Where we are

**Stage 1 has had two attempts shipped:**

| Version | What it was | Result | Status |
|---|---|---|---|
| **v1** | Single ~13M-param SimpleBaseline CNN, 256×256 → 49 heatmaps | PCK 0.321 (COCO val only). Crashed at e23 due to a heatmap-rasterization edge case, resumed to e50. | Done. Checkpoint at `results/v1/best.pt` and `results/v1_resumed/`. |
| **v2** | Same arch as v1 with an optimized pipeline: npy cache, GPU heatmap gen, scene-level FreiHAND val split, drop expensive aug. | PCK 0.351 COCO / 0.335 FreiHAND (hands 0.338/0.390). Stopped early at e79 of 210 max due to diminishing returns. | Done. Checkpoint at `results/v2/best.pt` + 8 periodic snapshots. |
| **v3** | **3-network pipeline (scaffolded, NOT yet trained)**: keep v2 for face/body, add a NEW palm detector (Net 2) + NEW hand-landmark specialist (Net 3). Expected hand PCK 0.55–0.65 realistic. | Scaffold complete, smoke tested on CPU. Ready to train. | **Next step.** |

## v3 is the open work — what it is

See `docs/v3-plan.md` for the full rationale (13-agent ruflo swarm synthesis). Short version:

**Why the previous attempts maxed out around 0.30–0.35 PCK**: hands are tiny in a full-body frame (~20px), and a single model trying to predict body + face + hand at one resolution can't be precise on hands. v3 splits the work:

- **v2's existing NN** stays in the pipeline for the easy keypoints (face/body — already at 0.45–0.55).
- **Net 2 — Palm Detector** (NEW, ~615K params): MobileNet-style depthwise-separable backbone + SSD-style multi-scale detection head. Input 192×192 → bounding boxes. Trained on COCO + FreiHAND + HaGRID v1 (the latter for ~552K human-annotated bboxes).
- **Net 3 — Hand Landmark Specialist** (NEW, ~1.27M params): same DW-separable backbone style. Input is a 224×224 *cropped hand region* (from Net 2's bbox or the GT bbox at training time). Output: 21 heatmaps at 56×56. Trained on FreiHAND + InterHand2.6M 5fps.

Inference glue (`src/stage1/inference_v3.py`):

```
frame → v2 → take slot [42:49] for face/body (nose, chin, forehead, shoulders, chest, neck)
       → Net 2 → 0–2 palm bboxes
       → for each bbox: crop → Net 3 → 21 hand kpts → unproject to frame coords
       → assemble unified 49-keypoint output
```

**Training is sequential** (one GPU): Net 2 first, then Net 3 Phase 1 (GT bboxes + jitter), then Phase 2 fine-tune (10 epochs on Net 2's predicted bboxes for calibration). All in one orchestrator script.

## Datasets

| Dataset | Used by | Source | Status |
|---|---|---|---|
| COCO-WholeBody (train2017 images + annotations) | Net 2 (palm bbox derived from kpts) | wget cocodataset.org + gdown for ann | scripted, ~20 GB |
| FreiHAND v2 | Net 2 + Net 3 | Kaggle CLI mirror `danieldelro/freihand` | scripted, ~6 GB |
| **HaGRID v1 (512px)** | Net 2 only (human bbox + gesture class) | Sber S3 mirror | scripted, ~17 GB. **HaGRID v2 landmark file is MediaPipe-pseudo-labeled — DO NOT USE.** |
| **InterHand2.6M 5fps** | Net 3 only (MoCap 21-kpt, two-hand) | Meta S3 public bucket `https://fb-baas-f32eacb9-8abb-11eb-b2b8-4857dd089e15.s3.amazonaws.com/InterHand2.6M/InterHand2.6M.images.5.fps.v1.0/` | scripted, ~50 GB. Annotations are on a separate Google Drive — `INTERHAND_ANN_GDRIVE_ID` env var must be set in `scripts/download_v3_data.sh` to fetch them. |

Total disk needed: ~100–110 GB. **Rent vast with disk = 200 GB** (not the default 80).

`HanCo` and `RHD` were considered but dropped from v3 (link rot + diminishing returns).

## Constraints carried forward

- **Hard compute budget**: $24 USD on vast.ai. Aim for under it.
- **Engineering budget**: ~24 hours total (already spent ~12 on scaffolding).
- **Hard kill switch**: $20 spent on v3 OR 14 wall-clock hours, whichever first.
- **GPU filter at vast launch**: `gpu_name in (RTX 4090, RTX 5090)`, `verified=true`, `rentable=true`, `reliability2 > 0.98`, `inet_down > 2000`, `cpu_cores_effective >= 12`, **`disk_space >= 200`**, US-located. (Avoid Norway and slow-network hosts — burned $1 on that earlier.)
- **Vast quirks observed**: SSH key sometimes doesn't propagate; if SSH fails after 5 min, destroy and pick a different host. (One California host was completely broken on this front.)

## File structure (v3-specific, new files)

```
src/stage1/
├── data/
│   ├── palm_boxes.py            BlazePalm-style bbox derivation + jitter + IoU
│   ├── hand_crops.py            Rotated padded crop + affine transform tracking
│   ├── hagrid.py                HaGRID v1 loader (bbox + gesture class only)
│   ├── interhand.py             InterHand2.6M 5fps loader (MANO→MediaPipe remap + camera projection)
│   ├── detector_dataset.py      COCO + FreiHAND + HaGRID → Net 2 training samples
│   └── landmark_dataset.py      FreiHAND + InterHand → Net 3 hand crops, supports Phase 2 cache
├── models/
│   ├── anchors.py               SSD anchor gen (P1 24×24, P2 12×12, P3 6×6) + match + encode/decode + NMS
│   ├── palm_detector.py         Net 2 (615K params, DW-separable, 3-scale SSD head)
│   └── landmark_net.py          Net 3 (1.27M params, DW-separable, 56×56 heatmaps)
├── losses_v3.py                 Focal + Smooth-L1 (Net 2); AdaptiveWing + soft-argmax L1 (Net 3)
├── augment/transforms_v3.py     CPU-light prep + kornia-based GPU batched augmentation
├── train_v3_detector.py         Net 2 trainer (AdamW + warmup + cosine + EMA + grad clip)
├── train_v3_landmark.py         Net 3 trainer (same patterns + GPU heatmap render + GPU aug)
├── inference_v3.py              Pipeline glue (v2 face/body + Net 2 bbox + Net 3 hand kpts)
└── eval_v3.py                   End-to-end PCK by finger group + AUC

src/common/v3_config.py          Lightweight YAML→dict config loader

configs/
├── stage1_v3_detector.yaml          Net 2 hparams (60 epochs, batch 256, LR 5e-4)
├── stage1_v3_landmark_phase1.yaml   Net 3 Phase 1 hparams (70 epochs, GT bboxes + jitter)
└── stage1_v3_landmark_phase2.yaml   Net 3 Phase 2 hparams (10 epochs fine-tune, LR 1e-5, Net 2 bbox cache)

scripts/
├── download_v3_data.sh           Pulls all v3 datasets on the rented instance
├── launch_v3.sh                  8-step orchestrator: deps → data → smoke → train Net 2 → predict bboxes → train Net 3 Phase 1 → Phase 2 → eval
├── predict_bboxes_for_phase2.py  Runs trained Net 2 over Net 3 training set → JSON cache
└── smoke_test_v3.py              GPU-side synthetic smoke test (palm_detector + landmark_net + kornia + losses + anchors)

tests/test_v3_schema.py           Pure-Python integrity checks (6 tests, all passing locally)

docs/
├── HANDOFF.md                    (this file)
├── training-plan.md              Original v1/v2 plan + lessons learned
├── v3-plan.md                    The swarm-synthesized v3 plan
├── hoyso-architecture.md         Stage 2 reference (not Stage 1)
└── google_iso_1st_place.md       Stage 2 reference (cleaned Kaggle writeup)
```

Existing infrastructure that stays (do NOT delete):

```
src/stage1/                       (v1/v2 lives here too — needed for face/body in v3 inference)
├── models/detector.py            v2's KeypointDetector — used in v3 inference for face/body slot
├── train.py / train_v2.py        v1/v2 training scripts (kept for reference + fallback)
├── data/{schema,coco_wholebody,freihand,unified,visualize}.py   v2-era loaders, also reused by v3
├── augment/transforms.py / transforms_v2.py   v2 aug (no longer used; v3 uses transforms_v3.py)
└── losses.py / metrics.py        v2 losses/metrics

results/
├── v1/best.pt                    50 MB (PCK 0.321, e46 of e50)
├── v1_resumed/{best,last}.pt     50 MB each
└── v2/best.pt + epoch_009..079   50 MB each — best.pt is e75 (PCK 0.339 combined)

playground/realtime_demo/
├── app.py                        Streamlit + WebRTC demo with: dropdown for any results/*/*.pt + 4-mode renderer (ours / MediaPipe only / both / future v3)
├── README-local.md
├── requirements.txt              Includes kornia, streamlit, streamlit-webrtc, mediapipe, av, torch, opencv-headless
└── mediapipe_models/             *.task files for demo-side MediaPipe (Hand + Face + Pose Landmarkers) — DEMO ONLY, NOT TRAINING

.venv-demo/                       Local virtualenv with full deps. Use it for any local checks.
.env.local                        VAST_API + KAGGLE_API keys. Already-loaded by every script that needs them.
```

## Tools you have access to

- **vast.ai API** via the key in `.env.local` (`VAST_API`). All previous instances were created via `urllib.request` direct calls — examples scattered in transcript.
- **Kaggle CLI** for FreiHAND mirror (`KAGGLE_API` in `.env.local`).
- **MediaPipe Tasks API** in the demo only (already wired). Three landmarker `.task` files downloaded.
- **Streamlit demo on localhost:8501** (kill with `pkill -f "streamlit run"`).
- **Ruflo MCP swarm** (used once to generate the v3 plan — swarm-1779405375250-xnmqfe, mesh, 15 max agents). Don't re-run unless re-planning.

## Conventions and quirks

- **Naming**: v1/v2/v3 are pipeline VERSIONS, not single neural networks. v1 and v2 each contain ONE NN. v3 contains THREE (v2's NN reused + Net 2 + Net 3).
- **Pseudo-labels are banned**. Anything labeled by another pretrained model (including MediaPipe in HaGRID v2) is off-limits for training. Only human annotations, MoCap, or synthetic-by-construction labels are OK.
- **The COCO image download is the rate-limit risk**. We've seen cocodataset.org throttle Norway hosts to 150 KB/s. US-located vast hosts are fine.
- **Streamlit auto-reloads on file edits**, but importing new modules sometimes requires a restart.
- **GPU augmentation via kornia** is wired into v3 training. CPU-side does minimal prep (cache mmap + normalize); kornia runs RandomAffine + ColorJitter + flip + blur + noise per batch on the GPU.
- **The `_streamlit_xsrf` cookie** can stick on stale browser tabs. Hard-refresh fixes most localhost issues.
- **Always destroy the vast instance** when training is done. Confirm via `python3 -c "..."` that 0 live instances remain. Earlier instances cost $7+ when left idle.

## What just spent money (for context)

| Instance | Cost | Outcome |
|---|---|---|
| H200 Sweden (v1 initial, crashed e23) | $7.02 | Salvaged via resume |
| 4090 Norway (data download throttled) | $1.00 | Killed, no useful work |
| 4090 California (SSH broken) | $0.30 | Killed, no useful work |
| 5090 NJ (v1 resume to e50) | $3.09 | `results/v1_resumed/best.pt` |
| 4090 California (v2, stopped at e79) | $3.65 | `results/v2/best.pt` |
| **Cumulative** | **~$15.06** | |

Remaining budget: **~$9 of the $24 cap** for v3. The v3 plan projects $13–18, which already exceeds the remaining. The user has implicitly accepted some overage if v3 hits the gate; check before exceeding $24 in actual spend.

## Communication style

The user has been:
- **Direct** — "kill it now and pull artifacts" is normal. Take it literally.
- **Cost-conscious** — they push back when budget overruns appear.
- **Sharp on technical detail** — they catch shortcuts (e.g., they spotted that v2 + v3 hand fusion would mostly add noise).
- **Math-light, ML-newer** — they know vectors/matrices/tensors but not "ResNet" / "encoder-decoder" by name. Explain architecture choices in plain terms and ground in math when needed.
- **Async-friendly** — they're fine with you running background tasks and notifying on milestones. They've explicitly asked to "be told when training is starting" rather than babysitting every step.
- **Iteratively planning** — they revise mid-conversation (e.g., dropping HanCo when the link rotted, adding HaGRID after finding the GitHub URL, asking smart "does it have to be sequential?" questions).
- **Patient on detail** when they're learning, decisive when they're committing.

## Next step

The user is ready to say "go" / "begin training." When they do:

1. **Run the live vast.ai offer query** (Python with `urllib.request` + `json` against `https://console.vast.ai/api/v0/bundles/`). Filter for the constraints in "Constraints carried forward" above.
2. **Pick the best offer** by perf/$ that satisfies the disk + bandwidth + CPU thresholds. Present 2–3 options first if more than one is comparable.
3. **Provision the instance** (PUT against `/asks/{offer_id}/`), attach SSH key, attach KAGGLE_API to `~/.kaggle/kaggle.json`, scp:
   - The code (rsync the whole project, exclude `data/`, `checkpoints/`, `.venv*`)
   - `results/v2/best.pt` (needed by v3 inference for face/body slot)
4. **On the instance**: install unzip + pip deps. If GPU is Blackwell (compute cap ≥ 12), upgrade torch to `torch+cu128` from `https://download.pytorch.org/whl/cu128`.
5. **Set `INTERHAND_ANN_GDRIVE_ID`** in the shell environment before running download_v3_data.sh (you need to look it up from the InterHand2.6M GitHub repo — the user will provide if asked, or you can prompt them).
6. **Run `bash scripts/launch_v3.sh`** — it does all 8 steps end-to-end (deps → data → smoke → Net 2 → bbox cache → Net 3 Phase 1 → Phase 2 → eval).
7. **Monitor via metrics-file watchers** (same pattern as v2 — `tail -F` on `checkpoints/stage1_v3_*/metrics.jsonl` filtered for epoch lines, fire as Monitor events).
8. **At each gate, check progress**:
   - G1: smoke_test_v3.py passes
   - G2 (after Net 2 training): palm AP@IoU=0.5 ≥ 0.85
   - G3 (mid Net 3 Phase 1): hand crop PCK ≥ 0.50 by epoch 30 of 70
   - G4 (end): final hand PCK ≥ 0.45
9. **When training is done**: pull all artifacts via rsync (palm_detector.pt + landmark_net.pt + metrics + eval JSON), destroy the instance, confirm 0 live instances.
10. **Wire the demo dropdown**: extend `playground/realtime_demo/app.py` to add a "v3 pipeline" renderer option that loads all three checkpoints via `V3Pipeline` from `src/stage1/inference_v3.py`.

If anything in the gates fails, follow the "stop and pivot" rules in `docs/v3-plan.md`.

## Stuff you can verify locally before any GPU work

```bash
# Schema integrity + config loadability
.venv-demo/bin/python tests/test_v3_schema.py

# Full smoke test on CPU (palm_detector + landmark_net + kornia + losses + anchors)
.venv-demo/bin/python scripts/smoke_test_v3.py

# Demo (currently configured for v1/v2; v3 dropdown entry not yet added)
.venv-demo/bin/streamlit run playground/realtime_demo/app.py
```

All of these pass as of handoff. If they break, something's wrong with the local environment or someone edited the wrong file — investigate before launching GPU.

## Open questions and assumptions

- **InterHand2.6M annotations gdrive ID** — not in scripts; user needs to provide or accept download failure. If they can't, you can either ship Net 3 with FreiHAND-only data (smaller dataset → lower PCK gain) OR have the user manually download and scp the annotation tarball.
- **HaGRID 512px URL** — best-guess Sber CDN URL is in `download_v3_data.sh`. May rot. Check before launch.
- **The user wants ONE click to "begin training" and walk away.** Respect that — chain everything in `launch_v3.sh`, set up watchers, only interrupt them at success or hard failure.
- **The "calibration set"** (50 self-recorded frames under their actual webcam) was discussed but is NOT a blocker for v3. They may want to add it later.

## What is genuinely DONE vs PENDING

| Done ✅ | Pending |
|---|---|
| v1, v2 trained, checkpoints saved | v3 training |
| v3 scaffold (all code, all configs, smoke test) | v3 GPU launch |
| MediaPipe wired into demo for visual comparison | v3 demo dropdown entry |
| Smoke tests pass on CPU | InterHand2.6M annotation download |
| Documentation: training-plan, v3-plan, hoyso-arch | Stage 0 calibration set (deferred) |
| | Stage 2 (sign classifier — entirely future) |

## TL;DR for picking up

1. Read `docs/v3-plan.md`.
2. Run `.venv-demo/bin/python scripts/smoke_test_v3.py` — confirm green.
3. When user says go: launch a US vast 4090/5090 with 200 GB disk + ≥12 CPU cores, scp code + v2's best.pt + creds, run `bash scripts/launch_v3.sh`.
4. Monitor via metrics file watchers. Pull + destroy when done. Stay under $24 if possible.
5. Wire the v3 dropdown entry in the demo.
6. Stage 2 is the next milestone after v3.
