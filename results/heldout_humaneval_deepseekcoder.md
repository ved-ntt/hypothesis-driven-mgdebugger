# A vs D: humaneval_deepseekcoder.jsonl

- A = MGDebugger, D = breakpoint localization
- Model: claude-haiku-5-5 (A), claude-haiku-5-5 (D)
- Problems compared: 32 (attempted by both runs; A attempted 32, D attempted 32)
- Outer attempts: 2 (A), 2 (D); harness fixed / fixed; k = 3 (D)
- Runs: `/mnt/c/Users/Vedantt/Downloads/NCSU/sem3/Testing/hypothesis-driven-mgdebugger/MGDebugger/src/output_data/experiments/humaneval_deepseekcoder_A_20261124-142116`, `/mnt/c/Users/Vedantt/Downloads/NCSU/sem3/Testing/hypothesis-driven-mgdebugger/MGDebugger/src/output_data/experiments/humaneval_deepseekcoder_L2_20261124-142116`

## Repairs

| Metric | A (MGDebugger) | D (breakpoint localization) |
| --- | --- | --- |
| Repaired, public-selection | 31 (96.9%) | 30 (93.8%) |
| Repaired, hidden-selection (paper) | 32 (100.0%) | 30 (93.8%) |
| Cost, total | $0.520 | $0.055 |
| Cost per problem | $0.0162 | $0.0017 |
| Cost per repair (public-selection) | $0.0168 | $0.0018 |
| Tokens per problem | 43,839 | 5,973 |
| LLM calls per problem | 14.0 | 3.1 |
| Cost ratio | | A costs 9.4x D |

## Paired outcome (public-selection)

| Both repaired | Only A | Only D | Neither |
| --- | --- | --- | --- |
| 29 | 2 | 1 | 0 |

Exact McNemar test on the 3 discordant problems: p = 1.000 (not significant at the 0.05 level: the difference could be chance).

- Only A: HumanEval/125, HumanEval/130
- Only D: HumanEval/135

## Cost by stage (per problem)

| Stage | A | D |
| --- | --- | --- |
| derive_tests | $0.00929 (57%) | $0.00000 (0%) |
| debug | $0.00545 (34%) | $0.00000 (0%) |
| decompose | $0.00150 (9%) | $0.00000 (0%) |
| localize | $0.00000 (0%) | $0.00125 (72%) |
| fix | $0.00000 (0%) | $0.00048 (28%) |

## What D's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 34 |
| Outcomes | fixed 26, fixed_fallback 6, not_top_level 2 |
| Rounds | 60 |
| Diverged / matched everywhere / invalid / no data | 26 / 25 / 3 / 0 |
| Invalid replies (after one retry) | 5% of rounds |
| Divergence kinds (value / missing hit / expression error) | 25 / 1 / 0 |
| Breakpoints per valid round (mean) | 0.91 |
| Fixes that passed the public tests, of fixes tried after a divergence | 26 of 26 |
| Fixes tried in the entry function (vs a helper) | 26 of 26 |
| Fallback fixes after a full match (D) that passed | 6 of 6 |
| Attempts that returned a fix | 32 (94%) |
| Rounds per returned fix (mean) | 1.88 |

