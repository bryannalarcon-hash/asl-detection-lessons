# Handoffs

Session resume points. Active handoffs live here; superseded ones are in
`archive/`. Later handoffs supersede earlier ones on overlapping topics.

## Current state (2026-05-26)

The app is **deployed + live on Railway** (https://asl-pilot-api-production.up.railway.app):
SPA + API + Postgres + auth + lessons catalog + dashboard all work; the real
capture-rep CV + hint system are wired into the practice flow. **Prod now serves
the CV models + reference videos from a mounted volume** (the earlier "missing
assets" was actually a `.railwayignore` unanchored-pattern build bug, now fixed).
**One open issue:** the camera self-view doesn't appear on the deployed site
(needs the user's browser console to diagnose). Net 4 is the 125/word model (test
top-1 0.78 / top-3 0.91). **Start at `HANDOFF_DEPLOY.md`.**

## Prior state (2026-05-25)

MediaPipe-gap retrain round. Net 3 was rewritten heatmap →
**direct coordinate regression** and trained (held-out FreiHAND
**val_pck_05 = 0.45**, up from the old heatmap net's 0.32). The new
keypoint-head Net 2 under-trained and regressed as a detector (AP 0.016 vs
net2_v3_1's 0.20), so the pipeline uses **net2_v3_1 + Net 3 2-pass
self-orientation** instead. Net 4 (PopSign, ~96 signs) is extracting +
training toward the end-to-end pipeline. Full outcome in the auto-memory
note `project_net_v3_regression_round.md`.

## Active

### Deploy / app track
- **`HANDOFF_DEPLOY.md`** — CURRENT. The Railway deploy (URL, service/Postgres
  IDs, env, boot CMD), what works vs the prod asset/camera gaps + exact next
  steps, the local dev state, everything that shipped this session, and gotchas.

### ML training track
- **`HANDOFF_WEBGPU_E2E.md`** — prior compaction resume point: what's RUNNING
  (pod B top-up, cron, :8601 PoC, perfworker agent), models incl. the Net 4
  baseline, the WebGPU browser port, the capture-rep PoC, next steps, gotchas.
- **`HANDOFF_REGRESSION_ROUND.md`** — prior round (Net 3 regression + the net2
  decision + infra). Superseded by the above on overlapping topics.
- **`HANDOFF_MEDIAPIPE_GAP.md`** — the ranked MediaPipe-gap action plan
  (regression Net 3, ROI tracking, Net 2 keypoints, Net 4 per-hand norm,
  checkpoint hygiene, INT8). The doctrine for the current round.
- **`net4_data_sourcing.md`** — the ~96-word PopSign-drawn ASL-1 vocabulary
  + memory-safe per-sign download/extract plan (Net 4 data).

### Frontend / pilot app track
- **`HANDOFF_FRONTEND.md`** — browser pilot state (scaffold + deltas).

## Archived (superseded)

`archive/` holds earlier ML handoffs kept for history:
`HANDOFF_NET3_V2` (pre-regression Net 3), `HANDOFF_POST_TRAIN`,
`HANDOFF_V3_1`, `HANDOFF_OPTIMIZATION_ROUND`, `HANDOFF_STAGE1`.

## Not a session handoff

`docs/ml-handoff.md` (sibling, not in this folder) is the CV black-box
**interface contract** between the ML and frontend tracks — a permanent
spec, not a session resume point.
