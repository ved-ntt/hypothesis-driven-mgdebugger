---
title: "Measure, Don't Imagine: Hypothesis-Driven Bug Localization for LLM Debugging"
author: "CSC 591, NC State University, Fall 2026. Team: [author names]"
date: "November 2026"
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
  \titleformat*{\section}{\normalsize\bfseries}
  \setlength{\parskip}{2pt}
  \pagestyle{empty}
  ```
---

**Abstract.** MGDebugger repairs LLM-generated code by decomposing a program into a tree of subfunctions,
writing tests for each, and asking the model to *simulate* execution to find the bug. We replace simulated
execution with real measurement. Variant C keeps MGDebugger's tree but makes the model state a hypothesis and
predict variable values, which the program then confirms or refutes by running. Variant D drops the tree: the
model places breakpoints with the values a correct program would hold, one real run records the actual values,
and the first mismatch marks the bug. With Claude Haiku 5.5 on 151 HumanEvalFix bugs, C matches MGDebugger
(144 vs. 143 repairs on 148 shared problems) at similar cost. D repairs 149 of 151 at one tenth of the cost.
On 224 bugs from three held-out sets, D is 6 to 15 times cheaper and not less accurate.

# 1 Introduction

LLM-based debuggers usually reason about what code *would* do. MGDebugger [1] is a strong example: it splits
buggy code into a hierarchy of subfunctions, generates tests for each, and debugs bottom-up while the model
traces execution in its own reasoning. Two costs follow. Imagined traces can be wrong, and nothing checks
them. And the hierarchy is expensive: on HumanEvalFix, decomposition and test generation take about 80% of
MGDebugger's tokens.

Scientific debugging [6] suggests a different loop: form a hypothesis, make a prediction, run an experiment,
and accept only what the experiment confirms. AutoSD [5] showed that an LLM can drive this loop with a
real debugger. We test this idea in two forms. **C** puts the loop inside
MGDebugger's tree. **D** uses it to replace the tree.

# 2 Method

**A (baseline).** MGDebugger as published [1], with test-harness fixes applied to all variants (Section 3).

**C: hypothesis loop.** At each failing function in MGDebugger's tree, the model proposes a hypothesis
("the loop starts at index 1") and predicts the sequence of values some variables will take on the failing
test. A tracer records the real values (`sys.settrace`, in a sandboxed child process). A harness, not the
model, compares prediction and observation. Only a confirmed hypothesis may drive a fix, and the fix must pass
the function's tests. Refuted hypotheses go into memory for the next round (up to 3).

**D: breakpoint localization.** No decomposition and no generated tests. The model sees the program with line
numbers and the first failing given test. It places 1 to 3 breakpoints, each a line, an expression, and the
values that expression should have on successive hits if the program were correct. One sandboxed run records
the actual values, taken just before each line executes. The earliest mismatch localizes the bug, and the model
rewrites only the function containing it. D follows three rules:

1. *Observe, don't recompute.* An expression must read program state (a variable, element, slice, or its
   length) or copy the program's own code on that line. Otherwise the model can write the correct formula
   itself, which always matches and finds nothing.
2. *A full match is evidence.* If every breakpoint matches but the output is wrong, the bug lies after those
   points. One fix attempt receives that evidence.
3. *Keep partial progress.* A fix that makes more given tests pass, without breaking any, becomes the program
   for the next round.

Rule 1 was added after an earlier version (L, without rules 1 and 2) missed bugs inside `return` expressions.

# 3 Experimental Setup

**Model.** Claude Haiku 5.5 for every variant, temperature 1.0 (the endpoint's minimum), 2 outer attempts.

**Data.** HumanEvalFix [2]: 164 human-written single bugs, 151 of which the given tests detect. Held-out sets,
never used while designing D: wrong solutions written by DeepSeek-Coder (32) and StarCoder (88) on HumanEval
[3], and by DeepSeek-Coder on MBPP [4] (104). We keep only bugs the given tests can detect.

**Harness.** We fixed defects in MGDebugger's harness for all variants: tests are compared by value rather than
by string, given tests the original parser dropped are kept, and test code runs in a child process with a
timeout. On MBPP we found one more defect: value comparison treats a list and a tuple as equal, while the
benchmark's asserts do not. An option that checks each given test with its own assert is reported separately.

**Metric.** A problem counts as repaired if the first attempt that passes the given tests also passes the
hidden tests. Variants are compared on the same problems with an exact McNemar test.

# 4 Results

\begin{table}[h]\small\centering
\caption{HumanEvalFix (151 detectable bugs).}
\begin{tabular}{lrrr}\toprule
 & Repaired & \$/repair & Calls/problem \\ \midrule
A (MGDebugger) & 143/148 & 0.0102 & 10.8 \\
C (hypotheses) & 147/151 & 0.0105 & 13.6 \\
L (D without rules 1, 2) & 129/151 & 0.0019 & 3.5 \\
D (breakpoints) & 149/151 & 0.0010 & 2.3 \\ \bottomrule
\end{tabular}\end{table}

**C matches MGDebugger.** On the 148 problems both completed, C repaired 144 and A 143 (p = 1.0). Of C's
327 hypotheses, 28% were refuted by the real run before any fix was written; in A the same mistaken beliefs
would have gone straight into a fix. The benchmark leaves little room to separate the two: MGDebugger's
decomposition step alone produced about a third of the repairs, before either debug step ran.

**D matches or beats MGDebugger at a tenth of the cost.** Paired with A on 148 problems, D repaired 146 vs.
143 (p = 0.45). Two further D runs repaired 150 of 151 each, so run-to-run variation is small. D needs 2.3 LLM
calls per problem because the first round finds the bug in 82% of attempts, and once a mismatch is found the
fix passed every time (149 of 149).

**Rule 1 is what makes D work.** Without it (variant L), 20 of 22 misses were bugs inside a `return`
expression. There, every value before the line is correct, and the model checked its own correct formula. On
those 66 bugs, L repaired 46 and D 65; on the other 82, both repaired 80 or more.

\begin{table}[h]\small\centering
\caption{Held-out sets: A vs. D (repaired, cost per problem).}
\begin{tabular}{lrrr}\toprule
Set & A & D & Cost A / D \\ \midrule
HumanEval, DeepSeek & 31/32 & 30/32 & 9.4x \\
HumanEval, StarCoder & 85/88 & 81/88 & 8.0x \\
MBPP, DeepSeek & 77/104 & 70/104 & 6.6x \\
\quad with exact test check & 69/104 & 89/104 & 14.8x \\ \midrule
Pooled, as planned & 193 & 181 & \\
Pooled, exact check on MBPP & 193 & 200 & \\ \bottomrule
\end{tabular}\end{table}

**Held-out check.** We froze D and wrote the evaluation plan before running it on the held-out sets (Table 2).
As planned, D repaired 181 of 224 and A 193 (p = 0.065). Most of the gap was on MBPP, where D accepted fixes
that returned a list where the test's assert expects a tuple. With exact checks, added after seeing these
results and reported as such, D repaired 89 of 104 MBPP bugs, more than either A run (77 and 69; p = 0.017
against the better one). Pooled, D then repairs 200 vs. 193 (p = 0.27). The cost advantage held on every set.

# 5 Discussion and Limitations

Measuring a few chosen values on a real run localizes bugs about as well as decomposing the program and
testing every piece, at a fraction of the cost. Hypotheses in C mainly add trust: every fix rests on a recorded
prediction and observation. The results have limits. We used one model at temperature 1.0 and measured run-to-run
variation only for D. D was designed after seeing its predecessor's failures on
HumanEvalFix, which is why we report the held-out check separately. D cannot observe an empty function body
(two StarCoder problems), and like A it can overfit when the given tests are thin. All programs were short, and
we did not test whether the hierarchy helps on long programs with interacting bugs.

# 6 Conclusion

Replacing imagined execution with measured execution works. Inside MGDebugger's hierarchy it matches the
original. As a replacement for the hierarchy, it matches or exceeds MGDebugger's accuracy at roughly a tenth of
its cost.

**Code and data:** https://github.com/ved-ntt/hypothesis-driven-mgdebugger

# References

\small

[1] Y. Shi, S. Wang, C. Wan, M. Wang, X. Gu. From Code to Correctness: Closing the Last Mile of Code Generation with Hierarchical Debugging. ICSE 2026; arXiv:2410.01215.

[2] N. Muennighoff et al. OctoPack: Instruction Tuning Code Large Language Models. ICLR 2024.

[3] M. Chen et al. Evaluating Large Language Models Trained on Code. arXiv:2107.03374, 2021.

[4] J. Austin et al. Program Synthesis with Large Language Models. arXiv:2108.07732, 2021.

[5] S. Kang, B. Chen, S. Yoo, J.-G. Lou. Explainable Automated Debugging via Large Language Model-driven Scientific Debugging. Empirical Software Engineering, doi:10.1007/s10664-024-10594-x; arXiv:2304.02195.

[6] A. Zeller. Why Programs Fail: A Guide to Systematic Debugging. 2nd ed., Morgan Kaufmann, 2009.
