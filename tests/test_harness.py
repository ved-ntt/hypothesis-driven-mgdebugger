"""MGDebugger harness changes (HDMG_HARNESS=fixed): value comparison, round tests, gold tests at the
top-level function, the detectable filter and sharding. Needs loguru and openai; skipped otherwise."""
import json
import os
import sys

import pytest

pytest.importorskip("loguru")
pytest.importorskip("openai")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "MGDebugger", "src")))
import config          # noqa: E402
import debug_pipeline  # noqa: E402
import mg_debugger     # noqa: E402
import utils           # noqa: E402

PAIR = "def pair():\n    return (2.0, 2.2)\n"


def test_fixed_harness_compares_values(monkeypatch):
    monkeypatch.setattr(config, "HARNESS", "fixed")
    assert utils.evaluate(PAIR, "pair", {"input": {}, "expected_output": [2.0, 2.2]})[0]


def test_published_harness_compares_repr_strings(monkeypatch):
    monkeypatch.setattr(config, "HARNESS", "published")
    assert not utils.evaluate(PAIR, "pair", {"input": {}, "expected_output": [2.0, 2.2]})[0]


def test_round_test_case(monkeypatch):
    monkeypatch.setattr(config, "HARNESS", "fixed")
    code = "def find_zero(xs):\n    return -0.4999999\n"
    assert utils.evaluate(code, "find_zero", {"input": {"xs": [1, 2]}, "expected_output": -0.5, "round": 2})[0]


TREE = '''def helper(x):
    return x + 1

def main_fn(x):
    return helper(x)
'''


def test_top_level_function_uses_the_gold_tests(monkeypatch):
    derived_for = []

    def fake_generate(full_code, gold, name):
        derived_for.append(name)
        return [{"input": {"x": 1}, "expected_output": 2}]
    monkeypatch.setattr(config, "HARNESS", "fixed")
    monkeypatch.setattr(config, "CURRENT_ENTRY_POINT", "main_fn")
    monkeypatch.setattr(mg_debugger, "convert_to_hierarchical", lambda code, include_example=False: TREE)
    monkeypatch.setattr(mg_debugger, "generate_test_cases", fake_generate)
    gold = [{"input": {"x": 1}, "expected_output": 2}]
    mg_debugger.mg_debug(TREE, gold)
    assert derived_for == ["helper"]          # no LLM-derived tests for main_fn
    assert "actual_output" not in gold[0]     # evaluate wrote into a copy, not the caller's gold tests


def test_published_harness_still_derives_top_level_tests(monkeypatch):
    derived_for = []
    monkeypatch.setattr(config, "HARNESS", "published")
    monkeypatch.setattr(config, "CURRENT_ENTRY_POINT", "main_fn")
    monkeypatch.setattr(mg_debugger, "convert_to_hierarchical", lambda code, include_example=False: TREE)
    monkeypatch.setattr(mg_debugger, "generate_test_cases",
                        lambda full_code, gold, name: derived_for.append(name) or
                        [{"input": {"x": 1}, "expected_output": 2}])
    mg_debugger.mg_debug(TREE, [{"input": {"x": 1}, "expected_output": 2}])
    assert derived_for == ["helper", "main_fn"]


def _problem(task, detectable, solved=False):
    return {"task_id": task, "prompt": "def f(x):\n    pass\n", "entry_point": "f",
            "solution": "def f(x):\n    return x\n", "canonical_solution": "    return x\n",
            "given_tests": ["assert f(1) == 1"], "test": "def check(candidate):\n    assert candidate(1) == 1\n",
            "is_solved": solved, "detectable": detectable,
            "public_tests": [{"input": {"x": 1}, "expected_output": 1, "assert": "assert f(1) == 1"}]}


@pytest.mark.parametrize("shard, expected", [((0, 2), ["T/0", "T/3"]), ((1, 2), ["T/1"])])
def test_detectable_filter_and_shards(tmp_path, monkeypatch, shard, expected):
    seeds = tmp_path / "clean.jsonl"
    rows = [_problem("T/0", True), _problem("T/1", True), _problem("T/2", False),
            _problem("T/3", True), _problem("T/4", True, solved=True)]
    seeds.write_text("".join(json.dumps(r) + "\n" for r in rows))
    for name, value in dict(HARNESS="fixed", ONLY_DETECTABLE=True, SHARD=shard, MAX_OUTER_RETRY=1,
                            STOP_ON="both", CALL_LOG=None).items():
        monkeypatch.setattr(config, name, value)
    seen = []
    monkeypatch.setattr(debug_pipeline, "mg_debug", lambda code, gold: seen.append(gold) or code)
    debug_pipeline.debug_dataset(str(seeds), output_folder=str(tmp_path))
    out = next(tmp_path.glob("*_debugging_seeds_from_*.jsonl"))
    done = [json.loads(l) for l in open(out)]
    assert [p["task_id"] for p in done] == expected
    assert all(p["fixed_public_selection"] for p in done)
    assert seen[0] == [{"input": {"x": 1}, "expected_output": 1}]   # gold tests from public_tests
