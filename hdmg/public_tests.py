"""Turn a problem's public tests (assert strings) into structured test cases.

MGDebugger's own parser (testcase_utils.parse_tests) drops tests it cannot read and crashes on some:
  assert round(find_zero([1, 2]), 2) == -0.5       -> dropped (HumanEval/32 ends up with no tests)
  assert longest([]) is None                        -> dropped
  assert decode_cyclic(encode_cyclic('abc')) == ... -> NameError, the whole problem is lost
This parser reads all three shapes. An argument that is not a literal is evaluated in the sandbox,
with the program the test belongs to, so encode_cyclic('abc') becomes the string it returns.

A parsed test is {"input": {param: value}, "expected_output": value, "assert": original text},
plus "round": n when the call's result is rounded to n digits before comparing.
"""
from __future__ import annotations

import ast
import json
from typing import Optional

try:
    from .sandbox import run_call
except ImportError:
    from sandbox import run_call


def parameter_names(program: str, entry_point: str) -> list[str]:
    for node in ast.walk(ast.parse(program)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == entry_point:
            a = node.args
            return [p.arg for p in a.posonlyargs + a.args]
    return []


def _value(node: ast.expr, program: str) -> tuple[bool, object]:
    """(ok, value) for an argument or expected value: a literal, else evaluated in the sandbox."""
    try:
        return True, ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        pass
    res = run_call(program, ast.unparse(node), timeout=10)
    if res.get("status") != "ok":
        return False, None
    try:
        value = ast.literal_eval(res["result_repr"])
    except (ValueError, SyntaxError):
        return False, None
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False, None
    return True, value


def _entry_call(node: ast.expr, entry_point: str) -> Optional[ast.Call]:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == entry_point:
        return node
    return None


def parse_assert(text: str, entry_point: str, params: list[str], program: str) -> tuple[Optional[dict], str]:
    """One assert string -> (test case or None, reason when None)."""
    try:
        node = ast.parse(text.strip()).body[0]
    except (SyntaxError, IndexError):
        return None, "not valid Python"
    if not isinstance(node, ast.Assert):
        return None, "not an assert"
    test = node.test
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], (ast.Eq, ast.Is))):
        return None, "not of the form <call> == <value> or <call> is <value>"

    left, right = test.left, test.comparators[0]
    case: dict = {"assert": text.strip()}
    call = _entry_call(left, entry_point)
    if call is None and isinstance(left, ast.Call) and isinstance(left.func, ast.Name) and left.func.id == "round" \
            and left.args and _entry_call(left.args[0], entry_point):
        call = left.args[0]
        digits = left.args[1] if len(left.args) > 1 else None
        case["round"] = ast.literal_eval(digits) if digits is not None else 0
    if call is None:
        return None, f"left side is not a call to {entry_point}"

    inputs = {}
    if len(call.args) > len(params):
        return None, "more positional arguments than parameters"
    for name, arg in zip(params, call.args):
        ok, value = _value(arg, program)
        if not ok:
            return None, f"argument {ast.unparse(arg)!r} could not be evaluated"
        inputs[name] = value
    for kw in call.keywords:
        if kw.arg is None:
            return None, "**kwargs in the call"
        ok, value = _value(kw.value, program)
        if not ok:
            return None, f"argument {ast.unparse(kw.value)!r} could not be evaluated"
        inputs[kw.arg] = value

    ok, expected = _value(right, program)
    if not ok:
        return None, f"expected value {ast.unparse(right)!r} could not be evaluated"
    case["input"] = inputs
    case["expected_output"] = expected
    return case, ""


def parse_public_tests(asserts: list[str], entry_point: str, program: str) -> tuple[list[dict], list[dict]]:
    """All asserts of one problem -> (parsed test cases, [{assert, reason}] for the ones left out)."""
    params = parameter_names(program, entry_point)
    parsed, skipped = [], []
    for text in asserts:
        case, reason = parse_assert(text, entry_point, params, program)
        if case is None:
            skipped.append({"assert": text, "reason": reason})
        else:
            parsed.append(case)
    return parsed, skipped
