# A vs C: humanevalfix.jsonl

- Model: claude-haiku-5-5 (A), claude-haiku-5-5 (C)
- Problems compared: 12 (attempted by both runs; A attempted 12, C attempted 12)
- Outer attempts: 2 (A), 2 (C); harness fixed / fixed; hypotheses per debug call k = 3
- Runs: `output_data/experiments/humanevalfix_A_20261123-155801`, `output_data/experiments/humanevalfix_C_20261123-160202`

## Repairs

| Metric | A (simulated trace) | C (hypothesis loop) |
| --- | --- | --- |
| Repaired, public-selection | 11 (91.7%) | 12 (100.0%) |
| Repaired, hidden-selection (paper) | 12 (100.0%) | 12 (100.0%) |
| Cost, total | $0.071 | $0.070 |
| Cost per problem | $0.0060 | $0.0058 |
| Cost per repair (public-selection) | $0.0065 | $0.0058 |
| Tokens per problem | 18,118 | 19,667 |
| LLM calls per problem | 7.8 | 9.1 |

## Paired outcome (public-selection)

| Both repaired | Only A | Only C | Neither |
| --- | --- | --- | --- |
| 11 | 0 | 1 | 0 |

Exact McNemar test on the 1 discordant problems: p = 1.000 (not significant at the 0.05 level: the difference could be chance).

- Only A: none
- Only C: HumanEval/3

## By bug type (public-selection)

| Bug type | Problems | A | C |
| --- | --- | --- | --- |
| excess logic | 1 | 1 (100.0%) | 1 (100.0%) |
| missing logic | 3 | 3 (100.0%) | 3 (100.0%) |
| operator misuse | 2 | 1 (50.0%) | 2 (100.0%) |
| value misuse | 2 | 2 (100.0%) | 2 (100.0%) |
| variable misuse | 4 | 4 (100.0%) | 4 (100.0%) |

## Where the debug step mattered

The decomposition step rewrites the code; when that rewrite already passes every test, the debug step never runs, in A or C. Those repairs do not distinguish the variants.

| | A | C |
| --- | --- | --- |
| Repairs where the debug step never ran (decomposition alone) | 7 | 8 |
| Repairs where the debug step ran | 4 | 4 |
| **Problems where both runs' first decomposition left a failing function** | 1 | 1 |
| Repaired among those | 1 (100.0%) | 1 (100.0%) |

On those 1 problems: only A repaired 0, only C repaired 0; exact McNemar p = 1.000.
- Only A: none
- Only C: none

## What C's hypothesis loop did

| Measure | Value |
| --- | --- |
| Debug calls (failing functions handed to the loop) | 4 |
| Outcomes | fixed 3, fix_failed 1 |
| Hypotheses (rounds) | 6 |
| Confirmed / rejected / invalid | 5 / 1 / 0 |
| Confirm rate (of valid hypotheses) | 83% |
| Invalid replies (after one retry) | 0% of rounds |
| Debug calls that returned a fix | 3 (75%) |
| Rounds per returned fix (mean) | 1.00 |

