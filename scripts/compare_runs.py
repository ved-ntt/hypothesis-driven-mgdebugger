"""Compare two runs (any variants: A, B, C) on the same problems.

  python3 scripts/compare_runs.py <run_1> <run_2> [--out results/<name>.md]

Each run is a folder from run_experiment.sh (merged) or run_variant_a.sh. Problems attempted by both
runs are paired. Reports, for each variant:
  - repairs under both scoring rules: public-selection (the first attempt that passes the given
    tests, graded on the hidden tests: what a real debugger gets) and hidden-selection (the paper's
    rule: any attempt passes the hidden tests)
  - the paired split (both / only one / neither) and an exact McNemar test on it
  - cost: dollars, tokens and LLM calls per problem, dollars per repair, and cost by pipeline stage
  - repairs by bug type (HumanEvalFix)
  - when both runs decompose (A, B): repairs the debug step produced vs decomposition alone
  - for B: what the hypothesis loop did; for C: what the breakpoint loop did
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
    if variant(run) == "B":
        return collections.Counter((nd.get("task_id"), nd.get("attempt")) for nd in run["nodes"])
    return collections.Counter((c["task_id"], c["attempt"]) for c in run["calls"]
                               if c.get("ok") and c.get("stage") == "debug")


DESCRIPTION = {"A": "MGDebugger", "B": "hypothesis loop", "C": "breakpoint localization"}


LEGACY = {"C": "B", "L" + "2": "C", "D": "C"}   # development names -> final letters


def variant(run: dict) -> str:
    v = run["params"].get("VARIANT", "A")
    if run["params"].get("VARIANT_SCHEME") != 2:
        # runs made before the letters were final used development names
        v = LEGACY.get(v, v)
    return v


def debug_step_section(runs: dict, shared: list, key: str) -> list:
    """Separate repairs the debug step produced from repairs the decomposition rewrite produced.

    Only for two decomposing variants (A, B). MGDebugger's first step rewrites the buggy code into
    subfunctions. If that rewrite already passes every test, no function fails and the debug step
    never runs; such repairs say nothing about the debug steps. The fair comparison is on problems
    where the first decomposition left a failing function in BOTH runs.
    """
    (x, X), (y, Y) = runs.items()
    inv = {x: debug_invocations(X), y: debug_invocations(Y)}

    def selected_attempt(p):
        return p.get("first_public_attempt") if key == "fixed_public_selection" else p.get("first_hidden_attempt")

    lines = ["## Where the debug step mattered", "",
             "The decomposition step rewrites the code; when that rewrite already passes every test, the debug "
             "step never runs. Those repairs do not distinguish the debug steps.", "",
             f"| | {x} | {y} |", "| --- | --- | --- |"]
    no_debug, with_debug = {}, {}
    for v, R in runs.items():
        fixed = [t for t in shared if R["problems"][t].get(key)]
        no_debug[v] = sum(1 for t in fixed if inv[v][(t, selected_attempt(R["problems"][t]))] == 0)
        with_debug[v] = len(fixed) - no_debug[v]
    lines.append(f"| Repairs where the debug step never ran (decomposition alone) | {no_debug[x]} | {no_debug[y]} |")
    lines.append(f"| Repairs where the debug step ran | {with_debug[x]} | {with_debug[y]} |")

    hard = [t for t in shared if inv[x][(t, 1)] > 0 and inv[y][(t, 1)] > 0]
    m = len(hard)
    if m:
        fx = sum(bool(X["problems"][t].get(key)) for t in hard)
        fy = sum(bool(Y["problems"][t].get(key)) for t in hard)
        ox = [t for t in hard if X["problems"][t].get(key) and not Y["problems"][t].get(key)]
        oy = [t for t in hard if Y["problems"][t].get(key) and not X["problems"][t].get(key)]
        p = mcnemar_exact(len(ox), len(oy))
        lines.append(f"| **Problems where both runs' first decomposition left a failing function** | {m} | {m} |")
        lines.append(f"| Repaired among those | {pct(fx, m)} | {pct(fy, m)} |")
        lines += ["", f"On those {m} problems: only {x} repaired {len(ox)}, only {y} repaired {len(oy)}; exact McNemar "
                  f"p = {p:.3f}.", f"- Only {x}: {', '.join(ox) or 'none'}", f"- Only {y}: {', '.join(oy) or 'none'}"]
    lines.append("")
    return lines


def stage_cost_section(runs: dict, shared: set, n: int) -> list:
    """Dollars per problem by pipeline stage: where each variant spends its tokens."""
    by = {}
    for v, R in runs.items():
        d = collections.defaultdict(float)
        for c in R["calls"]:
            if c.get("ok") and c.get("task_id") in shared:
                d[c.get("stage", "other")] += c.get("cost_usd", 0.0)
        by[v] = d
    stages = sorted(set().union(*[set(d) for d in by.values()]),
                    key=lambda s: -max(by[v].get(s, 0) for v in by))
    (x, y) = runs
    tx, ty = sum(by[x].values()), sum(by[y].values())
    lines = ["## Cost by stage (per problem)", "", f"| Stage | {x} | {y} |", "| --- | --- | --- |"]
    for s in stages:
        cx, cy = by[x].get(s, 0.0), by[y].get(s, 0.0)
        lines.append(f"| {s} | ${cx / n:.5f} ({100 * cx / tx if tx else 0:.0f}%) | ${cy / n:.5f} ({100 * cy / ty if ty else 0:.0f}%) |")
    lines.append("")
    return lines


def c_loop_section(label: str, nodes: list) -> list:
    rounds = [r for nd in nodes for r in nd.get("rounds", [])]
    verdicts = collections.Counter(r["verdict"] for r in rounds)
    judged = verdicts["confirmed"] + verdicts["rejected"]
    statuses = collections.Counter(nd["status"] for nd in nodes)
    fixes = sum(1 for nd in nodes if nd.get("returned_fix"))
    rounds_to_fix = [len(nd.get("rounds", [])) for nd in nodes if nd.get("returned_fix")]
    return [f"## What {label}'s hypothesis loop did", "",
            "| Measure | Value |", "| --- | --- |",
            f"| Debug calls (failing functions handed to the loop) | {len(nodes)} |",
            f"| Outcomes | {', '.join(f'{k} {v}' for k, v in statuses.most_common())} |",
            f"| Hypotheses (rounds) | {len(rounds)} |",
            f"| Confirmed / rejected / invalid | {verdicts['confirmed']} / {verdicts['rejected']} / {verdicts['invalid']} |",
            f"| Confirm rate (of valid hypotheses) | {100 * verdicts['confirmed'] / judged:.0f}% |" if judged else
            "| Confirm rate | n/a |",
            f"| Invalid replies (after one retry) | {100 * verdicts['invalid'] / len(rounds):.0f}% of rounds |" if rounds else
            "| Invalid replies | n/a |",
            f"| Debug calls that returned a fix | {fixes} ({100 * fixes / len(nodes):.0f}%) |" if nodes else
            "| Debug calls that returned a fix | n/a |",
            f"| Rounds per returned fix (mean) | {sum(rounds_to_fix) / len(rounds_to_fix):.2f} |" if rounds_to_fix else
            "| Rounds per returned fix | n/a |", ""]


def l_loop_section(label: str, nodes: list) -> list:
    rounds = [r for nd in nodes for r in nd.get("rounds", [])]
    verdicts = collections.Counter(r["verdict"] for r in rounds)
    statuses = collections.Counter(nd["status"] for nd in nodes)
    fixes = sum(1 for nd in nodes if nd.get("returned_fix"))
    bps = [b for r in rounds for b in (r.get("breakpoints") or [])]
    diverged = [r for r in rounds if r.get("verdict") == "diverged"]
    kinds = collections.Counter((r.get("divergence") or {}).get("kind") for r in diverged)
    in_entry = sum(1 for nd in nodes for r in nd.get("rounds", [])
                   if r.get("verdict") == "diverged" and r.get("fix_function") == nd.get("function"))
    fixed_rounds = [len(nd.get("rounds", [])) for nd in nodes if nd.get("returned_fix")]
    fix_success = sum(1 for r in diverged if str(r.get("outcome", "")).startswith("fixed"))
    fallback = [r for r in rounds if r.get("verdict") == "fallback"]
    fallback_ok = sum(1 for r in fallback if str(r.get("outcome", "")).startswith("fixed"))
    return [f"## What {label}'s breakpoint loop did", "",
            "| Measure | Value |", "| --- | --- |",
            f"| Attempts (calls of the loop; one per outer attempt) | {len(nodes)} |",
            f"| Outcomes | {', '.join(f'{k} {v}' for k, v in statuses.most_common())} |",
            f"| Rounds | {len(rounds)} |",
            f"| Diverged / matched everywhere / invalid / no data | {verdicts['diverged']} / {verdicts['no_divergence']} / "
            f"{verdicts['invalid']} / {verdicts['no_data']} |",
            f"| Invalid replies (after one retry) | {100 * verdicts['invalid'] / len(rounds):.0f}% of rounds |" if rounds else
            "| Invalid replies | n/a |",
            f"| Divergence kinds (value / missing hit / expression error) | {kinds['value']} / {kinds['missing']} / {kinds['error']} |",
            f"| Breakpoints per valid round (mean) | {len(bps) / (len(rounds) - verdicts['invalid']):.2f} |"
            if len(rounds) > verdicts["invalid"] else "| Breakpoints per valid round | n/a |",
            f"| Fixes that passed the public tests, of fixes tried after a divergence | {fix_success} of {len(diverged)} |",
            f"| Fixes tried in the entry function (vs a helper) | {in_entry} of {len(diverged)} |",
            f"| Fallback fixes after a full match (R2) that passed | {fallback_ok} of {len(fallback)} |",
            f"| Attempts that returned a fix | {fixes} ({100 * fixes / len(nodes):.0f}%) |" if nodes else
            "| Attempts that returned a fix | n/a |",
            f"| Rounds per returned fix (mean) | {sum(fixed_rounds) / len(fixed_rounds):.2f} |" if fixed_rounds else
            "| Rounds per returned fix | n/a |", ""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_1")
    ap.add_argument("run_2")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    R1, R2 = load_run(args.run_1), load_run(args.run_2)
    v1, v2 = variant(R1), variant(R2)
    x, y = (v1, v2) if v1 != v2 else (f"{v1}1", f"{v2}2")
    runs = {x: R1, y: R2}

    shared = sorted(set(R1["problems"]) & set(R2["problems"]), key=lambda t: int(t.split("/")[-1]))
    n = len(shared)
    if n == 0:
        raise SystemExit("the two runs have no problem in common")
    seeds_name = os.path.basename(R1["params"]["input_seeds"])
    k_note = "; ".join(f"k = {R['params'].get('HYPOTHESIS_K')} ({v})" for v, R in runs.items()
                       if variant(R) in ("B", "C"))
    out = [f"# {x} vs {y}: {seeds_name}", "",
           f"- {x} = {DESCRIPTION.get(v1, v1)}, {y} = {DESCRIPTION.get(v2, v2)}",
           f"- Model: {R1['params'].get('MODEL')} ({x}), {R2['params'].get('MODEL')} ({y})",
           f"- Problems compared: {n} (attempted by both runs; {x} attempted {len(R1['problems'])}, "
           f"{y} attempted {len(R2['problems'])})",
           f"- Outer attempts: {R1['params'].get('MAX_OUTER_RETRY_EFFECTIVE')} ({x}), "
           f"{R2['params'].get('MAX_OUTER_RETRY_EFFECTIVE')} ({y}); harness {R1['params'].get('HARNESS')} / "
           f"{R2['params'].get('HARNESS')}; exact given tests {bool(R1['params'].get('EXACT_TESTS'))} / "
           f"{bool(R2['params'].get('EXACT_TESTS'))}" + (f"; {k_note}" if k_note else ""),
           f"- Runs: `{R1['run']}`, `{R2['run']}`", ""]

    cost = {v: per_problem_cost(R, set(shared)) for v, R in runs.items()}
    rows = []
    for rule, key in (("public-selection", "fixed_public_selection"), ("hidden-selection (paper)", "fixed_hidden_selection")):
        rows.append((rule, key, {v: sum(bool(R["problems"][t].get(key)) for t in shared) for v, R in runs.items()}))

    out += ["## Repairs", "",
            f"| Metric | {x} ({DESCRIPTION.get(v1, v1)}) | {y} ({DESCRIPTION.get(v2, v2)}) |", "| --- | --- | --- |"]
    for rule, _, f in rows:
        out.append(f"| Repaired, {rule} | {pct(f[x], n)} | {pct(f[y], n)} |")
    tot = {v: sum(cost[v]["cost"].values()) for v in runs}
    toks = {v: sum(cost[v]["tokens"].values()) for v in runs}
    ncalls = {v: sum(cost[v]["calls"].values()) for v in runs}
    fixed_pub = rows[0][2]
    out.append(f"| Cost, total | ${tot[x]:.3f} | ${tot[y]:.3f} |")
    out.append(f"| Cost per problem | ${tot[x] / n:.4f} | ${tot[y] / n:.4f} |")
    out.append("| Cost per repair (public-selection) | "
               + " | ".join(f"${tot[v] / fixed_pub[v]:.4f}" if fixed_pub[v] else "n/a" for v in runs) + " |")
    out.append(f"| Tokens per problem | {toks[x] / n:,.0f} | {toks[y] / n:,.0f} |")
    out.append(f"| LLM calls per problem | {ncalls[x] / n:.1f} | {ncalls[y] / n:.1f} |")
    if tot[x] and tot[y]:
        lo, hi = sorted((x, y), key=lambda v: tot[v])
        out.append(f"| Cost ratio | | {hi} costs {tot[hi] / tot[lo]:.1f}x {lo} |")
    out.append("")

    out += ["## Paired outcome (public-selection)", ""]
    key = "fixed_public_selection"
    both = sum(1 for t in shared if R1["problems"][t].get(key) and R2["problems"][t].get(key))
    only_x = [t for t in shared if R1["problems"][t].get(key) and not R2["problems"][t].get(key)]
    only_y = [t for t in shared if R2["problems"][t].get(key) and not R1["problems"][t].get(key)]
    neither = n - both - len(only_x) - len(only_y)
    p = mcnemar_exact(len(only_x), len(only_y))
    out += [f"| Both repaired | Only {x} | Only {y} | Neither |", "| --- | --- | --- | --- |",
            f"| {both} | {len(only_x)} | {len(only_y)} | {neither} |", "",
            f"Exact McNemar test on the {len(only_x) + len(only_y)} discordant problems: p = {p:.3f}"
            + (" (difference unlikely to be chance at the 0.05 level)." if p < 0.05 else
               " (not significant at the 0.05 level: the difference could be chance)."), "",
            f"- Only {x}: {', '.join(only_x) or 'none'}", f"- Only {y}: {', '.join(only_y) or 'none'}", ""]

    bug_type = {t: R1["problems"][t].get("bug_type") for t in shared}
    if any(bug_type.values()):
        out += ["## By bug type (public-selection)", "", f"| Bug type | Problems | {x} | {y} |", "| --- | --- | --- | --- |"]
        for bt in sorted({b for b in bug_type.values() if b}):
            ts = [t for t in shared if bug_type[t] == bt]
            fx = sum(bool(R1["problems"][t].get(key)) for t in ts)
            fy = sum(bool(R2["problems"][t].get(key)) for t in ts)
            out.append(f"| {bt} | {len(ts)} | {pct(fx, len(ts))} | {pct(fy, len(ts))} |")
        out.append("")

    out += stage_cost_section(runs, set(shared), n)
    if v1 in ("A", "B") and v2 in ("A", "B"):
        out += debug_step_section(runs, shared, key)

    for v, R in runs.items():
        nodes = [nd for nd in R["nodes"] if nd.get("task_id") in set(shared)]
        if variant(R) == "B" and nodes:
            out += c_loop_section(v, nodes)
        elif variant(R) == "C" and nodes:
            out += l_loop_section(v, nodes)

    text = "\n".join(out) + "\n"
    print(text)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            f.write(text)
        print(f"written to {args.out}")


if __name__ == "__main__":
    main()
