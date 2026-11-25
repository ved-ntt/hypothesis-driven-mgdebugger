# A vs D: humanevalfix.jsonl

- A = MGDebugger, D = breakpoint localization
- Model: claude-haiku-5-5 (A), claude-haiku-5-5 (D)
- Problems compared: 148 (attempted by both runs; A attempted 148, D attempted 151)
- Outer attempts: 2 (A), 2 (D); harness fixed / fixed; k = 3 (D)
- Runs: `/mnt/c/Users/Vedantt/Downloads/NCSU/sem3/Testing/hypothesis-driven-mgdebugger/MGDebugger/src/output_data/experiments/humanevalfix_A_20261123-160502`, `/mnt/c/Users/Vedantt/Downloads/NCSU/sem3/Testing/hypothesis-driven-mgdebugger/MGDebugger/src/output_data/experiments/humanevalfix_L2_20261124-141314`

## Repairs

| Metric | A (MGDebugger) | D (breakpoint localization) |
| --- | --- | --- |
| Repaired, public-selection | 143 (96.6%) | 147 (99.3%) |
| Repaired, hidden-selection (paper) | 145 (98.0%) | 147 (99.3%) |
| Cost, total | $1.463 | $0.166 |
| Cost per problem | $0.0099 | $0.0011 |
| Cost per repair (public-selection) | $0.0102 | $0.0011 |
| Tokens per problem | 28,760 | 3,912 |
| LLM calls per problem | 10.8 | 2.4 |
| Cost ratio | | A costs 8.8x D |

## Paired outcome (public-selection)

| Both repaired | Only A | Only D | Neither |
| --- | --- | --- | --- |
| 142 | 1 | 5 | 0 |

Exact McNemar test on the 6 discordant problems: p = 0.219 (not significant at the 0.05 level: the difference could be chance).

- Only A: HumanEval/123
- Only D: HumanEval/32, HumanEval/80, HumanEval/83, HumanEval/87, HumanEval/130

## By bug type (public-selection)

| Bug type | Problems | A | D |
| --- | --- | --- | --- |
| excess logic | 27 | 25 (92.6%) | 27 (100.0%) |
| function misuse | 7 | 7 (100.0%) | 7 (100.0%) |
| missing logic | 25 | 25 (100.0%) | 25 (100.0%) |
| operator misuse | 25 | 24 (96.0%) | 25 (100.0%) |
| value misuse | 41 | 41 (100.0%) | 40 (97.6%) |
| variable misuse | 23 | 21 (91.3%) | 23 (100.0%) |

## Cost by stage (per problem)

| Stage | A | D |
| --- | --- | --- |
| derive_tests | $0.00651 (66%) | $0.00000 (0%) |
| debug | $0.00215 (22%) | $0.00000 (0%) |
| decompose | $0.00123 (12%) | $0.00000 (0%) |
| localize | $0.00000 (0%) | $0.00079 (71%) |
| fix | $0.00000 (0%) | $0.00033 (29%) |

## What D's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 149 |
| Outcomes | fixed 143, fixed_fallback 4, no_divergence 2 |
| Rounds | 196 |
| Diverged / matched everywhere / invalid / no data | 145 / 39 / 2 / 6 |
| Invalid replies (after one retry) | 1% of rounds |
| Divergence kinds (value / missing hit / expression error) | 135 / 9 / 1 |
| Breakpoints per valid round (mean) | 1.02 |
| Fixes that passed the public tests, of fixes tried after a divergence | 143 of 145 |
| Fixes tried in the entry function (vs a helper) | 145 of 145 |
| Fallback fixes after a full match (D) that passed | 4 of 4 |
| Attempts that returned a fix | 147 (99%) |
| Rounds per returned fix (mean) | 1.29 |

