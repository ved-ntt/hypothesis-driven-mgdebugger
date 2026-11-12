# Hypothesis-Driven MGDebugger

CSC 591 project. Keeps MGDebugger's hierarchical recursion (Shi et al., ICSE '26) and replaces
its LLM-simulated execution with a hypothesis -> prediction -> real observation loop.

## Layout

```
MGDebugger/          YerbaPage/MGDebugger @ 3e9dc4f (MIT) with small patches, all marked [hdmg]
                     the second commit in this repo's history is exactly our diff against upstream
hdmg/tracer.py       records chosen variables of one function while it runs (sys.settrace)
hdmg/sandbox.py      runs code in a child process with timeout + memory cap; run_call, run_traced
tests/               pytest for tracer and sandbox (incl. the palindrome example from the deck)
scripts/
  run_variant_a.sh   run variant A (MGDebugger as published) + summary   [Linux / WSL]
  run_variant_a.ps1  same for Windows PowerShell
  summarize.py       accuracy, RSR (two scoring rules), tokens and calls per stage
  seed_audit.py      how many "buggy" seeds already pass all public tests
  mock_llm_server.py fake OpenAI-compatible server for wiring tests (no model)
results/             audit output, run summaries, notes
```

## Setup

Python 3.10+. Tested on Linux; use WSL on Windows. The PowerShell script and native Windows are untested.

```
pip install -r requirements.txt
python -m pytest -q tests            # 15 tests, ~3 s
bash scripts/run_variant_a.sh mock humaneval 3    # wiring check, no model needed
```

## Running variant A (the Week 1 reproduction)

The model runs behind any OpenAI-compatible endpoint. Pick one:

| Backend | Start it | Run |
|---|---|---|
| Claude Haiku 5.5 (API credits) | key in `key/apikey.txt`; check with `python scripts/check_key.py` | `scripts/run_variant_a.sh claude humaneval 5` |
| Mistral Codestral (free tier) | key in `key/mistral.txt` | `scripts/run_variant_a.sh mistral humaneval 5` |
| vLLM on a GPU (paper setup) | `python -m vllm.entrypoints.openai.api_server --model deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct --trust-remote-code --api-key token-abc123s --port 18889` | `scripts/run_variant_a.sh vllm humaneval` |
| Ollama (local, 4-bit) | `ollama pull deepseek-coder-v2:16b` | `scripts/run_variant_a.sh ollama humaneval` |
| OpenAI API | `export HDMG_API_KEY=sk-...` | `scripts/run_variant_a.sh openai humaneval` |

Add a number to limit problems, e.g. `... humaneval 5`, for a quick first run.
Each run writes to `MGDebugger/src/output_data/<dataset>/.../<timestamp>/`:
`all_info.log`, `params.json`, `llm_calls.jsonl` (one line per LLM call), the per-problem
results jsonl (with per-attempt public/hidden pass and tokens), and `summary.txt`.

Settings (env vars): `HDMG_MODEL`, `HDMG_BASE_URL`, `HDMG_API_KEY`, `HDMG_TEMPERATURE` (0.8),
`HDMG_USE_MIN_P` (vLLM only), `HDMG_MAX_OUTER_RETRY` (10), `HDMG_STOP_ON` (`both` | `hidden` | `public`),
`HDMG_BUDGET_USD` (stop the run at this spend; `claude` backend defaults to $1), `HDMG_PRICE_IN` / `HDMG_PRICE_OUT`
(USD per million tokens, for the spend estimate), `HDMG_WORKSPACE_ID` (only for a Claude key not scoped to a workspace).

Claude note: models after Claude 4.7 reject temperature < 1 on the OpenAI-compatible endpoint, so the `claude`
backend omits temperature (samples at 1.0, vs the paper's 0.8). `key/` is gitignored.

Only the vLLM + DeepSeek-Coder-V2-Lite run is directly comparable to the paper's Table 1
(the seeds in the repo come from that model). Ollama serves a 4-bit quantization of the same
model, so expect some gap. An API model gives a valid A-vs-C comparison but not a paper match.

## Status

Week 1: see `results/week1_notes.md`.
