# A vs L2: mbpp_deepseekcoder.jsonl

- A = simulated trace, L2 = observe-only breakpoints
- Model: claude-haiku-5-5 (A), claude-haiku-5-5 (L2)
- Problems compared: 104 (attempted by both runs; A attempted 104, L2 attempted 104)
- Outer attempts: 2 (A), 2 (L2); harness fixed / fixed; k = 3 (L2)
- Runs: `/mnt/c/Users/Vedantt/Downloads/NCSU/sem3/Testing/hypothesis-driven-mgdebugger/MGDebugger/src/output_data/experiments/mbpp_deepseekcoder_A_20261124-170312`, `/mnt/c/Users/Vedantt/Downloads/NCSU/sem3/Testing/hypothesis-driven-mgdebugger/MGDebugger/src/output_data/experiments/mbpp_deepseekcoder_L2_20261124-170312`

## Repairs

| Metric | A (simulated trace) | L2 (observe-only breakpoints) |
| --- | --- | --- |
| Repaired, public-selection | 77 (74.0%) | 70 (67.3%) |
| Repaired, hidden-selection (paper) | 83 (79.8%) | 74 (71.2%) |
| Cost, total | $1.293 | $0.195 |
| Cost per problem | $0.0124 | $0.0019 |
| Cost per repair (public-selection) | $0.0168 | $0.0028 |
| Tokens per problem | 33,859 | 5,757 |
| LLM calls per problem | 13.8 | 3.4 |
| Cost ratio | | A costs 6.6x L2 |

## Paired outcome (public-selection)

| Both repaired | Only A | Only L2 | Neither |
| --- | --- | --- | --- |
| 59 | 18 | 11 | 16 |

Exact McNemar test on the 29 discordant problems: p = 0.265 (not significant at the 0.05 level: the difference could be chance).

- Only A: MBPP/13, MBPP/205, MBPP/246, MBPP/259, MBPP/275, MBPP/290, MBPP/299, MBPP/305, MBPP/307, MBPP/310, MBPP/311, MBPP/343, MBPP/355, MBPP/368, MBPP/386, MBPP/440, MBPP/444, MBPP/452
- Only L2: MBPP/47, MBPP/126, MBPP/134, MBPP/185, MBPP/235, MBPP/288, MBPP/306, MBPP/318, MBPP/360, MBPP/430, MBPP/488

## Cost by stage (per problem)

| Stage | A | L2 |
| --- | --- | --- |
| derive_tests | $0.00665 (53%) | $0.00000 (0%) |
| debug | $0.00446 (36%) | $0.00000 (0%) |
| decompose | $0.00133 (11%) | $0.00000 (0%) |
| localize | $0.00000 (0%) | $0.00113 (60%) |
| fix | $0.00000 (0%) | $0.00075 (40%) |

## What L2's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 139 |
| Outcomes | fixed 126, fix_failed 9, no_divergence 3, fixed_fallback 1 |
| Rounds | 191 |
| Diverged / matched everywhere / invalid / no data | 149 / 38 / 0 / 0 |
| Invalid replies (after one retry) | 0% of rounds |
| Divergence kinds (value / missing hit / expression error) | 146 / 0 / 3 |
| Breakpoints per valid round (mean) | 1.08 |
| Fixes that passed the public tests, of fixes tried after a divergence | 126 of 149 |
| Fixes tried in the entry function (vs a helper) | 148 of 149 |
| Fallback fixes after a full match (L2) that passed | 1 of 4 |
| Attempts that returned a fix | 127 (91%) |
| Rounds per returned fix (mean) | 1.20 |

