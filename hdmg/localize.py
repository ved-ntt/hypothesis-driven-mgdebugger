"""Variant L: localize the bug with breakpoints, then fix only there.

MGDebugger (variant A) finds the buggy function by decomposing the program into a tree of
subfunctions and asking the LLM to write tests for each one. On HumanEvalFix that machinery is
about 80% of the token cost (decompose ~13%, derive tests ~67%). Variant L skips both:

  1. Run the public tests on the program as it is. All pass -> nothing to do.
  2. Show the LLM the numbered program and the first failing test. It places 1-3 breakpoints:
     a line, an expression, and the values the CORRECT program would show there on successive hits.
  3. Run the failing test with those breakpoints (hdmg/sandbox.run_breakpoints records the real
     values). The earliest hit whose real value differs from the expected one is where the
     program first goes wrong.
  4. Ask the LLM to rewrite the function that contains that line, quoting the evidence. Splice it
     in and run every public test. All pass -> fixed. Otherwise the round goes into memory.
  5. No divergence (every breakpoint matched) also goes into memory, so the next round looks
     elsewhere. Up to k rounds.

The localization is real execution, not the LLM's simulation: the LLM predicts what SHOULD
happen and the sandbox says what DID happen, the same contract as variant C's hypotheses, but on
the whole program at once instead of node by node.

Nothing here imports MGDebugger. MGDebugger/src/debug_pipeline.py calls debug_program when
HDMG_VARIANT=L and passes in its LLM call.
"""
from __future__ import annotations

import ast
import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

try:
    from .compare import from_repr, values_equal
    from .hypothesis_loop import DEFAULT_TIMEOUT, LLM, LLMReply, extract_fenced, function_source, run_test
    from .sandbox import call_expr_from_input, run_breakpoints
except ImportError:
    from compare import from_repr, values_equal
    from hypothesis_loop import DEFAULT_TIMEOUT, LLM, LLMReply, extract_fenced, function_source, run_test
    from sandbox import call_expr_from_input, run_breakpoints

DEFAULT_K = 3            # localize -> fix rounds per program
MAX_BREAKPOINTS = 3
MAX_EXPECT = 20          # expected values per breakpoint (the tracer records at most this many hits)

SAFE_CALLS = {"len", "sum", "min", "max", "abs", "sorted", "list", "tuple", "set", "dict", "str", "int",
              "float", "bool", "round", "any", "all", "reversed", "enumerate", "zip", "range", "ord", "chr"}
SAFE_METHODS = {"count", "index", "get", "keys", "values", "items", "lower", "upper", "strip", "split",
                "startswith", "endswith", "isdigit", "isalpha", "isupper", "islower", "find", "join"}
_SAFE_NODES = (ast.Expression, ast.Name, ast.Load, ast.Constant, ast.Attribute, ast.Subscript, ast.Slice,
               ast.Tuple, ast.List, ast.Dict, ast.Set, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
               ast.IfExp, ast.Call, ast.keyword, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
               ast.comprehension, ast.Store, ast.operator, ast.unaryop, ast.boolop, ast.cmpop, ast.expr_context)


@dataclass
class LRound:
    n: int
    breakpoints: Optional[list] = None   # [{line, expr, expect, function, hits: [repr], truncated}]
    run_status: str = ""
    verdict: str = ""                    # invalid | no_divergence | diverged | no_data
    divergence: Optional[dict] = None    # {line, function, expr, hit, expected, actual, kind}
    fix_function: Optional[str] = None   # which function the fix rewrote
    outcome: str = ""
    validation_errors: list = field(default_factory=list)


@dataclass
class LResult:
    status: str                          # already_passing | fixed | fix_failed | no_divergence
    fixed_program: Optional[str] = None
    rounds: list = field(default_factory=list)


# ----- the program as the LLM sees it

def numbered(program: str) -> str:
    lines = program.splitlines()
    width = len(str(len(lines)))
    return "\n".join(f"{i:>{width}} |" + (f" {text}" if text else "") for i, text in enumerate(lines, 1))


def _is_docstring(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)


def breakpoint_lines(program: str) -> dict[int, str]:
    """{line: top-level function} for every line where a statement inside a function starts.

    Those are the lines that produce a trace 'line' event when execution reaches them. Docstrings
    are left out (not executed), and so are continuation lines of multi-line statements."""
    try:
        tree = ast.parse(program)
    except SyntaxError:
        return {}
    lines: dict[int, str] = {}
    for top in tree.body:
        if not isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(top):
            if node is top or not isinstance(node, ast.stmt) or _is_docstring(node):
                continue
            lines.setdefault(node.lineno, top.name)
    return lines


