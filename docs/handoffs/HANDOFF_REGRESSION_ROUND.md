# Handoff — Net 3 regression round + e2e + deliverables (2026-05-25)

Read this first after compaction. Self-contained resume point. Covers what's
trained, what's RUNNING right now, the key decisions, infra/tooling, the
final-deliverables status, and exact next steps.

---

## 1. TL;DR

MediaPipe-gap retrain round, executed mostly autonomously under a ~$20 RunPod
budget with a 10-min cron + artifact pulls.
- **Net 3 rewritten heatmap → direct coordinate regression: WIN.** Held-out
  FreiHAND **PCK@0.05 = 0.45 / @0.10 = 0.71 / @0.20 = 0.86** (old heatmap was
  0.32 @0.05). `results/v3/net3/best.pt` (head_type=regression).
- **New keypoint-head Net 2: FAILED as a detector** (AP@0.5 **0.016** vs
  net2_v3_1's **0.20** on COCO-WholeBody val) — under-trained by a cost-trim
  (45 ep + 200k samples/epoch cap vs v3_1's 70 full-dataset ep).
- **Decision (Bryann-confirmed): pipeline uses net2_v3_1 (good detector) +
  Net 3 2-pass self-orientation** (Net 3 reads its own wrist→middle-MCP to
  re-crop upright — needs NO net2 keypoints). The kpt-net2 is shelved.
- **Net 4 (PopSign ~96-word classifier): still extracting/training** → the
  e2e pipeline. NOT done yet.

Full outcome also in auto-memory `project_net_v3_regression_round.md`.

---

## 2. WHAT IS RUNNING RIGHT NOW (resume-critical)

- **Phase C pod (RunPod, role=phasec): `8r7bopgrywrdbh` @ `207.219.67.124:30367`.**
  Re-extracting PopSign keypoints with **net2_v3_1 + 2-pass** (config in
  `_remote_phase_c.sh`), ~25/96 signs when this was written. When it finishes
  all signs it auto: builds the Net 4 manifest (`build_manifest_popsign`),
  then **trains Net 4** (`configs/stage2_v4_classifier_popsign.yaml`), touches
  `.net4_done`. ~3-4 hr to finish extraction, then ~20-30 min Net 4.
  SSH: `ssh -i ~/.ssh/vast_v3 -o IdentitiesOnly=yes -p 30367 root@207.219.67.124`.
  Remote logs: `/workspace/asl/logs/{remote_phasec,extract,train_net4}.log`.
- **10-min cron `2f5e568d`** (fires :03/:13/:23/:33/:43/:53). Its prompt runs
  `bash scripts/round_health.sh` (mirrors artifacts from pods in `.round_env`),
  reports epoch/metrics, and on completion: pull+verify Net 4 best.pt → destroy
  the pod → e2e. SESSION-ONLY (dies if this Claude session ends — recreate with
  CronCreate if needed).
- **Background agents (may still be running):** `lessoneditor` (frontend dev
  lesson-config editor — NOT yet reviewed/committed), `datasetdoc` +
  `validationdoc` (writing deliverables #3/#4).
- **RunPod balance: ~$12.39.** Budget guard: keep total under ~$20.

---

## 3. Trained models (all local under results/v3/, gitignored)

| Net | Path | Metric | Status |
|---|---|---|---|
| Net 1 (face/body) | `results/v3/net1_v3_1/best.pt` (+best_export 53.6MB) | PCK ~0.72 | use (not retrained this round) |
| Net 2 detector | `results/v3/net2_v3_1/best.pt` | AP@0.5 **0.20** | **USE THIS ONE** |
| Net 2 kpt (new) | `results/v3/net2/best.pt` | AP@0.5 0.016 | FAILED — do not deploy |
| Net 3 regression | `results/v3/net3/best.pt` | PCK 0.45/0.71/0.86 | **USE — the win** |
| Net 3 heatmap (old) | `results/v3/net3_v2/best.pt` | 0.32 @0.05 | superseded |
| Net 4 classifier | `checkpoints/stage2_v4_classifier_popsign/` (on pod) | PENDING | training in Phase C |

Net 1's `best_export.pt` (optimizer-state-stripped, 53.6MB) is what Phase C
pushes to the pod for extraction.

---

## 4. Key code/tooling built this round (committed)

Infra (all in `scripts/`):
- `runpod_provision.py` — RunPod GraphQL (balance/offers/deploy/ssh/status/
  destroy). MUST use a curl-like User-Agent (WAF 403s urllib). Image default
  `runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04` (validated:
  sshd + PUBLIC_KEY injection + native sm_120 cu128 torch).
- `launch_train_pod.sh <net2|net3>` + `_remote_train.sh` — per-net training pod.
- `launch_phase_c.sh` + `_remote_phase_c.sh` — PopSign extract → Net 4. Per-sign
  download(resume+retry)/extract(`tar --no-same-owner`)/keypoint/rm loop, 40
  clips/sign, max_frames 32, 2-pass.
- `round_health.sh` — cron target: multi-pod artifact mirror + epoch/health.
- `eval_net2_ap.py` + `_remote_eval_net2.sh` + `launch_eval_net2.sh` — Net 2
  detection-AP harness (COCO-WholeBody val). `RUNPOD_GPU`/`FORCE_SECURE` envs.
- `build_clip_manifest.py`, `grab_lesson_videos.py`, `strip_checkpoint.py`.

ML (in `src/`): `HandLandmarkRegNet` in `landmark_net.py`; `losses_landmark_reg.py`;
`train_v3_landmark_reg.py`; Net 2 kpt head in `palm_detector.py` + `anchors.py`
(encode/decode_kpts, square anchors); `extract_keypoints.py` oriented-crop +
regression-head autodetect; `build_manifest_popsign.py`.

Frontend/lessons:
- `src/stage2/sign_verifier.py` — **SignVerifier** (committed, 9/9 tests in
  `tests/test_sign_verifier.py`): sliding-window + target-class-confidence
  persistence + motion/presence gate + hysteresis. For lesson verification.
  Wire into demo once Net 4 trains; port to TS later. Design note in
  `HANDOFF_FRONTEND.md`.
- `data/lesson_videos/*.mp4` — **96/96** reference clips (1 PopSign clip/sign;
  `bathroom`←`potty`). Gitignored; push to S3/CDN for the app.

Configs: `stage1_v3_landmark_reg.yaml`, `stage1_v3_detector_kpt.yaml`,
`stage2_v4_classifier_popsign.yaml`, `popsign_vocab.json` (96 signs + aliases).

---

## 5. Final deliverables (the 7-item list) — status

1. Browser ASL app — frontend exists (`frontend/`, Vite/React); see
   `HANDOFF_FRONTEND.md`. In progress (lesson-config dev editor being added).
2. Trained model for 75-100 signs — **Net 4 PENDING** (Phase C). Vocab = 96
   PopSign words.
3. Dataset + training docs (no-pretrained proof) — `datasetdoc` agent writing
   `docs/DATASET_AND_TRAINING.md`.
4. Validation report — `validationdoc` agent writing `docs/VALIDATION_REPORT.md`
   (Net 4 numbers PENDING; fill on completion).
5. Learner accounts + progress — frontend (`HANDOFF_FRONTEND.md`).
6. Practice interface (camera, pass/fail, hints, retry, saved progress) —
   frontend + SignVerifier for the pass/fail logic.
7. Privacy doc (camera/video handling) — NOT yet written. TODO.

---

## 6. Deferred / TODO (do NOT do mid-pipeline)

- **results/configs/scripts RENAME** to a clean scheme (`results/net2/v3_1/`,
  `results/net3/reg_v1/`, `configs/net3/landmark_reg.yaml`, etc.) — Bryann
  approved, but HOLD until the pipeline is idle (it'd break the live pod + cron
  which hardcode current paths). Docs were already reorganized (this round).
- **Net 4 "bathroom" class**: the running extraction used the pre-alias vocab,
  so Net 4 will have **95 classes, not 96** (bathroom→potty alias added after
  launch). Re-extract that one sign to include it, or leave at 95.
- **net2 fine-tune idea** (Bryann's plan): warm-start a kpt-head net2 FROM
  net2_v3_1 (keep v3_1 anchors, NOT square; add kpt head fresh; focal_gamma
  back to 2.0), fine-tune briefly → v3_1-quality detection + keypoints →
  enables **1-pass** orientation. Stays close to v3_1 so the CURRENT Net 4 may
  transfer WITHOUT re-extraction (validate by comparing new-net2→Net3 vs
  v3_1→Net3 landmarks first). ~1-2 hr.
- Remaining MediaPipe-gap items: #4 ROI tracking + presence gating, #7 OOD/
  quality gate (Req ≥90% — NOT done), #8 INT8 quantize (for 25MB browser
  budget), #9 shrink Net 1 (13.4M params, ~7× MediaPipe). InterHand was skipped
  for the Net 3 run (small-disk reliability) — could add for more pose diversity.
- Sliding-window lesson verification (SignVerifier) → wire into demo + TS port.

---

## 7. Accounts / gotchas

- RunPod: `RUNPOD_API` in `.env.local`. **Use SECURE pods** — community pods
  often have no public TCP SSH (proxy-only), which the direct-SSH provisioner
  can't use. SSH key `~/.ssh/vast_v3`. 5090 secure ~$0.99/hr; cheaper available
  types (4090/3090/A40) via `RUNPOD_GPU` + `FORCE_SECURE=1`.
- Kaggle: `KAGGLE_API` in `.env.local` is a KGAT token → export as
  `KAGGLE_API_TOKEN` on the remote (the bare `~/.kaggle/kaggle.json` is the
  broken legacy form).
- AWS: creds valid; `asl-net3-data` + `asl-pilot-datasets-*` buckets (RHD +
  EgoHands staged there; presign via `scripts/aws_presign_datasets.sh`).
- **Recurring footgun:** `pkill -f <pattern>` self-matches your own ssh/shell
  if the pattern is in your command string — kills your session. Use explicit
  PIDs or the `[p]attern` bracket trick. Also: scp uses `-P` for port (not `-p`).
  runpod image has no tmux/unzip — `_remote_*` scripts apt-install + use setsid.
- Local box: WSL, 7.6GB RAM (stream-extract only), 868GB disk. `python3` not
  `python`. `results/` and `data/` are gitignored.

---

## 8. Next steps (in order)

1. Let Phase C finish extraction → Net 4 trains automatically → `.net4_done`.
2. Cron (or you): pull+verify Net 4 best.pt to `results/v3/net4_popsign/`,
   record its top-1/top-3, **destroy the phasec pod** (pull-before-kill).
3. **E2E validation** (task #21): run a held-out PopSign clip through
   Net1→2→3(2-pass)→4 end to end; confirm a sign prediction. Use
   `src/stage2/predict_clip.py` (wire net2_v3_1 + net3 reg).
4. Fill Net 4 numbers into `docs/VALIDATION_REPORT.md`.
5. Review + commit `lessoneditor`'s output (build-then-review).
6. Write the privacy doc (deliverable #7).
7. THEN do the deferred results/configs rename (pipeline idle).
