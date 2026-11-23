#!/usr/bin/env bash
# Variant A: MGDebugger as published, with call logging and both scoring rules.
#
#   scripts/run_variant_a.sh <backend> <dataset> [max_examples]
#     backend: claude | mistral | vllm | ollama | openai | mock
#     dataset: humaneval | mbpp | humanevalfix
#
# Seeds are the paper's DeepSeek-Coder-V2-Lite seeds (HumanEval/MBPP), so a run with that
# model is directly comparable to Table 1. Override anything with HDMG_* env vars.
# Variant C (hypothesis loop) with the same pipeline:  HDMG_VARIANT=C scripts/run_variant_a.sh ...
set -euo pipefail
BACKEND=${1:?backend}; DATASET=${2:?dataset}; MAX=${3:-}
HERE="$(cd "$(dirname "$0")/.." && pwd)"

source "$HERE/scripts/backend_env.sh"

case "$DATASET" in
  humaneval)    SEEDS=input_data/humaneval/seed/deepseekcoder/seed.jsonl ;;
  mbpp)         SEEDS=input_data/mbpp/seed/deepseekcoder/seed.jsonl ;;
  humanevalfix) SEEDS=input_data/humanevalfix/seeds.jsonl ;;
  *) echo "unknown dataset $DATASET"; exit 1 ;;
esac

export HDMG_STOP_ON=${HDMG_STOP_ON:-both}
cd "$HERE/MGDebugger/src"
python3 main.py --seeds "$SEEDS" ${MAX:+--max-examples "$MAX"}
RUN_DIR=$(find output_data -type f -name params.json -printf '%T@ %h\n' | sort -nr | head -1 | cut -d' ' -f2-)
python3 "$HERE/scripts/summarize.py" "$RUN_DIR" | tee "$RUN_DIR/summary.txt"
