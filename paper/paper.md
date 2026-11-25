---
title: "Measure, Don't Imagine: Hypothesis-Driven Bug Localization for LLM Debugging"
author: |
  Vedantt Koul, Rishabh Ravi Kumar, Arjun Mamidala \
  CSC 591, NC State University, Fall 2026 \
  \url{https://github.com/ved-ntt/hypothesis-driven-mgdebugger}
date: ""
geometry: margin=0.75in
fontsize: 10pt
documentclass: article
mainfont: TeX Gyre Termes
classoption: twocolumn
header-includes: |
  ```{=latex}
  \usepackage{booktabs}
  \setlength{\columnsep}{0.25in}
  \usepackage{titlesec}
  \titlespacing*{\section}{0pt}{6pt}{3pt}
  \titlespacing*{\subsection}{0pt}{4pt}{2pt}
  \titleformat*{\section}{\normalsize\bfseries}
  \titleformat*{\subsection}{\small\bfseries}
  \setlength{\parskip}{2pt}
  \pagestyle{plain}
  ```
---

**Abstract.** MGDebugger repairs LLM-generated code by decomposing a program into a tree of subfunctions,
writing tests for each, and asking the model to *simulate* execution to find the bug. We replace simulated
execution with real measurement. Variant C keeps MGDebugger's tree but makes the model state a hypothesis and
predict variable values, which the program then confirms or refutes by running. Variant D drops the tree: the
model places breakpoints with the values a correct program would hold, one real run records the actual values,
and the first mismatch marks the bug. With Claude Haiku 5.5 on 151 HumanEvalFix bugs, C matches MGDebugger
(144 vs. 143 repairs on 148 shared problems) at similar cost. D repairs 149 of 151 at one tenth of the cost.
On 224 bugs from three held-out sets, D is 6 to 15 times cheaper than MGDebugger and not less accurate.
Code, data, logs and all reports are public at the URL above.

# 1 Introduction

Code written by large language models (LLMs) often contains small mistakes that keep it from passing its tests.
Most LLM debuggers fix such code by reasoning about what it *would* do. MGDebugger [1] is a strong example. It
splits buggy code into a hierarchy of subfunctions, generates tests for each one, and debugs bottom-up while
the model traces execution in its own reasoning. It reports a 97.6% repair rate on HumanEvalFix [2].

This design has two costs. First, the traces are imagined. The model writes down variable values it believes
the code produces, and nothing checks them; a wrong trace leads directly to a wrong fix. Second, the hierarchy
is expensive. In our reproduction, decomposing the program and generating tests for every subfunction took
about 80% of MGDebugger's tokens.

Scientific debugging [6] offers a different loop: form a hypothesis, make a prediction, run an experiment, and
accept only what the experiment confirms. We ask two questions:

* **RQ1.** Does replacing simulated execution with real experiments *inside* MGDebugger's hierarchy change
  repair success or cost? (variant C)
* **RQ2.** Can real experiments *replace* the hierarchy, and does that hold on bugs not used in its design?
  (variant D)

Our contributions are the two variants, a cleaned and corrected evaluation harness for MGDebugger, and a
held-out evaluation, planned before it was run, on 224 model-written bugs.

# 2 Related Work

**Execution-free LLM debugging.** Self-debugging approaches feed test failures back to the model and let it
explain and revise the code. MGDebugger [1] adds a hierarchy of subfunctions and an LLM-simulated executor that
traces variable states. It is our baseline.

**Execution-grounded debugging.** AutoSD [5] prompts an LLM to generate hypotheses about a bug and test them by
running a real debugger, following Zeller's scientific debugging [6]. Our variant C applies the same principle at
each node of MGDebugger's hierarchy, with a harness instead of the model deciding whether a hypothesis holds.
Variant D adapts the idea to fault localization: the model's predictions become breakpoint assertions, and the
first violated one localizes the bug.

**Benchmarks.** HumanEvalFix [2] contains 164 hand-written bugs in HumanEval [3] solutions. MGDebugger also
evaluates on wrong solutions that code models wrote for HumanEval and MBPP [4]; we use those as held-out sets.

# 3 Method

All variants share one pipeline: run the given (public) tests, debug if one fails, and score the result on
hidden tests. They differ only in how the bug is found and fixed. Figure 1 shows one round of C and of D on
the same buggy function.

\begin{figure}[t]\footnotesize
\begin{verbatim}
4 def find_longest_suffix(s):
5     suffix_start = 0
6     for i in range(len(s)):
7         if is_palindrome(s[i:]):
8             suffix_start = i   # keeps the
9     return suffix_start        # last match

Failing test: find_longest_suffix('cata')
  expected 1, got 3

C: hypothesis "later matches overwrite the
   first, longest one"; predicts that
   suffix_start takes [0, 1, 3]
   real run: [0, 1, 3] -> confirmed -> fix

D: breakpoint at line 9 on suffix_start,
   expected [1]
   real run: [3] -> diverges at line 9
   -> rewrite find_longest_suffix
\end{verbatim}
\caption{One round of C and of D on the same bug.}
\end{figure}

## 3.1 A: MGDebugger (baseline)

MGDebugger converts the buggy code into a tree of subfunctions, asks the model to write tests for each, and
tests the tree bottom-up. At a failing subfunction, the model simulates its execution step by step and proposes
a fix. An outer loop repeats the whole process until the program passes; we allow 2 outer attempts instead of
the paper's 10 to bound cost. The harness corrections of Section 4 apply to every variant, including A.

## 3.2 C: hypothesis loop inside the tree

C keeps decomposition, test generation and the bottom-up order. Only the debug step at a failing subfunction
changes. For up to 3 rounds:

1. The model receives the program, the failing test and its actual output, and returns one hypothesis with a
   prediction: the sequence of values chosen variables will take, e.g. `{"i": [1, 2, 3]}`.
2. The subfunction runs on the failing test in a sandboxed child process with a timeout and a memory cap. A
   tracer built on `sys.settrace` records every value the chosen variables take.
3. A harness compares prediction and observation, normalizing tuples versus lists and float precision. The
   model never judges its own prediction.
4. Only a confirmed hypothesis may drive a fix. The fix replaces that subfunction and must pass its tests.
   Rejected hypotheses, and confirmed ones whose fix failed, enter a memory for the next round.

If no round produces a passing fix, the function is left unchanged. MGDebugger's simulated debugger is never
called, so every repair C makes rests on a recorded prediction and observation.

## 3.3 D: breakpoint localization

D removes decomposition and test generation. Given the first failing given test, each round works as follows:

1. The model sees the program with line numbers and places 1 to 3 breakpoints. A breakpoint is a line, an
   expression, and the values that expression should have each time the line is reached *if the program were
   correct*.
2. One sandboxed run records the real values. Each value is taken just before its line executes, once per
   loop iteration or recursive call.
3. The earliest recorded value that differs from the expected one localizes the bug. A line reached fewer times
   than expected also counts as a divergence.
4. The model rewrites the function that contains the divergent line (or a helper it calls), given the
   evidence ("at line 9, `suffix_start` should be 1 but was 3"). The fix must pass every given test.

Breakpoints are validated before they run: the line must start a statement inside a function, and calls are
limited to ones without side effects, so a breakpoint cannot change the program's state. An invalid reply gets
one retry with the errors quoted. D adds three rules to this loop:

* **R1. Observe, don't recompute.** An expression must read program state (a variable, element, slice,
  attribute, or its length) or copy a piece of the program's own code on that line. Without this rule the
  model often writes the *correct* formula as the expression. That formula always matches the expected value,
  so the bug stays hidden.
