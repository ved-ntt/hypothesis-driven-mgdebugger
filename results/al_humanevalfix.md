# A vs L: humanevalfix.jsonl

- A = simulated trace, L = breakpoint localization
- Model: claude-haiku-5-5 (A), claude-haiku-5-5 (L)
- Problems compared: 148 (attempted by both runs; A attempted 148, L attempted 151)
- Outer attempts: 2 (A), 2 (L); harness fixed / fixed; k = 3 (L)
- Runs: `MGDebugger/src/output_data/experiments/humanevalfix_A_20261123-160502`, `MGDebugger/src/output_data/experiments/humanevalfix_L_20261123-190742`

## Repairs

| Metric | A (simulated trace) | L (breakpoint localization) |
| --- | --- | --- |
| Repaired, public-selection | 143 (96.6%) | 126 (85.1%) |
| Repaired, hidden-selection (paper) | 145 (98.0%) | 126 (85.1%) |
| Cost, total | $1.463 | $0.244 |
| Cost per problem | $0.0099 | $0.0017 |
| Cost per repair (public-selection) | $0.0102 | $0.0019 |
| Tokens per problem | 28,760 | 5,940 |
| LLM calls per problem | 10.8 | 3.5 |
| Cost ratio | | A costs 6.0x L |

## Paired outcome (public-selection)

| Both repaired | Only A | Only L | Neither |
| --- | --- | --- | --- |
| 121 | 22 | 5 | 0 |

Exact McNemar test on the 27 discordant problems: p = 0.002 (difference unlikely to be chance at the 0.05 level).

- Only A: HumanEval/4, HumanEval/11, HumanEval/27, HumanEval/29, HumanEval/30, HumanEval/38, HumanEval/52, HumanEval/54, HumanEval/65, HumanEval/66, HumanEval/77, HumanEval/79, HumanEval/84, HumanEval/103, HumanEval/115, HumanEval/118, HumanEval/120, HumanEval/123, HumanEval/125, HumanEval/127, HumanEval/159, HumanEval/162
- Only L: HumanEval/32, HumanEval/80, HumanEval/83, HumanEval/87, HumanEval/130

## By bug type (public-selection)

| Bug type | Problems | A | L |
| --- | --- | --- | --- |
| excess logic | 27 | 25 (92.6%) | 24 (88.9%) |
| function misuse | 7 | 7 (100.0%) | 2 (28.6%) |
| missing logic | 25 | 25 (100.0%) | 20 (80.0%) |
| operator misuse | 25 | 24 (96.0%) | 22 (88.0%) |
| value misuse | 41 | 41 (100.0%) | 37 (90.2%) |
| variable misuse | 23 | 21 (91.3%) | 21 (91.3%) |

## Cost by stage (per problem)

| Stage | A | L |
| --- | --- | --- |
| derive_tests | $0.00651 (66%) | $0.00000 (0%) |
| debug | $0.00215 (22%) | $0.00000 (0%) |
| localize | $0.00000 (0%) | $0.00135 (82%) |
| decompose | $0.00123 (12%) | $0.00000 (0%) |
| fix | $0.00000 (0%) | $0.00030 (18%) |

## What L's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 183 |
| Outcomes | fixed 129, no_divergence 52, fix_failed 2 |
| Rounds | 330 |
| Diverged / matched everywhere / invalid / no data | 132 / 188 / 5 / 5 |
| Divergence kinds (value / missing hit / expression error) | 116 / 16 / 0 |
| Breakpoints per valid round (mean) | 1.21 |
| Fixes that passed the public tests, of fixes tried after a divergence | 129 of 132 |
| Fixes tried in the entry function (vs a helper) | 130 of 132 |
| Attempts that returned a fix | 129 (70%) |
| Rounds per returned fix (mean) | 1.30 |

