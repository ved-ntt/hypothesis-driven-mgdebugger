# A vs C vs L vs L2 on HumanEvalFix: findings

Run on 23 Nov 2026 with Claude Haiku 5.5 (temperature 1.0, the endpoint's minimum), 151 detectable
HumanEvalFix bugs, 2 outer attempts, fixed harness, 4 parallel shards per variant. Full report:
`ab_humanevalfix.md`; run summaries and settings: `runs/`.

## Summary

| | A: simulated trace | C: hypothesis loop | L: breakpoints | **L2: observe-only breakpoints** |
| --- | --- | --- | --- | --- |
| Repaired, public-selection (problems the run completed) | 143 / 148 (96.6%) | 147 / 151 (97.4%) | 129 / 151 (85.4%) | **149 / 151 (98.7%)**; replicate 150 / 151 |
| Cost per problem | $0.0099 | $0.0102 | $0.0016 | **$0.0010** |
| Cost per repair | $0.0102 | $0.0105 | $0.0019 | **$0.0010** |
| Tokens per problem | 28,760 | 33,035 | 5,866 | 3,573 |
| LLM calls per problem | 10.8 | 13.6 | 3.5 | 2.3 |
| Wall time (4 shards) | about 1 h | about 55 min | about 12 min | about 6 min |

- **Held-out check (section at the end): L2's cost advantage is general (6.6x to 9.4x cheaper on every
  set); its accuracy advantage is not.** On the three held-out sets pooled, A repaired 193 of 224 and L2 181
  (only A 24, only L2 12, McNemar p = 0.065). Most of the gap is on MBPP and comes from one harness
  defect, found in the check: given tests were compared by value, so a fix returning a list where the test's
  assert expects a tuple was accepted. A post-hoc rerun with exact checks is reported separately.
- **On HumanEvalFix, L2 repairs at least as many bugs as MGDebugger at one tenth of the cost.** On the 148 problems both
  completed: A 143, L2 146 (replicate 147); only A repaired 2 (1), only L2 repaired 5. The accuracy gain
  is not statistically significant (McNemar p = 0.45; replicate p = 0.22); the 9.6x cost reduction is
  the robust result, and L2 is at least as accurate.
- A and C: no measurable difference (below).
- L, the first breakpoint version, was 6x cheaper but repaired fewer bugs (p = 0.002 against A): it
  missed bugs inside a `return` expression. L2 fixes exactly that (L 46 / 66 of those bugs, L2 65 / 66).
- Every recorded hidden-test verdict of all five runs (808 attempts) was re-checked by running the
  attempt's code against the hidden tests in a fresh process: no disagreement.

## A vs C: no measurable difference in repairs

