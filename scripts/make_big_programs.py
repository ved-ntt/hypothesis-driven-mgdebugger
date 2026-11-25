"""Pilot set of larger programs for A vs L2: several HumanEvalFix functions in one program.

  python3 scripts/make_big_programs.py [n=12] [seed=0]   -> data/clean/big_programs.jsonl

Each program = 1 or 2 buggy HumanEvalFix functions + 5 unrelated correct HumanEval functions + an entry
`run_all` that calls all of them and returns their results as a tuple. The first buggy function gets
run_all's arguments; every other function gets a fixed input from its own given tests. So the program is
~150 lines, the bug sits in a helper, not the entry, and half the programs have two bugs.

Given tests: run_all on the first buggy function's given inputs (expected values from the correct program).
Hidden tests: each buggy function's own HumanEval hidden tests, plus the given tests.
A pilot for "does L2 still work on bigger, multi-function, multi-bug programs", not a benchmark.
"""
import ast, json, os, random, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from hdmg.sandbox import run_call  # noqa: E402

def top_defs(code):
    return [n.name for n in ast.parse(code).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

def main(n=12, seed=0):
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "data/clean/humanevalfix.jsonl"))]
    simple = [r for r in rows if r["usable"] and len(top_defs(r["prompt"] + r["canonical_solution"])) == 1
              and len(top_defs(r["solution"])) == 1 and r["public_tests"]
              and all(isinstance(t["input"], dict) for t in r["public_tests"])]
    rng = random.Random(seed)
    rng.shuffle(simple)
    out, used = [], set()
    for i in range(n):
        n_bugs = 1 if i % 2 == 0 else 2
        bugs = [r for r in simple if r["task_id"] not in used][:n_bugs]
        used.update(b["task_id"] for b in bugs)
        others = [r for r in simple if r["task_id"] not in used][:5]
        used.update(o["task_id"] for o in others)
        first = bugs[0]
        params = list(first["public_tests"][0]["input"].keys())
        calls = [f"{first['entry_point']}({', '.join(params)})"]
        for r in bugs[1:] + others:
            args = ", ".join(f"{k}={v!r}" for k, v in r["public_tests"][0]["input"].items())
            calls.append(f"{r['entry_point']}({args})")
        entry = (f"def run_all({', '.join(params)}):\n"
                 f"    \"\"\"Runs every task of the program and returns their results as a tuple.\"\"\"\n"
                 f"    results = []\n" + "".join(f"    results.append({c})\n" for c in calls) +
                 f"    return tuple(results)\n")
        order = bugs + others
        rng.shuffle(order)
        def body(r, buggy):
            return (r["solution"] if buggy else r["prompt"] + r["canonical_solution"]).strip("\n")
        bug_ids = {b["task_id"] for b in bugs}
        buggy_prog = "\n\n\n".join(body(r, r["task_id"] in bug_ids) for r in order) + "\n\n\n" + entry
        good_prog = "\n\n\n".join(body(r, False) for r in order) + "\n\n\n" + entry
        public, given = [], []
        for t in first["public_tests"]:
            call = "run_all(" + ", ".join(f"{k}={v!r}" for k, v in t["input"].items()) + ")"
            res = run_call(good_prog, call, timeout=10)
            assert res["status"] == "ok", (first["task_id"], res)
            a = f"assert {call} == {res['result_repr']}"
            public.append({"assert": a, "input": t["input"], "expected_output": json.loads(json.dumps(res["result"]))})
            given.append(a)
        bad = [run_call(buggy_prog + "\n" + a + "\n", "True", timeout=10)["status"] == "ok" for a in given]
        if all(bad):
            continue  # buggy program passes its given tests: not detectable
        test = "\n\n".join(b["test"].replace("def check(candidate)", f"def check_{j}(candidate)")
                           for j, b in enumerate(bugs))
        test += ("\n\ndef check(candidate):\n" + "".join(f"    check_{j}({b['entry_point']})\n" for j, b in enumerate(bugs))
                 + "".join(f"    {a}\n" for a in given))
        out.append({"task_id": f"BIG/{i}", "prompt": "", "entry_point": "run_all", "solution": buggy_prog,
                    "canonical_solution": good_prog, "test": test, "given_tests": given, "is_solved": False,
                    "public_tests": public, "public_tests_skipped": [], "reference_passes_public": True,
                    "detectable": True, "usable": True, "bugs": sorted(bug_ids), "n_bugs": len(bugs),
                    "lines": buggy_prog.count("\n") + 1, "seed": ""})
    path = os.path.join(ROOT, "data/clean/big_programs.jsonl")
    with open(path, "w") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    print(f"{len(out)} programs, {sum(r['n_bugs'] for r in out)} bugs, "
          f"{min(r['lines'] for r in out)}-{max(r['lines'] for r in out)} lines -> {path}")

if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:]))
