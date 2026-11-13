"""Class demo: the hypothesis loop at one function, then the same loop inside MGDebugger's tree.

  python3 live_demo.py              live: Claude Haiku 5.5; every reply is saved to results/demo_recording.json
  python3 live_demo.py --replay     replay that recording: no network, no key, same output
  python3 live_demo.py --scripted   the proposal's hand-written hypotheses (H1, H2): no key needed

  --no-pause  don't wait for Enter    --only 1|2  run one part    --no-color  plain output

In every mode the code really runs and the harness decides every verdict; only the LLM's text is
replayed or scripted. Setup once: pip install -r requirements.txt. Live mode reads the key from
HDMG_API_KEY or key/apikey.txt (never printed). Rehearse live before class; if the network or the
model misbehaves on the day, run --replay.
"""
import argparse
import importlib.util
import json
import os
import sys
import tempfile
import textwrap
import time
from dataclasses import asdict

ROOT = os.path.dirname(os.path.abspath(__file__))
RECORDING = os.path.join(ROOT, "results", "demo_recording.json")

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
mode = ap.add_mutually_exclusive_group()
mode.add_argument("--replay", nargs="?", const=RECORDING, metavar="PATH", help="replay a recorded live run")
mode.add_argument("--scripted", action="store_true", help="hand-written replies, no LLM")
ap.add_argument("--record", default=RECORDING, metavar="PATH", help="where a live run saves its replies")
ap.add_argument("--only", choices=["1", "2"], help="run only part 1 or part 2")
ap.add_argument("--no-pause", action="store_true")
ap.add_argument("--no-color", action="store_true")
args = ap.parse_args()
LIVE = not (args.replay or args.scripted)

missing = [m for m in ("openai", "loguru", "numpy") if importlib.util.find_spec(m) is None]
if missing:
    sys.exit(f"Missing packages: {', '.join(missing)}.  Run:  pip install -r requirements.txt")

sys.path.insert(0, ROOT)
from hdmg.hypothesis_loop import LLMReply, debug_node, replace_function  # noqa: E402
from hdmg.sandbox import call_expr_from_input, run_call                 # noqa: E402

COLOR = sys.stdout.isatty() and not args.no_color


def _c(code):
    return lambda text: f"\033[{code}m{text}\033[0m" if COLOR else str(text)


BOLD, GREEN, RED, YELLOW, DIM = _c("1"), _c("32"), _c("31"), _c("33"), _c("2")


def pause():
    if not args.no_pause:
        input(DIM("[Enter] "))


def step(title):
    pause()
    print("\n" + BOLD(f"== {title} =="))


def wrap(text, indent):
    return textwrap.fill(text, 100, subsequent_indent=" " * indent)


# ---- the example (proposal slides 9 and 10) ----------------------------------------------------
PROGRAM = """def is_palindrome(t):
    return t == t[::-1]

def find_longest_suffix(s):
    suffix_start = 0
    for i in range(len(s)):
        if is_palindrome(s[i:]):
            suffix_start = i
    return suffix_start
"""
TARGET = "find_longest_suffix"
TESTS = [{"input": {"s": "cata"}, "expected_output": 1}]

TREE = PROGRAM + """
def build_result(s, start):
    return s + s[:start][::-1]

def make_palindrome(s):
    if not s:
        return ''
    return build_result(s, find_longest_suffix(s))
"""
GOLD = [{"input": {"s": "cata"}, "expected_output": "catac"}]
DERIVED = {      # what MGDebugger's test-derivation step produces for each function of the tree
    "is_palindrome": [{"input": {"t": "aba"}, "expected_output": True}],
    "find_longest_suffix": TESTS,
    "build_result": [{"input": {"s": "cata", "start": 1}, "expected_output": "catac"}],
    "make_palindrome": GOLD,
}


def _json_block(hyp):
    return "```json\n" + json.dumps(hyp) + "\n```"