| | A: simulated trace | C: hypothesis loop |
| --- | --- | --- |
| Repaired, public-selection (148 problems both runs completed) | 143 (96.6%) | 144 (97.3%) |
| Repaired, hidden-selection (paper's rule) | 145 (98.0%) | 145 (98.0%) |
| Paired split | only A: 2 | only C: 3 (both: 141, neither: 2) |
| Exact McNemar p | 1.000 | |
| Cost per repair | $0.0102 | $0.0106 |
| LLM calls per problem | 10.8 | 13.7 |
| Wall time (4 shards) | about 1 h | about 55 min |

C repairs as often as A at about 4% higher cost. With 5 discordant problems out of 148, a difference
of this size cannot be distinguished from chance.

## Why the benchmark can barely separate the variants

1. **The decomposition step fixes about a third of the bugs on its own.** MGDebugger first rewrites
   the buggy code into subfunctions. In 49 of A's 143 repairs and 61 of C's 144, that rewrite already
   passed every test, so neither debug step ran. HumanEvalFix bugs are single planted mistakes in
   short functions, and Haiku tends to correct them while refactoring.
2. **When the debug step did have to work, both variants almost always succeed.** On the 76 problems
   where both runs' first decomposition left a failing function: A 71 (93.4%), C 72 (94.7%).
3. **The ceiling is high.** Both variants repair over 96% of detectable bugs, leaving room for only a
   handful of disagreements. A harder benchmark (LiveCodeBench, longer programs) would be needed to
   show a difference, if there is one.

## What the hypothesis loop did (C)

| Measure | Value |
| --- | --- |
| Failing functions handed to the loop | 180 |
| Outcomes | fixed 122, confirmed but fix failed 40, nothing confirmed 17, already passing 1 |
| Hypotheses | 327: 233 confirmed, 91 rejected, 3 invalid |
| Confirm rate | 72% of valid hypotheses |
| Invalid replies after one retry | 1% |
| Hypotheses per returned fix | 1.28 |

- The model formed checkable hypotheses reliably: 99% of replies were valid JSON naming real
  variables with concrete predicted values.
- 28% of hypotheses were refuted by the real run. In A, the equivalent mistaken beliefs would have gone
  straight into a fix unchecked; C rejected them before any fix was written.
- A confirmed hypothesis is not a correct fix: 40 of 180 loop calls confirmed a hypothesis whose fix
  then failed the function's tests. Confirmation shows the prediction about the buggy code was right,
  not that the proposed change is.
- Every C repair is backed by a recorded hypothesis, prediction and observation; A's repairs have only
  the model's imagined trace. That auditability is C's clearest advantage in this experiment.

## Variant L: localize with breakpoints instead of decomposing

Suggested by the instructor to cut token cost. MGDebugger spends about 80% of its tokens finding the
bug: decomposing the program (12-13%) and writing tests for every subfunction (66-67%). L drops both.
The LLM sees the numbered program and the failing test and places 1-3 breakpoints, each a line, an
expression, and the values the correct program would show there. The sandbox runs the test and
records the real values; the first mismatch localizes the bug, and the LLM rewrites that function.
Same model, harness, seeds, 2 outer attempts, up to 3 rounds per attempt. Reports: `al_humanevalfix.md`,
`cl_humanevalfix.md`.

### Result: 6x cheaper, 12 points fewer repairs

| | A | C | L |
| --- | --- | --- | --- |
| Repaired, public-selection | 143 / 148 | 147 / 151 | 129 / 151 |
| Paired with L (only that variant / only L) | 22 / 5, p = 0.002 | 22 / 4, p = 0.001 | |
| Cost per repair | $0.0102 | $0.0105 | $0.0019 |
| Where the money goes | derive tests 66%, debug 22%, decompose 12% | derive tests 67%, hypotheses 15%, decompose 13%, fix 6% | breakpoints 82%, fix 18% |
| Wall time (4 shards) | about 1 h | about 55 min | about 12 min |

### Why L misses: bugs inside a `return` expression

Breakpoints record state **before** a line runs. When the planted bug is inside the final `return`
expression, every value the program computes before it is correct, so no breakpoint can disagree.
The model then tends to write the *correct* computation as the breakpoint expression, which of course
matches. Examples from the run:

- HumanEval/4 returns `sum(abs(x - mean) for x in numbers) / mean` (should divide by `len(numbers)`).
  The model's breakpoints: `sum(abs(x - mean) ...)` = 4.0, `len(numbers)` = 4,
  `sum(...) / len(numbers)` = 1.0, `mean` = 2.5. All matched, so no fix was attempted.
- HumanEval/54 returns `s0 == s1` (should compare sets). The model checked `set(s0) == set(s1)`, the fixed
  expression, three times.

Splitting the problems by where the bug is (paired across all three runs, 148 problems):

| Bug location | Problems | A | C | L |
| --- | --- | --- | --- | --- |
| Inside a `return` statement | 66 | 65 | 64 | 46 (70%) |
| Anywhere else | 82 | 78 | 80 | 80 (98%) |

20 of L's 22 failures are `return` bugs. Where a breakpoint can see the bug, L repairs 80 of 82, as
many as C and more than A, at one sixth of the cost.

### What the breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (one per outer attempt) | 186 |
| Outcomes | fixed 132, every breakpoint matched 52, fix failed 2 |
| Rounds | 333: diverged 135, matched everywhere 188, invalid 5, no data 5 |
| Fix passed the public tests, when a divergence was found | 132 of 135 (98%) |
| Breakpoints per round | 1.2 |
| Rounds per returned fix | 1.30 |

- When L finds a divergence, the fix almost always works (98%). The weak step is localization, not repair.
- Failed problems are also L's most expensive: 37% of its spend goes to the 22 problems it never
  repairs, three matched rounds per attempt.

## Variant L2: observe the program, don't recompute it

Two changes to L, aimed at the failure above:

1. **Observe, don't recompute.** A breakpoint expression must be a value the program holds (a variable,
   an element or slice, an attribute, `len` of one) or a piece of the program's own code on that line,
   copied. Anything else is rejected with a list of the pieces of that line it may use. In HumanEval/4
   the model can no longer ask for `sum(...) / len(numbers)`; it must ask for the program's
   `sum(...) / mean`, which is 1.6 where 1.0 is expected, so the bug is found on the first round.
   Copied code may call what the program calls (its own helpers, `hashlib.md5`), but not methods that
   change state (`append`, `pop`, ...).
