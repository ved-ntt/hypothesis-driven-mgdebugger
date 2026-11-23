"""Compare a variant A run and a variant C run on the same problems.

  python3 scripts/compare_runs.py <run_A> <run_C> [--out results/ab_<dataset>.md]

Each run is a folder from run_experiment.sh (merged) or run_variant_a.sh. Problems attempted by both
runs are paired. Reports, for each variant:
  - repairs under both scoring rules: public-selection (the first attempt that passes the given
    tests, graded on the hidden tests: what a real debugger gets) and hidden-selection (the paper's
    rule: any attempt passes the hidden tests)
  - the paired split (both / only A / only C / neither) and an exact McNemar test on it
  - cost: dollars, tokens and LLM calls per problem, and dollars per repair
  - repairs by bug type (HumanEvalFix)
  - for C: what the hypothesis loop did (rounds, verdicts, confirm rate, fixes returned)
"""
import argparse
import collections
import glob
import json
import math
import os


def load_run(run: str) -> dict:
    params = json.load(open(os.path.join(run, "params.json")))
    files = glob.glob(os.path.join(run, "*_debugging_seeds_from_*.jsonl"))
    if not files:
        raise SystemExit(f"no results file in {run}")
    problems = {}
    for f in files:
        for line in open(f):
            p = json.loads(line)
            if "attempts" in p and p.get("attempts"):
                problems[p["task_id"]] = p
    calls_path = os.path.join(run, "llm_calls.jsonl")
    calls = [json.loads(l) for l in open(calls_path)] if os.path.exists(calls_path) else []
    nodes_path = os.path.join(run, "hypothesis_nodes.jsonl")
    nodes = [json.loads(l) for l in open(nodes_path) if l.strip()] if os.path.exists(nodes_path) else []
    return {"run": run, "params": params, "problems": problems, "calls": calls, "nodes": nodes}


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value for b and c discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def pct(x: int, n: int) -> str:
    return f"{x} ({100 * x / n:.1f}%)" if n else "0"


def per_problem_cost(run: dict, task_ids) -> dict:
    cost = collections.defaultdict(float)
    tokens = collections.defaultdict(int)
    calls = collections.defaultdict(int)
    for c in run["calls"]:
        if c.get("ok") and c.get("task_id") in task_ids:
            cost[c["task_id"]] += c.get("cost_usd", 0.0)
            tokens[c["task_id"]] += c.get("prompt_tokens", 0) + c.get("completion_tokens", 0)
            calls[c["task_id"]] += 1
    return {"cost": cost, "tokens": tokens, "calls": calls}


def debug_invocations(run: dict) -> collections.Counter:
    """(task_id, attempt) -> times the debug step ran: A's debug_function calls, C's loop calls."""
    if run["params"].get("VARIANT", "A") == "C":
        return collections.Counter((nd.get("task_id"), nd.get("attempt")) for nd in run["nodes"])
    return collections.Counter((c["task_id"], c["attempt"]) for c in run["calls"]
                               if c.get("ok") and c.get("stage") == "debug")


