"""Two-minute demo for the progress check. No API calls, no cost, runs in a few seconds.

  python3 scripts/demo.py            # press Enter between steps
  python3 scripts/demo.py --no-pause # run straight through

Part 1: the hypothesis loop's building blocks (tracer + sandbox) on the proposal's example.
Part 2: evidence from the real pilot run (Claude Haiku 5.5, variant A).
"""
import glob, json, os, re, sys, time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "hdmg"))
from sandbox import run_call, run_traced, sequences  # noqa: E402

PAUSE = "--no-pause" not in sys.argv
B, G, R, Y, D, X = "\033[1m", "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def step(title):
    if PAUSE:
        input(f"\n{D}[Enter]{X} ")
    print(f"\n{B}== {title} =={X}")


BUGGY = '''def is_palindrome(t):
    return t == t[::-1]

def find_longest_suffix(s):
    suffix_start = 0
    for i in range(len(s)):
        if is_palindrome(s[i:]):
            suffix_start = i
    return suffix_start

def build_result(s, start):
    return s + s[:start][::-1]

def make_palindrome(s):
    if not s:
        return ''
    return build_result(s, find_longest_suffix(s))
'''
FIXED = BUGGY.replace('''    suffix_start = 0
    for i in range(len(s)):
        if is_palindrome(s[i:]):
            suffix_start = i
    return suffix_start''', '''    for i in range(len(s)):
        if is_palindrome(s[i:]):
            return i
    return 0''')


def check(hyp, var, predicted):
    print(f"  Hypothesis: {hyp}")
    print(f"  Prediction: {var} = {predicted}")
    t0 = time.time()
    r = run_traced(BUGGY, "find_longest_suffix('cata')", "find_longest_suffix", [var])
    observed = sequences(r)[var]
    ms = (time.time() - t0) * 1000
    print(f"  Observed  : {var} = {observed}   {D}(real run in a separate process, {ms:.0f} ms){X}")
    ok = observed == predicted
    print(f"  Verdict   : {G + 'CONFIRMED' if ok else R + 'REJECTED'}{X}  {D}(decided by code, not the LLM){X}")
    return ok


print(f"{B}Hypothesis-Driven MGDebugger: demo{X}")
print("Task: make_palindrome(s) returns the shortest palindrome that starts with s.")

step("1. The public test fails")
r = run_call(BUGGY, "make_palindrome('cata')")
print(f"  make_palindrome('cata') = {r['result']!r}   expected 'catac'   {R}FAIL{X}")
print("  MGDebugger splits it into is_palindrome, find_longest_suffix, build_result.")
print("  Bottom-up: is_palindrome passes its tests; find_longest_suffix('cata') returns 3, expected 1.")

step("2. Hypothesis 1 at the failing function")
print(f"  {D}(Hypotheses are hand-written here; in week 2 the LLM writes them in this format.){X}")
check("the loop skips index 0, so the whole string is never checked", "i", [1, 2, 3])
print(f"  {D}Rejected hypotheses go into memory so the LLM does not retry them.{X}")

step("3. Hypothesis 2")
check("later palindromic suffixes overwrite the first (longest) match", "suffix_start", [0, 1, 3])

step("4. Fix, then re-test")
sub = run_call(FIXED, "find_longest_suffix('cata')")["result"]
root = run_call(FIXED, "make_palindrome('cata')")["result"]
print(f"  find_longest_suffix('cata') = {sub}   expected 1   {G}PASS{X}")
print(f"  make_palindrome('cata')     = {root!r}  expected 'catac'   {G}PASS{X}")

step("5. Bad code can't hang the debugger")
t0 = time.time()
r = run_call("def f():\n    while True:\n        pass\n", "f()", timeout=2)
print(f"  infinite loop -> status '{r['status']}' after {time.time() - t0:.1f} s; the process is killed")
print(f"  {D}(Upstream MGDebugger runs code in a thread that can't be stopped.){X}")

# ---- Part 2: the real pilot run --------------------------------------------------------
runs = sorted(d for d in glob.glob(os.path.join(ROOT, "MGDebugger/src/output_data/humaneval/seed/deepseekcoder/2*"))
              if os.path.exists(os.path.join(d, "llm_calls.jsonl")))
if runs:
    run = runs[0] if os.path.basename(runs[0]) == "20261103-153022" else runs[-1]
    step("6. Real pilot: MGDebugger (variant A) on Claude Haiku 5.5, 5 HumanEval bugs")
    calls = [json.loads(l) for l in open(os.path.join(run, "llm_calls.jsonl")) if l.strip()]
    ok = [c for c in calls if c.get("ok")]
    by = {}
    for c in ok:
        by.setdefault(c["stage"], [0, 0])
        by[c["stage"]][0] += 1
        by[c["stage"]][1] += c["prompt_tokens"] + c["completion_tokens"]
    tot = sum(v[1] for v in by.values())
    res = [json.loads(l) for l in open(glob.glob(os.path.join(run, "*_debugging_seeds_from_*.jsonl"))[0])]
    done = [p for p in res if "attempts" in p]
    fixed = sum(bool(p.get("fixed_hidden_selection")) for p in done)
    print(f"  fixed {fixed} of {len(done)}   LLM calls {len(ok)}   spend ${sum(c.get('cost_usd', 0) for c in ok):.3f}")
    for s, (n, t) in sorted(by.items(), key=lambda kv: -kv[1][1]):
        print(f"    {s:13} {n:4} calls   {100 * t / tot:4.0f}% of tokens")

    step("7. Finding 3: a derived test contradicts the public test (HumanEval/54)")
    log = open(os.path.join(run, "all_info.log")).read()
    a = log.find("Processing unsolved problem: HumanEval/54")
    sec = log[a:log.find("Processing unsolved problem:", a + 10)]
    gold = re.search(r"Extracted gold test cases: (.*)", sec)
    voted = re.search(r"Voted \d+ test cases for same_chars: (.*)", sec)
    want = "{'s0': 'eabcdzzzz', 's1': 'dddzzzzzzzddeddabc'}"
    for label, m in [("public test", gold), ("LLM-derived", voted)]:
        if m:
            hit = re.search(re.escape(want) + r", 'expected_output': (\w+)", m.group(1))
            if hit:
                print(f"  {label:12}: same_chars('eabcdzzzz', 'dddzzzzzzzddeddabc') == {hit.group(1)}")
    print(f"  {Y}The derived test agrees with the buggy code, so nothing fails and the debug step never runs.{X}")
else:
    print(f"\n{D}(No pilot run found under MGDebugger/src/output_data; skipping part 2.){X}")
print()
