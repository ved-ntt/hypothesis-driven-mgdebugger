# Configuration and hyperparameters for MGDebugger

import os

# [hdmg] Model and endpoint come from env vars so the same code runs against
# vLLM, Ollama or an OpenAI-compatible API. Defaults are the paper's setup.
MODEL = os.environ.get("HDMG_MODEL", "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct")

# LLM Client Configuration
LLM_BASE_URL = os.environ.get("HDMG_BASE_URL", "http://localhost:18889/v1")
LLM_API_KEY = os.environ.get("HDMG_API_KEY", "token-abc123s")

# Hyperparameters
MAX_VLLM_RETRIES = 10  # maximum number of retries for the VLLM call
MAX_PARSE_RETRIES = 3  # we sometimes fail to parse the code/test cases from the response, so we retry
MAX_DEBUG_RETRIES = 3  # 3 seems to be slightly better than 1, but the difference is not significant
RETRY_DELAY = 0  # seconds
REPEAT_CONVERT_HIERARCHICAL_NUM = 1  # seems unimportant
REPEAT_TEST_CASE_GENERATION_NUM = 1  # 1 seems to be better than 3
MAX_OUTER_RETRY = 10  # maximum number of retries for the entire debugging process
CONTINUOUS_RETRY = False  # whether to retry from the last fixed code, else retry from the original buggy code. it seems better to set this to False
TEMPERATURE = 0.8  # 0.8 better than 1.0 better than 0.2
MINP = 0.05
# [hdmg] min_p is a vLLM-only sampling parameter; OpenAI-style APIs reject it.
USE_MIN_P = os.environ.get("HDMG_USE_MIN_P", "1") == "1"
# [hdmg] Temperature override (paper: 0.8). "none" omits it: Claude models after 4.7
# reject any temperature below 1 on the OpenAI-compatible endpoint.
_t = os.environ.get("HDMG_TEMPERATURE")
TEMPERATURE = None if (_t or "").lower() == "none" else float(_t) if _t else TEMPERATURE
# [hdmg] Claude: needed only if the API key is not scoped to a workspace
WORKSPACE_ID = os.environ.get("HDMG_WORKSPACE_ID") or None
# [hdmg] Spend guard. Prices in USD per million tokens; budget 0 = no limit.
PRICE_IN = float(os.environ.get("HDMG_PRICE_IN", "0"))
PRICE_OUT = float(os.environ.get("HDMG_PRICE_OUT", "0"))
BUDGET_USD = float(os.environ.get("HDMG_BUDGET_USD", "0"))
SPENT_USD = 0.0
# [hdmg] Outer-loop stopping rule. The paper stops on the HIDDEN tests ("hidden").
# "public" stops on the given tests only (deployable). "both" runs until both rules
# have fired (or the budget ends) so either metric can be computed from one run.
STOP_ON = os.environ.get("HDMG_STOP_ON", "both")
# [hdmg] Cap the outer loop (paper: 10)
MAX_OUTER_RETRY = int(os.environ.get("HDMG_MAX_OUTER_RETRY", MAX_OUTER_RETRY))
# [hdmg] Per-LLM-call JSONL log; set by main.py to <output_folder>/llm_calls.jsonl
CALL_LOG = None
# [hdmg] Context for the call log: which problem / outer attempt is running
CURRENT_TASK_ID = None
CURRENT_ATTEMPT = None

# Global statistics tracking
TOTAL_PROMPT_TOKENS = 0
TOTAL_COMPLETION_TOKENS = 0
TOTAL_MG_DEBUG_CALLS = 0
TOTAL_DEBUG_FUNCTION_CALLS = 0
TOTAL_GENERATE_TEST_CASES_CALLS = 0
TOTAL_CONVERT_HIERARCHICAL_CALLS = 0 