* **R2. A full match is evidence.** If every breakpoint matches but the output is still wrong, the error lies
  after those points. One fix attempt receives the matched values as evidence instead of giving up.
* **R3. Keep partial progress.** A fix that makes more given tests pass, without breaking any, becomes the
  program for the next round, which then localizes the next failing test.

D grew out of an earlier version, **L**, without these rules. We report L as an ablation.

# 4 Experimental Setup

**Model and settings.** Claude Haiku 5.5 through an OpenAI-compatible endpoint, for every variant. The endpoint
does not accept temperatures below 1.0, so all runs sample at 1.0. Each problem gets 2 outer attempts; C and D
use at most 3 rounds per attempt; sandboxed runs time out after 5 s. Problems run in 4 parallel shards.

**Data.** HumanEvalFix [2] has 164 bugs; 13 of them pass every given test, so no debugger that sees only the
given tests can detect them, which leaves 151. The held-out sets are wrong solutions that code models wrote,
taken from MGDebugger's repository: DeepSeek-Coder on HumanEval (32 usable bugs), StarCoder on HumanEval (88),
and DeepSeek-Coder on MBPP (104). A bug is usable if it fails a given test, that test can be parsed, and the
reference solution passes it.

**Harness corrections.** Reproducing MGDebugger, we found defects that affect every variant and fixed them for
all. Test results were compared as strings, so `(1, 2)` failed against `[1, 2]`. The test parser dropped or
crashed on given tests of 4 HumanEvalFix problems. A function returning a set crashed the debug prompt. A test
that timed out kept running in a thread of the debugger's own process. Tests now run in a child process;
re-running all 808 recorded HumanEvalFix attempts this way reproduced every verdict.