def debug_step_section(A: dict, C: dict, shared: list, key: str) -> list:
    """Separate repairs the debug step produced from repairs the decomposition rewrite produced.

    MGDebugger's first step rewrites the buggy code into subfunctions. If that rewrite already passes
    every test, no function fails and the debug step never runs, in A or C; such repairs say nothing
    about A vs C. The fair comparison is on problems where the first decomposition left a failing
    function in BOTH runs, so both debug steps had to work.
    """
    inv = {"A": debug_invocations(A), "C": debug_invocations(C)}
    runs = {"A": A, "C": C}

    def selected_attempt(p):
        return p.get("first_public_attempt") if key == "fixed_public_selection" else p.get("first_hidden_attempt")

    lines = ["## Where the debug step mattered", "",
             "The decomposition step rewrites the code; when that rewrite already passes every test, the debug "
             "step never runs, in A or C. Those repairs do not distinguish the variants.", "",
             "| | A | C |", "| --- | --- | --- |"]
    no_debug, with_debug = {}, {}
    for v in ("A", "C"):
        fixed = [t for t in shared if runs[v]["problems"][t].get(key)]
        no_debug[v] = sum(1 for t in fixed if inv[v][(t, selected_attempt(runs[v]["problems"][t]))] == 0)
        with_debug[v] = len(fixed) - no_debug[v]
    lines.append(f"| Repairs where the debug step never ran (decomposition alone) | {no_debug['A']} | {no_debug['C']} |")
    lines.append(f"| Repairs where the debug step ran | {with_debug['A']} | {with_debug['C']} |")

    hard = [t for t in shared if inv["A"][(t, 1)] > 0 and inv["C"][(t, 1)] > 0]
    m = len(hard)
    if m:
        fa = sum(bool(A["problems"][t].get(key)) for t in hard)
        fc = sum(bool(C["problems"][t].get(key)) for t in hard)
        oa = [t for t in hard if A["problems"][t].get(key) and not C["problems"][t].get(key)]
        oc = [t for t in hard if C["problems"][t].get(key) and not A["problems"][t].get(key)]
        p = mcnemar_exact(len(oa), len(oc))
        lines.append(f"| **Problems where both runs' first decomposition left a failing function** | {m} | {m} |")
        lines.append(f"| Repaired among those | {pct(fa, m)} | {pct(fc, m)} |")
        lines += ["", f"On those {m} problems: only A repaired {len(oa)}, only C repaired {len(oc)}; exact McNemar "
                  f"p = {p:.3f}.", f"- Only A: {', '.join(oa) or 'none'}", f"- Only C: {', '.join(oc) or 'none'}"]
    lines.append("")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_a")
    ap.add_argument("run_c")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    A, C = load_run(args.run_a), load_run(args.run_c)
    for run, want in ((A, "A"), (C, "C")):
        got = run["params"].get("VARIANT", "A")
        if got != want:
            raise SystemExit(f"{run['run']} is variant {got}, expected {want}")

    shared = sorted(set(A["problems"]) & set(C["problems"]), key=lambda t: int(t.split("/")[-1]))
    n = len(shared)
    if n == 0:
        raise SystemExit("the two runs have no problem in common")
    seeds_name = os.path.basename(A["params"]["input_seeds"])
    out = [f"# A vs C: {seeds_name}", "",
           f"- Model: {A['params'].get('MODEL')} (A), {C['params'].get('MODEL')} (C)",
           f"- Problems compared: {n} (attempted by both runs; A attempted {len(A['problems'])}, "
           f"C attempted {len(C['problems'])})",
           f"- Outer attempts: {A['params'].get('MAX_OUTER_RETRY_EFFECTIVE')} (A), "
           f"{C['params'].get('MAX_OUTER_RETRY_EFFECTIVE')} (C); harness {A['params'].get('HARNESS')} / "
           f"{C['params'].get('HARNESS')}; hypotheses per debug call k = {C['params'].get('HYPOTHESIS_K')}",
           f"- Runs: `{A['run']}`, `{C['run']}`", ""]

    cost = {v: per_problem_cost(r, set(shared)) for v, r in (("A", A), ("C", C))}
    rows = []
    for rule, key in (("public-selection", "fixed_public_selection"), ("hidden-selection (paper)", "fixed_hidden_selection")):
        fa = sum(bool(A["problems"][t].get(key)) for t in shared)
        fc = sum(bool(C["problems"][t].get(key)) for t in shared)
        rows.append((rule, key, fa, fc))

    out += ["## Repairs", "", "| Metric | A (simulated trace) | C (hypothesis loop) |", "| --- | --- | --- |"]
    for rule, _, fa, fc in rows:
        out.append(f"| Repaired, {rule} | {pct(fa, n)} | {pct(fc, n)} |")
    tot = {v: sum(cost[v]["cost"].values()) for v in ("A", "C")}
    toks = {v: sum(cost[v]["tokens"].values()) for v in ("A", "C")}
    ncalls = {v: sum(cost[v]["calls"].values()) for v in ("A", "C")}
    fixed_pub = {"A": rows[0][2], "C": rows[0][3]}
    out.append(f"| Cost, total | ${tot['A']:.3f} | ${tot['C']:.3f} |")
    out.append(f"| Cost per problem | ${tot['A'] / n:.4f} | ${tot['C'] / n:.4f} |")
    out.append("| Cost per repair (public-selection) | "
               + " | ".join(f"${tot[v] / fixed_pub[v]:.4f}" if fixed_pub[v] else "n/a" for v in ("A", "C")) + " |")
    out.append(f"| Tokens per problem | {toks['A'] / n:,.0f} | {toks['C'] / n:,.0f} |")
    out.append(f"| LLM calls per problem | {ncalls['A'] / n:.1f} | {ncalls['C'] / n:.1f} |")
    out.append("")

    out += ["## Paired outcome (public-selection)", ""]
    key = "fixed_public_selection"
    both = sum(1 for t in shared if A["problems"][t].get(key) and C["problems"][t].get(key))
    only_a = [t for t in shared if A["problems"][t].get(key) and not C["problems"][t].get(key)]
    only_c = [t for t in shared if C["problems"][t].get(key) and not A["problems"][t].get(key)]
    neither = n - both - len(only_a) - len(only_c)
    p = mcnemar_exact(len(only_a), len(only_c))
    out += ["| Both repaired | Only A | Only C | Neither |", "| --- | --- | --- | --- |",
            f"| {both} | {len(only_a)} | {len(only_c)} | {neither} |", "",
            f"Exact McNemar test on the {len(only_a) + len(only_c)} discordant problems: p = {p:.3f}"
            + (" (difference unlikely to be chance at the 0.05 level)." if p < 0.05 else
               " (not significant at the 0.05 level: the difference could be chance)."), "",
            f"- Only A: {', '.join(only_a) or 'none'}", f"- Only C: {', '.join(only_c) or 'none'}", ""]

    bug_type = {t: A["problems"][t].get("bug_type") for t in shared}
    if any(bug_type.values()):
        out += ["## By bug type (public-selection)", "", "| Bug type | Problems | A | C |", "| --- | --- | --- | --- |"]
        for bt in sorted({b for b in bug_type.values() if b}):
            ts = [t for t in shared if bug_type[t] == bt]
            fa = sum(bool(A["problems"][t].get(key)) for t in ts)
            fc = sum(bool(C["problems"][t].get(key)) for t in ts)
            out.append(f"| {bt} | {len(ts)} | {pct(fa, len(ts))} | {pct(fc, len(ts))} |")
        out.append("")

    out += debug_step_section(A, C, shared, key)

    nodes = [nd for nd in C["nodes"] if nd.get("task_id") in set(shared)]
    if nodes:
        rounds = [r for nd in nodes for r in nd.get("rounds", [])]
        verdicts = collections.Counter(r["verdict"] for r in rounds)
        judged = verdicts["confirmed"] + verdicts["rejected"]
        statuses = collections.Counter(nd["status"] for nd in nodes)
        fixes = sum(1 for nd in nodes if nd.get("returned_fix"))
        rounds_to_fix = [len(nd.get("rounds", [])) for nd in nodes if nd.get("returned_fix")]
        out += ["## What C's hypothesis loop did", "",
                "| Measure | Value |", "| --- | --- |",
                f"| Debug calls (failing functions handed to the loop) | {len(nodes)} |",
                f"| Outcomes | {', '.join(f'{k} {v}' for k, v in statuses.most_common())} |",
                f"| Hypotheses (rounds) | {len(rounds)} |",
                f"| Confirmed / rejected / invalid | {verdicts['confirmed']} / {verdicts['rejected']} / {verdicts['invalid']} |",
                f"| Confirm rate (of valid hypotheses) | {100 * verdicts['confirmed'] / judged:.0f}% |" if judged else
                "| Confirm rate | n/a |",
                f"| Invalid replies (after one retry) | {100 * verdicts['invalid'] / len(rounds):.0f}% of rounds |" if rounds else
                "| Invalid replies | n/a |",
                f"| Debug calls that returned a fix | {fixes} ({100 * fixes / len(nodes):.0f}%) |",
                f"| Rounds per returned fix (mean) | {sum(rounds_to_fix) / len(rounds_to_fix):.2f} |" if rounds_to_fix else
                "| Rounds per returned fix | n/a |", ""]

    text = "\n".join(out) + "\n"
    print(text)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            f.write(text)
        print(f"written to {args.out}")


if __name__ == "__main__":
    main()
