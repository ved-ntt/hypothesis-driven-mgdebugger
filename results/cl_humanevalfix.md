# C vs L: humanevalfix.jsonl

- C = hypothesis loop, L = breakpoint localization
- Model: claude-haiku-5-5 (C), claude-haiku-5-5 (L)
- Problems compared: 151 (attempted by both runs; C attempted 151, L attempted 151)
- Outer attempts: 2 (C), 2 (L); harness fixed / fixed; k = 3 (C); k = 3 (L)
- Runs: `MGDebugger/src/output_data/experiments/humanevalfix_C_20261123-170409`, `MGDebugger/src/output_data/experiments/humanevalfix_L_20261123-190742`

## Repairs

| Metric | C (hypothesis loop) | L (breakpoint localization) |
| --- | --- | --- |
| Repaired, public-selection | 147 (97.4%) | 129 (85.4%) |
| Repaired, hidden-selection (paper) | 148 (98.0%) | 129 (85.4%) |
| Cost, total | $1.538 | $0.246 |
| Cost per problem | $0.0102 | $0.0016 |
| Cost per repair (public-selection) | $0.0105 | $0.0019 |
| Tokens per problem | 33,035 | 5,866 |
| LLM calls per problem | 13.6 | 3.5 |
| Cost ratio | | C costs 6.3x L |

## Paired outcome (public-selection)

| Both repaired | Only C | Only L | Neither |
| --- | --- | --- | --- |
| 125 | 22 | 4 | 0 |

Exact McNemar test on the 26 discordant problems: p = 0.001 (difference unlikely to be chance at the 0.05 level).

- Only C: HumanEval/4, HumanEval/11, HumanEval/27, HumanEval/29, HumanEval/30, HumanEval/38, HumanEval/52, HumanEval/54, HumanEval/65, HumanEval/66, HumanEval/77, HumanEval/79, HumanEval/84, HumanEval/103, HumanEval/115, HumanEval/118, HumanEval/120, HumanEval/123, HumanEval/125, HumanEval/127, HumanEval/159, HumanEval/162
- Only L: HumanEval/74, HumanEval/80, HumanEval/87, HumanEval/91

## By bug type (public-selection)

| Bug type | Problems | C | L |
| --- | --- | --- | --- |
| excess logic | 27 | 27 (100.0%) | 24 (88.9%) |
| function misuse | 7 | 7 (100.0%) | 2 (28.6%) |
| missing logic | 28 | 28 (100.0%) | 23 (82.1%) |
| operator misuse | 25 | 24 (96.0%) | 22 (88.0%) |
| value misuse | 41 | 40 (97.6%) | 37 (90.2%) |
| variable misuse | 23 | 21 (91.3%) | 21 (91.3%) |

## Cost by stage (per problem)

| Stage | C | L |
| --- | --- | --- |
| derive_tests | $0.00682 (67%) | $0.00000 (0%) |
| hypothesis | $0.00148 (15%) | $0.00000 (0%) |
| localize | $0.00000 (0%) | $0.00133 (82%) |
| decompose | $0.00129 (13%) | $0.00000 (0%) |
| fix | $0.00059 (6%) | $0.00030 (18%) |

## What C's hypothesis loop did

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

## What L's breakpoint loop did

| Measure | Value |
| --- | --- |
| Attempts (calls of the loop; one per outer attempt) | 186 |
| Outcomes | fixed 132, no_divergence 52, fix_failed 2 |
| Rounds | 333 |
| Diverged / matched everywhere / invalid / no data | 135 / 188 / 5 / 5 |
| Divergence kinds (value / missing hit / expression error) | 119 / 16 / 0 |
| Breakpoints per valid round (mean) | 1.21 |
| Fixes that passed the public tests, of fixes tried after a divergence | 132 of 135 |
| Fixes tried in the entry function (vs a helper) | 133 of 135 |
| Attempts that returned a fix | 132 (71%) |
| Rounds per returned fix (mean) | 1.30 |