**Scoring.** A problem is *repaired* if the first attempt that passes the given tests also passes the hidden
tests. This is what a deployed debugger could achieve. (The MGDebugger paper selects attempts by the hidden
tests; the repository reports both.) Variants are compared on the problems both runs completed, with a
two-sided exact McNemar test on the discordant problems. Cost is computed from logged tokens at Haiku 5.5 prices.

# 5 Results

## 5.1 RQ1: C matches MGDebugger

\begin{table}[h]\small\centering
\caption{HumanEvalFix (151 detectable bugs).}
\begin{tabular}{lrrr}\toprule
 & Repaired & \$/repair & Calls/problem \\ \midrule
A (MGDebugger) & 143/148 & 0.0102 & 10.8 \\
C (hypotheses) & 147/151 & 0.0105 & 13.6 \\
L (D without R1--R3) & 129/151 & 0.0019 & 3.5 \\
D (breakpoints) & 149/151 & 0.0010 & 2.3 \\ \bottomrule
\end{tabular}\end{table}

On the 148 problems both completed, C repaired 144 and A 143 (only A: 2, only C: 3, p = 1.0), at 4% higher cost
per repair. The loop behaved as intended: of 327 hypotheses, 233 were confirmed and 91 refuted by the real run,
and only 3 replies were invalid after a retry. The refuted 28% are mistaken beliefs that A would have turned
directly into a fix. A confirmed hypothesis did not guarantee a working fix, though: 40 of 180 loop calls
confirmed a hypothesis whose fix then failed the function's tests.

The benchmark leaves little room to separate A and C. MGDebugger's decomposition step rewrites the code, and in
49 of A's and 61 of C's repairs that rewrite alone passed every test, so neither debug step ran. On the 76
problems where both runs' first decomposition left a failing function, A repaired 71 and C 72.

## 5.2 RQ2: D replaces the tree at a tenth of the cost

Paired with A on 148 problems, D repaired 146 vs. 143 (only A: 2, only D: 5, p = 0.45). Two more D runs repaired
150 of 151 each (147 vs. 143 paired, p = 0.22), so D's run-to-run variation is small. Table 2 shows where the
cost goes.

\begin{table}[h]\small\centering
\caption{Share of cost by pipeline stage (HumanEvalFix).}
\begin{tabular}{lrrr}\toprule
Stage & A & C & D \\ \midrule
Decompose & 12\% & 13\% & -- \\
Derive tests per subfunction & 66\% & 67\% & -- \\
Debug (simulate / hypothesis) & 22\% & 15\% & -- \\
Breakpoints & -- & -- & 69\% \\
Fix & -- & 6\% & 31\% \\ \midrule
Cost per problem & \$0.0099 & \$0.0102 & \$0.0010 \\ \bottomrule
\end{tabular}\end{table}

D needs 2.3 LLM calls per problem because its first round found a divergence in 82% of attempts (126 of 153).
Once a divergence was found, the fix passed every time (149 of 149): a precise location and the wrong value are
enough evidence for the fix step. A full HumanEvalFix run took about 6 minutes for D and about an hour for A.

**Ablation: R1 is what makes D work.** Variant L repaired only 129 bugs. Table 3 splits the bugs by location:
20 of L's 22 misses were bugs inside a `return` expression. There, every value computed before the line is
correct, so no breakpoint taken before the line can differ. L's model then tended to write the correct formula
as its expression. In HumanEval/4, which divides by `mean` instead of `len(numbers)`, it checked
`sum(...) / len(numbers)`, saw the expected 1.0, and never attempted a fix. Under R1 it must copy the program's
`sum(...) / mean`, which is 1.6, and the bug is found. In L's fully matched rounds, 116 of 217 breakpoints were
such self-written formulas, against 24 of 176 in rounds that found the bug. R2 added only 2 to 4 repairs per run.

\begin{table}[h]\small\centering
\caption{HumanEvalFix repairs by bug location (148 problems).}
\begin{tabular}{lrrrrr}\toprule
Bug location & n & A & C & L & D \\ \midrule
Inside a \texttt{return} & 66 & 65 & 64 & 46 & 65 \\
Elsewhere & 82 & 78 & 80 & 80 & 81 \\ \bottomrule
\end{tabular}\end{table}

## 5.3 Held-out evaluation

D was designed after inspecting L's failures on HumanEvalFix, so its HumanEvalFix result could reflect that
benchmark. We therefore froze D, wrote the evaluation plan, and only then ran A and D on the three held-out
sets (Table 4).

