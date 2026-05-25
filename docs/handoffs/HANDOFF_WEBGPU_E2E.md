# Handoff — WebGPU port + Net 4 + live demos (compaction resume point)

Read this FIRST after compaction. Self-contained. Covers what's RUNNING right
now, the models, what shipped this session, the in-flight agent, next steps,
and gotchas. (Prior round's detail: `HANDOFF_REGRESSION_ROUND.md`.)

---

## 1. WHAT'S RUNNING RIGHT NOW (resume-critical)

- **Pod B (RunPod, role `phasec_topup`): `jdvh9l9xgljcp6` @ `64.119.209.250:13169`**, a 3090 / 128 vCPU box. Extracting the **85/word top-up** (PopSign clips 41–125) with the fast extractor: env in `.remote_env` = `OFFSET=40 MAX_PER_SIGN=85 BATCHED=1 TRAIN_NET4=0 WORKERS=16 SIGN_CONCURRENCY=4`. ~**59/96 signs** at handoff (npz=5067; check live). On finish it touches `.topup_done` and STOPS (does NOT train — TRAIN_NET4=0). SSH: `ssh -i ~/.ssh/vast_v3 -o IdentitiesOnly=yes -p 13169 root@64.119.209.250`. npz at `/workspace/asl/data/signs/popsign_kpt_cache`; logs `logs/remote_phasec_topup.log` + `logs/extract.log`. Balance ~**$9.07** (cap ~$20).
- **Cron `2f5e568d`** (every 10m): `bash scripts/round_health.sh` over `.round_env` (only the phasec_topup line now). **Session-only** — recreate with CronCreate if the session ends.
- **Local servers:** WebGPU capture-rep PoC on **:8601** (`cd playground/webgpu_poc && npm run dev`). ASL backend on **:4000** (`BACKEND_PORT=4000 npm run -w backend dev`; Postgres :5433 docker, healthy). **Frontend :5173 is DOWN** (relaunch: `VITE_API_URL=http://localhost:4000 npm run -w frontend dev`). Streamlit demo :8501 DOWN (killed for RAM). NOTE: ports 3000/3001 are the unrelated **Meridian** project (~1.4 GB RAM); box is 7.6 GB total, tight.
- **Background agent `perfworker` (agentId `a0e2163fb30dda316`)** — building the batched-eval + ~28-frame speedup for the PoC worker (the capture-rep eval was >1 min; this batches Net1 over all frames in one forward + Net3 crops, keeps Net2 per-frame, samples ~28 frames). Resume via `SendMessage(to: "a0e2163fb30dda316")`. When it returns: rebuild + restart :8601.

---

## 2. Models / artifacts (local, results/v3/, gitignored)

| Net | Path | Note |
|---|---|---|
| Net 1 | `results/v3/net1_v3_1/best_export.pt` (53.6MB) | face/body, use |
| Net 2 | `results/v3/net2_v3_1/best.pt` | the GOOD detector (AP 0.20), use |
| Net 3 | `results/v3/net3/best.pt` | regression, 2-pass self-orient |
| Net 4 baseline (40/word) | `results/v3/net4_popsign_baseline40/best.pt` (8.2MB) | **test top1 56.7% / top3 78.3%** |
| 40/word npz | `results/v3/net4_kpt_40word/` | 3800 npz |
| top-up npz checkpoint | `results/v3/net4_kpt_topup_ckpt/topup_ckpt.tgz` | ~45–59 signs, insurance pull |

Constrained-target eval (`scripts/eval_net4_verifier.py`): verifier accept rate
**~0.6%** — the baseline is UNDER-CONFIDENT (mean target prob ~0.22), so the demo
needs `conf_thresh ~0.25` (not 0.5) for green to fire. OOD rejection 100% (trivial
while under-confident). The 125/word retrain + calibration is the fix.

---

## 3. What shipped this session (committed, pushed to main)

- **Lesson-config dev editor** — per-STAGE (handshape/movement/sign) trims + reps, per-sign video preview w/ scrubber + native play controls (`/dev/lesson-config`, dev-gated, DCE-stripped in prod).
- **Privacy doc** `docs/PRIVACY.md` (deliverable #7).
- **Curriculum = PopSign 96-word training vocab** — `scripts/seed-dev-user.ts` LESSON_CATALOG rewritten; DB reseeded (12 lessons / 96 signs); glosses match clip filenames; ReferenceVideo defaults to the real per-sign clip; clips served from `frontend/public/videos/lessons/` (gitignored, 96 clips).
- **Full-sign-only lesson plan** + advance button "Continue" (word transition) / "Next rep (X of N)".
- **Net 4 manifest fix** (`build_manifest_popsign`) — maps npz→gloss via the gloss stored IN the npz (PopSign stems carry the sign mid-name; prefix match failed → 0 entries before).
- **Fast extractor**: `extract_keypoints_batched.py` (GPU frame-batch), `--workers` thread pool, `_remote_phase_c.sh` OFFSET/BATCHED/WORKERS/SIGN_CONCURRENCY/TRAIN_NET4 knobs, `build_clip_manifest --offset`, `launch_phase_c.sh` ROLE + `.remote_env` + `--gpu`. Bottleneck ladder learned: GPU idle → CPU decode (threads, ~3×) → per-sign download/untar I/O (sign-concurrency).
- **WebGPU browser port** (commit `f6e78ae`): `frontend/src/cv/` — `ort/{models,session}.ts`, `pipeline/{geom,anchors,stage1,features,stage2,verifier}.ts`, `evaluate.real.ts`; `tools/onnx_export/{export_all,dump_reference}.py`; parity fixtures + tests (`frontend/tests/cv/`, opt-in `vitest.parity.config.ts`). **V1 verified parity: TS == Python exactly** (per-net ≤1.5e-5, e2e top-3 order+probs match `predict_clip`: red→RED, mom→MAD; verifier 9/9). `evaluate.ts` still exports **mock** (flip to `evaluate.real` after in-browser verify). `onnxruntime-web` added to frontend deps. Plan: `docs/WEBGPU_PORT_PLAN.md`. ONNX assets gitignored (`frontend/public/models/*.onnx`, regenerable).

---

## 4. The WebGPU PoC (`playground/webgpu_poc/`, gitignored Vite app)

Capture-rep flow: smooth live preview → **Record sign** (3-2-1 countdown + ~2s
buffered capture, no inference) → batched worker eval → **green ✓ / orange verdict
+ top-3 + target conf**. ORT runs in a **Web Worker** (off main thread). Sidebar:
alphabetical 96-gloss target, conf (default 0.25) + vote sliders, 2-pass toggle
(default off = 1-pass Net3). Run: `cd playground/webgpu_poc && npm install && npm
run dev` → http://localhost:8601 (Chrome/Edge 113+ on a GPU machine). EP pill shows
webgpu vs wasm. Shared engine `playground/webgpu_poc/src/{worker,main,protocol}.ts`
imports `@cv` (= `frontend/src/cv`). Perf reality: in-browser real-time was too slow
(Net1 13.4M + per-frame readback) → moved to capture-rep + batched eval. Offline:
ORT wasm comes from jsdelivr CDN — for offline copy `node_modules/onnxruntime-web/dist`
jsep wasm to a local dir + repoint `ort.env.wasm.wasmPaths` in `session.ts`.

---

## 5. NEXT STEPS (in order)

1. **Pod B finishes (96/96 + `.topup_done`):** pull the full 85/word npz, merge with
   `results/v3/net4_kpt_40word/` → **125/word**; run the FIXED `build_manifest_popsign`
   (gloss-from-npz); train production Net 4 (`configs/stage2_v4_classifier_popsign.yaml`)
   on a pod; pull `best.pt`; **destroy pod B (pull-before-kill)**, remove its `.round_env`
   line. Record top1/top3 in `docs/VALIDATION_REPORT.md`.
2. **Re-point** the demo/PoC + ONNX export at the 125/word model; re-export net4.onnx,
   re-run parity, refresh the PoC model.
3. **perfworker returns** → rebuild + restart :8601, user re-measures eval speed.
4. Deferred: INT8 quant + Net1 shrink (browser real-time, after model final), RGB→kpts
   Stage-1 parity fixtures (close V1's gap), flip `evaluate.ts` mock→real (after browser
   verify), the results/configs rename (HOLD until pipeline idle).

---

## 6. Gotchas

- **Subagents cannot SendMessage each other** — only lead→agent. They coordinate via the
  shared filesystem + their final reports. (Why the clean IO contract / fixtures mattered.)
- **Sandbox SIGTERMs long-lived listening sockets** started via `run_in_background` (killed
  the :5173 frontend); start servers with `nohup ... &` (the streamlit/vite/http servers
  persisted that way).
- `pkill -f <pat>` self-matches your own ssh — use `[p]attern` brackets or explicit PIDs.
- **Net4 ONNX `key_padding_mask` is FLOAT32** (1.0=padded), not bool (in-graph cast).
- scp uses `-P` (port) not `-p`; PopSign tars need `tar --no-same-owner`.
- RunPod: use SECURE or set `RUNPOD_GPU` + retry on capacity errors (5090 default often
  unavailable; 3090/4090/A40 via `--gpu`). `RUNPOD_API` in `.env.local`.
- Local box: WSL, 7.6GB RAM (tight; Meridian ~1.4GB), CPU-only torch, `python3` not `python`.
