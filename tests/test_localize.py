"""Variant L tests, offline: breakpoint tracing in the sandbox and the localize -> fix loop with a
scripted LLM."""
import json

import localize as lz
from hypothesis_loop import LLMReply
from sandbox import run_breakpoints


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages):
        self.calls.append([dict(m) for m in messages])
        assert self.replies, "LLM called more times than scripted"
        return LLMReply(self.replies.pop(0))

    def prompt(self, i):
        return self.calls[i][-1]["content"]


def J(obj):
    return "```json\n" + json.dumps(obj) + "\n```"


# lines:   1                     2                       3      4                         5
PAL = """def is_palindrome(t):
    return t == t[::-1]

def find_longest_suffix(s):
    suffix_start = 0
    for i in range(len(s)):
        if is_palindrome(s[i:]):
            suffix_start = i
    return suffix_start
"""
PAL_TESTS = [{"input": {"s": "cata"}, "expected_output": 1}]
GOOD_FIX = ("```python\ndef find_longest_suffix(s):\n    for i in range(len(s)):\n"
            "        if is_palindrome(s[i:]):\n            return i\n    return 0\n```")
BAD_FIX = "```python\ndef find_longest_suffix(s):\n    return 99\n```"
# the correct program returns at i == 1, so line 9 is never reached with suffix_start == 3
DIVERGING = {"breakpoints": [{"line": 9, "expr": "suffix_start", "expect": [1]}], "why": "."}
MATCHING = {"breakpoints": [{"line": 2, "expr": "t", "expect": ["cata", "ata"]}], "why": "."}


# ----- sandbox / tracer

def test_breakpoints_record_every_hit_in_order():
    r = run_breakpoints(PAL, "find_longest_suffix('cata')",
                        [{"line": 7, "expr": "(i, s[i:])"}, {"line": 2, "expr": "t"}])
    assert r["status"] == "ok" and r["result"] == 3
    loop, helper = r["breakpoints"]
    assert [h["repr"] for h in loop["hits"]] == ["(0, 'cata')", "(1, 'ata')", "(2, 'ta')", "(3, 'a')"]
    assert [h["repr"] for h in helper["hits"]] == ["'cata'", "'ata'", "'ta'", "'a'"]
    assert [h["seq"] for h in loop["hits"]] == [1, 3, 5, 7]          # interleaved with the helper's


def test_value_is_taken_before_the_line_runs():
    r = run_breakpoints("def f():\n    x = 1\n    x = 2\n    return x\n", "f()",
                        [{"line": 3, "expr": "x"}, {"line": 2, "expr": "x"}])
    assert [h["repr"] for h in r["breakpoints"][0]["hits"]] == ["1"]
    assert r["breakpoints"][1]["hits"][0]["repr"].startswith("<error: NameError")


def test_comprehension_line_counts_once_and_sees_locals():
    r = run_breakpoints("def g(xs):\n    k = 2\n    return [x * k for x in xs]\n", "g([1, 2])",
                        [{"line": 3, "expr": "[x * k for x in xs]"}])
    assert [h["repr"] for h in r["breakpoints"][0]["hits"]] == ["[2, 4]"]


def test_recursion_hits_every_call():
    fib = "def fib(n):\n    if n < 2:\n        return n\n    return fib(n - 1) + fib(n - 2)\n"
    r = run_breakpoints(fib, "fib(3)", [{"line": 2, "expr": "n"}])
    assert [h["repr"] for h in r["breakpoints"][0]["hits"]] == ["3", "2", "1", "0", "1"]


def test_timeout_still_returns_hits():
    loop = "def f(n):\n    i = 0\n    while i < n:\n        i -= 1\n    return i\n"
    r = run_breakpoints(loop, "f(3)", [{"line": 4, "expr": "i"}], timeout=2)
    assert r["status"] == "timeout"
    bp = r["breakpoints"][0]
    assert [h["repr"] for h in bp["hits"]][:3] == ["0", "-1", "-2"] and bp["truncated"]


def test_exception_run_keeps_hits():
    r = run_breakpoints("def f(xs):\n    y = xs[0]\n    return xs[5]\n", "f([7])", [{"line": 3, "expr": "y"}])
    assert r["status"] == "exception" and r["breakpoints"][0]["hits"][0]["repr"] == "7"


