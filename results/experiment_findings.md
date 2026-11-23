# A vs C on HumanEvalFix: findings

Run on 23 Nov 2026 with Claude Haiku 5.5 (temperature 1.0, the endpoint's minimum), 151 detectable
HumanEvalFix bugs, 2 outer attempts, fixed harness, 4 parallel shards per variant. Full report:
`ab_humanevalfix.md`; run summaries and settings: `runs/`.

## Result: no measurable difference in repairs

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

## Caveats

- One model (Haiku 5.5), one run per variant, temperature 1.0: run-to-run variation is not measured.
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
