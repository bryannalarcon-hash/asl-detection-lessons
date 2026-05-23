#!/bin/bash
# Smoke harness for v3 detector throughput measurement.
# Runs one config with `timeout`, parses median it/s from tqdm output.
# Usage: scripts/bench_smoke.sh <name> <duration_sec> [extra train flags...]
set +e
NAME=$1
DUR=${2:-90}
shift 2 || true
LOG=/tmp/smoke_${NAME}.log
T0=$(date +%s)
ulimit -n 65536
cd /workspace/asl-learning
echo "=== $NAME starting $(date -u) ==="
timeout $((DUR + 20)) python3 -u -m src.stage1.train_v3_detector \
    --config configs/stage1_v3_detector.yaml "$@" 2>&1 | tee "$LOG"
RC=$?
T1=$(date +%s)
ELAPSED=$((T1 - T0))
# Parse it/s from tqdm; ignore first 25 entries (warmup), then median + tail mean.
python3 - <<PYEOF
import re, statistics, sys
lines = open("$LOG").read().replace('\r','\n').split('\n')
rates = []
for ln in lines:
    m = re.search(r'(\d+\.\d+)\s*it/s', ln)
    if m:
        rates.append(float(m.group(1)))
if not rates:
    print(f"NAME=$NAME RC=$RC ELAPSED=$ELAPSED ITERS=0 sustained=FAIL")
    sys.exit(0)
warm = rates[25:] if len(rates) > 30 else rates
tail = warm[-30:] if len(warm) > 30 else warm
median = statistics.median(tail)
mean = statistics.mean(tail)
mx = max(tail)
print(f"NAME=$NAME RC=$RC ELAPSED=${ELAPSED}s ITERS={len(rates)} "
      f"sustained_median={median:.2f} mean={mean:.2f} max={mx:.2f} it/s")
# Save numbers to a CSV file
import os
csv = "/workspace/asl-learning/bench/v3_arch_round.csv"
os.makedirs(os.path.dirname(csv), exist_ok=True)
hdr = "name,rc,elapsed,iters,sustained_median,mean,max\n"
if not os.path.exists(csv):
    open(csv,"w").write(hdr)
with open(csv,"a") as f:
    f.write(f"$NAME,$RC,${ELAPSED},{len(rates)},{median:.2f},{mean:.2f},{mx:.2f}\n")
PYEOF
echo "=== $NAME done $(date -u) ==="