# ----- validation

def test_breakpoint_lines_are_statement_starts_inside_functions():
    lines = lz.breakpoint_lines(PAL)
    assert lines == {2: "is_palindrome", 5: "find_longest_suffix", 6: "find_longest_suffix",
                     7: "find_longest_suffix", 8: "find_longest_suffix", 9: "find_longest_suffix"}
    doc = 'def f(x):\n    """doc"""\n    return x\n'
    assert lz.breakpoint_lines(doc) == {3: "f"}


def test_unsafe_expressions_are_rejected():
    assert lz.check_expression("len(xs) + sum(x for x in xs)") == []
    assert lz.check_expression("s.lower().count('a')") == []
    assert lz.check_expression("xs.append(1)")                 # mutates
    assert lz.check_expression("__import__('os')")             # not whitelisted
    assert lz.check_expression("x.__class__")                  # private attribute
    assert lz.check_expression("(y := 1)")                     # assignment
    assert lz.check_expression("lambda: 1")


def test_validation_messages():
    lines = lz.breakpoint_lines(PAL)
    assert lz.validate_breakpoints({"breakpoints": []}, lines, set())
    errs = lz.validate_breakpoints({"breakpoints": [{"line": 3, "expr": "s", "expect": [1]}]}, lines, set())
    assert "nearest usable lines" in errs[0]
    errs = lz.validate_breakpoints({"breakpoints": [{"line": 9, "expr": "suffix_start", "expect": [1]}]},
                                   lines, {(9, "suffix_start")})
    assert "already tried" in errs[0]
    assert lz.validate_breakpoints(DIVERGING, lines, set()) == []


# ----- divergence

def _bp(line, expr, expect, hits, seqs=None, truncated=False, function="f"):
    return {"line": line, "expr": expr, "expect": expect, "hits": hits, "function": function,
            "seqs": seqs or list(range(1, len(hits) + 1)), "truncated": truncated}


def test_earliest_value_mismatch_wins():
    a = _bp(5, "x", [1, 2, 3], ["1", "2", "9"], seqs=[1, 3, 5])
    b = _bp(7, "y", [0, 5], ["0", "6"], seqs=[2, 4])
    div, _ = lz.find_divergence([a, b], "ok")
    assert (div["line"], div["hit"], div["actual"]) == (7, 2, "6")


def test_normalized_comparison_and_prefix():
    a = _bp(5, "p", [[1, 2]], ["(1, 2)", "(3, 4)"])      # tuple vs list; extra hits are not checked
    assert lz.find_divergence([a], "ok") == (None, [])


def test_missing_hits_count_after_value_mismatches():
    a = _bp(5, "x", [1, 2], ["1"], seqs=[1])
    b = _bp(7, "y", [0, 0], ["0", "1"], seqs=[2, 3])
    div, _ = lz.find_divergence([a, b], "ok")
    assert div["line"] == 7
    div, _ = lz.find_divergence([a], "ok")
    assert div["kind"] == "missing" and "only 1 time" in div["actual"]


def test_name_error_is_unusable_not_a_divergence():
    a = _bp(5, "z", [1], ["<error: NameError: name 'z' is not defined>"])
    div, notes = lz.find_divergence([a], "ok")
    assert div is None and "NameError" in notes[0]


# ----- the loop

def test_already_passing_makes_no_calls():
    llm = ScriptedLLM([])
    r = lz.localize_and_fix(PAL, "find_longest_suffix", [{"input": {"s": "abc"}, "expected_output": 2}], llm)
    assert r.status == "already_passing"


def test_diverges_then_fixed():
    llm = ScriptedLLM([J(DIVERGING), GOOD_FIX])
    r = lz.localize_and_fix(PAL, "find_longest_suffix", PAL_TESTS, llm)
    assert r.status == "fixed" and len(llm.calls) == 2
    assert r.rounds[0].verdict == "diverged" and r.rounds[0].divergence["actual"] == "3"
    first, fix = llm.prompt(0), llm.prompt(1)
    assert "\n9 | " in first and "got 3" in first                       # numbered listing, actual output
    assert "should be 1 but was 3" in fix and "Rewrite ONLY find_longest_suffix" in fix
    assert llm.calls[1][0]["content"] == lz.FIX_SYSTEM_L
    assert "return i" in r.fixed_program and "def is_palindrome" in r.fixed_program