SCRIPTED = [
    _json_block({"hypothesis": "The loop starts at index 1, so the whole string is never checked",
                 "observe": ["i"], "expect": {"i": [1, 2, 3]}, "why": "i would skip 0"}),
    _json_block({"hypothesis": "Later palindromic suffixes overwrite the first, longest match",
                 "observe": ["suffix_start"], "expect": {"suffix_start": [0, 1, 3]},
                 "why": "suffix_start is reassigned at every palindromic suffix, so it ends at the last one"}),
    "```python\ndef find_longest_suffix(s):\n    for i in range(len(s)):\n"
    "        if is_palindrome(s[i:]):\n            return i\n    return 0\n```",
]


# ---- the LLM: live (recorded), replayed or scripted -------------------------------------------
MODEL = os.environ.get("HDMG_MODEL", "claude-haiku-5-5")
PRICE_IN, PRICE_OUT = 0.10, 0.50          # USD per million tokens, Haiku 5.5


def _load(path):
    try:
        return json.load(open(path))
    except FileNotFoundError:
        sys.exit(f"No recording at {path}. Make one with a live run first, or use --scripted.")


def _client():
    from openai import OpenAI
    key = os.environ.get("HDMG_API_KEY")
    if not key:
        path = os.path.join(ROOT, "key", "apikey.txt")
        if not os.path.exists(path):
            sys.exit("Live mode needs a key: HDMG_API_KEY or key/apikey.txt. Or use --replay / --scripted.")
        key = open(path).read().strip()
    ws = os.environ.get("HDMG_WORKSPACE_ID")
    return OpenAI(api_key=key, base_url=os.environ.get("HDMG_BASE_URL", "https://api.anthropic.com/v1/"),
                  default_headers={"anthropic-workspace-id": ws} if ws else None)


