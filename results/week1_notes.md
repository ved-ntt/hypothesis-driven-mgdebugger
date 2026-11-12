# Week 1 notes

## Done

- [x] Cloned MGDebugger (upstream commit 3e9dc4f). Seed counts match the paper exactly:
      HumanEval buggy seeds 38 / 39 / 40 (DeepSeek-Coder-V2-Lite / CodeQwen1.5 / Codestral),
      i.e. 76.8 / 76.2 / 75.6% seed accuracy; MBPP 67.2 / 67.4 / 65.4%. HumanEvalFix has 164 buggy programs.
- [x] Call logging: every LLM call -> `llm_calls.jsonl` with problem, outer attempt, stage
      (decompose / derive_tests / debug), prompt and completion tokens, latency, retries.
- [x] Per-attempt results: public-test pass, hidden-test pass, tokens, for every outer attempt.
- [x] Config from env vars; min_p made optional so OpenAI-style APIs and Ollama work.
- [x] Sandbox runner (`hdmg/sandbox.py`): child process, timeout, 512 MB cap on Linux,
      timeouts / exceptions / crashes returned as observations.
- [x] Tracer (`hdmg/tracer.py`): named variables of one function, in order, with line numbers,
      return value and exceptions; copies values so later mutation can't rewrite history;
      first-call or all-calls mode for recursion; caps on events and repr length.
- [x] 15 tests pass, incl. the deck example: `i` = [0,1,2,3] rejects H1, `suffix_start` = [0,1,3] confirms H2.
- [x] End-to-end wiring checked with a mock LLM server on HumanEval and HumanEvalFix.
- [ ] **Variant A run with a real model, compared to Table 1.** Needs a model endpoint (see README).

## Swap point for week 2

`MGDebugger/src/mg_debugger.py` calls `debug_function(fixed_code, func_name, test_cases)`
(`function_debugger.py`) for each failing node. Variants B-E replace only that call.

## Findings so far

**1. The paper's outer loop picks the winning attempt with the hidden tests.**
`debug_pipeline.py` runs up to 10 fresh attempts (temperature 0.8) and stops at the first whose
output passes `problem["test"]`, which `utils.evaluate_simple` documents as "the private test cases".
A deployed debugger cannot do this. The patched pipeline therefore records both:
- *hidden-selection* (paper's rule): fixed if any attempt passes the hidden tests;
- *public-selection*: take the first attempt that passes the given tests, grade it on hidden tests.
With `HDMG_STOP_ON=both` (default) one run gives both numbers. The token cost of each rule is
reported separately, since they stop at different attempts.

**2. 16-34% of "buggy" seeds already pass all their public tests** (`scripts/seed_audit.py`):

| Seed set | Buggy | Pass all public tests | Share |
|---|---|---|---|
| HumanEval / DeepSeek-Coder-V2-Lite | 38 | 6 | 15.8% |
| HumanEval / CodeQwen1.5 | 39 | 7 | 17.9% |
| HumanEval / Codestral | 40 | 11 | 27.5% |
| MBPP / DeepSeek-Coder-V2-Lite | 164 | 55 | 33.5% |
| MBPP / CodeQwen1.5 | 163 | 41 | 25.2% |
| MBPP / Codestral | 173 | 47 | 27.2% |

For these, derived subfunction tests pass, so MGDebugger never calls the debug step. They can
only count as "fixed" if the decomposition rewrite happens to change behavior and the hidden-test
selection picks that attempt. `summarize.py` reports how many fixes had no debug call in the
winning attempt. No variant (including ours) can diagnose these from public tests alone, so
report RSR both over all buggy seeds and over the public-detectable subset.

**3. Table 3's real-execution row does not reconcile** (from the proposal): 92.7% accuracy implies
~68% RSR, not the reported 47.4%. Variant B re-measures it.

**4. Upstream bugs noticed (left unfixed to keep the reproduction faithful):**
- `utils.evaluate`: `except TimeoutError:` logs `str(e)` with `e` undefined, so a timeout raises
  NameError instead of returning a failed test.
- `mg_debugger.mg_debug`: if all 3 decomposition attempts fail, `dependency_graph` is undefined
  and the attempt crashes (counted as unfixed).
- `timeout_utils.function_with_timeout`: a timed-out thread is not actually stopped
  (`Thread._stop` does not kill it), so infinite loops keep running in the background.
  Our sandbox kills a child process instead.

## Next

1. Run variant A on HumanEval (38 problems) with a real model; check hidden-selection RSR against
   76.3% (DeepSeek-Coder-V2-Lite). Then HumanEvalFix (164).
2. Week 2: hypothesis loop (variant C) on top of `hdmg/sandbox.run_traced`.

## Pilot: variant A, Claude Haiku 5.5, 5 HumanEval problems, 2 attempts (2026-11-03)

Run: `MGDebugger/src/output_data/humaneval/seed/deepseekcoder/20261103-153022`
(temperature omitted = 1.0; not comparable to the paper: n = 5, 2 attempts instead of 10, different model)

- Fixed 2 of 5 (HumanEval/41, /67, both on attempt 1). $0.155 total, $0.031 per problem, 145 calls,
  ~92k tokens per problem, ~8 s per call, ~20 min sequential.
- Cost is driven by `derive_tests`: Haiku decomposes into 5-19 functions per attempt and each gets
  its own test-derivation call (85 of 145 calls, 63% of tokens). Output tokens (272k) exceed input
  (186k), and output is 5x the input price.
- **Derived tests can contradict the given tests, even for the root function.** HumanEval/54: the
  given test says `same_chars('eabcdzzzz', 'dddzzzzzzzddeddabc') == True`; the LLM-derived test for
  `same_chars` itself says `False`, i.e. it matches the buggy code. All derived tests then "pass",
  the debug step is never called, and the bug survives.
  Cheap fix for all variants (B-E; A stays as published): use the given tests verbatim for the
  entry-point function instead of re-deriving them.
- **HumanEval/32: no public tests were parsed.** Its given tests are `assert round(find_zero([1, 2]), 2) == -0.5`;
  upstream `parse_tests` cannot read the `round(...)` wrapper and returns an empty list, so every derived
  test list is empty too. Nothing can fail, so the debug step never runs (0 debug calls, 13 and 19 functions).
- **HumanEval/20: tuple vs list in test comparison.** Derived tests are JSON, which has no tuples, so the
  expected `(2.0, 2.2)` is stored as `[2.0, 2.2]`. `utils.evaluate` compares `repr` strings, so any function
  returning a tuple always "fails" (`Expected [1.0, 2.0], but got (1.0, 2.0)`); exact float comparison adds
  more (`Expected 0.2, but got 0.20000000000000018`). 41 false failures, 12 functions "could not be fixed",
  and the repeated rewrites broke a seed that had passed all its public tests. Its real bug (the pair is
  not sorted) is invisible to the public tests anyway.
- Upshot: of the 3 unfixed pilot problems, none was a failure of the debugging step itself. All three are
  test-handling problems (oracle error, parser, comparison). Proposed: fix parsing and comparison (value
  equality, tuple/list normalised, float tolerance) for every variant, and report A both as published and
  with the fixed harness, so the A vs C comparison isn't driven by harness bugs.
