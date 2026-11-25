# A vs L2: big_programs.jsonl

- A = simulated trace, L2 = observe-only breakpoints
- Model: claude-haiku-5-5 (A), claude-haiku-5-5 (L2)
- Problems compared: 6 (attempted by both runs; A attempted 6, L2 attempted 12)
- Outer attempts: 2 (A), 2 (L2); harness fixed / fixed; exact given tests True / True; k = 3 (L2)
- Runs: `MGDebugger/src/output_data/experiments/big_programs_A_20261124-202921`, `MGDebugger/src/output_data/experiments/big_programs_L2_20261124-202921`

## Repairs

| Metric | A (simulated trace) | L2 (observe-only breakpoints) |
| --- | --- | --- |
| Repaired, public-selection | 2 (33.3%) | 3 (50.0%) |
| Repaired, hidden-selection (paper) | 2 (33.3%) | 3 (50.0%) |
| Cost, total | $1.281 | $0.023 |
| Cost per problem | $0.2135 | $0.0039 |
| Cost per repair (public-selection) | $0.6406 | $0.0078 |
| Tokens per problem | 670,477 | 18,010 |
| LLM calls per problem | 222.3 | 4.7 |
| Cost ratio | | A costs 55.1x L2 |

## Paired outcome (public-selection)

| Both repaired | Only A | Only L2 | Neither |
| --- | --- | --- | --- |
| 1 | 1 | 2 | 2 |

Exact McNemar test on the 3 discordant problems: p = 1.000 (not significant at the 0.05 level: the difference could be chance).

- Only A: BIG/5
- Only L2: BIG/0, BIG/4

## Cost by stage (per problem)

| Stage | A | L2 |
| --- | --- | --- |
| debug | $0.14590 (68%) | $0.00000 (0%) |
| derive_tests | $0.05947 (28%) | $0.00000 (0%) |
| decompose | $0.00816 (4%) | $0.00000 (0%) |
| localize | $0.00000 (0%) | $0.00285 (74%) |
| fix | $0.00000 (0%) | $0.00103 (26%) |

## What L2's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 9 |
| Outcomes | fixed 6, fix_failed 2, fixed_fallback 1 |
| Rounds | 17 |
| Diverged / matched everywhere / invalid / no data | 10 / 6 / 0 / 0 |
| Invalid replies (after one retry) | 0% of rounds |
| Divergence kinds (value / missing hit / expression error) | 9 / 1 / 0 |
| Breakpoints per valid round (mean) | 1.00 |
| Fixes that passed the public tests, of fixes tried after a divergence | 6 of 10 |
| Fixes tried in the entry function (vs a helper) | 0 of 10 |
| Fallback fixes after a full match (L2) that passed | 1 of 1 |
| Attempts that returned a fix | 7 (78%) |
| Rounds per returned fix (mean) | 1.57 |

