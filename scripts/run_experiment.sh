#!/usr/bin/env bash
# One variant on one cleaned dataset, split across parallel shards, then merged and summarized.
#
#   scripts/run_experiment.sh <backend> <dataset> <variant> [shards] [max_problems_per_shard]
#     backend: claude | mistral | vllm | ollama | openai | mock      (scripts/backend_env.sh)
#     dataset: humanevalfix | humaneval | humaneval_starcoder | mbpp_deepseekcoder
#              (cleaned seeds in data/clean/<dataset>.jsonl, made by scripts/clean_data.py)
#     variant: A (MGDebugger) | B (hypothesis loop inside MGDebugger's tree)
#              | C (breakpoint localization, no decomposition)
#     shards:  parallel processes (default 4)
#
# Budget: HDMG_RUN_BUDGET_USD (default 5) is the cap for the whole run, split evenly across shards.
# Undetectable bugs are skipped and the fixed harness is on (HDMG_ONLY_DETECTABLE=1,
# HDMG_HARNESS=fixed); outer attempts default to 2 (HDMG_MAX_OUTER_RETRY).
# Output: MGDebugger/src/output_data/experiments/<dataset>_<variant>_<timestamp>/ with one folder
# per shard, merged logs at the top, and summary.txt. Compare two runs with scripts/compare_runs.py.
#
# Resume an interrupted run (same backend, dataset and variant): only the problems no shard finished
# are run, in new shard folders of the same run, then everything is merged again.
#   HDMG_RESUME=MGDebugger/src/output_data/experiments/<run> scripts/run_experiment.sh claude humanevalfix C 4
set -euo pipefail
BACKEND=${1:?backend}; DATASET=${2:?dataset}; VARIANT=${3:?variant A, B or C}
SHARDS=${4:-4}; MAX=${5:-}
HERE="$(cd "$(dirname "$0")/.." && pwd)"

case "$DATASET" in
  humaneval) SEEDS="$HERE/data/clean/humaneval_deepseekcoder.jsonl" ;;
  *)         SEEDS="$HERE/data/clean/$DATASET.jsonl" ;;   # humanevalfix, humaneval_starcoder, mbpp_deepseekcoder, ...
esac
[ -f "$SEEDS" ] || python3 "$HERE/scripts/clean_data.py"
[ -f "$SEEDS" ] || { echo "unknown dataset $DATASET (no $SEEDS; see scripts/clean_data.py)"; exit 1; }

source "$HERE/scripts/backend_env.sh"
export HDMG_VARIANT="$VARIANT"
export HDMG_HARNESS=${HDMG_HARNESS:-fixed} HDMG_ONLY_DETECTABLE=${HDMG_ONLY_DETECTABLE:-1}
export HDMG_STOP_ON=${HDMG_STOP_ON:-both} HDMG_MAX_OUTER_RETRY=${HDMG_MAX_OUTER_RETRY:-2}
RUN_BUDGET=${HDMG_RUN_BUDGET_USD:-5}
export HDMG_BUDGET_USD=$(python3 -c "print(round($RUN_BUDGET / $SHARDS, 4))")

RESUME_TAG=""
if [ -n "${HDMG_RESUME:-}" ]; then
  RESUME_DIR="$(cd "$HDMG_RESUME" && pwd)"
  SEEDS="$(python3 "$HERE/scripts/resume_seeds.py" "$RESUME_DIR")"
  if [ -z "$SEEDS" ]; then echo "nothing left to run in $RESUME_DIR"; exit 0; fi
  RESUME_TAG="_r$(date +%H%M%S)"
fi

cd "$HERE/MGDebugger/src"
if [ -n "$RESUME_TAG" ]; then
  RUN="$(python3 -c "import os,sys; print(os.path.relpath(sys.argv[1]))" "$RESUME_DIR")"
else
  RUN="output_data/experiments/${DATASET}_${VARIANT}_$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$RUN"
echo "Run $RUN: backend=$BACKEND model=${HDMG_MODEL:-?} variant=$VARIANT shards=$SHARDS" \
     "budget=\$$RUN_BUDGET (\$$HDMG_BUDGET_USD per shard) outer=$HDMG_MAX_OUTER_RETRY"

PIDS=()
for ((i = 0; i < SHARDS; i++)); do
  python3 main.py --seeds "$SEEDS" --shard "$i/$SHARDS" --out "$RUN/shard$i$RESUME_TAG" ${MAX:+--max-examples "$MAX"} \
    > "$RUN/shard$i$RESUME_TAG.log" 2>&1 &
  PIDS+=($!)
done

# progress every 60 s: problems finished per shard (from each shard's log)
while true; do
  alive=0
  for p in "${PIDS[@]}"; do kill -0 "$p" 2>/dev/null && alive=$((alive + 1)); done
  done_now=$(cat "$RUN"/shard*"$RESUME_TAG"/all_info.log 2>/dev/null | grep -cE "Successfully fixed problem|Failed to fix problem|Error occurred while processing problem" || true)
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