2. **A full match is evidence too.** If every round matched and nothing was fixed, one more fix call
   gets the matched values ("the program is right up to here, so the bug comes after").

Run twice (same settings), reports `al2_humanevalfix.md` (A vs L2), `cl2_humanevalfix.md`,
`ll2_humanevalfix.md` (L vs L2), `al2_humanevalfix_run2.md`, `l2_replicate_humanevalfix.md`.

### Result

| | A | L2 run 1 | L2 run 2 |
| --- | --- | --- | --- |
| Repaired, public-selection (148 paired problems) | 143 | 146 | 147 |
| Only A / only L2 | | 2 / 5, p = 0.45 | 1 / 5, p = 0.22 |
| Repaired, of all 151 | | 149 | 150 |
| Cost per repair | $0.0102 | $0.0010 | $0.0011 |
| Where the money goes | derive tests 66%, debug 22%, decompose 12% | breakpoints 69%, fix 31% | |

The two L2 runs agree on 150 of 151 problems. HumanEval/123 fails in both (and in L and C): its buggy
`get_odd_collatz` loops forever on the failing input, so no breakpoint value comes back before the timeout.

By bug location (148 problems, all runs):

| Bug location | Problems | A | C | L | L2 run 1 | L2 run 2 |
| --- | --- | --- | --- | --- | --- | --- |
| Inside a `return` statement | 66 | 65 | 64 | 46 | 65 | 66 |
| Anywhere else | 82 | 78 | 80 | 80 | 81 | 81 |

### What the breakpoint loop did (run 1)

| Measure | Value |
| --- | --- |
| Attempts (all 151 problems) | 153 (one outer attempt was enough for 149 problems) |
| Outcomes | fixed after a divergence 149, fixed after a full match 2, nothing found 2 |
| First round found a divergence | 126 of 153 attempts (82%) |
| Rounds | 191: diverged 149, matched everywhere 33, no data 5, invalid 2, fallback fix 2 |
| Fix passed the public tests, when a divergence was found | 149 of 149 |
| Breakpoints per round | 1.04 |

- The observe rule does nearly all of the work: the fallback fix after a full match added 2 repairs in
  run 1 and 4 in run 2. Without it L2 would still repair 147 and 146.
- Once a divergence is found, the fix passed every time. Localizing on real values gives the fix step
  precise evidence ("`x` should be 1.0 but was 1.6 at line 13"), and that is all it needs.
- Cost drops further than L's because the first round usually finds the bug: 2.3 LLM calls per
  problem against L's 3.5 and A's 10.8.

### Why this beats MGDebugger on cost without losing accuracy

MGDebugger localizes by restructuring: decompose the program into subfunctions, have the LLM write tests
for each one, test them bottom-up. About 80% of its tokens go there, and its debug step then simulates
execution in the LLM. L2 localizes by measurement: one LLM call names a few values that must hold, one
real run checks them, and the first wrong one is the bug. On short single-bug programs like HumanEvalFix
that is enough; whether it holds on longer programs with several interacting bugs, where MGDebugger's
hierarchy is meant to help, is not tested here.

