# Handoffs

Session resume points. Active handoffs live here; superseded ones are in
`archive/`. Later handoffs supersede earlier ones on overlapping topics.

## Current state (2026-05-25)

MediaPipe-gap retrain round in progress. Net 3 was rewritten heatmap →
**direct coordinate regression** and trained (held-out FreiHAND
**val_pck_05 = 0.45**, up from the old heatmap net's 0.32). The new
keypoint-head Net 2 under-trained and regressed as a detector (AP 0.016 vs
net2_v3_1's 0.20), so the pipeline uses **net2_v3_1 + Net 3 2-pass
self-orientation** instead. Net 4 (PopSign, ~96 signs) is extracting +
training toward the end-to-end pipeline. Full outcome in the auto-memory
note `project_net_v3_regression_round.md`.

## Active

### ML training track
- **`HANDOFF_REGRESSION_ROUND.md`** — CURRENT. The regression round + e2e +
  final-deliverables resume point: what's trained, what's running (Phase C →
  Net 4), the net2 decision, infra/tooling, deliverables status, next steps.
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
