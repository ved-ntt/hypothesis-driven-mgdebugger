# A vs C: humanevalfix.jsonl

- A = MGDebugger, C = breakpoint localization
- Model: claude-haiku-5-5 (A), claude-haiku-5-5 (C)
- Problems compared: 148 (attempted by both runs; A attempted 148, C attempted 151)
- Outer attempts: 2 (A), 2 (C); harness fixed / fixed; k = 3 (C)
- Runs: `MGDebugger/src/output_data/experiments/humanevalfix_A_20261123-160502`, `MGDebugger/src/output_data/experiments/humanevalfix_C_20261123-202524`

## Repairs

| Metric | A (MGDebugger) | C (breakpoint localization) |
| --- | --- | --- |
| Repaired, public-selection | 143 (96.6%) | 146 (98.6%) |
| Repaired, hidden-selection (paper) | 145 (98.0%) | 146 (98.6%) |
| Cost, total | $1.463 | $0.152 |
| Cost per problem | $0.0099 | $0.0010 |
| Cost per repair (public-selection) | $0.0102 | $0.0010 |
| Tokens per problem | 28,760 | 3,601 |
| LLM calls per problem | 10.8 | 2.3 |
| Cost ratio | | A costs 9.6x C |

## Paired outcome (public-selection)

| Both repaired | Only A | Only C | Neither |
| --- | --- | --- | --- |
| 141 | 2 | 5 | 0 |

Exact McNemar test on the 7 discordant problems: p = 0.453 (not significant at the 0.05 level: the difference could be chance).

- Only A: HumanEval/38, HumanEval/123
- Only C: HumanEval/32, HumanEval/80, HumanEval/83, HumanEval/87, HumanEval/130

## By bug type (public-selection)

| Bug type | Problems | A | C |
| --- | --- | --- | --- |
| excess logic | 27 | 25 (92.6%) | 27 (100.0%) |
| function misuse | 7 | 7 (100.0%) | 7 (100.0%) |
| missing logic | 25 | 25 (100.0%) | 24 (96.0%) |
| operator misuse | 25 | 24 (96.0%) | 25 (100.0%) |
| value misuse | 41 | 41 (100.0%) | 40 (97.6%) |
| variable misuse | 23 | 21 (91.3%) | 23 (100.0%) |

## Cost by stage (per problem)

| Stage | A | C |
| --- | --- | --- |
| derive_tests | $0.00651 (66%) | $0.00000 (0%) |
| debug | $0.00215 (22%) | $0.00000 (0%) |
| decompose | $0.00123 (12%) | $0.00000 (0%) |
| localize | $0.00000 (0%) | $0.00070 (69%) |
| fix | $0.00000 (0%) | $0.00032 (31%) |

## What C's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 150 |
| Outcomes | fixed 146, fixed_fallback 2, no_divergence 2 |
| Rounds | 188 |
| Diverged / matched everywhere / invalid / no data | 146 / 33 / 2 / 5 |
| Invalid replies (after one retry) | 1% of rounds |
| Divergence kinds (value / missing hit / expression error) | 138 / 7 / 1 |
| Breakpoints per valid round (mean) | 1.03 |
| Fixes that passed the public tests, of fixes tried after a divergence | 146 of 146 |
| Fixes tried in the entry function (vs a helper) | 144 of 146 |
| Fallback fixes after a full match (C) that passed | 2 of 2 |
| Attempts that returned a fix | 148 (99%) |
| Rounds per returned fix (mean) | 1.23 |


