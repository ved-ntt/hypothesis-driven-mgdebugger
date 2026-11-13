"""MGDebugger's real recursion (mg_debug) with variant A and C, the LLM replaced by a fake client.

Decomposition and test derivation are stubbed to the deck's make_palindrome tree, so the only
LLM calls are the debug step's. Needs MGDebugger's requirements (loguru, openai); skipped otherwise.
"""
import json
import os
import sys
import types

import pytest

pytest.importorskip("loguru")
pytest.importorskip("openai")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "MGDebugger", "src")))
import config        # noqa: E402  (MGDebugger's modules)
import llm_client    # noqa: E402
import mg_debugger   # noqa: E402

from sandbox import run_call                                   # noqa: E402
from test_hypothesis_loop import GOOD_FIX, H1, H2, J, PAL      # noqa: E402

TREE = PAL + '''
def build_result(s, start):
    return s + s[:start][::-1]

def make_palindrome(s):
    if not s:
        return ''
    return build_result(s, find_longest_suffix(s))
'''
GOLD = [{"input": {"s": "cata"}, "expected_output": "catac"}]
DERIVED = {
    "is_palindrome": [{"input": {"t": "aba"}, "expected_output": True}],
    "find_longest_suffix": [{"input": {"s": "cata"}, "expected_output": 1}],
    "build_result": [{"input": {"s": "cata", "start": 1}, "expected_output": "catac"}],
    "make_palindrome": GOLD,
}


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)

    def create(self, **kwargs):
        assert self.replies, "LLM called more times than scripted"
        text = self.replies.pop(0)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))],
            usage=types.SimpleNamespace(prompt_tokens=100, completion_tokens=20))


@pytest.fixture
def mg(tmp_path, monkeypatch):
    def run(variant, replies):
        fake = FakeCompletions(replies)
        monkeypatch.setattr(llm_client, "client", types.SimpleNamespace(chat=types.SimpleNamespace(completions=fake)))
        for name, value in dict(VARIANT=variant, HYPOTHESIS_K=3, SANDBOX_TIMEOUT=5.0,
                                CALL_LOG=str(tmp_path / "llm_calls.jsonl"),
                                HYPOTHESIS_LOG=str(tmp_path / "hypothesis_nodes.jsonl"),
                                CURRENT_TASK_ID="HumanEval/10", CURRENT_ATTEMPT=1).items():
            monkeypatch.setattr(config, name, value)
        monkeypatch.setattr(mg_debugger, "convert_to_hierarchical", lambda code, include_example=False: TREE)
        monkeypatch.setattr(mg_debugger, "generate_test_cases",
                            lambda full_code, gold, name: [dict(t) for t in DERIVED[name]])
        fixed = mg_debugger.mg_debug(TREE, GOLD)

        def lines(name):
            path = tmp_path / name
            return [json.loads(l) for l in open(path)] if path.exists() else []
        assert fake.replies == [], "not every scripted reply was used"
        return fixed, [c["stage"] for c in lines("llm_calls.jsonl")], lines("hypothesis_nodes.jsonl")
    return run


def root_output(code):
    return run_call(code, "make_palindrome('cata')")["result"]


def test_variant_c_fixes_the_failing_node_inside_the_tree(mg):
    fixed, stages, nodes = mg("C", [J(H1), J(H2), GOOD_FIX])
    assert root_output(fixed) == "catac"
    assert stages == ["hypothesis", "hypothesis", "fix"]
    (node,) = nodes
    assert node["function"] == "find_longest_suffix" and node["status"] == "fixed"
    assert node["task_id"] == "HumanEval/10" and node["returned_fix"] is True


def test_variant_c_without_a_confirmed_hypothesis_changes_nothing(mg):
    # pure C: no simulated-trace fallback, so the bug survives and MGDebugger moves up the tree
    at_suffix = [J(H1), J(dict(H1, hypothesis="b")), J(dict(H1, hypothesis="c"))]
    at_root = [J({"hypothesis": h, "observe": ["s"], "expect": {"s": ["not cata"]}, "why": "."}) for h in "xyz"]
    fixed, stages, nodes = mg("C", at_suffix + at_root)
    assert root_output(fixed) == "catatac"
    assert stages == ["hypothesis"] * 6
    assert [(n["function"], n["status"]) for n in nodes] == [("find_longest_suffix", "no_confirmed"),
                                                             ("make_palindrome", "no_confirmed")]


def test_variant_a_is_unchanged(mg):
    fixed, stages, nodes = mg("A", [GOOD_FIX])
    assert root_output(fixed) == "catac"
    assert stages == ["debug"] and nodes == []