class DemoLLM:
    """Every LLM call of one demo part. Callable as messages -> text (the shape of MGDebugger's
    get_completion_with_retry) and has .complete (the hypothesis loop's LLM protocol)."""

    def __init__(self, part):
        self.part, self.calls, self.tokens, self.cost = part, 0, 0, 0.0
        if LIVE:
            self.client = _client()
            self.recording = json.load(open(args.record)) if os.path.exists(args.record) else {}
            self.recording.update(model=MODEL, recorded_at=time.strftime("%Y-%m-%d %H:%M"), **{part: []})
        else:
            replies = _load(args.replay)[part] if args.replay else \
                [{"text": t, "prompt_tokens": 0, "completion_tokens": 0} for t in SCRIPTED]
            self.queue = list(replies)

    def __call__(self, messages):
        self.calls += 1
        if LIVE:
            if sys.stdout.isatty():
                print(DIM(f"    ... asking {MODEL} (call {self.calls})"), end="\r", flush=True)
            try:
                resp = self.client.chat.completions.create(model=MODEL, messages=messages, max_tokens=2000)
            except Exception as e:
                print()
                sys.exit(RED(f"Live call failed: {str(e)[:300]}") + "\nRerun with --replay to use the recording.")
            if sys.stdout.isatty():
                print(" " * 60, end="\r")
            u = resp.usage
            reply = {"text": resp.choices[0].message.content or "",
                     "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens}
            self.recording[self.part].append(reply)
            os.makedirs(os.path.dirname(args.record), exist_ok=True)
            json.dump(self.recording, open(args.record, "w"), indent=1)
        else:
            if not self.queue:
                sys.exit("The recording has fewer replies than this run needs (the code changed?). Re-record live.")
            reply = self.queue.pop(0)
        self.tokens += reply["prompt_tokens"] + reply["completion_tokens"]
        self.cost += (reply["prompt_tokens"] * PRICE_IN + reply["completion_tokens"] * PRICE_OUT) / 1e6
        return reply["text"]

    def complete(self, messages):
        return LLMReply(self(messages))

    def summary(self):
        if args.scripted:
            return f"{self.calls} LLM calls (scripted replies)"
        return (f"{self.calls} LLM calls | {self.tokens:,} tokens | ${self.cost:.4f}"
                + (" (recorded)" if args.replay else ""))


# ---- display -----------------------------------------------------------------------------------
def show_round(r):
    """One round of the loop, from a Round as a dict."""
    print(f"\n  {BOLD('Round ' + str(r['n']))}")
    hyp = r["hypothesis"]
    if hyp is None:
        print(f"    Reply      : {YELLOW('invalid')}, {'; '.join(r['validation_errors'])}")
        return
    print(f"    Hypothesis : {wrap(hyp['hypothesis'], 17)}")
    for name in hyp["observe"]:
        print(f"    Prediction : {name} = {json.dumps(hyp['expect'][name])}")
    if r["run_status"] in ("ok", "exception"):
        for name in hyp["observe"]:
            print(f"    Observed   : {name} = {json.dumps(r['observed'].get(name))}     "
                  + DIM("real run, recorded by the tracer"))
    else:
        print(f"    Observed   : {r['reason']}")
    verdict = GREEN("CONFIRMED") if r["verdict"] == "confirmed" else RED("REJECTED")
    print(f"    Verdict    : {verdict}     " + DIM("decided by code, not by the LLM"))


def show_program(code):
    for n, line in enumerate(code.rstrip("\n").split("\n"), 1):
        print(DIM(f"  {n:>2}  ") + line)


def outcome(fixed):
    return GREEN("PASS") if fixed else RED("FAIL")


# ---- part 1: one function --------------------------------------------------------------------------
def part1():
    step("1. One function: the LLM guesses, the code judges")
    print("Task: return the start index of the longest palindromic suffix of s.\n")
    show_program(PROGRAM)
    got = run_call(PROGRAM, "find_longest_suffix(s='cata')")["result_repr"]
    print(f"\n  Failing test: find_longest_suffix(s='cata')   expected 1   got {got}   {RED('FAIL')}")
    print(DIM("  Instead of imagining a trace, the LLM must state a hypothesis and predict values;"
              " the harness runs the code and checks them."))
    pause()

    llm = DemoLLM("part1")
    result = debug_node(PROGRAM, TARGET, TESTS, llm, k=3)
    for i, rnd in enumerate(result.rounds):
        if i:
            pause()
        show_round(asdict(rnd))
    pause()
    if result.status == "fixed":
        print(f"\n  {BOLD('Fix')} {DIM('(written from the confirmed hypothesis)')}")
        for line in result.fixed_function.split("\n"):
            print("    " + line)
        new = run_call(replace_function(PROGRAM, TARGET, result.fixed_function), "find_longest_suffix(s='cata')")
        print(f"\n  [0] find_longest_suffix(s='cata')   expected 1   got {new['result_repr']}   {GREEN('PASS')}")
        print(BOLD(f"\n  FIXED after {len(result.rounds)} hypotheses") + f"  |  {llm.summary()}")
    else:
        print(BOLD(f"\n  {result.status.upper()} after {len(result.rounds)} hypotheses") + f"  |  {llm.summary()}")


# ---- part 2: the merge into MGDebugger --------------------------------------------------------------
def part2():
    step("2. The merge: the same loop inside MGDebugger's recursion (variant C)")
    sys.path.insert(0, os.path.join(ROOT, "MGDebugger", "src"))
    from loguru import logger
    logger.remove()                                     # MGDebugger logs a lot; keep the screen clean
    import config
    import mg_debugger

    got = run_call(TREE, "make_palindrome(s='cata')")["result_repr"]
    print(f"Public test: make_palindrome(s='cata')   expected 'catac'   got {got}   {RED('FAIL')}\n")
    print("MGDebugger decomposes the program into a tree and derives a test for every function:")
    print("    make_palindrome\n    ├── find_longest_suffix\n    │   └── is_palindrome\n    └── build_result")
    print(DIM("(decomposition and derived tests are fixed to the proposal's example here; normally two LLM steps)"))
    print("\nIt then walks the tree bottom-up. A function whose test fails goes to the debug step;"
          "\nin variant C that step is the hypothesis loop instead of an imagined trace.")
    pause()

    llm = DemoLLM("part2")
    log = tempfile.NamedTemporaryFile("w+", suffix=".jsonl", delete=False).name
    config.VARIANT, config.HYPOTHESIS_LOG, config.HYPOTHESIS_K = "C", log, 3
    mg_debugger.convert_to_hierarchical = lambda code, include_example=False: TREE
    mg_debugger.generate_test_cases = lambda full_code, gold, name: [dict(t) for t in DERIVED[name]]
    mg_debugger.get_completion_with_retry = llm          # the debug step's LLM calls

    real_evaluate = mg_debugger.evaluate

    def evaluate(code, func_name, test_case, *a, **kw):  # MGDebugger's own test run, printed
        passed, tc = real_evaluate(code, func_name, test_case, *a, **kw)
        call = call_expr_from_input(func_name, test_case["input"])
        print(f"  {call:<33} expected {test_case['expected_output']!r:<8} "
              f"got {tc.get('actual_output')!r:<10} {outcome(passed)}")
        return passed, tc
    mg_debugger.evaluate = evaluate

    adapter = mg_debugger._hypothesis_debugger()

    def debug_step(function_code, function_name, test_cases, full_code, **kw):
        print(YELLOW(f"    -> hypothesis loop at {function_name}"))
        analysis, fix = adapter(function_code, function_name, test_cases, full_code, **kw)
        node = json.loads(open(log).read().strip().split("\n")[-1])
        for r in node["rounds"]:
            verdict = GREEN("CONFIRMED") if r["verdict"] == "confirmed" else \
                RED("REJECTED") if r["verdict"] == "rejected" else YELLOW("INVALID")
            text = (r["hypothesis"] or {}).get("hypothesis", "(invalid reply)")
            print(f"       Round {r['n']}  {verdict}  {text}")
            print(DIM(f"                 {r['reason']}"))
        if fix:
            print(GREEN(f"    -> fix passes {function_name}'s tests; merged into the tree, MGDebugger re-tests it"))
        else:
            print(RED(f"    -> no confirmed fix ({node['status']}); {function_name} is left as it is"))
        return analysis, fix
    mg_debugger._hypothesis_debugger = lambda: debug_step

    fixed_program = mg_debugger.mg_debug(TREE, GOLD)
    os.unlink(log)
    pause()
    final = run_call(fixed_program, "make_palindrome(s='cata')")["result_repr"]
    ok = final == "'catac'"
    print(f"\n  Public test again: make_palindrome(s='cata')   expected 'catac'   got {final}   {outcome(ok)}")
    print(BOLD(f"\n  {'FIXED' if ok else 'NOT FIXED'}") + f"  |  debug step: {llm.summary()}")
    print(DIM("  The debug step called the LLM only at the failing function; passing functions cost one real run."))


# ---- main ----------------------------------------------------------------------------------------
if LIVE:
    shown = os.path.relpath(args.record, ROOT)
    banner = f"LIVE  {MODEL}  (replies saved to {args.record if shown.startswith('..') else shown})"
elif args.replay:
    banner = f"REPLAY  {_load(args.replay).get('model', '?')} recorded {_load(args.replay).get('recorded_at', '?')}"
else:
    banner = "SCRIPTED  hand-written LLM replies (the proposal's H1 and H2)"
print(BOLD("Hypothesis-Driven MGDebugger: demo") + "   " + YELLOW(banner))
print(DIM("The LLM guesses, the code judges: every prediction is checked against a real run."))
if args.only != "2":
    part1()
if args.only != "1":
    part2()
print()
