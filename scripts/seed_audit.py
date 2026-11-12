"""How many 'buggy' seeds already pass every public (given) test?

A debugger that only sees public tests cannot tell these are wrong: its derived tests pass
and no debugging happens. Under MGDebugger's protocol they can still be counted as fixed,
because the outer retry loop stops on the hidden tests. Runs each check in the sandbox.

  python scripts/seed_audit.py MGDebugger/src/input_data
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hdmg"))
from sandbox import run_call

root = sys.argv[1]
sets = ["humaneval/seed/deepseekcoder", "humaneval/seed/codeqwen", "humaneval/seed/codestral",
        "mbpp/seed/deepseekcoder", "mbpp/seed/codeqwen", "mbpp/seed/codestral"]
print(f"{'seed set':32}{'buggy':>7}{'pass public':>13}{'share':>8}")
out = {}
for s in sets:
    rows = [json.loads(l) for l in open(os.path.join(root, s, "seed.jsonl"))]
    buggy = [r for r in rows if not r["is_solved"]]
    passing = []
    for r in buggy:
        code = r["solution"] + "\n\n" + "\n".join(r["given_tests"])
        if run_call(code, "True", timeout=10)["status"] == "ok":
            passing.append(r["task_id"])
    out[s] = passing
    print(f"{s:32}{len(buggy):>7}{len(passing):>13}{100 * len(passing) / len(buggy):>7.1f}%")
json.dump(out, open(os.path.join(os.path.dirname(__file__), "..", "results", "seed_audit.json"), "w"), indent=1)
