#!/usr/bin/env bash
# Reproduce the experiments of the README / paper.
#
#   bash scripts/reproduce.sh smoke          # no API key, free, ~5 min: tests + mock runs of A, B, C
#   bash scripts/reproduce.sh humanevalfix   # A, B, C on HumanEvalFix (151 bugs): ~1 h, ~$3.50
#   bash scripts/reproduce.sh heldout        # A and C on the 3 held-out sets (224 bugs): ~1.5 h, ~$3.50
#   bash scripts/reproduce.sh all            # humanevalfix, then heldout
#
# Live stages need the Claude API key in key/apikey.txt (see README). Runs go to
# MGDebugger/src/output_data/experiments/, reports to results/repro/. Safe to run again after an
# interruption: a finished run is reused, an unfinished one is resumed (REPRO_FRESH=1 starts over).
# Set HDMG_EXACT_TESTS=1 for exact given-test checks (the post-hoc MBPP setting in the paper).
set -uo pipefail
STAGE=${1:-smoke}
HERE="$(cd "$(dirname "$0")/.." && pwd)"
EXP="$HERE/MGDebugger/src/output_data/experiments"
OUT="$HERE/results/repro"
mkdir -p "$EXP" "$OUT"

latest() {  # newest run folder of dataset $1, variant $2 made with the final variant letters
  local d
  for d in $(ls -d "$EXP/${1}_${2}_"* 2>/dev/null | sort -r); do
    # runs from before the letters were final reuse "C" for another variant: skip them
    grep -qs '"VARIANT_SCHEME": 2' "$d/params.json" "$d"/shard*/params.json && { echo "$d"; return; }
  done
}

run_one() {  # dataset variant budget_usd
  local ds=$1 v=$2 budget=$3 last
  last=$(latest "$ds" "$v")
  if [ -n "$last" ] && [ -z "${REPRO_FRESH:-}" ]; then
    if [ -z "$(python3 "$HERE/scripts/resume_seeds.py" "$last" --check)" ]; then
      echo "[$ds $v] finished: $last"; return
    fi
    echo "[$ds $v] resuming $last"
    HDMG_RESUME="$last" HDMG_RUN_BUDGET_USD=$budget bash "$HERE/scripts/run_experiment.sh" claude "$ds" "$v" 4
  else
    HDMG_RUN_BUDGET_USD=$budget bash "$HERE/scripts/run_experiment.sh" claude "$ds" "$v" 4
  fi
}

compare() {  # dataset v1 v2
  python3 "$HERE/scripts/compare_runs.py" "$(latest "$1" "$2")" "$(latest "$1" "$3")" \
    --out "$OUT/${1}_${2}_vs_${3}.md" > /dev/null && echo "$(date +%H:%M) report: results/repro/${1}_${2}_vs_${3}.md"
}

smoke() {
  ( cd "$HERE" && python3 -m pytest -q tests ) || exit 1
  for v in A B C; do
    bash "$HERE/scripts/run_experiment.sh" mock humanevalfix "$v" 2 2 | grep -E "Variant|debugged so far|public-selection"
  done
  echo "smoke test passed (mock model: the repair numbers mean nothing, only that the pipeline runs)"
}

humanevalfix() {
  echo "$(date +%H:%M) HumanEvalFix: A, B, C in parallel (logs: MGDebugger/src/output_data/repro_humanevalfix_*.log)"
  for v in A B C; do run_one humanevalfix "$v" 3 > "$EXP/../repro_humanevalfix_$v.log" 2>&1 & done
  wait
  compare humanevalfix A B; compare humanevalfix A C; compare humanevalfix B C
}

heldout() {
  for ds in humaneval_deepseekcoder humaneval_starcoder mbpp_deepseekcoder; do
    echo "$(date +%H:%M) $ds: A and C in parallel (logs: MGDebugger/src/output_data/repro_${ds}_*.log)"
    run_one "$ds" A 3 > "$EXP/../repro_${ds}_A.log" 2>&1 &
    run_one "$ds" C 1 > "$EXP/../repro_${ds}_C.log" 2>&1 &
    wait
    compare "$ds" A C
  done
}

case "$STAGE" in
  smoke) smoke ;;
  humanevalfix) humanevalfix ;;
  heldout) heldout ;;
  all) humanevalfix; heldout ;;
  *) echo "usage: scripts/reproduce.sh smoke|humanevalfix|heldout|all"; exit 1 ;;
esac
