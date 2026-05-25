# Handoffs

Session resume points, ordered newest-first. Each handoff describes the
state at the time it was written; later handoffs supersede earlier ones
on overlapping topics.

## ML training track

1. **`HANDOFF_MEDIAPIPE_GAP.md`** — CURRENT. Net 3 v2 landed (0.32 PCK@0.05);
   MediaPipe gap analysis + greenlit action plan (regression Net 3, ROI
   tracking, Net 2 keypoints, Net 4 per-hand norm, checkpoint hygiene, INT8).
   Demo upgrades (box expansion, stable-box filter, one-euro smoothing).
2. `net4_data_sourcing.md` — ≥500-clip/word PopSign-drawn ASL-1 vocabulary +
   memory-safe acquisition plan (sourcing verified, nothing downloaded).
3. `HANDOFF_NET3_V2.md` — Net 3 v2 retrain prep round.
4. `HANDOFF_POST_TRAIN.md` — post-training state after Net 1 + Net 2 finished;
   Net 3 v1 failed on disk-full.
3. `HANDOFF_V3_1.md` — v3.1 round (Vast instance `37514594`, cron job, goal
   state).
4. `HANDOFF_OPTIMIZATION_ROUND.md` — optimization attempts (CUDA Graphs,
   channels_last, etc.).
5. `HANDOFF_STAGE1.md` — original Stage 1 keypoint detector handoff (v3
   plan, dataset details, conventions).

## Frontend / pilot app track

- `HANDOFF_FRONTEND.md` — current state of the browser pilot (scaffold +
  post-scaffold deltas: heatmap rewrite, sign-complete toast, resume
  cursor, mode toggles, etc.).

## Not a session handoff

`docs/ml-handoff.md` (sibling, not in this folder) is the CV black-box
**interface contract** between the ML and frontend tracks. It's a
permanent spec, not a session resume point.
