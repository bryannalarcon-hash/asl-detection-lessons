#!/bin/bash
# Dual-job status check — Net 2 on vast (ssh) + Net 1 on Modal.
# Print a tight summary table. Used by the 20-min cron.
set +e
export PATH=/opt/conda/bin:$PATH 2>/dev/null

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

echo ""
echo "## Net 2 (vast 37423131 → ssh9.vast.ai:23130)"
ssh -o ConnectTimeout=12 -o StrictHostKeyChecking=no -i ~/.ssh/vast_v3 -p 23130 root@ssh9.vast.ai '
LOG=/workspace/asl-learning/logs/launch.log
METRICS=/workspace/asl-learning/checkpoints/stage1_v3_detector/metrics.jsonl
echo "  step: $(tail -200 "$LOG" 2>/dev/null | tr "\r" "\n" | grep -oE "^\[[1-5]/5\]" | tail -1 || echo "?")"
echo "  epochs:"
tail -3 "$METRICS" 2>/dev/null | python3 -c "import json,sys
for ln in sys.stdin:
    d=json.loads(ln); print(f\"    epoch {d[\\\"epoch\\\"]:03d}  {d[\\\"epoch_secs\\\"]}s  loss={d[\\\"train_loss\\\"]:.4f}  cls={d[\\\"cls_loss\\\"]:.4f}  box={d[\\\"box_loss\\\"]:.4f}\")
" 2>/dev/null
echo "  GPU: $(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>/dev/null | head -1)"
echo "  errors: $(grep -ciE "FATAL|Traceback|CUDA OOM|out of memory" "$LOG" 2>/dev/null) total"
echo "  disk: $(df -h /workspace 2>/dev/null | tail -1 | awk "{print \$5}") used"
' 2>&1 | grep -v "Welcome to vast"

echo ""
echo "## Net 1 (Modal asl-net1-retrain)"
modal app list 2>&1 | grep -E "asl-net1|state|App ID" | head -3
echo "  status:"
modal run modal_apps/train_net1.py::status 2>&1 | tail -20 | grep -v "Modal\|Updated" | head -15
