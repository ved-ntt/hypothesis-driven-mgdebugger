# A vs D: humaneval_starcoder.jsonl

- A = MGDebugger, D = breakpoint localization
- Model: claude-haiku-5-5 (A), claude-haiku-5-5 (D)
- Problems compared: 88 (attempted by both runs; A attempted 88, D attempted 88)
- Outer attempts: 2 (A), 2 (D); harness fixed / fixed; k = 3 (D)
- Runs: `/mnt/c/Users/Vedantt/Downloads/NCSU/sem3/Testing/hypothesis-driven-mgdebugger/MGDebugger/src/output_data/experiments/humaneval_starcoder_A_20261124-144317`, `/mnt/c/Users/Vedantt/Downloads/NCSU/sem3/Testing/hypothesis-driven-mgdebugger/MGDebugger/src/output_data/experiments/humaneval_starcoder_L2_20261124-144317`

## Repairs

| Metric | A (MGDebugger) | D (breakpoint localization) |
| --- | --- | --- |
| Repaired, public-selection | 85 (96.6%) | 81 (92.0%) |
| Repaired, hidden-selection (paper) | 85 (96.6%) | 81 (92.0%) |
| Cost, total | $0.953 | $0.120 |
| Cost per problem | $0.0108 | $0.0014 |
| Cost per repair (public-selection) | $0.0112 | $0.0015 |
| Tokens per problem | 30,791 | 4,673 |
| LLM calls per problem | 11.3 | 2.7 |
| Cost ratio | | A costs 8.0x D |

## Paired outcome (public-selection)

| Both repaired | Only A | Only D | Neither |
| --- | --- | --- | --- |
| 81 | 4 | 0 | 3 |

Exact McNemar test on the 4 discordant problems: p = 0.125 (not significant at the 0.05 level: the difference could be chance).

- Only A: HumanEval/6, HumanEval/32, HumanEval/93, HumanEval/129
- Only D: none

## Cost by stage (per problem)

| Stage | A | D |
| --- | --- | --- |
| derive_tests | $0.00663 (61%) | $0.00000 (0%) |
| debug | $0.00289 (27%) | $0.00000 (0%) |
| decompose | $0.00131 (12%) | $0.00000 (0%) |
| localize | $0.00000 (0%) | $0.00088 (65%) |
| fix | $0.00000 (0%) | $0.00048 (35%) |

## What D's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 96 |
| Outcomes | fixed 88, no_divergence 4, fix_failed 2, fixed_fallback 2 |
| Rounds | 129 |
| Diverged / matched everywhere / invalid / no data | 93 / 22 / 12 / 0 |
| Invalid replies (after one retry) | 9% of rounds |
| Divergence kinds (value / missing hit / expression error) | 89 / 2 / 2 |
| Breakpoints per valid round (mean) | 1.01 |
| Fixes that passed the public tests, of fixes tried after a divergence | 88 of 93 |
| Fixes tried in the entry function (vs a helper) | 88 of 93 |
| Fallback fixes after a full match (D) that passed | 2 of 2 |
| Attempts that returned a fix | 90 (94%) |
| Rounds per returned fix (mean) | 1.23 |

