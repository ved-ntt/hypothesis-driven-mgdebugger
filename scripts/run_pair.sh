#!/usr/bin/env bash
# A and L2 side by side on one dataset (8 shards in all), then compare_runs.py.
#   scripts/run_pair.sh <dataset> <report.md>          e.g. HDMG_EXACT_TESTS=1 scripts/run_pair.sh mbpp_deepseekcoder results/x.md
# Environment (HDMG_EXACT_TESTS, budgets...) passes through to both runs. If interrupted, resume each
# run with HDMG_RESUME=<run folder> scripts/run_experiment.sh claude <dataset> <A|L2> 4
set -uo pipefail
DS=${1:?dataset}; OUT=${2:?report path}
HERE="$(cd "$(dirname "$0")/.." && pwd)"
EXP="$HERE/MGDebugger/src/output_data/experiments"
START=$(date +%Y%m%d-%H%M%S)
HDMG_RUN_BUDGET_USD=${A_BUDGET:-3} bash "$HERE/scripts/run_experiment.sh" claude "$DS" A 4 > "$EXP/../pair_${DS}_A.log" 2>&1 &
pa=$!
HDMG_RUN_BUDGET_USD=${L2_BUDGET:-1} bash "$HERE/scripts/run_experiment.sh" claude "$DS" L2 4 > "$EXP/../pair_${DS}_L2.log" 2>&1 &
pl=$!
echo "$(date +%H:%M) A and L2 running on $DS (logs: MGDebugger/src/output_data/pair_${DS}_*.log)"
wait $pa $pl
a=$(ls -d "$EXP/${DS}_A_"* | sort | tail -1); l=$(ls -d "$EXP/${DS}_L2_"* | sort | tail -1)
python3 "$HERE/scripts/compare_runs.py" "$a" "$l" --out "$OUT" > /dev/null && echo "$(date +%H:%M) done: $OUT"