def check_expression(expr: str) -> list[str]:
    """Errors if the expression could change state or isn't a plain read of program values."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return [f"expression {expr!r} does not parse: {e.msg}"]
    errors = []
    for node in ast.walk(tree):
        if not isinstance(node, _SAFE_NODES):
            errors.append(f"expression {expr!r} uses {type(node).__name__}, which is not allowed")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            errors.append(f"expression {expr!r} reads a private attribute {node.attr!r}")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in SAFE_CALLS:
                continue
            if isinstance(f, ast.Attribute) and f.attr in SAFE_METHODS:
                continue
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", type(f).__name__)
            errors.append(f"expression {expr!r} calls {name}; only "
                          f"{', '.join(sorted(SAFE_CALLS))} and the methods {', '.join(sorted(SAFE_METHODS))} are allowed")
    return errors[:3]


def validate_breakpoints(reply: Any, lines: dict[int, str], tried: set) -> list[str]:
    if not isinstance(reply, dict) or not isinstance(reply.get("breakpoints"), list):
        return ['reply must be a JSON object with a "breakpoints" list']
    bps = reply["breakpoints"]
    if not 1 <= len(bps) <= MAX_BREAKPOINTS:
        return [f"give 1 to {MAX_BREAKPOINTS} breakpoints, got {len(bps)}"]
    errors, seen = [], set()
    for i, bp in enumerate(bps):
        where = f"breakpoint {i + 1}"
        if not isinstance(bp, dict):
            errors.append(f"{where} must be an object with line, expr and expect")
            continue
        line, expr, expect = bp.get("line"), bp.get("expr"), bp.get("expect")
        if not isinstance(line, int) or isinstance(line, bool):
            errors.append(f"{where}: line must be an integer")
        elif line not in lines:
            near = sorted(lines, key=lambda x: abs(x - line))[:5]
            errors.append(f"{where}: line {line} does not start a statement inside a function "
                          f"(nearest usable lines: {sorted(near)})")
        if not isinstance(expr, str) or not expr.strip():
            errors.append(f"{where}: expr must be a non-empty string")
        else:
            errors.extend(f"{where}: {e}" for e in check_expression(expr))
        if not isinstance(expect, list) or not expect:
            errors.append(f"{where}: expect must be a non-empty list of values, one per hit")
        elif len(expect) > MAX_EXPECT:
            errors.append(f"{where}: at most {MAX_EXPECT} expected values")
        key = (line, (expr or "").strip() if isinstance(expr, str) else expr)
        if key in seen:
            errors.append(f"{where} repeats another breakpoint")
        elif key in tried:
            errors.append(f"{where} (line {line}, {expr}) was already tried in an earlier round; choose another")
        seen.add(key)
    return errors


# ----- prompts

LOCALIZE_SYSTEM = (
    "You localize bugs in Python programs with breakpoints. A breakpoint is a line number and a Python "
    "expression. When the failing test runs, the expression is evaluated each time execution reaches that "
    "line, BEFORE the line runs, and the real values are recorded. For each breakpoint you give the values "
    "the CORRECT program (the one the docstring and the tests describe) would show on successive hits. "
    "The first recorded value that differs from yours shows where the program goes wrong.\n"
    "Rules:\n"
    "- Line numbers refer to the numbered listing. Use a line where a statement inside a function starts.\n"
    "- A loop header, or a line inside a loop, is hit once per iteration; a line in a recursive function "
    "is hit in every call. A variable assigned ON the line still has its old value there (or does not "
    "exist yet), so to see a result, break on the line after it.\n"
    "- Expressions may use variables, literals, operators, indexing, slicing, comprehensions, the calls "
    + ", ".join(sorted(SAFE_CALLS)) + ", and the methods " + ", ".join(sorted(SAFE_METHODS)) + ".\n"
    "- 1 to " + str(MAX_BREAKPOINTS) + " breakpoints, each with 1 to " + str(MAX_EXPECT) + " expected values "
    "in JSON (lists for tuples, null for None, sorted lists for sets). If a line is hit more often than "
    "you list, only the values you list are checked.\n"
    "- Put breakpoints where they split the computation (an intermediate result, the value about to be "
    "returned) so a mismatch narrows the bug to a few lines. Don't reuse breakpoints from earlier rounds.\n"
    "Reply with one ```json block, nothing else:\n"
    '{"breakpoints": [{"line": 7, "expr": "total", "expect": [0, 1, 3]}], "why": "one sentence"}'
)

FIX_SYSTEM_L = ("You fix Python programs. The breakpoint evidence shows where the program first differs "
                "from the correct one; change only what that requires.")


def localize_prompt(program: str, call: str, expected: Any, actual: str, memory: list[str]) -> str:
    return (
        f"## Program (numbered lines)\n{numbered(program)}\n\n"
        f"## Failing test\n{call}  expected {expected!r}  got {actual}\n\n"
        f"## Earlier rounds\n{chr(10).join(memory) or 'none'}"
    )


def fix_prompt(program: str, call: str, expected: Any, actual: str, evidence: str, function: str) -> str:
    return (
        f"## Program\n{program}\n\n"
        f"## Failing test\n{call}  expected {expected!r}  got {actual}\n\n"
        f"## Breakpoint evidence\n{evidence}\n\n"
        f"## Reply\nRewrite ONLY {function}, same name and parameters, in one ```python block. If the wrong "
        f"value came from a helper that {function} calls, rewrite that helper instead."
    )


# ----- running and comparing

def run_round_breakpoints(program: str, call: str, bps: list[dict], lines: dict[int, str],
                          timeout: float) -> tuple[dict, list[dict]]:
    """Run the failing call with the breakpoints. Returns (sandbox result, breakpoints annotated with
    their function, real hits and whether the tracer stopped recording)."""
    run = run_breakpoints(program, call, [{"line": b["line"], "expr": b["expr"]} for b in bps],
                          timeout=timeout, max_hits=MAX_EXPECT)
    recorded = run.get("breakpoints") or []
    out = []
    for i, b in enumerate(bps):
        rec = recorded[i] if i < len(recorded) else {"hits": [], "truncated": False}
        out.append({"line": b["line"], "expr": b["expr"], "expect": b["expect"], "function": lines[b["line"]],
                    "hits": [h["repr"] for h in rec["hits"]], "seqs": [h["seq"] for h in rec["hits"]],
                    "truncated": rec.get("truncated", False)})
    return run, out


def find_divergence(bps: list[dict], run_status: str) -> tuple[Optional[dict], list[str]]:
    """Earliest point where a real value differs from the expected one.

    Value mismatches are ordered by when they happened. A breakpoint reached fewer times than
    expected can only be noticed at the end of the run, so it counts after every value mismatch.
    An expression that raised NameError (usually a variable not assigned yet at that line) is
    reported as unusable, not as a divergence. Returns (divergence or None, notes on unusable ones)."""
    candidates, notes = [], []
    for b in bps:
        for i, expected in enumerate(b["expect"]):
            if i >= len(b["hits"]):
                if run_status == "ok" or not b["truncated"]:
                    candidates.append((float("inf"), {
                        "kind": "missing", "line": b["line"], "function": b["function"], "expr": b["expr"],
                        "hit": i + 1, "expected": expected,
                        "actual": f"line reached only {len(b['hits'])} time(s)"}))
                break
            text = b["hits"][i]
            if text.startswith("<error: NameError"):
                notes.append(f"line {b['line']} `{b['expr']}`: {text[1:-1]}")
                break
            if text.startswith("<error:"):
                candidates.append((b["seqs"][i], {
                    "kind": "error", "line": b["line"], "function": b["function"], "expr": b["expr"],
                    "hit": i + 1, "expected": expected, "actual": text}))
                break
            if not values_equal(from_repr(text), expected):
                candidates.append((b["seqs"][i], {
                    "kind": "value", "line": b["line"], "function": b["function"], "expr": b["expr"],
                    "hit": i + 1, "expected": expected, "actual": text}))
                break
    if not candidates:
        return None, notes
    return min(candidates, key=lambda c: c[0])[1], notes


def _source_line(program: str, line: int) -> str:
    lines = program.splitlines()
    return lines[line - 1].strip() if 0 < line <= len(lines) else ""


def describe_evidence(program: str, div: dict, bps: list[dict]) -> str:
    where = f"line {div['line']} in {div['function']} (`{_source_line(program, div['line'])}`)"
    if div["kind"] == "missing":
        first = f"At {where}: expected hit #{div['hit']} with `{div['expr']}` == {div['expected']!r}, but the {div['actual']}."
    else:
        first = (f"At {where}, before the line runs, on hit #{div['hit']}: `{div['expr']}` should be "
                 f"{div['expected']!r} but was {div['actual']}.")
    matched = [f"line {b['line']} `{b['expr']}` = {b['hits'][:len(b['expect'])]}" for b in bps
               if b is not None and (b["line"], b["expr"]) != (div["line"], div["expr"])
               and len(b["hits"]) >= len(b["expect"])
               and all(not h.startswith("<error") and values_equal(from_repr(h), e)
                       for h, e in zip(b["hits"], b["expect"]))]
    if matched:
        first += "\nThese breakpoints matched the correct program: " + "; ".join(matched)
    return first


def _short(text: str, limit: int = 120) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "..."


# ----- asking the LLM

def parse_reply(text: str) -> tuple[Optional[Any], list[str]]:
    block = extract_fenced(text, "json")
    if block is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end < start:
            return None, ["no JSON object found; reply with one object in a ```json block"]
        block = text[start:end + 1]
    try:
        return json.loads(block), []
    except json.JSONDecodeError as e:
        return None, [f"the JSON does not parse: {e}"]


def ask_breakpoints(llm: LLM, program: str, call: str, expected: Any, actual: str, memory: list[str],
                    lines: dict[int, str], tried: set) -> tuple[Optional[list], list[str]]:
    messages = [{"role": "system", "content": LOCALIZE_SYSTEM},
                {"role": "user", "content": localize_prompt(program, call, expected, actual, memory)}]
    reply = llm.complete(messages)
    data, errors = parse_reply(reply.text)
    errors = errors or validate_breakpoints(data, lines, tried)
    if errors:
        retry = ("Your breakpoint reply was invalid:\n" + "\n".join(errors) +
                 "\nReply again with one corrected ```json block.")
        messages = messages + [{"role": "assistant", "content": reply.text},
                               {"role": "user", "content": retry}]
        reply = llm.complete(messages)
        data, errors = parse_reply(reply.text)
        errors = errors or validate_breakpoints(data, lines, tried)
    if errors:
        return None, errors
    return [{"line": b["line"], "expr": b["expr"].strip(), "expect": b["expect"]} for b in data["breakpoints"]], []


def top_level_functions(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def ask_fix(llm: LLM, program: str, call: str, expected: Any, actual: str, div: dict,
            bps: list[dict]) -> tuple[Optional[str], Optional[str]]:
    """(new program, name of the function rewritten) or (None, None) if the reply had no usable def.

    Takes the last ```python block that defines a function of the program; the function at the
    divergence is preferred if the block defines several."""
    evidence = describe_evidence(program, div, bps)
    prompt = fix_prompt(program, call, expected, actual, evidence, div["function"])
    reply = llm.complete([{"role": "system", "content": FIX_SYSTEM_L}, {"role": "user", "content": prompt}])
    known = set(top_level_functions(program))
    for block in reversed(re.findall(r"```(?:python|py)?\s*\n(.*?)```", reply.text, re.DOTALL)):
        names = [n for n in top_level_functions(block) if n in known]
        if not names:
            continue
        name = div["function"] if div["function"] in names else names[0]
        source = function_source(block, name)
        if source:
            return replace_top_level(program, name, source), name
    return None, None


def replace_top_level(program: str, name: str, new_source: str) -> str:
    try:
        from .hypothesis_loop import replace_function
    except ImportError:
        from hypothesis_loop import replace_function
    return replace_function(program, name, new_source)


# ----- the loop

def localize_and_fix(program: str, entry_point: str, tests: list[dict], llm: LLM, k: int = DEFAULT_K,
                     timeout: float = DEFAULT_TIMEOUT) -> LResult:
    baseline = [run_test(program, entry_point, t, timeout) for t in tests]
    if all(passed for passed, _ in baseline):
        return LResult(status="already_passing")

    focus_index = next(i for i, (passed, _) in enumerate(baseline) if not passed)
    focus, actual = tests[focus_index], baseline[focus_index][1]
    call = call_expr_from_input(entry_point, focus["input"])
    lines = breakpoint_lines(program)
    memory: list[str] = []
    rounds: list[LRound] = []
    tried: set = set()
    any_diverged = False

    for n in range(1, k + 1):
        bps, errors = ask_breakpoints(llm, program, call, focus["expected_output"], actual, memory, lines, tried)
        if bps is None:
            rounds.append(LRound(n, verdict="invalid", outcome="; ".join(errors), validation_errors=errors))
            memory.append(f"Round {n}: invalid reply ({_short('; '.join(errors))})")
            continue
        tried.update((b["line"], b["expr"]) for b in bps)

        run, annotated = run_round_breakpoints(program, call, bps, lines, timeout)
        status = run.get("status", "")
        rnd = LRound(n, breakpoints=[{k_: v for k_, v in b.items() if k_ != "seqs"} for b in annotated],
                     run_status=status)
        rounds.append(rnd)
        if status not in ("ok", "exception", "timeout") or "breakpoints" not in run:
            rnd.verdict, rnd.outcome = "no_data", f"run ended with status '{status}', nothing recorded"
            memory.append(f"Round {n}: {rnd.outcome}")
            continue

        div, notes = find_divergence(annotated, status)
        summary = "; ".join(f"line {b['line']} `{b['expr']}` expected {_short(b['expect'], 60)} "
                            f"got {_short(b['hits'][:len(b['expect'])], 60)}" for b in annotated)
        if div is None:
            rnd.verdict = "no_divergence"
            rnd.outcome = "every breakpoint matched the correct program; the bug is elsewhere"
            if notes:
                rnd.outcome += " (unusable: " + "; ".join(notes) + ")"
            memory.append(f"Round {n}: {summary} | MATCHED, so the bug is not before these points"
                          + (f" | unusable: {'; '.join(notes)}" if notes else ""))
            continue

        any_diverged = True
        rnd.verdict, rnd.divergence = "diverged", div
        new_program, fn = ask_fix(llm, program, call, focus["expected_output"], actual, div, annotated)
        rnd.fix_function = fn
        where = f"diverged at line {div['line']} ({div['function']}): `{div['expr']}` expected {_short(div['expected'], 60)} got {_short(div['actual'], 60)}"
        if new_program is None:
            rnd.outcome = "the fix reply had no ```python block defining a function of the program"
        else:
            results = [run_test(new_program, entry_point, t, timeout) for t in tests]
            if all(passed for passed, _ in results):
                rnd.outcome = f"fixed {fn}"
                return LResult(status="fixed", fixed_program=new_program, rounds=rounds)
            failures = [f"[{i}] got {_short(got, 80)}" for i, (passed, got) in enumerate(results) if not passed]
            rnd.outcome = f"rewrote {fn}, tests still fail: " + "; ".join(failures[:3])
        memory.append(f"Round {n}: {summary} | {where} | {rnd.outcome}")

    return LResult(status="fix_failed" if any_diverged else "no_divergence", rounds=rounds)


