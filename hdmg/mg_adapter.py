"""Plug the hypothesis loop into MGDebugger's recursion (variant C).

MGDebugger walks the decomposed tree bottom-up and, at each function whose derived tests fail,
calls debug_function(function_code, function_name, test_cases) -> (analysis, fixed_function | None).
Finding WHICH function is buggy stays MGDebugger's job. Variant C replaces only that call:
debug_function_hypothesis takes the same arguments plus the full program (the target can't run
without its helpers), runs the hypothesis loop there, and returns the same pair.

This is pure C: when the loop produces no fix, the answer is None and MGDebugger keeps the function
as it is and moves on. MGDebugger's simulated-trace debug_function is never called, so every fix in
a C run comes from a confirmed hypothesis.

Nothing here imports MGDebugger. The caller (MGDebugger/src/mg_debugger.py, marked [hdmg]) passes
in its LLM call, so this module is testable offline.
"""
from __future__ import annotations

import ast
import json
import time
from dataclasses import asdict
from typing import Callable, Optional

try:
    from .hypothesis_loop import (DEFAULT_K, DEFAULT_TIMEOUT, FIX_SYSTEM, LLM, LLMReply, NodeResult,
                                  debug_node)
except ImportError:
    from hypothesis_loop import (DEFAULT_K, DEFAULT_TIMEOUT, FIX_SYSTEM, LLM, LLMReply, NodeResult,
                                 debug_node)


# MGDebugger's call log names the pipeline stage after the calling function: llm_client._caller_stage
# turns a frame named hdmg_<x> into stage "<x>". These two wrappers are those frames.

def hdmg_hypothesis(complete: Callable[[list], str], messages: list[dict]) -> str:
    return complete(messages)


def hdmg_fix(complete: Callable[[list], str], messages: list[dict]) -> str:
    return complete(messages)


class CompletionLLM:
    """The loop's LLM protocol on top of a messages -> text function
    (MGDebugger's get_completion_with_retry), with each call tagged by stage."""

    def __init__(self, complete: Callable[[list], str]):
        self._complete = complete

    def complete(self, messages: list[dict]) -> LLMReply:
        system = messages[0].get("content") if messages and messages[0].get("role") == "system" else None
        call = hdmg_fix if system == FIX_SYSTEM else hdmg_hypothesis
        return LLMReply(call(self._complete, messages) or "")


_KEEP = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def runnable_program(full_code: str) -> str:
    """Imports, functions and classes of `full_code`, without other top-level statements.

    MGDebugger's evaluate() runs only the extracted functions, so example calls, prints or asserts
    the decomposition step left at top level must not run in the loop's sandbox either.
    """
    try:
        tree = ast.parse(full_code)
    except SyntaxError:
        return full_code
    lines = full_code.splitlines()
    parts = []
    for node in tree.body:
        if isinstance(node, _KEEP):
            start = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])
            parts.append("\n".join(lines[start - 1:node.end_lineno]))
    return "\n\n".join(parts) + "\n"


def _defines_top_level(program: str, name: str) -> bool:
    try:
        tree = ast.parse(program)
    except SyntaxError:
        return False
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name for n in tree.body)


def summarize(status: str, result: Optional[NodeResult]) -> str:
    """Human-readable analysis for MGDebugger's log: one line per round."""
    rounds = result.rounds if result else []
    lines = [f"hypothesis loop: {status} after {len(rounds)} round(s)"]
    for r in rounds:
        hyp = (r.hypothesis or {}).get("hypothesis", "(invalid reply)")
        lines.append(f"  round {r.n} {r.verdict.upper()}: {hyp} | {r.reason}")
    return "\n".join(lines)


def debug_function_hypothesis(function_code: str, function_name: str, test_cases: list, full_code: str, *,
                              complete: Optional[Callable[[list], str]] = None, llm: Optional[LLM] = None,
                              k: int = DEFAULT_K, timeout: float = DEFAULT_TIMEOUT,
                              log_path: Optional[str] = None,
                              log_context: Optional[dict] = None) -> tuple[Optional[str], Optional[str]]:
    """Variant C's debug step. Same contract as MGDebugger's debug_function: (analysis, fix or None).

    function_code  the target as MGDebugger holds it; unused (the loop reads the target from
                   full_code), kept so the call has debug_function's arguments
    full_code      the whole decomposed program (MGDebugger's hierarchical_code)
    complete       messages -> text, e.g. llm_client.get_completion_with_retry; or pass `llm` directly
    log_path       append one JSON line per call: status and every round

    Exceptions inside the loop are logged and treated as "no fix" so they can't abort MGDebugger's
    recursion. BaseExceptions (e.g. llm_client.BudgetExceeded) pass through on purpose.
    """
    if llm is None:
        if complete is None:
            raise TypeError("pass complete= or llm=")
        llm = CompletionLLM(complete)
    t0 = time.time()
    record = {"type": "node", **(log_context or {}), "function": function_name}

    tests = [t for t in test_cases if isinstance(t, dict) and "input" in t and "expected_output" in t]
    if len(tests) < len(test_cases):
        record["tests_dropped"] = len(test_cases) - len(tests)
    program = runnable_program(full_code)

    result: Optional[NodeResult] = None
    if not tests:
        status = "no_tests"
    elif not _defines_top_level(program, function_name):
        status = "not_top_level"
    else:
        try:
            result = debug_node(program, function_name, tests, llm, k=k, timeout=timeout)
            status = result.status
        except Exception as e:
            status = "error"
            record["error"] = f"{type(e).__name__}: {e}"

    # Only "fixed" returns code. Note "already_passing": every test passes when compared by value,
    # although MGDebugger's evaluate() (which compares repr strings: (1, 2) != [1, 2]) said one failed.
    # The function is right, so it is left as it is.
    analysis = summarize(status, result)
    fixed = result.fixed_function if result is not None and status == "fixed" else None

    if log_path:
        record.update(status=status, returned_fix=fixed is not None, seconds=round(time.time() - t0, 2),
                      rounds=[asdict(r) for r in result.rounds] if result is not None else [])
        with open(log_path, "a") as f:
            f.write(json.dumps(record, default=repr) + "\n")
    return analysis, fixed
