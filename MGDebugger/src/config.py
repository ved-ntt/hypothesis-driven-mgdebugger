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
# [hdmg] Debug step at a failing node. "A": MGDebugger as published (LLM-simulated trace).
# "C": the hypothesis loop (hdmg/mg_adapter.py). Everything else in the pipeline is identical.
# "L": no decomposition and no derived tests: the LLM places breakpoints on the whole program, the
# sandbox records real values, the first divergence localizes the bug, then one function is fixed
# (hdmg/localize.py). It replaces mg_debug in debug_pipeline; the outer loop and scoring are unchanged.
VARIANT = os.environ.get("HDMG_VARIANT", "A").strip().upper()
# "D": L with observe-only breakpoints, a fix after a full match and kept partial progress
# (hdmg/localize.py, observe=True). Called "L2" during development; "L2" is still accepted.
if VARIANT == "L2":
    VARIANT = "D"
if VARIANT not in ("A", "C", "L", "D"):
    raise ValueError(f"HDMG_VARIANT must be A, C, L or D, got {VARIANT!r}")
# [hdmg] Variant C: hypotheses per debug attempt; variant L: localize -> fix rounds per attempt.
# Seconds per sandbox run (both). Pure C: no fallback to
# debug_function, so every C fix comes from a confirmed hypothesis.
HYPOTHESIS_K = int(os.environ.get("HDMG_K", "3"))
SANDBOX_TIMEOUT = float(os.environ.get("HDMG_SANDBOX_TIMEOUT", "5"))
# [hdmg] Variant C per-node / variant L per-attempt JSONL log; set by main.py to <output_folder>/hypothesis_nodes.jsonl
HYPOTHESIS_LOG = None
# [hdmg] Test harness. "fixed" (default) for every variant: compare test results by value (tuple vs
# list, float tolerance) instead of repr strings; take the gold tests from the cleaned seeds'
# public_tests (scripts/clean_data.py), which reads the round(...) and "is None" asserts upstream
# drops; test the top-level function on those gold tests instead of LLM-re-derived ones.
# "published" keeps MGDebugger's method exactly. (In both modes a test that times out is logged
# as a failure; upstream crashed there with a NameError.)
HARNESS = os.environ.get("HDMG_HARNESS", "fixed").strip().lower()
if HARNESS not in ("fixed", "published"):
    raise ValueError(f"HDMG_HARNESS must be fixed or published, got {HARNESS!r}")
# [hdmg] Skip problems whose buggy code passes every given test ("detectable": false in the cleaned
# seeds): no debugger that sees only the given tests can find those bugs.
ONLY_DETECTABLE = os.environ.get("HDMG_ONLY_DETECTABLE", "1") == "1"
# [hdmg] Exact given tests (fixed harness): the value comparison treats (1, 2) and [1, 2] as equal, but
# the benchmark's own asserts use Python's ==. With HDMG_EXACT_TESTS=1 a given test passes only if its
# assert passes, and L / D prompts show the expected value as the assert writes it. Off by default so
# earlier runs stay reproducible; matters on MBPP, whose functions often return tuples.
EXACT_TESTS = os.environ.get("HDMG_EXACT_TESTS", "0") == "1"
CURRENT_PUBLIC_TESTS = None
# [hdmg] Retry backoff for failed LLM calls (rate limits when shards run in parallel), seconds
RETRY_BACKOFF = float(os.environ.get("HDMG_RETRY_BACKOFF", "2"))
# [hdmg] Run one shard of the problems: (index, count), set by main.py --shard i/N
SHARD = None
# [hdmg] Entry point of the problem being debugged; mg_debug tests it on the gold tests
CURRENT_ENTRY_POINT = None

# [hdmg] The repo root, so MGDebugger can import hdmg (shared comparison, hypothesis loop)
import sys as _sys
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in _sys.path:
    _sys.path.append(_ROOT)

# Global statistics tracking
TOTAL_PROMPT_TOKENS = 0
TOTAL_COMPLETION_TOKENS = 0
TOTAL_MG_DEBUG_CALLS = 0
TOTAL_DEBUG_FUNCTION_CALLS = 0
TOTAL_GENERATE_TEST_CASES_CALLS = 0
TOTAL_CONVERT_HIERARCHICAL_CALLS = 0 