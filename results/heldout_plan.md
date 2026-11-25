# Held-out check of variant C (written before any held-out run)

(Variant letters were made final after this plan was written; only the names were changed since.)

## Why

C's rules were developed while working on HumanEvalFix, and C was then scored on HumanEvalFix. Its
result there (149 and 150 of 151, against MGDebugger's 143 of 148, at a tenth of the cost) could be a
fit to that benchmark. This check runs the frozen C and MGDebugger (A) on bug sets that played no part
in designing C.

## What C is (frozen at commit 2b57d71)

Three rules, none of which mentions a benchmark, a bug type or a code pattern:

1. **Observe the program, don't recompute it.** A breakpoint expression must read program state (a
   variable, element, slice, attribute, `len` of one) or copy a piece of the program's own code on that
   line. A breakpoint is a measurement of the program; an expression the model writes itself measures the
   model's own formula. This is the same reason a test oracle must not be computed by the code under test.
2. **A full match is evidence.** If every breakpoint matched the expected values and the output is still
   wrong, the error is after those points; the fix step is told so instead of giving up.
3. **Keep partial progress.** A fix that makes more public tests pass without breaking any becomes the
   program for the next round, localized again on the next failing test. Programs with several bugs can
   then be repaired one bug at a time.

Changes since the HumanEvalFix C runs, made before any held-out run: the prompt no longer says that
"the bug is often in the last line" (a frequency observed on HumanEvalFix) and its examples no longer
resemble a HumanEvalFix problem; it states the general fact instead (a breakpoint shows the state before
its line, so a line's own computation is checked by copying its expressions); rule 3 was added. C is
therefore run again on HumanEvalFix as well.

## Held-out sets

Bugs written by code models, not planted by hand: wrong algorithms, several errors in one program,
missing cases. Different from HumanEvalFix's single-token planted bugs. Only the data format of these
sets was looked at (to parse their given tests), not C's behaviour on them.

| Set | Usable bugs | What differs from HumanEvalFix |
| --- | --- | --- |
| HumanEval, DeepSeek-Coder seeds | 32 | the model's own wrong solutions |
| HumanEval, StarCoder seeds | 88 | a weaker model: messier code, often several bugs |
| MBPP, DeepSeek-Coder seeds | 104 | another benchmark; one given test per problem |

"Usable": the buggy code fails a given test, at least one given test parses, and the reference solution
passes the given tests (`data_cleaning.md`).

## Runs


Same settings as before: Claude Haiku 5.5, fixed harness, 2 outer attempts, k = 3, 4 shards.
The runs were made with `scripts/run_heldout.sh` at commit 2b57d71; `scripts/reproduce.sh heldout` runs the same comparison with the current code.

## What is reported, whatever it shows

- Repairs under public-selection on the problems both variants completed, the paired split and the exact
  McNemar p-value; hidden-selection as a second view.
- Cost per problem and per repair, tokens, LLM calls.
- C's loop statistics (divergence found on the first round, fixes after a full match, partial progress).

C counts as a general improvement over A if, on the held-out sets pooled, it repairs at least as many bugs
as A within chance (no significant loss) at a fraction of A's cost. A significant loss on any set is
reported as a limitation, with the cases that explain it.
