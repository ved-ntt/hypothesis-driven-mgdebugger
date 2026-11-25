# D1 vs D2: humanevalfix.jsonl

- D1 = breakpoint localization, D2 = breakpoint localization
- Model: claude-haiku-5-5 (D1), claude-haiku-5-5 (D2)
- Problems compared: 151 (attempted by both runs; D1 attempted 151, D2 attempted 151)
- Outer attempts: 2 (D1), 2 (D2); harness fixed / fixed; k = 3 (D1); k = 3 (D2)
- Runs: `MGDebugger/src/output_data/experiments/humanevalfix_L2_20261123-202524`, `MGDebugger/src/output_data/experiments/humanevalfix_L2_20261123-203848`

## Repairs

| Metric | D1 (observe-only breakpoints) | D2 (observe-only breakpoints) |
| --- | --- | --- |
| Repaired, public-selection | 149 (98.7%) | 150 (99.3%) |
| Repaired, hidden-selection (paper) | 149 (98.7%) | 150 (99.3%) |
| Cost, total | $0.154 | $0.158 |
| Cost per problem | $0.0010 | $0.0010 |
| Cost per repair (public-selection) | $0.0010 | $0.0011 |
| Tokens per problem | 3,573 | 3,683 |
| LLM calls per problem | 2.3 | 2.4 |
| Cost ratio | | D2 costs 1.0x D1 |

## Paired outcome (public-selection)

| Both repaired | Only D1 | Only D2 | Neither |
| --- | --- | --- | --- |
| 149 | 0 | 1 | 1 |

Exact McNemar test on the 1 discordant problems: p = 1.000 (not significant at the 0.05 level: the difference could be chance).

- Only D1: none
- Only D2: HumanEval/38

## By bug type (public-selection)

| Bug type | Problems | D1 | D2 |
| --- | --- | --- | --- |
| excess logic | 27 | 27 (100.0%) | 27 (100.0%) |
| function misuse | 7 | 7 (100.0%) | 7 (100.0%) |
| missing logic | 28 | 27 (96.4%) | 28 (100.0%) |
| operator misuse | 25 | 25 (100.0%) | 25 (100.0%) |
| value misuse | 41 | 40 (97.6%) | 40 (97.6%) |
| variable misuse | 23 | 23 (100.0%) | 23 (100.0%) |

## Cost by stage (per problem)

| Stage | D1 | D2 |
| --- | --- | --- |
| localize | $0.00070 (69%) | $0.00073 (70%) |
| fix | $0.00032 (31%) | $0.00032 (30%) |

## What D1's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 153 |
| Outcomes | fixed 149, fixed_fallback 2, no_divergence 2 |
| Rounds | 191 |
| Diverged / matched everywhere / invalid / no data | 149 / 33 / 2 / 5 |
| Invalid replies (after one retry) | 1% of rounds |
| Divergence kinds (value / missing hit / expression error) | 141 / 7 / 1 |
| Breakpoints per valid round (mean) | 1.03 |
| Fixes that passed the public tests, of fixes tried after a divergence | 149 of 149 |
| Fixes tried in the entry function (vs a helper) | 147 of 149 |
| Fallback fixes after a full match (D) that passed | 2 of 2 |
| Attempts that returned a fix | 151 (99%) |
| Rounds per returned fix (mean) | 1.23 |

## What D2's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 152 |
| Outcomes | fixed 146, fixed_fallback 4, no_divergence 2 |
| Rounds | 195 |
| Diverged / matched everywhere / invalid / no data | 147 / 35 / 3 / 6 |
| Invalid replies (after one retry) | 2% of rounds |
| Divergence kinds (value / missing hit / expression error) | 143 / 4 / 0 |
| Breakpoints per valid round (mean) | 1.01 |
| Fixes that passed the public tests, of fixes tried after a divergence | 146 of 147 |
| Fixes tried in the entry function (vs a helper) | 147 of 147 |
| Fallback fixes after a full match (D) that passed | 4 of 4 |
| Attempts that returned a fix | 150 (99%) |
| Rounds per returned fix (mean) | 1.26 |


