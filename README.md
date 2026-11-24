# Hypothesis-Driven MGDebugger

CSC 591 project. Keeps MGDebugger's hierarchical recursion (Shi et al., ICSE '26) and replaces
its LLM-simulated execution with a hypothesis -> prediction -> real observation loop (variant C).
Variants L and L2 drop the decomposition entirely and localize the bug with breakpoints on real
execution. On HumanEvalFix with Claude Haiku 5.5, L2 repairs 98.7% of detectable bugs (MGDebugger:
96.6%) at one tenth of MGDebugger's token cost.

## Layout

```
MGDebugger/          YerbaPage/MGDebugger @ 3e9dc4f (MIT) with small patches, all marked [hdmg]
                     the second commit in this repo's history is exactly our diff against upstream
hdmg/tracer.py       records chosen variables of one function while it runs (sys.settrace)
hdmg/tracer.py       also BreakpointTracer: evaluates expressions at chosen lines on every hit
hdmg/sandbox.py      runs code in a child process with timeout + memory cap; run_call, run_traced,
                     run_breakpoints
hdmg/hypothesis_loop.py  variant C at one node: hypothesis -> real run -> harness verdict -> fix
hdmg/localize.py     variant L: breakpoints with expected values -> real run -> first divergence -> fix
hdmg/mg_adapter.py   plugs the loop into MGDebugger's recursion (debug_function_hypothesis)
hdmg/compare.py      value comparison shared by MGDebugger's fixed harness and the loop's verdict
hdmg/public_tests.py parses given tests (incl. round(...), "is None", helper calls in arguments)
data/clean/          cleaned seeds: structured public tests, detectable flag (scripts/clean_data.py)
tests/               pytest for tracer, sandbox, the loop, the adapter, the harness, mg_debug end to end
scripts/
  run_experiment.sh  one variant on a cleaned dataset, parallel shards, merged + summarized
  compare_runs.py    any two runs (A, C, L) on the same problems: repairs, paired McNemar test, cost
                     by stage, bug types, loop stats
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
python -m pytest -q tests            # 87 tests, ~10 s
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

## Running variant L (breakpoint localization)

A vs C showed that about 80% of MGDebugger's cost is localization machinery: decomposing the program
(~13%) and asking the LLM to write tests for every subfunction (~67%). Variant L replaces all of it:

1. Run the public tests. If one fails, show the LLM the **numbered** program and that failing test.
2. The LLM places 1-3 breakpoints: a line, an expression (`total`, `len(stack)`, `s[i:]`), and the values the
   **correct** program would show on successive hits.
3. The sandbox runs the failing test with those breakpoints (`run_breakpoints`; values are taken before the
   line runs, once per loop iteration or recursive call). The earliest hit whose real value differs from the
   expected one is where the program first goes wrong.
4. The LLM rewrites the function containing that line (or the helper the wrong value came from), quoting the
   evidence ("at line 9, `suffix_start` should be 1 on hit #1 but was 3"). The fix must pass every public test.
5. A round where everything matched, or a fix that failed, goes into memory for the next round
   (`HDMG_K`, default 3 rounds per attempt).

Expressions are checked before they run (variables, operators, indexing, comprehensions, and a whitelist
of pure calls like `len`, `sorted`, `s.count`), so a breakpoint cannot change the program's state.
Everything else (outer attempts, scoring, harness, budget) is the same pipeline as A and C.

```
bash scripts/run_experiment.sh mock humanevalfix L 2 3               # wiring check, no model needed
HDMG_RUN_BUDGET_USD=2 bash scripts/run_experiment.sh claude humanevalfix L 4
python3 scripts/compare_runs.py MGDebugger/src/output_data/experiments/humanevalfix_A_<ts> \
                                MGDebugger/src/output_data/experiments/humanevalfix_L_<ts> \
                                --out results/al_humanevalfix.md
```

**Variant L2** (`HDMG_VARIANT=L2`) targets L's main miss, a bug inside a `return` expression, where every
value before the line is correct and the model, free to write any expression, wrote the correct formula and
saw it match. Three changes: (1) observe, don't recompute: an expression must be a value the program holds
(variable, element, slice, `len` of it) or a piece of the program's own code on that line, copied; (2) when
every round matched, one more fix call gets the matched values as evidence that the bug comes after them;
(3) a fix that makes more public tests pass without breaking any is kept, and the next round localizes the
next failing test, so a program with several bugs can be repaired one at a time.
In L's run, 116 of the 217 breakpoints in fully matched rounds were the model's own formulas, which L2 rejects
(versus 24 of 176 in rounds that found the bug).

```
HDMG_RUN_BUDGET_USD=2 bash scripts/run_experiment.sh claude humanevalfix L2 4
```

L2 is also checked on bug sets that played no part in its design (HumanEval with DeepSeek and StarCoder
seeds, MBPP with DeepSeek seeds); the plan, written before those runs, is `results/heldout_plan.md`:

```
bash scripts/run_heldout.sh        # about 1.5 h, about $4; safe to run again if interrupted
```

If a run is cut off (closed terminal, crash), resume it: only the problems no shard finished are run again.
`HDMG_RESUME=MGDebugger/src/output_data/experiments/<run> bash scripts/run_experiment.sh claude humanevalfix L 4`

An L run writes `hypothesis_nodes.jsonl` with one `"type": "localize"` line per attempt (every round, its
breakpoints, the real hits, the divergence and the fix outcome); its LLM calls are stages `localize` and `fix`.

`pytest tests` runs the MGDebugger end-to-end tests only when its requirements (loguru, openai) are installed.

## Status

- Week 1 (reproduction, findings): `results/week1_notes.md`
- Data cleaning: `results/data_cleaning.md`
- Hypothesis loop, MGDebugger integration, live demo: done (variant C)
- Harness fixes, parallel runner, A vs C comparison: done
- **Held-out check of L2 (HumanEval with DeepSeek and StarCoder bugs, MBPP): cost advantage general
  (8x cheaper), accuracy advantage not.** Pooled over 224 held-out bugs A repairs 193, L2 181 (p = 0.065).
  Main cause found: given tests compared by value, not with the assert's `==` (tuple vs list, MBPP);
  post-hoc rerun with `HDMG_EXACT_TESTS=1` pending. `results/experiment_findings.md`, `results/heldout_*.md`.
- **Variant L2 (observe-only breakpoints): as accurate as MGDebugger at one tenth of the cost (HumanEvalFix).** 149 of 151
  repaired (replicate: 150), $0.0010 per repair vs A's $0.0102; on the 148 paired problems A 143, L2 146
  (p = 0.45, replicate 147, p = 0.22). See `results/experiment_findings.md` and `results/al2_humanevalfix.md`.
- **Variant L (breakpoint localization, no decomposition): 6x cheaper, 85% vs 97% repaired.** $0.0019 per
  repair vs A's $0.0102; 129 of 151 repaired. 20 of its 22 misses are bugs inside a `return` expression,
  which a breakpoint taken before the line cannot see; on all other bugs it repairs 80 of 82, as many as C.
  See `results/experiment_findings.md`, `results/al_humanevalfix.md`, `results/cl_humanevalfix.md`.
- **A vs C on HumanEvalFix (Claude Haiku 5.5, 151 bugs): no measurable difference.** 143 vs 144 repaired
  of the 148 both runs completed (McNemar p = 1.0), C at about 4% higher cost; a third of repairs come
  from the decomposition rewrite alone. See `results/experiment_findings.md` and `results/ab_humanevalfix.md`.