def test_match_goes_to_memory_then_next_round_localizes():
    llm = ScriptedLLM([J(MATCHING), J(DIVERGING), GOOD_FIX])
    r = lz.localize_and_fix(PAL, "find_longest_suffix", PAL_TESTS, llm)
    assert r.status == "fixed"
    assert [x.verdict for x in r.rounds] == ["no_divergence", "diverged"]
    assert "MATCHED" in llm.prompt(1)


def test_failed_fix_is_remembered_and_rounds_are_capped():
    llm = ScriptedLLM([J(DIVERGING), BAD_FIX,
                       J({"breakpoints": [{"line": 8, "expr": "i", "expect": [1]}]}), BAD_FIX])
    r = lz.localize_and_fix(PAL, "find_longest_suffix", PAL_TESTS, llm, k=2)
    assert r.status == "fix_failed" and len(r.rounds) == 2
    assert "tests still fail" in llm.prompt(2) and "got 99" in llm.prompt(2)


def test_invalid_reply_gets_one_retry():
    bad = {"breakpoints": [{"line": 3, "expr": "s", "expect": [1]}]}
    llm = ScriptedLLM([J(bad), J(DIVERGING), GOOD_FIX])
    r = lz.localize_and_fix(PAL, "find_longest_suffix", PAL_TESTS, llm)
    assert r.status == "fixed"
    assert llm.prompt(1).startswith("Your breakpoint reply was invalid")


def test_repeated_breakpoint_is_refused_in_later_round():
    llm = ScriptedLLM([J(MATCHING), J(MATCHING), J(MATCHING)])
    r = lz.localize_and_fix(PAL, "find_longest_suffix", PAL_TESTS, llm, k=2)
    assert [x.verdict for x in r.rounds][1] == "invalid"


def test_fix_may_rewrite_a_helper():
    prog = ("def helper(x):\n    return x + 2\n\ndef main(x):\n    y = helper(x)\n    return y * 10\n")
    tests = [{"input": {"x": 1}, "expected_output": 20}]
    loc = {"breakpoints": [{"line": 6, "expr": "y", "expect": [2]}]}
    fix = "```python\ndef helper(x):\n    return x + 1\n```"
    llm = ScriptedLLM([J(loc), fix])
    r = lz.localize_and_fix(prog, "main", tests, llm)
    assert r.status == "fixed" and r.rounds[0].fix_function == "helper"


# ----- adapter

def test_debug_program_logs_and_tags_stages(tmp_path):
    seen = []

    def complete(messages):
        import inspect
        seen.append(inspect.stack()[1].function)
        return [J(DIVERGING), GOOD_FIX][len(seen) - 1]

    log = tmp_path / "nodes.jsonl"
    code = "from typing import List\n\n" + PAL + "\nprint('top level')\n"
    out = lz.debug_program(code, "find_longest_suffix", PAL_TESTS, complete=complete, log_path=str(log),
                           log_context={"task_id": "T"})
    assert "return i" in out and "print('top level')" not in out
    assert seen == ["hdmg_localize", "hdmg_fix"]
    rec = json.loads(log.read_text())
    assert rec["type"] == "localize" and rec["status"] == "fixed" and rec["task_id"] == "T"


def test_debug_program_returns_input_when_not_fixed():
    llm = ScriptedLLM([J(MATCHING)])
    assert lz.debug_program(PAL, "find_longest_suffix", PAL_TESTS, llm=llm, k=1) == PAL


# ----- pipeline test scripts in a child process (fixed harness)

def test_run_script_verdicts_and_runaway_program_is_killed():
    from sandbox import run_script
    assert run_script("def f(x):\n    return x\nassert f(1) == 1\n") == (True, "")
    ok, reason = run_script("assert 1 == 2, 'nope'\n")
    assert not ok and reason.startswith("AssertionError")
    # an infinite loop that allocates: killed by the timeout or the memory cap, never left running
    ok, reason = run_script("xs = []\nwhile True:\n    xs.append([0] * 1000)\n", timeout=3, mem_mb=200)
    assert not ok and ("MemoryError" in reason or "timeout" in reason)
