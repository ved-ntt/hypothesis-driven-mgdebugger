"""Summarize one MGDebugger run directory (output_data/<dataset>/<model>/<timestamp>).

Reports accuracy and repair success rate (RSR) two ways:
  hidden-selection: the paper's rule; an attempt counts if it passes the hidden tests
  public-selection: take the first attempt that passes the given tests, grade it on hidden tests
plus tokens and LLM calls per problem and per stage, and the paper's numbers for comparison.

  python scripts/summarize.py MGDebugger/src/output_data/humaneval/seed/deepseekcoder/<timestamp>
"""
import collections, glob, json, os, sys

# Shi et al. Table 1 (HumanEval / MBPP) and Table 4 (HumanEvalFix), RSR %
PAPER = {
    ("humaneval", "deepseekcoder"): {"acc": 94.5, "rsr": 76.3},
    ("humaneval", "codeqwen"): {"acc": 91.5, "rsr": 64.1},
    ("humaneval", "codestral"): {"acc": 94.5, "rsr": 77.5},
    ("mbpp", "deepseekcoder"): {"acc": 80.0, "rsr": 39.0},
    ("mbpp", "codeqwen"): {"acc": 80.8, "rsr": 41.1},
    ("mbpp", "codestral"): {"acc": 76.8, "rsr": 32.9},
    ("humanevalfix", "deepseekcoder"): {"rsr": 97.6},
    ("humanevalfix", "codeqwen"): {"rsr": 87.8},
    ("humanevalfix", "codestral"): {"rsr": 90.2},
}


def main(run_dir):
    params = json.load(open(os.path.join(run_dir, "params.json")))
    seeds_path = params["input_seeds"]
    for base in [os.path.join(run_dir, *[".."] * k) for k in range(3, 8)]:
        if os.path.exists(os.path.join(base, seeds_path)):
            seeds_path = os.path.join(base, seeds_path)
            break
    seeds = [json.loads(l) for l in open(seeds_path)]
    n_total = len(seeds)
    n_solved_before = sum(s["is_solved"] for s in seeds)
    n_buggy = n_total - n_solved_before

    res_files = [f for f in glob.glob(os.path.join(run_dir, "*_debugging_seeds_from_*.jsonl"))]
    problems = [json.loads(l) for l in open(res_files[0])]
    done = [p for p in problems if "attempts" in p or p.get("debugged") is not None]
    attempted = [p for p in problems if "attempts" in p]

    def count(key):
        return sum(bool(p.get(key)) for p in attempted)

    fixed_h, fixed_p = count("fixed_hidden_selection"), count("fixed_public_selection")
    n = len(attempted)

    calls = [json.loads(l) for l in open(os.path.join(run_dir, "llm_calls.jsonl"))] \
        if os.path.exists(os.path.join(run_dir, "llm_calls.jsonl")) else []
    ok = [c for c in calls if c.get("ok")]
    by_stage = collections.defaultdict(lambda: [0, 0])
    for c in ok:
        by_stage[c["stage"]][0] += 1
        by_stage[c["stage"]][1] += c["prompt_tokens"] + c["completion_tokens"]

    # tokens each scoring rule would have spent (attempts up to where it stops)
    def tokens_until(p, key):
        stop = p.get(key) or len(p["attempts"])
        return sum(a["tokens"] for a in p["attempts"][:stop])
    tok_h = sum(tokens_until(p, "first_hidden_attempt") for p in attempted)
    tok_p = sum(tokens_until(p, "first_public_attempt") for p in attempted)

    parts = seeds_path.replace("\\", "/").split("/")
    dataset = next((d for d in ["humanevalfix", "humaneval", "mbpp"] if d in parts), "?")
    seed_model = parts[-2]
    if dataset == "humanevalfix":  # buggy code is human-written; key the paper row by the debugging model
        m = params["MODEL"].lower()
        seed_model = next((k for k, pat in [("deepseekcoder", "deepseek"), ("codeqwen", "codeqwen"),
                                            ("codestral", "codestral")] if pat in m), m)
    paper = PAPER.get((dataset, seed_model), {})

    print(f"Run: {run_dir}")
    print(f"Model: {params['MODEL']}  stop_on={params.get('STOP_ON')}  T={params.get('TEMPERATURE_EFFECTIVE')}"
          f"  min_p={params.get('USE_MIN_P')}  outer={params.get('MAX_OUTER_RETRY_EFFECTIVE')}")
    print(f"Dataset: {dataset}  seeds from: {seed_model}  problems: {n_total}  buggy: {n_buggy}  debugged so far: {n}")
    if n < n_buggy:
        print(f"  (partial run: RSR below is over the {n} problems attempted)")
    print()
    print(f"{'':28}{'fixed':>8}{'RSR %':>9}{'acc %':>9}{'tokens/problem':>16}")
    for name, fixed, tok in [("hidden-selection (paper)", fixed_h, tok_h), ("public-selection", fixed_p, tok_p)]:
        rsr = 100 * fixed / n if n else 0
        acc = 100 * (n_solved_before + fixed) / n_total if n == n_buggy else float("nan")
        print(f"{name:28}{fixed:>8}{rsr:>9.1f}{acc:>9.1f}{(tok / n if n else 0):>16.0f}")
    if paper:
        print(f"{'paper':28}{'':>8}{paper.get('rsr', float('nan')):>9.1f}{paper.get('acc', float('nan')):>9.1f}")
    print()
    print(f"LLM calls: {len(ok)} ok, {len(calls) - len(ok)} failed;  per problem: {len(ok) / n if n else 0:.1f}")
    for stage, (k, t) in sorted(by_stage.items()):
        print(f"  {stage:14} calls {k:>6}   tokens {t:>10}   per problem {k / n if n else 0:>6.1f} calls, {t / n if n else 0:>8.0f} tok")
    spent = sum(c.get("cost_usd", 0) for c in ok)
    if spent:
        print(f"Spend: ${spent:.3f} total, ${spent / n if n else 0:.4f} per problem")
    stopped = [p["task_id"] for p in problems if p.get("budget_stopped")]
    if stopped:
        print(f"Budget reached during {stopped}; excluded. Problems never started: "
              f"{len(problems) - n - len(stopped)}")
    overfit = sum(1 for p in attempted for a in p["attempts"] if a["public_pass"] and not a["hidden_pass"])
    print(f"Attempts passing public but failing hidden tests (overfit): {overfit}")
    # Did the winning attempt call the debug step at all? If not, the "fix" came from the
    # decomposition rewrite (temperature 0.8), picked out by the hidden tests.
    debug_calls = collections.Counter((c["task_id"], c["attempt"]) for c in ok if c["stage"] == "debug")
    winners = [p for p in attempted if p.get("first_hidden_attempt")]
    no_debug = [p["task_id"] for p in winners if debug_calls[(p["task_id"], p["first_hidden_attempt"])] == 0]
    print(f"Hidden-selection fixes whose winning attempt made no debug call: {len(no_debug)} of {len(winners)}"
          + (f"  {no_debug}" if no_debug else ""))
    attempts_hist = collections.Counter(p.get("first_hidden_attempt") for p in attempted)
    print(f"First attempt that passed hidden tests: {dict(sorted(attempts_hist.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)))}")


if __name__ == "__main__":
    main(sys.argv[1])
