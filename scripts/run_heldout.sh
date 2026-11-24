#!/usr/bin/env bash
# Held-out check for variant L2 (results/heldout_plan.md): A and L2 on seed sets never looked at
# while designing L2, plus L2 again on HumanEvalFix with the frozen version.
#
#   bash scripts/run_heldout.sh            # backend claude; safe to run again after an interruption
#   bash scripts/run_heldout.sh mock 2     # wiring check: mock model, 2 problems per shard, one at a time
#
# For each (dataset, variant): skips it if a finished run exists, resumes an unfinished one,
# otherwise starts a new one. A and L2 on the same dataset run at the same time (8 shards).
# Then writes results/heldout_<dataset>.md with compare_runs.py.
set -uo pipefail
BACKEND=${1:-claude}; MAX=${2:-}
HERE="$(cd "$(dirname "$0")/.." && pwd)"
EXP="$HERE/MGDebugger/src/output_data/experiments"
AFTER=20261124-140000   # runs started before L2 was frozen don't count

stamp() { basename "$1" | grep -oE '[0-9]{8}-[0-9]{6}$'; }

latest() {  # newest run of dataset $1, variant $2 started after AFTER
  local d
  for d in $(ls -d "$EXP/${1}_${2}_"* 2>/dev/null | sort -r); do
    [[ "$(stat_name "$d")" > "$AFTER" || "$(stat_name "$d")" == "$AFTER" ]] && { echo "$d"; return; }
  done
}
stat_name() { stamp "$1"; }

run_one() {  # dataset variant budget
  local ds=$1 v=$2 budget=$3 last
  last=$(latest "$ds" "$v")
  if [ -n "$last" ] && [ -z "$(python3 "$HERE/scripts/resume_seeds.py" "$last" --check)" ]; then
    echo "[$ds $v] finished: $last"; return
  fi
  if [ -n "$last" ]; then
    echo "[$ds $v] resuming $last"
    HDMG_RESUME="$last" HDMG_RUN_BUDGET_USD=$budget bash "$HERE/scripts/run_experiment.sh" "$BACKEND" "$ds" "$v" 4 $MAX
  else
    echo "[$ds $v] new run"
    HDMG_RUN_BUDGET_USD=$budget bash "$HERE/scripts/run_experiment.sh" "$BACKEND" "$ds" "$v" 4 $MAX
  fi
}


# 1. L2 (frozen) on HumanEvalFix again; A's HumanEvalFix run is reused
run_one humanevalfix L2 1 > "$EXP/../heldout_humanevalfix_L2.log" 2>&1
python3 "$HERE/scripts/compare_runs.py" "$EXP/humanevalfix_A_20261123-160502" "$(latest humanevalfix L2)" \
  --out "$HERE/results/heldout_humanevalfix.md" > /dev/null && echo "humanevalfix: results/heldout_humanevalfix.md"

# 2. held-out sets: A and L2 side by side
for ds in humaneval_deepseekcoder humaneval_starcoder mbpp_deepseekcoder; do
  echo "$(date +%H:%M) $ds: A and L2 running (logs: MGDebugger/src/output_data/heldout_${ds}_*.log)"
  if [ "$BACKEND" = mock ]; then   # one mock server port: one run at a time
    run_one "$ds" A 3 > "$EXP/../heldout_${ds}_A.log" 2>&1
    run_one "$ds" L2 1 > "$EXP/../heldout_${ds}_L2.log" 2>&1
  else
    run_one "$ds" A 3 > "$EXP/../heldout_${ds}_A.log" 2>&1 &
    pa=$!
    run_one "$ds" L2 1 > "$EXP/../heldout_${ds}_L2.log" 2>&1 &
    pl=$!
    wait $pa $pl
  fi
  python3 "$HERE/scripts/compare_runs.py" "$(latest "$ds" A)" "$(latest "$ds" L2)" \
    --out "$HERE/results/heldout_${ds}.md" > /dev/null && echo "$(date +%H:%M) $ds: results/heldout_${ds}.md"
done
echo "done"
