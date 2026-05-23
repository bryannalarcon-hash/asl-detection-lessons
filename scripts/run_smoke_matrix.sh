#!/bin/bash
# Sequential smoke matrix.
# Each smoke is bench_smoke.sh NAME DUR_SEC train-args...
set +e
ulimit -n 65536
cd /workspace/asl-learning
rm -f bench/v3_arch_round.csv
mkdir -p bench

run() {
  local name=$1; shift
  local dur=${1:-90}; shift
  echo ""
  echo "########################################"
  echo "### $name  (dur=${dur}s)"
  echo "### args: $@"
  echo "########################################"
  bash scripts/bench_smoke.sh "$name" "$dur" "$@" 2>&1 | tr '\r' '\n' | grep -E "(NAME=|\[init|\[dali-cache|FAIL)" | head -20
}

run baseline 90 --use-dali
run dali_cache_precomp 90 --use-dali
run numba_only 90 --use-dali --use-numba-anchors
run cache_numba 90 --use-dali --use-numba-anchors --channels-last
run cache_numba_fused 90 --use-dali --use-numba-anchors --channels-last --fused-adamw

echo ""
echo "##### RESULTS #####"
cat bench/v3_arch_round.csv
