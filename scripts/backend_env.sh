# Model backend settings, shared by run_variant_a.sh and run_experiment.sh. Source it with
# BACKEND and HERE set:   source "$HERE/scripts/backend_env.sh"
# Any HDMG_* variable already set in the environment wins over these defaults.
case "$BACKEND" in
  vllm)   # python -m vllm.entrypoints.openai.api_server --model deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct \
          #   --trust-remote-code --api-key token-abc123s --port 18889
    export HDMG_BASE_URL=${HDMG_BASE_URL:-http://localhost:18889/v1}
    export HDMG_MODEL=${HDMG_MODEL:-deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct}
    export HDMG_API_KEY=${HDMG_API_KEY:-token-abc123s}
    export HDMG_USE_MIN_P=${HDMG_USE_MIN_P:-1} ;;
  ollama) # ollama pull deepseek-coder-v2:16b   (the Lite-Instruct model, 4-bit)
    export HDMG_BASE_URL=${HDMG_BASE_URL:-http://localhost:11434/v1}
    export HDMG_MODEL=${HDMG_MODEL:-deepseek-coder-v2:16b}
    export HDMG_API_KEY=${HDMG_API_KEY:-ollama}
    export HDMG_USE_MIN_P=0 ;;
  openai) # needs HDMG_API_KEY; not one of the paper's seed models, so compare relative gains only
    export HDMG_BASE_URL=${HDMG_BASE_URL:-https://api.openai.com/v1}
    export HDMG_MODEL=${HDMG_MODEL:-gpt-4o-mini}
    : "${HDMG_API_KEY:?set HDMG_API_KEY}"
    export HDMG_USE_MIN_P=0 ;;
  claude) # Claude Haiku 5.5 via the OpenAI-compatible endpoint; key read from key/apikey.txt
    export HDMG_BASE_URL=${HDMG_BASE_URL:-https://api.anthropic.com/v1/}
    export HDMG_MODEL=${HDMG_MODEL:-claude-haiku-5-5}
    if [ -z "${HDMG_API_KEY:-}" ]; then
      [ -f "$HERE/key/apikey.txt" ] || { echo "No key: put it in key/apikey.txt or set HDMG_API_KEY"; exit 1; }
      HDMG_API_KEY=$(tr -d '\r\n ' < "$HERE/key/apikey.txt")
    fi
    export HDMG_API_KEY
    export HDMG_USE_MIN_P=0
    export HDMG_TEMPERATURE=none            # models after Claude 4.7 reject temperature < 1
    export HDMG_PRICE_IN=${HDMG_PRICE_IN:-0.10} HDMG_PRICE_OUT=${HDMG_PRICE_OUT:-0.50}
    export HDMG_BUDGET_USD=${HDMG_BUDGET_USD:-1} ;;   # per process; raise it deliberately
  mistral) # free Experiment tier; key in key/mistral.txt
    export HDMG_BASE_URL=${HDMG_BASE_URL:-https://api.mistral.ai/v1}
    export HDMG_MODEL=${HDMG_MODEL:-codestral-latest}
    export HDMG_API_KEY=${HDMG_API_KEY:-$(tr -d '\r\n ' < "$HERE/key/mistral.txt")}
    export HDMG_USE_MIN_P=0 ;;
  mock)   # wiring test only; results mean nothing
    export HDMG_BASE_URL=http://127.0.0.1:18889/v1 HDMG_API_KEY=x HDMG_USE_MIN_P=0
    export HDMG_PRICE_IN=${HDMG_PRICE_IN:-0.10} HDMG_PRICE_OUT=${HDMG_PRICE_OUT:-0.50}
    python3 "$HERE/scripts/mock_llm_server.py" --mode oracle \
      --seeds "$HERE/MGDebugger/src/input_data/humaneval/seed/deepseekcoder/seed.jsonl" --port 18889 &
    MOCK_PID=$!; trap 'kill $MOCK_PID 2>/dev/null' EXIT; sleep 1 ;;
  *) echo "unknown backend $BACKEND"; exit 1 ;;
esac
