"""Hypothesis loop tests, offline: ScriptedLLM returns fixed replies and fails if called too often.

Each test pins down one behavior of debug_node, mostly the bugs fixed on top of 6e973f9.
"""
import json
import time

import hypothesis_loop as hl
from hypothesis_loop import LLMReply, debug_node, judge


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []                       # the messages of every call, copied

    def complete(self, messages):
        self.calls.append([dict(m) for m in messages])
        assert self.replies, "LLM called more times than scripted"
        return LLMReply(self.replies.pop(0))

    def prompt(self, i):
        """The last user message of call i."""
        return self.calls[i][-1]["content"]


def J(obj):
    return "```json\n" + json.dumps(obj) + "\n```"


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
H1 = {"hypothesis": "The loop starts at index 1", "observe": ["i"], "expect": {"i": [1, 2, 3]}, "why": "."}
H2 = {"hypothesis": "Later matches overwrite the first, longest one", "observe": ["suffix_start"],
      "expect": {"suffix_start": [0, 1, 3]}, "why": "."}
GOOD_FIX = ("```python\ndef find_longest_suffix(s):\n    for i in range(len(s)):\n"
            "        if is_palindrome(s[i:]):\n            return i\n    return 0\n```")
BAD_FIX = "```python\ndef find_longest_suffix(s):\n    return 99\n```"


def test_palindrome_rejected_then_confirmed_then_fixed():
    llm = ScriptedLLM([J(H1), J(H2), GOOD_FIX])
    r = debug_node(PAL, "find_longest_suffix", PAL_TESTS, llm)
    assert r.status == "fixed"
    assert [x.verdict for x in r.rounds] == ["rejected", "confirmed"]
    second = llm.prompt(1)
    assert "REJECTED" in second and "observed [0, 1, 2, 3]" in second
    assert "\n['Round" not in second                     # memory is lines, not a Python list repr


def test_prompt_shows_actual_output():
    llm = ScriptedLLM([J(H2), GOOD_FIX])
    debug_node(PAL, "find_longest_suffix", PAL_TESTS, llm)
    assert "expected 1  got 3" in llm.prompt(0)


def test_already_passing_makes_no_llm_call():
    llm = ScriptedLLM([])
    r = debug_node(PAL, "is_palindrome", [{"input": {"t": "aba"}, "expected_output": True}], llm)
    assert r.status == "already_passing" and llm.calls == []


def test_baseline_runs_each_test_once(monkeypatch):
    calls = []
    real = hl.run_call
    monkeypatch.setattr(hl, "run_call", lambda *a, **kw: calls.append(a) or real(*a, **kw))
    debug_node(PAL, "find_longest_suffix", PAL_TESTS, ScriptedLLM([J(H1)]), k=1)
    assert len(calls) == 1                               # was 2: the failing test ran twice


def test_observe_name_missing_from_expect_is_retried_not_a_crash():
    bad = {"hypothesis": "x", "observe": ["i"], "expect": {}, "why": "."}
    llm = ScriptedLLM([J(bad), J(H2), GOOD_FIX])
    r = debug_node(PAL, "find_longest_suffix", PAL_TESTS, llm, k=1)
    assert r.status == "fixed" and r.rounds[0].verdict == "confirmed"
    retry = llm.prompt(1)
    assert retry.startswith("Your reply was invalid") and '"expect" has no entry for i' in retry
    assert llm.calls[1][-2] == {"role": "assistant", "content": J(bad)}   # bad reply kept in the conversation


def test_invalid_json_once_then_valid():
    llm = ScriptedLLM(["I think the bug is on line 8.", J(H2), GOOD_FIX])
    r = debug_node(PAL, "find_longest_suffix", PAL_TESTS, llm, k=1)
    assert r.status == "fixed" and len(r.rounds) == 1 and r.rounds[0].verdict == "confirmed"


def test_invalid_twice_records_an_invalid_round_and_moves_on():
    llm = ScriptedLLM(["not json", "{still not json", J(H2), GOOD_FIX])
    r = debug_node(PAL, "find_longest_suffix", PAL_TESTS, llm, k=2)
    assert [x.verdict for x in r.rounds] == ["invalid", "confirmed"] and r.status == "fixed"
    first = r.rounds[0]
    assert first.n == 1 and first.hypothesis is None and first.validation_errors


def test_observing_a_name_the_target_never_assigns_is_a_validation_error():
    bad = {"hypothesis": "x", "observe": ["z"], "expect": {"z": []}, "why": "."}
    llm = ScriptedLLM([J(bad), J(bad)])
    r = debug_node(PAL, "find_longest_suffix", PAL_TESTS, llm, k=1)
    assert r.rounds[0].verdict == "invalid" and "'z'" in r.rounds[0].reason
    assert r.status == "no_confirmed"


def test_timeout_rejects_and_never_confirms():
    loop = "def f(x):\n    y = 0\n    while True:\n        pass\n"
    # A killed run returns no trace, so every variable looks like [] -- that used to match this prediction
    hyp = {"hypothesis": "the loop never ends", "observe": ["y"], "expect": {"y": []}, "why": "."}
    t0 = time.time()
    r = debug_node(loop, "f", [{"input": 1, "expected_output": 2}], ScriptedLLM([J(hyp)]), k=1, timeout=1)
    assert r.rounds[0].verdict == "rejected" and r.rounds[0].run_status == "timeout"
    assert "timed out" in r.rounds[0].reason and r.status == "no_confirmed"
    assert time.time() - t0 < 1 + 1 + 2                  # baseline run + traced run, each capped at timeout


def test_judge_rejects_crash_and_memory_runs():
    hyp = {"observe": ["y"], "expect": {"y": []}}
    for status in ("crash", "memory"):
        verdict, reason = judge(hyp, {"status": status})
        assert verdict == "rejected" and status in reason


def test_confirmed_but_fix_fails_is_remembered_and_ends_fix_failed():
    llm = ScriptedLLM([J(H2), BAD_FIX, J(H1)])
    r = debug_node(PAL, "find_longest_suffix", PAL_TESTS, llm, k=2)
    assert [x.verdict for x in r.rounds] == ["confirmed", "rejected"]
    assert r.status == "fix_failed"
    assert "CONFIRMED, but the fix failed: [0] got 99" in llm.prompt(2)


def test_all_rejected_is_no_confirmed_with_k_rounds():
    h3 = {"hypothesis": "is_palindrome is wrong", "observe": ["__return__"], "expect": {"__return__": [1]},
          "why": "."}
    llm = ScriptedLLM([J(H1), J(h3), J(dict(H1, hypothesis="again"))])
    r = debug_node(PAL, "find_longest_suffix", PAL_TESTS, llm, k=3)
    assert r.status == "no_confirmed" and len(r.rounds) == 3
    assert all(x.verdict == "rejected" for x in r.rounds)


def test_observable_names():
    code = ("def f(a, /, b, *args, c=1, **kw):\n"
            "    x = 1\n    y += 1\n    z: int = 2\n    for i, j in []: pass\n"
            "    with open('p') as fh: pass\n"
            "    try: pass\n    except Exception as err: pass\n"
            "    if (w := 3): pass\n"
            "    sq = [k * k for k in range(3)]\n"
            "    g = lambda q: q\n")
    names = hl.observable_names(code, "f")
    assert {"a", "b", "args", "c", "kw", "x", "y", "z", "i", "j", "fh", "err", "w", "sq", "g",
            "__return__", "__exception__"} <= names
    assert "k" not in names and "q" not in names         # other frames: the tracer can't see them
    assert hl.observable_names(code, "missing") is None