\begin{table}[h]\small\centering
\caption{Held-out sets: repairs, discordant pairs (only A / only D) with McNemar p, and cost ratio A/D.}
\begin{tabular}{lrrrr}\toprule
Set & A & D & Disc. (p) & Cost \\ \midrule
HumanEval, DeepSeek & 31/32 & 30/32 & 2/1 (1.0) & 9.4x \\
HumanEval, StarCoder & 85/88 & 81/88 & 4/0 (0.13) & 8.0x \\
MBPP, DeepSeek & 77/104 & 70/104 & 18/11 (0.27) & 6.6x \\
\quad exact checks & 69/104 & 89/104 & 3/23 ($<$0.001) & 14.8x \\ \midrule
Pooled, as planned & 193 & 181 & 24/12 (0.065) & \\
Pooled, exact MBPP & 193 & 200 & 11/18 (0.27) & \\ \bottomrule
\end{tabular}\end{table}

As planned, D repaired 181 of 224 bugs and A 193 (p = 0.065). The cost advantage held on every set. Most of
the accuracy gap came from MBPP, and inspecting it revealed one more harness defect: comparing results by value
treats a list and a tuple as equal, but the benchmark's own `assert` does not. MBPP functions often return
tuples, and 33 of D's accepted fixes returned lists where the assert expects a tuple. We added an option that
checks each given test with its own assert and shows the expected value as the assert writes it. Because it was
added after seeing these results, we report it separately. With exact checks D repaired 89 of 104 MBPP bugs,
more than A in either of its MBPP runs (77 with the lenient check, 69 with the exact one; p = 0.017 against
the better). Pooled, D then repairs 200 bugs to A's 193 (p = 0.27).

The remaining held-out misses point to two gaps in D. Two StarCoder "solutions" were empty function bodies, so
D had no line to observe and never attempted a fix, while A rewrote the function. And with thin given tests,
both variants sometimes accepted fixes that passed the given tests but failed hidden ones (A 16 times, D 19).

# 6 Discussion

**Measuring matches imagining on accuracy and wins on cost.** Inside the hierarchy (C), real experiments neither
helped nor hurt repair rates, but they made each fix traceable to a recorded observation and refuted 28% of the
model's hypotheses before they could cause a wrong fix. Replacing the hierarchy (D) was the larger change. A few
well-chosen measurements localized the bugs in these programs as well as decomposing the code and testing every
piece, at about a tenth of the tokens.

**Why it works.** A breakpoint turns the model's knowledge of the *specification* into a checkable claim about
the program's state, and the run checks it. The model only has to know what a correct program would compute at
a point, not to simulate the buggy one. R1 matters because it keeps that claim about the program rather than
about the model's own formula.

**Threats to validity.** We used one model at temperature 1.0 and measured run-to-run variation only for D. D's
rules were developed on HumanEvalFix; the held-out check addresses this, but its exact-check result is post-hoc.
All benchmark programs are short, mostly single functions with a single bug. MGDebugger's hierarchy is meant
for longer programs with several interacting bugs, which we did not evaluate. Our numbers are not directly
comparable to the MGDebugger paper's (different model, 2 attempts instead of 10, undetectable bugs excluded,
corrected harness).

# 7 Conclusion

We replaced imagined execution in an LLM debugger with measured execution. Inside MGDebugger's hierarchy,
hypotheses tested by real runs match the original's accuracy and back every fix with evidence. Used to replace
the hierarchy, breakpoints with predicted values match or exceed MGDebugger's accuracy at roughly a tenth of its
cost, on its benchmark and on 224 held-out bugs. Future work should evaluate long programs with several bugs and
let D count a fix as progress when a divergent breakpoint value becomes correct.

**Availability.** Code, cleaned data, per-call logs, run summaries, all reports and a one-command reproduction
script: \url{https://github.com/ved-ntt/hypothesis-driven-mgdebugger}.

# References

\small

[1] Y. Shi, S. Wang, C. Wan, M. Wang, X. Gu. From Code to Correctness: Closing the Last Mile of Code Generation with Hierarchical Debugging. ICSE 2026; arXiv:2410.01215.

[2] N. Muennighoff et al. OctoPack: Instruction Tuning Code Large Language Models. ICLR 2024.

[3] M. Chen et al. Evaluating Large Language Models Trained on Code. arXiv:2107.03374, 2021.

[4] J. Austin et al. Program Synthesis with Large Language Models. arXiv:2108.07732, 2021.

[5] S. Kang, B. Chen, S. Yoo, J.-G. Lou. Explainable Automated Debugging via Large Language Model-driven Scientific Debugging. Empirical Software Engineering, doi:10.1007/s10664-024-10594-x; arXiv:2304.02195.

[6] A. Zeller. Why Programs Fail: A Guide to Systematic Debugging. 2nd ed., Morgan Kaufmann, 2009.
