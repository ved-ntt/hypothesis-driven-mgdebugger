import time
import json
import inspect
from openai import OpenAI
from loguru import logger
from config import MODEL, LLM_BASE_URL, LLM_API_KEY, MAX_VLLM_RETRIES, RETRY_DELAY, TEMPERATURE, MINP
import config

client = OpenAI(
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    # [hdmg] Claude keys not scoped to a workspace need this header
    default_headers={"anthropic-workspace-id": config.WORKSPACE_ID} if config.WORKSPACE_ID else None,
)


class BudgetExceeded(BaseException):  # not Exception: upstream code catches Exception broadly
    """[hdmg] Raised before a call once HDMG_BUDGET_USD has been spent."""


def budget_left():
    return config.BUDGET_USD <= 0 or config.SPENT_USD < config.BUDGET_USD


_STAGES = {
    "convert_to_hierarchical": "decompose",
    "generate_test_cases": "derive_tests",
    "debug_function": "debug",
}


def _caller_stage():
    """[hdmg] Name the pipeline stage that made this LLM call."""
    for frame in inspect.stack()[2:8]:
        if frame.function in _STAGES:
            return _STAGES[frame.function]
        if frame.function.startswith("hdmg_"):
            return frame.function[len("hdmg_"):]
    return "other"


def _log_call(record):
    """[hdmg] Append one JSON line per LLM call."""
    if config.CALL_LOG:
        with open(config.CALL_LOG, "a") as f:
            f.write(json.dumps(record) + "\n")


def get_completion_with_retry(messages, model=MODEL, max_retries=MAX_VLLM_RETRIES):
    """Get completion from LLM with retry mechanism"""
    if not budget_left():
        raise BudgetExceeded(f"spent ${config.SPENT_USD:.2f} of ${config.BUDGET_USD:.2f}")
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting LLM call (attempt {attempt + 1}/{max_retries})")
            logger.info(f"Input messages: {messages[-1]['content']}")
            t0 = time.time()
            kwargs = dict(messages=messages, model=model)
            if config.TEMPERATURE is not None:
                kwargs["temperature"] = config.TEMPERATURE
            if config.USE_MIN_P:
                kwargs["extra_body"] = {"min_p": MINP}
            chat_completion = client.chat.completions.create(**kwargs)
            response = chat_completion.choices[0].message.content
            logger.info(f"LLM response: {response}")
            logger.info("LLM call received")

            # Update token counts
            config.TOTAL_PROMPT_TOKENS += chat_completion.usage.prompt_tokens
            config.TOTAL_COMPLETION_TOKENS += chat_completion.usage.completion_tokens

            cost = (chat_completion.usage.prompt_tokens * config.PRICE_IN
                    + chat_completion.usage.completion_tokens * config.PRICE_OUT) / 1e6
            config.SPENT_USD += cost

            _log_call({
                "task_id": config.CURRENT_TASK_ID,
                "attempt": config.CURRENT_ATTEMPT,
                "stage": _caller_stage(),
                "model": model,
                "prompt_tokens": chat_completion.usage.prompt_tokens,
                "completion_tokens": chat_completion.usage.completion_tokens,
                "latency_s": round(time.time() - t0, 3),
                "retries_before_success": attempt,
                "cost_usd": round(cost, 6),
                "ok": True,
            })

            return response
        except Exception as e:
            logger.error(f"LLM call failed: {str(e)}")
            cost = (chat_completion.usage.prompt_tokens * config.PRICE_IN
                    + chat_completion.usage.completion_tokens * config.PRICE_OUT) / 1e6
            config.SPENT_USD += cost

            _log_call({"task_id": config.CURRENT_TASK_ID, "attempt": config.CURRENT_ATTEMPT,
                       "stage": _caller_stage(), "model": model, "ok": False, "error": str(e)[:300]})
            if attempt < max_retries - 1:
                # [hdmg] exponential backoff (2, 4, 8 ... capped at 60 s) so parallel shards that hit a
                # rate limit wait instead of spending all retries in a second; upstream: RETRY_DELAY = 0
                delay = max(RETRY_DELAY, min(60.0, config.RETRY_BACKOFF * 2 ** attempt)) \
                    if config.RETRY_BACKOFF > 0 else RETRY_DELAY
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error("Max retries reached. Giving up.")
                raise 