## Caveats

- One model (Haiku 5.5), temperature 1.0. A, C and L ran once; L2 ran twice (149 and 150 repaired,
  agreeing on 150 of 151 problems), so L2's run-to-run variation is small, but A's and C's is unmeasured.
- A and C graded test scripts in MGDebugger's in-process runner; L and L2 (partly) in a child process.
  Re-running every recorded attempt of all five runs in a child process reproduced every verdict.
- L2 was designed after seeing L's failures on this same benchmark. The rule it adds is general (observe
  program state, don't recompute it), but a confirmation on another benchmark would be stronger.
- The L run was interrupted after 121 problems (a buggy program left running by MGDebugger's
  in-process test runner exhausted memory) and resumed for the remaining 30. Test scripts now run in a
  child process under the fixed harness; on all 328 buggy and canonical HumanEvalFix programs that gives
  the same verdict as before, except 2 where the old runner hung or crashed.
- "Inside a `return` statement" is found by diffing each buggy program against the canonical one.
- A lost 3 problems (HumanEval/16, /34, /58) to a harness crash that only affects A: functions that
  return a set could not be written into A's debug prompt. Fixed after the run (`utils.evaluate`);
  the comparison uses the 148 problems both runs completed. Giving all 3 to either side would not
  make the result significant.
- 13 undetectable bugs (their buggy code passes every given test) are excluded by design
  (`data_cleaning.md`).
- Not comparable to the paper's 97.6% on HumanEvalFix: different model, 2 attempts instead of 10,
  undetectable bugs excluded, fixed harness.

## Pilot (12 problems, same settings)

A 11/12, C 12/12 under public-selection; $0.07 each (`ab_humanevalfix_pilot.md`).

## Held-out check of L2 (pre-registered in `heldout_plan.md`)

L2 frozen at commit 2b57d71 (the three rules: observe, don't recompute; a full match is evidence; keep
partial progress), run against A on HumanEvalFix again and on three bug sets that played no part in its
design. Same settings as before. Reports: `heldout_<set>.md`.

| Set | Problems | A | L2 | Only A / only L2 | McNemar p | Cost per problem, A / L2 |
| --- | --- | --- | --- | --- | --- | --- |
| HumanEvalFix (design set, L2 rerun) | 148 | 143 | 147 | 1 / 5 | 0.22 | $0.0099 / $0.0011 |
| HumanEval, DeepSeek seeds | 32 | 31 | 30 | 2 / 1 | 1.00 | $0.0162 / $0.0017 |
| HumanEval, StarCoder seeds | 88 | 85 | 81 | 4 / 0 | 0.13 | $0.0108 / $0.0014 |
| MBPP, DeepSeek seeds | 104 | 77 | 70 | 18 / 11 | 0.27 | $0.0124 / $0.0019 |
| **Held-out pooled** | **224** | **193 (86.2%)** | **181 (80.8%)** | **24 / 12** | **0.065** | 8x cheaper |

Repairs under public-selection on the problems both runs completed.

**Against the plan's criterion** ("at least as many as A within chance, at a fraction of the cost"): the
pooled loss is not significant at 0.05 (p = 0.065), so the criterion is formally met, but L2 repaired 12
fewer bugs and no held-out set favours it. The honest reading: **L2's cost reduction generalizes; its
accuracy gain on HumanEvalFix does not.** On held-out bugs L2 is somewhat less accurate than MGDebugger.

### Why L2 loses on the held-out sets

