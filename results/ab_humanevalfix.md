# A vs C: humanevalfix.jsonl

- Model: claude-haiku-5-5 (A), claude-haiku-5-5 (C)
- Problems compared: 148 (attempted by both runs; A attempted 148, C attempted 151)
- Outer attempts: 2 (A), 2 (C); harness fixed / fixed; hypotheses per debug call k = 3
- Runs: `output_data/experiments/humanevalfix_A_20261123-160502`, `output_data/experiments/humanevalfix_C_20261123-170409`

## Repairs

| Metric | A (simulated trace) | C (hypothesis loop) |
| --- | --- | --- |
| Repaired, public-selection | 143 (96.6%) | 144 (97.3%) |
| Repaired, hidden-selection (paper) | 145 (98.0%) | 145 (98.0%) |
| Cost, total | $1.463 | $1.521 |
| Cost per problem | $0.0099 | $0.0103 |
| Cost per repair (public-selection) | $0.0102 | $0.0106 |
| Tokens per problem | 28,760 | 33,342 |
| LLM calls per problem | 10.8 | 13.7 |

## Paired outcome (public-selection)

| Both repaired | Only A | Only C | Neither |
| --- | --- | --- | --- |
| 141 | 2 | 3 | 2 |

Exact McNemar test on the 5 discordant problems: p = 1.000 (not significant at the 0.05 level: the difference could be chance).

- Only A: HumanEval/74, HumanEval/91
- Only C: HumanEval/32, HumanEval/83, HumanEval/130

## By bug type (public-selection)

| Bug type | Problems | A | C |
| --- | --- | --- | --- |
| excess logic | 27 | 25 (92.6%) | 27 (100.0%) |
| function misuse | 7 | 7 (100.0%) | 7 (100.0%) |
| missing logic | 25 | 25 (100.0%) | 25 (100.0%) |
| operator misuse | 25 | 24 (96.0%) | 24 (96.0%) |
| value misuse | 41 | 41 (100.0%) | 40 (97.6%) |
| variable misuse | 23 | 21 (91.3%) | 21 (91.3%) |

## Where the debug step mattered

The decomposition step rewrites the code; when that rewrite already passes every test, the debug step never runs, in A or C. Those repairs do not distinguish the variants.

| | A | C |
| --- | --- | --- |
| Repairs where the debug step never ran (decomposition alone) | 49 | 61 |
| Repairs where the debug step ran | 94 | 83 |
| **Problems where both runs' first decomposition left a failing function** | 76 | 76 |
| Repaired among those | 71 (93.4%) | 72 (94.7%) |

On those 76 problems: only A repaired 2, only C repaired 3; exact McNemar p = 1.000.
- Only A: HumanEval/74, HumanEval/91
- Only C: HumanEval/32, HumanEval/83, HumanEval/130

## What C's hypothesis loop did

| Measure | Value |
| --- | --- |
| Debug calls (failing functions handed to the loop) | 180 |
| Outcomes | fixed 122, fix_failed 40, no_confirmed 17, already_passing 1 |
| Hypotheses (rounds) | 327 |
| Confirmed / rejected / invalid | 233 / 91 / 3 |
| Confirm rate (of valid hypotheses) | 72% |
| Invalid replies (after one retry) | 1% of rounds |
| Debug calls that returned a fix | 122 (68%) |
| Rounds per returned fix (mean) | 1.28 |

