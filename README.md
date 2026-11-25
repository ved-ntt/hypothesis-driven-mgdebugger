# Hypothesis-Driven MGDebugger

CSC 591 project, NC State University, Fall 2026. Paper: [`paper/paper.pdf`](paper/paper.pdf) (2 pages).

LLM debuggers usually *imagine* what code does. MGDebugger (Shi et al., ICSE 2026) splits a buggy program into a
tree of subfunctions, writes tests for each one, and asks the model to simulate execution step by step to find
the bug. We replace imagined execution with **measured** execution: the model states what it expects to see,
the program really runs, and only what the run confirms is used to fix the code.

We built two variants and compare them with MGDebugger (A):

| Variant | Idea | HumanEvalFix repaired | Cost per repair | LLM calls per problem |
| --- | --- | --- | --- | --- |
| **A** MGDebugger (baseline) | decompose, write tests per subfunction, simulate execution | 143 / 148 | $0.0102 | 10.8 |
| **C** Hypothesis loop | A's tree, but each failing function is debugged by hypothesis, prediction and a real run | 147 / 151 | $0.0105 | 13.6 |
| **D** Breakpoint localization | no tree: breakpoints with expected values, one real run, fix where the first value differs | **149 / 151** | **$0.0010** | **2.3** |

Claude Haiku 5.5, 151 detectable HumanEvalFix bugs, 2 outer attempts. **C matches MGDebugger** (144 vs 143 on the
148 problems both completed, p = 1.0). **D matches or beats MGDebugger at a tenth of the cost**, and on 224 bugs
from three held-out sets it stays 6 to 15 times cheaper without losing accuracy (Section 3).