1. **Lenient test check (MBPP, 16 of L2's problems).** The fixed harness compares a given test by value:
   (1, 2) equals [1, 2], because the cleaned tests are stored as JSON, which has no tuples. The benchmark's
   own assert uses Python's ==, where they differ. MBPP functions often return tuples. 33 of L2's accepted
   fixes on MBPP passed the value check but failed the real assert; on 16 problems L2 never produced a fix
   that passed it. L2 is hit harder than A because it stops at the first fix its check accepts, and its
   prompts showed the expected value as JSON, so `((6, 7), (4, 9))` appeared as `[[6, 7], [4, 9]]`. A has
   the same lenient check; how much it cost A is measured by the rerun below.
   HumanEvalFix and HumanEval were not affected (0 such fixes).
2. **No code to observe (StarCoder, 2 problems).** StarCoder's "solution" to HumanEval/6 and /129 is an
   empty function body (comments only). There is no line to break on, every L2 round is rejected, and no
   fix is attempted. A rewrites the function from scratch.
3. **Fixes that fit thin given tests (all sets).** A fix that passes the given tests but fails the hidden
   ones: A 16, L2 19 across the held-out sets. MBPP gives one test per problem.

### Post-hoc: MBPP with exact test checks

`HDMG_EXACT_TESTS=1` makes a given test pass only if its own assert passes, runs the test with the
assert's own arguments (tuples stay tuples), and shows L2 the expected value as the assert writes it.
It applies to both variants (A's check of the top-level function uses the assert too). Because this was
added after seeing the held-out results, the rerun is reported as post-hoc, next to the pre-registered
result above, not instead of it. Report: `heldout_mbpp_exact.md`.

| MBPP, 104 problems | A, lenient run | A, exact run | L2, lenient run | L2, exact run |
| --- | --- | --- | --- | --- |
| Repaired, public-selection | 77 | 69 | 70 | **89** |
| Repaired, hidden-selection | 83 | 74 | 74 | 91 |
| Cost per problem | $0.0124 | $0.0246 | $0.0019 | $0.0017 |
| LLM calls per problem | 13.8 | 28.9 | 3.4 | 2.9 |

- **With exact checks L2 repairs 89 of 104, more than either A run.** Against A's better run (77, lenient):
  only A 5, only L2 17, p = 0.017. Against A's exact run (69): only A 3, only L2 23, p < 0.001. A repaired
  86 problems in at least one of its two runs; L2's single exact run repaired 89.
- **A got worse and twice as expensive with exact checks**, mainly because its prompts were not changed:
  A's debug prompt shows test cases as JSON, so when a list fails a tuple test the expected and actual values
  print identically and A keeps retrying (28.9 calls per problem). L2's prompts show the assert's own
  expected value. This asymmetry favours L2 in the exact run, which is why the comparison against A's lenient
  run is the conservative one.
- **A varies a lot between runs on MBPP**: the two A runs disagree on 26 problems (17 repaired only in the
  first, 9 only in the second), including 10 lost problems that never hit an exact-check failure. Single runs
  of A on MBPP are noisy; L2's two MBPP runs agree more because they differ mostly where the check changed.
- A's exact run was interrupted after 53 problems and resumed; from the resume on, A's per-function tests ran
  in a child process (same verdicts except for programs that hang or crash; `utils.evaluate`).

**Held-out pooled, post-hoc** (MBPP: L2 exact run against A's better, lenient run; the HumanEval sets had no
fixes affected by the check and are unchanged): A 193, L2 200 of 224 (only A 11, only L2 18, p = 0.27), at
about an eighth of the cost.

### Conclusion of the held-out check

- **Cost: general.** L2 is 6.6x to 15x cheaper than MGDebugger on every set, because it never decomposes
  the program or writes tests for subfunctions; 2.3 to 3.4 LLM calls per problem against 10.8 to 28.9.
- **Accuracy: not worse, not shown to be better.** Pre-registered: L2 181, A 193 of 224 (p = 0.065).
  After fixing a harness defect that hurt L2 on MBPP (post-hoc): L2 200, A 193 (p = 0.27). The only
  significant difference on held-out data is MBPP after the fix, in L2's favour.
- **Known gaps** (each seen on held-out data, none fixed, so that the held-out runs stay valid for the
  version they tested): an empty function body leaves nothing to observe (2 StarCoder problems); thin given
  tests let a fix pass them and still be wrong (about as often as A).