# ----- adapter for MGDebugger's pipeline

# llm_client._caller_stage names the stage after a calling frame hdmg_<x>
def hdmg_localize(complete: Callable[[list], str], messages: list[dict]) -> str:
    return complete(messages)


def hdmg_fix(complete: Callable[[list], str], messages: list[dict]) -> str:
    return complete(messages)


class StagedLLM:
    def __init__(self, complete: Callable[[list], str]):
        self._complete = complete

    def complete(self, messages: list[dict]) -> LLMReply:
        system = messages[0].get("content") if messages and messages[0].get("role") == "system" else None
        call = hdmg_fix if system == FIX_SYSTEM_L else hdmg_localize
        return LLMReply(call(self._complete, messages) or "")


def debug_program(buggy_code: str, entry_point: str, gold_tests: list, *,
                  complete: Optional[Callable[[list], str]] = None, llm: Optional[LLM] = None,
                  k: int = DEFAULT_K, timeout: float = DEFAULT_TIMEOUT, log_path: Optional[str] = None,
                  log_context: Optional[dict] = None) -> str:
    """Variant L's replacement for mg_debug(buggy_code, gold_tests): returns the fixed program, or
    the program unchanged when no fix passed every public test. Logs one JSON line per call.

    Exceptions inside are logged and treated as no fix; BaseExceptions (llm_client.BudgetExceeded)
    pass through."""
    try:
        from .mg_adapter import runnable_program
    except ImportError:
        from mg_adapter import runnable_program
    if llm is None:
        if complete is None:
            raise TypeError("pass complete= or llm=")
        llm = StagedLLM(complete)
    t0 = time.time()
    record = {"type": "localize", **(log_context or {}), "function": entry_point}
    tests = [t for t in gold_tests if isinstance(t, dict) and "input" in t and "expected_output" in t]
    program = runnable_program(buggy_code)

    result: Optional[LResult] = None
    if not tests:
        status = "no_tests"
    elif entry_point not in top_level_functions(program):
        status = "not_top_level"
    else:
        try:
            result = localize_and_fix(program, entry_point, tests, llm, k=k, timeout=timeout)
            status = result.status
        except Exception as e:
            status = "error"
            record["error"] = f"{type(e).__name__}: {e}"

    fixed = result.fixed_program if result is not None and status == "fixed" else None
    if log_path:
        record.update(status=status, returned_fix=fixed is not None, seconds=round(time.time() - t0, 2),
                      rounds=[asdict(r) for r in result.rounds] if result is not None else [])
        with open(log_path, "a") as f:
            f.write(json.dumps(record, default=repr) + "\n")
    return fixed if fixed is not None else buggy_code
