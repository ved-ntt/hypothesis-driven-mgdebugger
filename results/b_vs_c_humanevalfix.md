# B vs C: humanevalfix.jsonl

- B = hypothesis loop, C = breakpoint localization
- Model: claude-haiku-5-5 (B), claude-haiku-5-5 (C)
- Problems compared: 151 (attempted by both runs; B attempted 151, C attempted 151)
- Outer attempts: 2 (B), 2 (C); harness fixed / fixed; k = 3 (B); k = 3 (C)
- Runs: `MGDebugger/src/output_data/experiments/humanevalfix_B_20261123-170409`, `MGDebugger/src/output_data/experiments/humanevalfix_C_20261123-202524`

## Repairs

| Metric | B (hypothesis loop) | C (breakpoint localization) |
| --- | --- | --- |
| Repaired, public-selection | 147 (97.4%) | 149 (98.7%) |
| Repaired, hidden-selection (paper) | 148 (98.0%) | 149 (98.7%) |
| Cost, total | $1.538 | $0.154 |
| Cost per problem | $0.0102 | $0.0010 |
| Cost per repair (public-selection) | $0.0105 | $0.0010 |
| Tokens per problem | 33,035 | 3,573 |
| LLM calls per problem | 13.6 | 2.3 |
| Cost ratio | | B costs 10.0x C |

## Paired outcome (public-selection)

| Both repaired | Only B | Only C | Neither |
| --- | --- | --- | --- |
| 145 | 2 | 4 | 0 |

Exact McNemar test on the 6 discordant problems: p = 0.688 (not significant at the 0.05 level: the difference could be chance).

- Only B: HumanEval/38, HumanEval/123
- Only C: HumanEval/74, HumanEval/80, HumanEval/87, HumanEval/91

## By bug type (public-selection)

| Bug type | Problems | B | C |
| --- | --- | --- | --- |
| excess logic | 27 | 27 (100.0%) | 27 (100.0%) |
| function misuse | 7 | 7 (100.0%) | 7 (100.0%) |
| missing logic | 28 | 28 (100.0%) | 27 (96.4%) |
| operator misuse | 25 | 24 (96.0%) | 25 (100.0%) |
| value misuse | 41 | 40 (97.6%) | 40 (97.6%) |
| variable misuse | 23 | 21 (91.3%) | 23 (100.0%) |

## Cost by stage (per problem)

| Stage | B | C |
| --- | --- | --- |
| derive_tests | $0.00682 (67%) | $0.00000 (0%) |
| hypothesis | $0.00148 (15%) | $0.00000 (0%) |
| decompose | $0.00129 (13%) | $0.00000 (0%) |
| localize | $0.00000 (0%) | $0.00070 (69%) |
| fix | $0.00059 (6%) | $0.00032 (31%) |

## What B's hypothesis loop did

| Measure | Value |
| --- | --- |
| Debug calls (failing functions handed to the loop) | 182 |
| Outcomes | fixed 123, fix_failed 40, no_confirmed 18, already_passing 1 |
| Hypotheses (rounds) | 331 |
| Confirmed / rejected / invalid | 234 / 94 / 3 |
| Confirm rate (of valid hypotheses) | 71% |
| Invalid replies (after one retry) | 1% of rounds |
| Debug calls that returned a fix | 123 (68%) |
| Rounds per returned fix (mean) | 1.28 |

## What C's breakpoint loop did

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
| Fallback fixes after a full match (C) that passed | 2 of 2 |
| Attempts that returned a fix | 151 (99%) |
| Rounds per returned fix (mean) | 1.23 |


