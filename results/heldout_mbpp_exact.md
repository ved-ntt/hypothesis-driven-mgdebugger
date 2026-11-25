# A vs D: mbpp_deepseekcoder.jsonl

- A = MGDebugger, D = breakpoint localization
- Model: claude-haiku-5-5 (A), claude-haiku-5-5 (D)
- Problems compared: 104 (attempted by both runs; A attempted 104, D attempted 104)
- Outer attempts: 2 (A), 2 (D); harness fixed / fixed; exact given tests True / True; k = 3 (D)
- Runs: `MGDebugger/src/output_data/experiments/mbpp_deepseekcoder_A_20261124-182425`, `MGDebugger/src/output_data/experiments/mbpp_deepseekcoder_L2_20261124-182425`

## Repairs

| Metric | A (MGDebugger) | D (breakpoint localization) |
| --- | --- | --- |
| Repaired, public-selection | 69 (66.3%) | 89 (85.6%) |
| Repaired, hidden-selection (paper) | 74 (71.2%) | 91 (87.5%) |
| Cost, total | $2.561 | $0.173 |
| Cost per problem | $0.0246 | $0.0017 |
| Cost per repair (public-selection) | $0.0371 | $0.0019 |
| Tokens per problem | 64,211 | 5,094 |
| LLM calls per problem | 28.9 | 2.9 |
| Cost ratio | | A costs 14.8x D |

## Paired outcome (public-selection)

| Both repaired | Only A | Only D | Neither |
| --- | --- | --- | --- |
| 66 | 3 | 23 | 12 |

Exact McNemar test on the 26 discordant problems: p = 0.000 (difference unlikely to be chance at the 0.05 level).

- Only A: MBPP/246, MBPP/386, MBPP/444
- Only D: MBPP/81, MBPP/110, MBPP/114, MBPP/126, MBPP/139, MBPP/155, MBPP/185, MBPP/209, MBPP/235, MBPP/236, MBPP/243, MBPP/252, MBPP/259, MBPP/290, MBPP/305, MBPP/318, MBPP/321, MBPP/343, MBPP/355, MBPP/368, MBPP/416, MBPP/419, MBPP/440

## Cost by stage (per problem)

| Stage | A | D |
| --- | --- | --- |
| debug | $0.01620 (66%) | $0.00000 (0%) |
| derive_tests | $0.00703 (29%) | $0.00000 (0%) |
| decompose | $0.00140 (6%) | $0.00000 (0%) |
| localize | $0.00000 (0%) | $0.00100 (60%) |
| fix | $0.00000 (0%) | $0.00067 (40%) |

## What D's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 120 |
| Outcomes | fixed 109, fix_failed 8, fixed_fallback 2, no_divergence 1 |
| Rounds | 165 |
| Diverged / matched everywhere / invalid / no data | 131 / 31 / 0 / 0 |
| Invalid replies (after one retry) | 0% of rounds |
| Divergence kinds (value / missing hit / expression error) | 125 / 4 / 2 |
| Breakpoints per valid round (mean) | 1.08 |
| Fixes that passed the public tests, of fixes tried after a divergence | 109 of 131 |
| Fixes tried in the entry function (vs a helper) | 131 of 131 |
| Fallback fixes after a full match (D) that passed | 2 of 3 |
| Attempts that returned a fix | 111 (92%) |
| Rounds per returned fix (mean) | 1.23 |

