# Hypothesis-Driven MGDebugger

CSC 591 project. Keeps MGDebugger's hierarchical recursion (Shi et al., ICSE '26) and replaces
its LLM-simulated execution with a hypothesis -> prediction -> real observation loop.

## Layout

```
MGDebugger/          YerbaPage/MGDebugger @ 3e9dc4f (MIT) with small patches, all marked [hdmg]
                     the second commit in this repo's history is exactly our diff against upstream
hdmg/tracer.py       records chosen variables of one function while it runs (sys.settrace)
hdmg/sandbox.py      runs code in a child process with timeout + memory cap; run_call, run_traced
hdmg/hypothesis_loop.py  variant C at one node: hypothesis -> real run -> harness verdict -> fix
hdmg/mg_adapter.py   plugs the loop into MGDebugger's recursion (debug_function_hypothesis)
hdmg/compare.py      value comparison shared by MGDebugger's fixed harness and the loop's verdict
hdmg/public_tests.py parses given tests (incl. round(...), "is None", helper calls in arguments)
data/clean/          cleaned seeds: structured public tests, detectable flag (scripts/clean_data.py)
tests/               pytest for tracer, sandbox, the loop, the adapter, the harness, mg_debug end to end
scripts/
  run_experiment.sh  one variant on a cleaned dataset, parallel shards, merged + summarized
  compare_runs.py    A vs C on the same problems: repairs, paired McNemar test, cost, bug types, loop stats
  clean_data.py      builds data/clean/ and results/data_cleaning.md
  run_variant_a.sh   one run on the original seeds + summary                  [Linux / WSL]
  run_variant_a.ps1  same for Windows PowerShell
  backend_env.sh     model backends (claude, mistral, vllm, ollama, openai, mock)
  merge_runs.py      merges shard folders (used by run_experiment.sh)
  summarize.py       accuracy, RSR (two scoring rules), tokens and calls per stage
  seed_audit.py      how many "buggy" seeds already pass all public tests
  mock_llm_server.py fake OpenAI-compatible server for wiring tests (no model)
live_demo.py         class demo: the loop at one function, then inside MGDebugger's tree
results/             data cleaning report, notes, A vs C comparisons
```

## Setup

Python 3.10+. Tested on Linux; use WSL on Windows. The PowerShell script and native Windows are untested.

```
pip install -r requirements.txt
python -m pytest -q tests            # 63 tests, ~10 s
bash scripts/run_experiment.sh mock humanevalfix C 2 2   # wiring check, no model needed
```

## The A vs C experiment

```
python3 scripts/check_key.py                                   # key in key/apikey.txt
HDMG_RUN_BUDGET_USD=1 bash scripts/run_experiment.sh claude humanevalfix A 4 3   # pilot: 12 problems
HDMG_RUN_BUDGET_USD=1 bash scripts/run_experiment.sh claude humanevalfix C 4 3
python3 scripts/compare_runs.py MGDebugger/src/output_data/experiments/humanevalfix_A_<ts> \
                                MGDebugger/src/output_data/experiments/humanevalfix_C_<ts> \
                                --out results/ab_humanevalfix_pilot.md
```

Drop the last argument (problems per shard) for the full run. A and C can run at the same time in two
terminals. Both use the same pipeline, seeds, model and harness; only the debug step at a failing
function differs. Defaults: fixed harness, undetectable bugs skipped, 2 outer attempts, $5 per run
(`HDMG_RUN_BUDGET_USD`, split across shards), retries back off exponentially on API errors.

**Data cleaning** (`results/data_cleaning.md`): every given test is parsed, including the forms MGDebugger
drops or crashes on (HumanEval/12, /32, /38, /90 in HumanEvalFix), and bugs the given tests cannot detect
are flagged: 13 of 164 in HumanEvalFix, 6 of 38 in HumanEval (DeepSeek seeds).

**Harness** (`HDMG_HARNESS`, default `fixed`; `published` keeps MGDebugger's method):
test results are compared by value ((1, 2) equals [1, 2], float tolerance, `round(f(x), n)` tests),
gold tests come from the cleaned seeds, and the top-level function is tested on the gold tests instead of
LLM-re-derived ones (the HumanEval/54 failure).

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

## Running variant C (hypothesis loop)

Same pipeline, same scripts; only the debug step at a failing function changes.

```
HDMG_VARIANT=C bash scripts/run_variant_a.sh mock humaneval 3      # wiring check, no model needed
HDMG_VARIANT=C bash scripts/run_variant_a.sh claude humanevalfix 5
```

MGDebugger still decomposes, derives tests and finds the failing function bottom-up. At that function
`mg_debugger.py` calls `hdmg.mg_adapter.debug_function_hypothesis` instead of `debug_function`: the LLM
proposes a hypothesis and predicts variable values, the sandbox runs the code and records them, and only a
confirmed hypothesis may drive a fix, which must pass the node's tests. If no fix comes out of the loop, the
function is left as it is (pure C: MGDebugger's simulated-trace `debug_function` is never called, so every C fix
comes from a confirmed hypothesis). Settings: `HDMG_K` (3 hypotheses per debug attempt), `HDMG_SANDBOX_TIMEOUT`
(5 s). A C run also writes `hypothesis_nodes.jsonl` (one line per debug call, with every round), and its LLM
calls appear in `llm_calls.jsonl` as stages `hypothesis` and `fix`.

The project compares A and C only, on the same pipeline, seeds and budget.

`pytest tests` runs the MGDebugger end-to-end tests only when its requirements (loguru, openai) are installed.

## Status

- Week 1 (reproduction, findings): `results/week1_notes.md`
- Data cleaning: `results/data_cleaning.md`
- Hypothesis loop, MGDebugger integration, live demo: done (variant C)
- Harness fixes, parallel runner, A vs C comparison: done; results go in `results/ab_*.md`
