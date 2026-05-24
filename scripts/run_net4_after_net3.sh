#!/bin/bash
# Net 4 orchestrator — runs on the Vast 5090 after Net 3 training finishes.
#
# Lifecycle:
#   1. Poll Net 3's metrics.jsonl + process count every 60 s.
#   2. When Net 3 has reached its final epoch (per train.epochs in config)
#      OR the python process is gone AND we have a best.pt, advance.
#   3. Copy Net 3's best.pt into results/v3/net3_v1/.
#   4. Extract per-frame keypoints across the full manifest using all three
#      Stage 1 nets on GPU (rm-rf old kpt_cache first so the cache always
#      matches the latest Net 3 weights).
#   5. Train Net 4 with the configured stage2 config.
#   6. Drop a flag file at /workspace/asl/.net4_done that the cron picks up.
#
# Run on the remote via:
#   nohup bash /workspace/asl/scripts/run_net4_after_net3.sh \
#     > /workspace/asl/logs/run_net4.log 2>&1 & disown
#
# Idempotent restarts: the script no-ops past phases whose marker files exist.

set -euo pipefail

ROOT=/workspace/asl
NET3_METRICS="$ROOT/checkpoints/stage1_v3_landmark_v1/metrics.jsonl"
NET3_BEST="$ROOT/checkpoints/stage1_v3_landmark_v1/best.pt"
NET3_DST_DIR="$ROOT/results/v3/net3_v1"
KPT_CACHE="$ROOT/data/signs/kpt_cache"
NET4_CONFIG="$ROOT/configs/stage2_v4_classifier.yaml"
NET4_CKPT_DIR="$ROOT/checkpoints/stage2_v4_classifier_v1"
DONE_FLAG="$ROOT/.net4_done"
SMOKE_FLAG="$ROOT/.smoke_done"
KPT_DONE_FLAG="$ROOT/.kpts_done"
NET3_DONE_FLAG="$ROOT/.net3_done"
TOTAL_EPOCHS=200  # matches configs/stage1_v3_landmark_v1.yaml train.epochs
SMOKE_OUT="$ROOT/results/v4/e2e_smoke_result.json"

mkdir -p "$ROOT/logs" "$NET3_DST_DIR" "$KPT_CACHE" "$NET4_CKPT_DIR"

log() { echo "[orch $(date -u +%H:%M:%S)] $*"; }

# --- Phase 1: wait for Net 3 ----------------------------------------------
phase_wait_net3() {
  if [[ -f "$NET3_DONE_FLAG" ]]; then
    log "phase 1 skipped (net3 done flag exists)"; return 0
  fi
  log "phase 1: waiting for Net 3 to finish (target ep $TOTAL_EPOCHS)"
  while true; do
    if [[ ! -f "$NET3_METRICS" ]]; then
      sleep 60; continue
    fi
    procs=$(pgrep -f "train_v3_landmark" | wc -l || echo 0)
    lines=$(wc -l < "$NET3_METRICS" 2>/dev/null || echo 0)
    last_ep=$(tail -1 "$NET3_METRICS" 2>/dev/null \
              | python3 -c "import sys,json; \
                 line=sys.stdin.readline().strip(); \
                 print(json.loads(line).get('epoch', -1) if line else -1)" \
              2>/dev/null || echo -1)
    # Done when we've reached the final epoch OR no train process AND we
    # have at least one epoch in the metrics file (so we know training
    # actually ran, not just crashed at init).
    if [[ "$last_ep" -ge $((TOTAL_EPOCHS - 1)) ]] \
       || ( [[ "$procs" -eq 0 ]] && [[ "$lines" -gt 1 ]] ); then
      log "Net 3 finished. ep=$last_ep lines=$lines procs=$procs"
      touch "$NET3_DONE_FLAG"
      return 0
    fi
    sleep 60
  done
}

