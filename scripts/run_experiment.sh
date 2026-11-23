#!/usr/bin/env bash
# One variant on one cleaned dataset, split across parallel shards, then merged and summarized.
#
#   scripts/run_experiment.sh <backend> <dataset> <variant> [shards] [max_problems_per_shard]
#     backend: claude | mistral | vllm | ollama | openai | mock      (scripts/backend_env.sh)
#     dataset: humanevalfix | humaneval   (cleaned seeds in data/clean/, made by scripts/clean_data.py)
#     variant: A (MGDebugger's simulated trace) | C (hypothesis loop)
#     shards:  parallel processes (default 4)
#
# Budget: HDMG_RUN_BUDGET_USD (default 5) is the cap for the whole run, split evenly across shards.
# Undetectable bugs are skipped and the fixed harness is on (HDMG_ONLY_DETECTABLE=1,
# HDMG_HARNESS=fixed); outer attempts default to 2 (HDMG_MAX_OUTER_RETRY).
# Output: MGDebugger/src/output_data/experiments/<dataset>_<variant>_<timestamp>/ with one folder
# per shard, merged logs at the top, and summary.txt. Compare two runs with scripts/compare_runs.py.
set -euo pipefail
BACKEND=${1:?backend}; DATASET=${2:?dataset}; VARIANT=${3:?variant A or C}
SHARDS=${4:-4}; MAX=${5:-}
HERE="$(cd "$(dirname "$0")/.." && pwd)"

case "$DATASET" in
  humanevalfix) SEEDS="$HERE/data/clean/humanevalfix.jsonl" ;;
  humaneval)    SEEDS="$HERE/data/clean/humaneval_deepseekcoder.jsonl" ;;
  *) echo "unknown dataset $DATASET (humanevalfix | humaneval)"; exit 1 ;;
esac
[ -f "$SEEDS" ] || python3 "$HERE/scripts/clean_data.py"

source "$HERE/scripts/backend_env.sh"
export HDMG_VARIANT="$VARIANT"
export HDMG_HARNESS=${HDMG_HARNESS:-fixed} HDMG_ONLY_DETECTABLE=${HDMG_ONLY_DETECTABLE:-1}
export HDMG_STOP_ON=${HDMG_STOP_ON:-both} HDMG_MAX_OUTER_RETRY=${HDMG_MAX_OUTER_RETRY:-2}
RUN_BUDGET=${HDMG_RUN_BUDGET_USD:-5}
export HDMG_BUDGET_USD=$(python3 -c "print(round($RUN_BUDGET / $SHARDS, 4))")

cd "$HERE/MGDebugger/src"
RUN="output_data/experiments/${DATASET}_${VARIANT}_$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN"
echo "Run $RUN: backend=$BACKEND model=${HDMG_MODEL:-?} variant=$VARIANT shards=$SHARDS" \
     "budget=\$$RUN_BUDGET (\$$HDMG_BUDGET_USD per shard) outer=$HDMG_MAX_OUTER_RETRY"

PIDS=()
for ((i = 0; i < SHARDS; i++)); do
  python3 main.py --seeds "$SEEDS" --shard "$i/$SHARDS" --out "$RUN/shard$i" ${MAX:+--max-examples "$MAX"} \
    > "$RUN/shard$i.log" 2>&1 &
  PIDS+=($!)
done

# progress every 60 s: problems finished per shard (from each shard's log)
while true; do
  alive=0
  for p in "${PIDS[@]}"; do kill -0 "$p" 2>/dev/null && alive=$((alive + 1)); done
  done_now=$(cat "$RUN"/shard*/all_info.log 2>/dev/null | grep -cE "Successfully fixed problem|Failed to fix problem|Error occurred while processing problem" || true)
  echo "$(date +%H:%M:%S)  problems finished: $done_now  shards running: $alive/$SHARDS"
  [ "$alive" -eq 0 ] && break
  sleep 60
done

FAILED=0
for p in "${PIDS[@]}"; do wait "$p" || FAILED=$((FAILED + 1)); done
[ "$FAILED" -eq 0 ] || echo "WARNING: $FAILED shard(s) exited with an error; see $RUN/shard*.log"

python3 "$HERE/scripts/merge_runs.py" "$RUN"
python3 "$HERE/scripts/summarize.py" "$RUN" | tee "$RUN/summary.txt"
echo "Merged run: MGDebugger/src/$RUN"
