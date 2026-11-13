"""Variant C adapter at one MGDebugger node, offline (no MGDebugger imports, no LLM)."""
import inspect
import json

import pytest

from mg_adapter import debug_function_hypothesis, runnable_program
from test_hypothesis_loop import GOOD_FIX, H1, H2, J, PAL

TARGET = "find_longest_suffix"
TESTS = [{"input": {"s": "cata"}, "expected_output": 1}]
# The decomposed program as MGDebugger holds it, with top-level code the decomposition step left behind
TREE = PAL + '''
def build_result(s, start):
    return s + s[:start][::-1]

def make_palindrome(s):
    if not s:
        return ''
    return build_result(s, find_longest_suffix(s))

print(make_palindrome("cata"))
assert False, "top-level code must not run in the sandbox"
'''
FUNCTION_CODE = PAL.split("\n\n", 1)[1]          # what MGDebugger passes as function_code


class ScriptedComplete:
    """messages -> text, like MGDebugger's get_completion_with_retry. Records the calling function's
    name, which is what llm_client._caller_stage turns into the stage in llm_calls.jsonl."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.callers = []

    def __call__(self, messages):
        self.callers.append(inspect.stack()[1].function)
        assert self.replies, "LLM called more times than scripted"
        return self.replies.pop(0)


def run(replies, tmp_path=None, **kw):
    complete = ScriptedComplete(replies)
    log = str(tmp_path / "nodes.jsonl") if tmp_path else None
    analysis, fix = debug_function_hypothesis(FUNCTION_CODE, kw.pop("name", TARGET), kw.pop("tests", TESTS),
                                              kw.pop("full_code", TREE), complete=complete, log_path=log,
                                              log_context={"task_id": "T/1", "attempt": 1}, **kw)
    records = [json.loads(l) for l in open(log)] if log else []
    return analysis, fix, complete, records


def test_fixes_the_node_and_returns_only_the_target(tmp_path):
    # the fix reply also redefines a helper; only the target's def may come back to MGDebugger
    fix_reply = GOOD_FIX.replace("```python\n", "```python\ndef is_palindrome(t):\n    return False\n\n")
    analysis, fix, complete, records = run([J(H1), J(H2), fix_reply], tmp_path)
    assert fix.startswith("def find_longest_suffix(s):") and "is_palindrome(t)" not in fix
    assert complete.callers == ["hdmg_hypothesis", "hdmg_hypothesis", "hdmg_fix"]   # stages in the call log
    assert "fixed after 2 round(s)" in analysis and "round 1 REJECTED" in analysis
    (rec,) = records
    assert rec["task_id"] == "T/1" and rec["function"] == TARGET and rec["status"] == "fixed"
    assert rec["returned_fix"] is True and [r["verdict"] for r in rec["rounds"]] == ["rejected", "confirmed"]


def test_nothing_confirmed_returns_no_fix(tmp_path):
    analysis, fix, complete, records = run([J(H1), J(dict(H1, hypothesis="b")), J(dict(H1, hypothesis="c"))],
                                           tmp_path)
    assert fix is None and analysis.startswith("hypothesis loop: no_confirmed after 3 round(s)")
    assert complete.callers == ["hdmg_hypothesis"] * 3              # no simulated-trace debug call
    assert records[0]["status"] == "no_confirmed" and records[0]["returned_fix"] is False


def test_already_passing_by_value_returns_no_fix_and_no_llm_call():
    # MGDebugger's evaluate compares repr strings, so (1, 2) "fails" against the JSON test's [1, 2]
    code = "def pair(a, b):\n    return (a, b)\n"
    analysis, fix, complete, _ = run([], name="pair", full_code=code,
                                     tests=[{"input": {"a": 1, "b": 2}, "expected_output": [1, 2]}])
    assert fix is None and complete.callers == [] and "already_passing" in analysis


def test_an_error_inside_the_loop_is_no_fix_not_a_crash(tmp_path):
    def broken(messages):
        raise ValueError("boom")
    analysis, fix = debug_function_hypothesis(FUNCTION_CODE, TARGET, TESTS, TREE, complete=broken,
                                              log_path=str(tmp_path / "n.jsonl"))
    assert fix is None and "error" in analysis
    rec = json.loads(open(tmp_path / "n.jsonl").read())
    assert rec["status"] == "error" and "ValueError: boom" in rec["error"]


def test_budget_stop_passes_through():
    class BudgetExceeded(BaseException):         # llm_client.BudgetExceeded is a BaseException too
        pass

    def out_of_money(messages):
        raise BudgetExceeded()
    with pytest.raises(BudgetExceeded):
        debug_function_hypothesis(FUNCTION_CODE, TARGET, TESTS, TREE, complete=out_of_money)


def test_target_that_is_not_top_level_makes_no_llm_call():
    nested = "def outer(s):\n    def inner(s):\n        return 3\n    return inner(s)\n"
    analysis, fix, complete, _ = run([], name="inner", full_code=nested)
    assert complete.callers == [] and fix is None and "not_top_level" in analysis


def test_malformed_derived_tests_are_dropped(tmp_path):
    tests = TESTS + [{"input": {"s": "x"}}, "garbage"]
    _, fix, _, records = run([J(H2), GOOD_FIX], tmp_path, tests=tests)
    assert fix is not None and records[0]["tests_dropped"] == 2


def test_runnable_program_keeps_definitions_and_drops_statements():
    code = ("import math\nfrom typing import List\nX = 1\n\n@staticmethod\ndef f():\n    return math.pi\n\n"
            "class C:\n    pass\n\nprint(f())\nif __name__ == '__main__':\n    f()\n")
    out = runnable_program(code)
    assert "import math" in out and "from typing import List" in out and "@staticmethod\ndef f():" in out
    assert "class C:" in out and "print(" not in out and "__main__" not in out and "X = 1" not in out
