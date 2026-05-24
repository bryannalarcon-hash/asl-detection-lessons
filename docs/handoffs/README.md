# Handoffs

Session resume points, ordered newest-first. Each handoff describes the
state at the time it was written; later handoffs supersede earlier ones
on overlapping topics.

## ML training track

1. **`HANDOFF_NET3_V2.md`** — current. Net 3 v2 retrain (multi-threshold PCK,
   config + arch + loss landed; pre-launch).
2. `HANDOFF_POST_TRAIN.md` — post-training state after Net 1 + Net 2 finished;
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