Contents: [1 Problem](#1-the-problem) · [2 Method](#2-method) · [3 Results](#3-results) ·
[4 Reproduce](#4-reproduce) · [5 Repository layout](#5-repository-layout) ·
[6 Engineering details](#6-engineering-details) · [7 Limitations](#7-limitations)

## 1. The problem

MGDebugger has two weaknesses we target.

1. **Its execution traces are imagined.** The model "runs" the code in its head and reports variable values.
   Nothing checks those values, so a wrong trace leads straight to a wrong fix.
2. **Its localization is expensive.** Decomposing the program and writing tests for every subfunction take about
   80% of its tokens on HumanEvalFix (decompose 12%, derive tests 66%).

Scientific debugging (Zeller, *Why Programs Fail*) offers a different loop: hypothesis, prediction, experiment,
and accept only what the experiment confirms.

## 2. Method

### C: hypothesis loop inside MGDebugger's tree

MGDebugger still decomposes the program and finds the failing subfunction bottom-up. At that function, C
replaces the simulated trace with this loop (up to 3 rounds):

1. The model proposes a hypothesis, e.g. *"the loop starts at index 1, so the first suffix is skipped"*, and
   predicts the values some variables will take: `{"i": [1, 2, 3]}`.
2. The function runs on the failing test in a sandbox; a tracer records the real values of those variables.
3. The **harness**, not the model, compares prediction and observation: confirmed or rejected.
4. Only a confirmed hypothesis may drive a fix, and the fix must pass the function's tests. Rejected
   hypotheses are remembered so the next round tries something else.

Code: `hdmg/hypothesis_loop.py` (the loop), `hdmg/mg_adapter.py` (plugs it into MGDebugger), `hdmg/tracer.py`.

### D: breakpoint localization, no tree

D drops decomposition and generated tests. For a failing given test:

1. The model sees the program **with line numbers** and places 1 to 3 breakpoints. Each is a line, an
   expression, and the values that expression should have each time the line is reached *if the program were
   correct*: `{"line": 9, "expr": "suffix_start", "expect": [1]}`.
2. One sandboxed run records the real values, taken just before each line executes (once per loop iteration
   or recursive call).
3. The earliest real value that differs from the expected one localizes the bug: *"at line 9, `suffix_start`
   should be 1 but was 3"*.
4. The model rewrites only the function containing that line, given that evidence. The fix must pass every
   given test.

Three rules make this work:

| Rule | Why |
| --- | --- |
| **Observe, don't recompute.** An expression must read program state (variable, element, slice, `len`) or copy the program's own code on that line. | Otherwise the model writes the *correct* formula as the expression, which always matches and finds nothing. This was the main failure of D's first version (L): 20 of its 22 misses. |
| **A full match is evidence.** If every breakpoint matches but the output is wrong, one fix attempt is told the bug comes after those points. | The bug is localized even without a mismatch. |
| **Keep partial progress.** A fix that makes more given tests pass, without breaking any, becomes the program for the next round. | Programs with several bugs can be fixed one bug at a time. |

Code: `hdmg/localize.py` (the loop and rules), `hdmg/tracer.py` (`BreakpointTracer`), `hdmg/sandbox.py`
(`run_breakpoints`). D was called **L2** during development; run folders under `results/runs/` keep that name.

## 3. Results

All numbers: Claude Haiku 5.5, temperature 1.0, 2 outer attempts, bugs the given tests can detect.
"Repaired" means the first attempt that passes the given tests also passes the hidden tests. Variants are
compared on the same problems with an exact McNemar test. Full analysis: [`results/experiment_findings.md`](results/experiment_findings.md).

### HumanEvalFix (151 bugs)

| | A | C | L (D without rules 1, 2) | D |
| --- | --- | --- | --- | --- |
| Repaired | 143 / 148 | 147 / 151 | 129 / 151 | 149 / 151 (repeat runs: 150, 150) |
| Cost per repair | $0.0102 | $0.0105 | $0.0019 | $0.0010 |
| Tokens per problem | 28,760 | 33,035 | 5,866 | 3,573 |
| Bugs inside a `return` expression (66) | 65 | 64 | 46 | 65 |
| All other bugs (82) | 78 | 80 | 80 | 81 |

- **C vs A:** 144 vs 143 on 148 shared problems, p = 1.0. 28% of C's hypotheses were refuted by the real run
  before any fix was written. MGDebugger's decomposition step alone produced about a third of all repairs, so
  this benchmark leaves little room to separate the debug steps.
- **D vs A:** 146 vs 143 on 148 shared problems (p = 0.45); repeat runs 147 vs 143 (p = 0.22). D's first round
  finds the bug in 82% of attempts, and once a mismatch is found, the fix passed every time (149 of 149).

Reports: [`a_vs_c`](results/a_vs_c_humanevalfix.md), [`a_vs_d`](results/a_vs_d_humanevalfix.md),
[`c_vs_d`](results/c_vs_d_humanevalfix.md), [`l_vs_d`](results/l_vs_d_humanevalfix.md),
[`a_vs_l`](results/a_vs_l_humanevalfix.md), [`d_replicate`](results/d_replicate_humanevalfix.md).

### Held-out check of D (224 bugs never used in D's design)

D was frozen and the evaluation plan written ([`results/heldout_plan.md`](results/heldout_plan.md)) before these runs.
The bugs are wrong solutions written by code models, not hand-planted ones.

| Set | A | D | A costs |
| --- | --- | --- | --- |
| HumanEval, DeepSeek-Coder bugs | 31 / 32 | 30 / 32 | 9.4x D |
| HumanEval, StarCoder bugs | 85 / 88 | 81 / 88 | 8.0x D |
| MBPP, DeepSeek-Coder bugs | 77 / 104 | 70 / 104 | 6.6x D |
| MBPP, with exact test checks (post-hoc) | 69 / 104 | **89 / 104** | 14.8x D |
| **Pooled, as planned** | **193** | **181** (p = 0.065) | |
| **Pooled, exact checks on MBPP** | **193** | **200** (p = 0.27) | |

- The cost advantage held on every set.
- Most of the planned gap came from a harness defect found on MBPP: comparing results by value treats a list and
  a tuple as equal, so D accepted fixes that the benchmark's own `assert` rejects. With exact checks
  (`HDMG_EXACT_TESTS=1`), added after seeing these results and reported as such, D repairs 89 of 104 MBPP bugs,
  more than either A run (p = 0.017 against A's better run).

Reports: `results/heldout_*.md`.

## 4. Reproduce

### 4.1 Requirements

- Python 3.10 or newer on Linux. On Windows, use WSL (tested on Ubuntu in WSL; native Windows is untested).
- `pip install -r requirements.txt` (openai, loguru, tqdm, numpy, pytest).

```
git clone https://github.com/ved-ntt/hypothesis-driven-mgdebugger
cd hypothesis-driven-mgdebugger
pip install -r requirements.txt
```

### 4.2 Without an API key (free, about 5 minutes)

```
bash scripts/reproduce.sh smoke
```

This runs the 98 unit and integration tests, then runs A, C and D end to end on 4 HumanEvalFix problems against
a mock model (`scripts/mock_llm_server.py`). Expected ending:

```
98 passed in 15s
Variant: A
Dataset: humanevalfix  seeds from: deepseekcoder  problems: 164  buggy: 151  debugged so far: 4
...
Variant: D  k=3  sandbox timeout=5.0 s
Dataset: humanevalfix  seeds from: deepseekcoder  problems: 164  buggy: 151  debugged so far: 4
public-selection                   4    100.0      nan             656
smoke test passed (mock model: the repair numbers mean nothing, only that the pipeline runs)
```

To see C's loop step by step with scripted model replies (no key): `python3 live_demo.py --scripted`.

To re-derive every table in Section 3 from the committed results, read `results/*.md`; each report states the
run folders it came from, and `results/runs/` holds each run's settings (`params.json`) and summary.

### 4.3 With the Claude API

1. Put an Anthropic API key in `key/apikey.txt` (the `key/` folder is gitignored; never commit it).
2. Check it (costs well under $0.001): `python3 scripts/check_key.py`
3. Run the experiments:

| Command | What it runs | Time | Cost |
| --- | --- | --- | --- |
| `bash scripts/reproduce.sh humanevalfix` | A, C, D on HumanEvalFix, in parallel | about 1 h | about $3.50 |
| `bash scripts/reproduce.sh heldout` | A and D on the 3 held-out sets | about 1.5 h | about $3.50 |
| `HDMG_EXACT_TESTS=1 bash scripts/reproduce.sh heldout` | same, with exact given-test checks | about 1.5 h | about $4.50 |

Reports are written to `results/repro/` (for example `humanevalfix_A_vs_D.md`), runs to
`MGDebugger/src/output_data/experiments/`. Keep the terminal open and the machine awake. If a run is
interrupted, run the same command again: finished runs are reused and unfinished ones resume where they stopped.

One variant on one dataset:

```
bash scripts/run_experiment.sh claude humanevalfix D 4        # backend, dataset, variant, parallel shards
python3 scripts/compare_runs.py MGDebugger/src/output_data/experiments/humanevalfix_A_<time> \
                                MGDebugger/src/output_data/experiments/humanevalfix_D_<time> --out results/my_a_vs_d.md
```

Datasets: `humanevalfix`, `humaneval` (DeepSeek-Coder seeds), `humaneval_starcoder`, `mbpp_deepseekcoder`.
Variants: `A`, `C`, `D`, and `L` (D's first version). A fifth argument limits problems per shard for a quick
trial, e.g. `... humanevalfix D 4 3` runs 12 problems.

### 4.4 Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `HDMG_RUN_BUDGET_USD` | 5 | stop a run at this spend (split across shards); unfinished problems are left out of scoring |
| `HDMG_MAX_OUTER_RETRY` | 2 | outer attempts per problem (the paper uses 10) |
| `HDMG_K` | 3 | rounds per attempt (C: hypotheses, D: breakpoint rounds) |
| `HDMG_SANDBOX_TIMEOUT` | 5 | seconds per sandboxed run |
| `HDMG_EXACT_TESTS` | 0 | 1: a given test passes only if its own `assert` passes (tuple is not list) |
| `HDMG_HARNESS` | fixed | `published` keeps MGDebugger's original test harness |
| `HDMG_RESUME` | | resume an interrupted run folder |
| `HDMG_MODEL` | claude-haiku-5-5 | model name for the `claude` backend |

Other backends (vLLM, Ollama, OpenAI, Mistral) are set up in `scripts/backend_env.sh`. Only vLLM with
DeepSeek-Coder-V2-Lite matches the MGDebugger paper's setup.

### 4.5 Data

The cleaned datasets are committed in `data/clean/`. To rebuild them from the original seeds (about 3 minutes,
offline): `python3 scripts/clean_data.py`, which also writes `results/data_cleaning.md`.

## 5. Repository layout

```
paper/                 paper.md, paper.pdf, build.sh (pandoc + xelatex)
hdmg/                  our code; nothing here imports MGDebugger
  tracer.py            VariableTracer (C) and BreakpointTracer (D), built on sys.settrace
  sandbox.py           child-process runner with timeout and memory cap: run_call, run_traced, run_breakpoints
  hypothesis_loop.py   C at one function: hypothesis -> real run -> harness verdict -> fix
  mg_adapter.py        plugs C into MGDebugger's bottom-up recursion
  localize.py          D (and L): breakpoints -> real run -> first divergence -> fix
  compare.py           value comparison (tuple vs list, float tolerance, round(...) tests)
  public_tests.py      parses given asserts into structured tests
MGDebugger/            upstream YerbaPage/MGDebugger @ 3e9dc4f (MIT); our patches are marked [hdmg]
data/clean/            cleaned datasets: structured given tests, detectable / usable flags
tests/                 98 pytest tests: tracer, sandbox, C's loop, D's loop and rules, harness, end to end
scripts/
  reproduce.sh         smoke | humanevalfix | heldout | all
  run_experiment.sh    one variant on one dataset, parallel shards, merge, summary, resume
  compare_runs.py      two runs on the same problems: repairs, McNemar test, cost by stage, loop statistics
  clean_data.py        builds data/clean/ and results/data_cleaning.md
  summarize.py         one run: repairs under both scoring rules, tokens and calls per stage
  merge_runs.py, resume_seeds.py   used by run_experiment.sh
  backend_env.sh, check_key.py     model backends, API key check
  mock_llm_server.py   fake OpenAI-compatible model for tests and the smoke run
live_demo.py           class demo of C's loop (--scripted needs no key)
results/               findings, comparison reports, held-out plan, data cleaning, run summaries
```

## 6. Engineering details

**Harness fixes** (applied to all variants, `HDMG_HARNESS=fixed`). Found while reproducing MGDebugger:
- Test results were compared as strings, so `(1, 2)` failed against `[1, 2]` and `0.30000000000000004` against
  `0.3`. Now compared by value, with `round(f(x), n)` tests supported.
- The upstream test parser dropped or crashed on some given tests (HumanEval/12, /32, /38, /90). Our parser
  (`hdmg/public_tests.py`) keeps all 460 HumanEvalFix tests.
- A function returning a set crashed MGDebugger's debug prompt (3 problems lost in A).
- A test that timed out kept running in a thread and could exhaust memory or keep the process alive; tests
  now run in a child process with a timeout and a memory cap. Re-running all 808 recorded HumanEvalFix
  attempts this way reproduced every verdict.

**Data cleaning** (`results/data_cleaning.md`). 13 of 164 HumanEvalFix bugs pass every given test, so no debugger
that sees only those tests can find them. They are excluded, as are MBPP problems whose given test cannot be
parsed or whose reference solution fails it.

**Logging.** Every run writes `llm_calls.jsonl` (stage, tokens, cost, latency for each call) and
`hypothesis_nodes.jsonl` (for C: every hypothesis, prediction, observation and verdict; for D: every breakpoint,
the real values, the divergence and the fix outcome). `compare_runs.py` builds the reports from these.

**Statistics.** Paired comparison on problems both runs completed; exact two-sided McNemar test on discordant
problems. Two scoring rules are reported: public-selection (the deployable one, used above) and
hidden-selection (the MGDebugger paper's rule).

## 7. Limitations

- One model (Claude Haiku 5.5) at temperature 1.0. Run-to-run variation was measured only for D.
- D was designed after seeing L's failures on HumanEvalFix; the held-out check addresses this, and the exact-test
  result on MBPP is post-hoc.
- D cannot observe an empty function body, and, like A, it can overfit when the given tests are thin (MBPP has
  one per problem).
- All benchmarks are short programs. Whether MGDebugger's hierarchy helps on long programs with interacting
  bugs was not tested.
- Not comparable to the MGDebugger paper's numbers: different model, 2 attempts instead of 10, undetectable bugs
  excluded, fixed harness.

## Team

[author names]. Built on MGDebugger by Shi et al. (https://github.com/YerbaPage/MGDebugger, MIT license).
