# L21 vs L22: humanevalfix.jsonl

- L21 = observe-only breakpoints, L22 = observe-only breakpoints
- Model: claude-haiku-5-5 (L21), claude-haiku-5-5 (L22)
- Problems compared: 151 (attempted by both runs; L21 attempted 151, L22 attempted 151)
- Outer attempts: 2 (L21), 2 (L22); harness fixed / fixed; k = 3 (L21); k = 3 (L22)
- Runs: `MGDebugger/src/output_data/experiments/humanevalfix_L2_20261123-202524`, `MGDebugger/src/output_data/experiments/humanevalfix_L2_20261123-203848`

## Repairs

| Metric | L21 (observe-only breakpoints) | L22 (observe-only breakpoints) |
| --- | --- | --- |
| Repaired, public-selection | 149 (98.7%) | 150 (99.3%) |
| Repaired, hidden-selection (paper) | 149 (98.7%) | 150 (99.3%) |
| Cost, total | $0.154 | $0.158 |
| Cost per problem | $0.0010 | $0.0010 |
| Cost per repair (public-selection) | $0.0010 | $0.0011 |
| Tokens per problem | 3,573 | 3,683 |
| LLM calls per problem | 2.3 | 2.4 |
| Cost ratio | | L22 costs 1.0x L21 |

## Paired outcome (public-selection)

| Both repaired | Only L21 | Only L22 | Neither |
| --- | --- | --- | --- |
| 149 | 0 | 1 | 1 |

Exact McNemar test on the 1 discordant problems: p = 1.000 (not significant at the 0.05 level: the difference could be chance).

- Only L21: none
- Only L22: HumanEval/38

## By bug type (public-selection)

| Bug type | Problems | L21 | L22 |
| --- | --- | --- | --- |
| excess logic | 27 | 27 (100.0%) | 27 (100.0%) |
| function misuse | 7 | 7 (100.0%) | 7 (100.0%) |
| missing logic | 28 | 27 (96.4%) | 28 (100.0%) |
| operator misuse | 25 | 25 (100.0%) | 25 (100.0%) |
| value misuse | 41 | 40 (97.6%) | 40 (97.6%) |
| variable misuse | 23 | 23 (100.0%) | 23 (100.0%) |

## Cost by stage (per problem)

| Stage | L21 | L22 |
| --- | --- | --- |
| localize | $0.00070 (69%) | $0.00073 (70%) |
| fix | $0.00032 (31%) | $0.00032 (30%) |

## What L21's breakpoint loop did

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
| Fallback fixes after a full match (L2) that passed | 2 of 2 |
| Attempts that returned a fix | 151 (99%) |
| Rounds per returned fix (mean) | 1.23 |

## What L22's breakpoint loop did

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
| Fallback fixes after a full match (L2) that passed | 4 of 4 |
| Attempts that returned a fix | 150 (99%) |
| Rounds per returned fix (mean) | 1.26 |


