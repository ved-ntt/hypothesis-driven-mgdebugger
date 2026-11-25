# L vs D: humanevalfix.jsonl

- L = breakpoints, first version, D = breakpoint localization
- Model: claude-haiku-5-5 (L), claude-haiku-5-5 (D)
- Problems compared: 151 (attempted by both runs; L attempted 151, D attempted 151)
- Outer attempts: 2 (L), 2 (D); harness fixed / fixed; k = 3 (L); k = 3 (D)
- Runs: `MGDebugger/src/output_data/experiments/humanevalfix_L_20261123-190742`, `MGDebugger/src/output_data/experiments/humanevalfix_L2_20261123-202524`

## Repairs

| Metric | L (breakpoints, first version) | D (breakpoint localization) |
| --- | --- | --- |
| Repaired, public-selection | 129 (85.4%) | 149 (98.7%) |
| Repaired, hidden-selection (paper) | 129 (85.4%) | 149 (98.7%) |
| Cost, total | $0.246 | $0.154 |
| Cost per problem | $0.0016 | $0.0010 |
| Cost per repair (public-selection) | $0.0019 | $0.0010 |
| Tokens per problem | 5,866 | 3,573 |
| LLM calls per problem | 3.5 | 2.3 |
| Cost ratio | | L costs 1.6x D |

## Paired outcome (public-selection)

| Both repaired | Only L | Only D | Neither |
| --- | --- | --- | --- |
| 129 | 0 | 20 | 2 |

Exact McNemar test on the 20 discordant problems: p = 0.000 (difference unlikely to be chance at the 0.05 level).

- Only L: none
- Only D: HumanEval/4, HumanEval/11, HumanEval/27, HumanEval/29, HumanEval/30, HumanEval/52, HumanEval/54, HumanEval/65, HumanEval/66, HumanEval/77, HumanEval/79, HumanEval/84, HumanEval/103, HumanEval/115, HumanEval/118, HumanEval/120, HumanEval/125, HumanEval/127, HumanEval/159, HumanEval/162

## By bug type (public-selection)

| Bug type | Problems | L | D |
| --- | --- | --- | --- |
| excess logic | 27 | 24 (88.9%) | 27 (100.0%) |
| function misuse | 7 | 2 (28.6%) | 7 (100.0%) |
| missing logic | 28 | 23 (82.1%) | 27 (96.4%) |
| operator misuse | 25 | 22 (88.0%) | 25 (100.0%) |
| value misuse | 41 | 37 (90.2%) | 40 (97.6%) |
| variable misuse | 23 | 21 (91.3%) | 23 (100.0%) |

## Cost by stage (per problem)

| Stage | L | D |
| --- | --- | --- |
| localize | $0.00133 (82%) | $0.00070 (69%) |
| fix | $0.00030 (18%) | $0.00032 (31%) |

## What L's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 186 |
| Outcomes | fixed 132, no_divergence 52, fix_failed 2 |
| Rounds | 333 |
| Diverged / matched everywhere / invalid / no data | 135 / 188 / 5 / 5 |
| Invalid replies (after one retry) | 2% of rounds |
| Divergence kinds (value / missing hit / expression error) | 119 / 16 / 0 |
| Breakpoints per valid round (mean) | 1.21 |
| Fixes that passed the public tests, of fixes tried after a divergence | 132 of 135 |
| Fixes tried in the entry function (vs a helper) | 133 of 135 |
| Fallback fixes after a full match (D) that passed | 0 of 0 |
| Attempts that returned a fix | 132 (71%) |
| Rounds per returned fix (mean) | 1.30 |

## What D's breakpoint loop did

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