# --- Phase 2: copy artifacts ----------------------------------------------
phase_copy_net3() {
  log "phase 2: copying Net 3 artifacts to results/v3/net3_v1/"
  cp -v "$NET3_BEST" "$NET3_DST_DIR/best.pt" 2>&1 | tail -2 || \
    log "  WARN: cp best.pt failed"
  cp -v "$ROOT/checkpoints/stage1_v3_landmark_v1/last.pt" \
        "$NET3_DST_DIR/last.pt" 2>&1 | tail -2 || true
  cp -v "$NET3_METRICS" "$NET3_DST_DIR/metrics.jsonl" 2>&1 | tail -2 || true
}

# --- Phase 3: keypoint extraction -----------------------------------------
phase_extract_kpts() {
  if [[ -f "$KPT_DONE_FLAG" ]]; then
    log "phase 3 skipped (kpts done flag exists)"; return 0
  fi
  # Stale cache from earlier Net 3 weights — rebuild against the final.
  log "phase 3: clearing old kpt_cache, extracting fresh from Net 3 best"
  rm -rf "$KPT_CACHE"/*.npz 2>/dev/null || true
  cd "$ROOT"
  python3 -u -m src.stage2.data.extract_keypoints \
    --manifest "$ROOT/data/signs/manifest.jsonl" \
    --net1 "$ROOT/results/v3/net1_v3_1/best.pt" \
    --net2 "$ROOT/results/v3/net2_v3_1/best.pt" \
    --net3 "$NET3_DST_DIR/best.pt" \
    --out "$KPT_CACHE" \
    --device cuda \
    --max-frames 64
  touch "$KPT_DONE_FLAG"
  log "phase 3 done. cache size:"
  du -sh "$KPT_CACHE" || true
  ls "$KPT_CACHE" | wc -l
}

# --- Phase 4: train Net 4 -------------------------------------------------
phase_train_net4() {
  if [[ -f "$NET4_CKPT_DIR/best.pt" ]]; then
    log "phase 4 skipped (net4 best.pt exists)"; return 0
  fi
  log "phase 4: training Net 4"
  cd "$ROOT"
  python3 -u -m src.stage2.train_v4_classifier \
    --config "$NET4_CONFIG"
}

# --- Phase 5: e2e smoke test ----------------------------------------------
phase_e2e_smoke() {
  if [[ -f "$SMOKE_FLAG" ]]; then
    log "phase 5 skipped (smoke flag exists)"; return 0
  fi
  log "phase 5: running e2e smoke test on test split"
  cd "$ROOT"
  mkdir -p "$ROOT/results/v4"
  # The smoke runner exits non-zero on failure; we capture but still
  # advance to phase 6 so flags reflect "complete" and the cron can
  # surface the numbers regardless of pass/fail.
  set +e
  python3 -u -m scripts.e2e_smoke_test \
    --manifest "$ROOT/data/signs/manifest.jsonl" \
    --net1 "$ROOT/results/v3/net1_v3_1/best.pt" \
    --net2 "$ROOT/results/v3/net2_v3_1/best.pt" \
    --net3 "$NET3_DST_DIR/best.pt" \
    --net4 "$NET4_CKPT_DIR/best.pt" \
    --num-clips 30 \
    --min-top3 0.5 \
    --device cuda \
    2>&1 | tee "$ROOT/logs/e2e_smoke.log"
  smoke_status=$?
  set -e
  log "phase 5 done. smoke_status=$smoke_status (0=pass, nonzero=under-threshold)"
  touch "$SMOKE_FLAG"
}

# --- Phase 6: mark done ---------------------------------------------------
phase_done() {
  touch "$DONE_FLAG"
  log "phase 6: ORCHESTRATOR DONE. flag at $DONE_FLAG"
}

main() {
  log "orchestrator starting (pid $$)"
  phase_wait_net3
  phase_copy_net3
  phase_extract_kpts
  phase_train_net4
  phase_e2e_smoke
  phase_done
}

main "$@"
