# The LLM guesses, the code judges
# Improvement upon the research paper where there was merely execution simulation

# Imports ast to find the target function and the variables it can be observed on
# Imports json to parse the LLM's structured replies

from __future__ import annotations

import ast
import json
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

# Imports the sandbox/tracer module functions for running code safely

try:
    from .sandbox import run_call, run_traced, call_expr_from_input
    from .tracer import RETURN, EXCEPTION
except ImportError:
    from sandbox import run_call, run_traced, call_expr_from_input
    from tracer import RETURN, EXCEPTION


# Defaults (overridable by argument)
DEFAULT_K = 3              # max hypotheses per node
DEFAULT_TIMEOUT = 5.0      # seconds per sandbox run
MAX_OBSERVE = 3            # variables per hypothesis
MAX_SEQUENCE = 50          # values per predicted sequence


# Box holding the raw text that comes back from the LLM
@dataclass
class LLMReply:
    text: str


# Says that anything that has a .complete(messages) -> LLMReply method counts as an LLM
class LLM(Protocol):
    def complete(self, messages: list[dict]) -> LLMReply: ...


# Records a trip through the loop: the hypothesis proposed, the observation when the code ran, and if the hypothesis was confirmed or rejected, as well as the reason
@dataclass
class Round:
    n: int
    hypothesis: Optional[dict]     # None when the reply was invalid
    observed: dict
    verdict: str                   # confirmed | rejected | invalid
    reason: str
    run_status: str = ""           # ok | exception | timeout | crash | memory; "" if nothing ran
    validation_errors: list[str] = field(default_factory=list)


# Final answer for one function: did it end up fixed, was it already passing, or did it run out of rounds
@dataclass
class NodeResult:
    status: str                    # already_passing | fixed | fix_failed | no_confirmed
    fixed_function: Optional[str] = None
    rounds: list[Round] = field(default_factory=list)


# running the code

# Ground truth function
# Builds the function call, runs it in the sandbox, and checks the output against the expected answer.
# Returns (passed, what actually happened); the second part is shown to the LLM as "got ...".

def run_test(program: str, target: str, test: dict, timeout: float = DEFAULT_TIMEOUT) -> tuple[bool, str]:
    res = run_call(program, call_expr_from_input(target, test["input"]), timeout=timeout)
    status = res.get("status")
    if status == "ok":
        return res.get("result") == test["expected_output"], res.get("result_repr") or repr(res.get("result"))
    if status == "timeout":
        return False, f"timeout after {timeout:g} s"
    if status == "exception":
        return False, res.get("exception") or "exception"
    return False, f"run ended with status '{status}'"


# For each variable name, it pulls the list of real values that variable took during a traced run.

def extract_observed_values(run_result: dict, name: str) -> list:
    trace = run_result.get("trace") or {}
    return [e["value"] for e in trace.get("events", []) if e["call"] == 0 and e["var"] == name]


# Compares LLM predictions against what actually happened.
# A run that timed out or crashed recorded nothing, so it can never confirm anything.

def judge(hyp: dict, run_result: dict) -> tuple[str, str]:
    status = run_result.get("status")
    if status == "timeout":
        return "rejected", f"timed out after {run_result.get('timeout_s', '?')} s, no values recorded"
    if status not in ("ok", "exception"):
        return "rejected", f"run ended with status '{status}', no values recorded"

    reasons = []
    ok = True
    for name in hyp["observe"]:
        observed = extract_observed_values(run_result, name)
        predicted = hyp["expect"][name]
        if observed != predicted:
            ok = False
        reasons.append(f"{name}: predicted {predicted!r}, observed {observed!r}")
    return ("confirmed" if ok else "rejected"), "; ".join(reasons)


# Instructions sent to the LLM
# Instructions tells the LLM to propose one hypothesis, and predict specific variable values.

# (wording of the rules from the build spec, section 5: the model must know how values are recorded)
HYPOTHESIS_SYSTEM = (
    "You debug Python by forming hypotheses and predicting what the code will do.\n"
    "A program and a failing test are given. Propose ONE hypothesis about why the test fails, and predict "
    "concrete values that named variables will take when the CURRENT, BUGGY code runs on the failing test, "
    "if your hypothesis is right. Do not predict what correct code would do.\n"
    "The code will be run and your prediction checked automatically against the real values.\n\n"
    "Rules:\n"
    "- Variables are recorded each time their value changes; consecutive equal values appear once. "
    "The first assignment counts. __return__ is the return value; __exception__ is \"TypeName: message\".\n"
    "- Observe 1 to 3 parameters or local variables of the function under test (or __return__ / "
    "__exception__) and predict every value each one takes, in order.\n"
    "- Write values as JSON: strings quoted, tuples as lists, None as null.\n"
    "- Choose variables whose values would differ if your hypothesis were wrong.\n"
    "- Do not repeat a hypothesis listed under Earlier hypotheses.\n"
    "- Reply with one JSON object in a ```json block and nothing else:\n"
    '{"hypothesis": "...", "observe": ["name"], "expect": {"name": [1, 2]}, "why": "..."}'
)

# Tells the LLM to fix and rewrite only what the confirmed hypothesis requires to fix the function
FIX_SYSTEM = "You fix Python functions and change only what the confirmed hypothesis requires."


def extract_fenced(text: str, lang: str) -> Optional[str]:
    start_marker = f"```{lang}"
    start = text.find(start_marker)
    if start == -1:
        return None
    start += len(start_marker)
    end = text.find("```", start)
    if end == -1:
        return None
    return text[start:end].strip()


# Names the tracer can actually record inside the target: its parameters, names its own body
# assigns, and __return__ / __exception__. Names bound only in comprehensions, lambdas or nested
# functions live in other frames, so the tracer can't see them. None if the target isn't found.

def observable_names(program: str, target: str) -> Optional[set[str]]:
    try:
        tree = ast.parse(program)
    except SyntaxError:
        return None
    fn = next((node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target), None)
    if fn is None:
        return None
    args = fn.args
    names = {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs}
    names |= {a.arg for a in (args.vararg, args.kwarg) if a is not None}
    names |= {RETURN, EXCEPTION}
    other_scopes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef,
                    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, other_scopes):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)                      # =, +=, x: int =, for, with-as, :=
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)                    # except E as name
        stack.extend(ast.iter_child_nodes(node))
    return names


# Checks a parsed reply before anything runs. Returns a list of error messages (empty = valid).

def validate_hypothesis(hyp: Any, target: str, observable: Optional[set[str]]) -> list[str]:
    if not isinstance(hyp, dict):
        return ["the reply must be one JSON object"]
    errors = []
    if not isinstance(hyp.get("hypothesis"), str) or not hyp["hypothesis"].strip():
        errors.append('"hypothesis" must be a non-empty string')

    observe = hyp.get("observe")
    if not (isinstance(observe, list) and 1 <= len(observe) <= MAX_OBSERVE
            and all(isinstance(name, str) for name in observe)):
        errors.append(f'"observe" must be a list of 1 to {MAX_OBSERVE} variable names')
        observe = []
    elif observable is not None:
        for name in observe:
            if name not in observable:
                errors.append(f'"observe": {name!r} is not a parameter of {target} or a variable it assigns; '
                              f'choose from {", ".join(sorted(observable))}')

    expect = hyp.get("expect")
    if not isinstance(expect, dict):
        errors.append('"expect" must be an object with one entry per name in "observe"')
    else:
        missing = [name for name in observe if name not in expect]
        extra = [name for name in expect if name not in observe]
        if missing:
            errors.append(f'"expect" has no entry for {", ".join(missing)}')
        if extra:
            errors.append(f'"expect" has entries not listed in "observe": {", ".join(map(str, extra))}')
        for name in observe:
            if name in expect and not (isinstance(expect[name], list) and len(expect[name]) <= MAX_SEQUENCE):
                errors.append(f'"expect"["{name}"] must be a list of at most {MAX_SEQUENCE} values, in order')
    return errors


# Pulls the JSON out of a reply (a ```json block, else the outermost {...}) and validates it.

def parse_hypothesis(text: str, target: str, observable: Optional[set[str]]) -> tuple[Optional[dict], list[str]]:
    block = extract_fenced(text, "json")
    if block is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end < start:
            return None, ["no JSON object found; reply with one object in a ```json block"]
        block = text[start:end + 1]
    try:
        hyp = json.loads(block)
    except json.JSONDecodeError as e:
        return None, [f"the JSON does not parse: {e}"]
    return hyp, validate_hypothesis(hyp, target, observable)


# Builds the prompt sent to the LLM (the program source, the function under test, which test is failing
# and what it actually returned, and earlier hypotheses), then parses and validates the reply.
# An invalid reply gets one retry with the errors quoted back. Returns (hypothesis or None, errors).

def ask_hypothesis(llm: LLM, program: str, target: str, test: dict, actual: str,
                   memory: list[str], observable: Optional[set[str]]) -> tuple[Optional[dict], list[str]]:
    earlier = "\n".join(memory) or "none"
    prompt = (
        f"## Program\n{program}\n\n"
        f"## Function under test: {target}\n\n"
        f"## Failing test\n{call_expr_from_input(target, test['input'])} "
        f"expected {test['expected_output']!r}  got {actual}\n\n"
        f"## Earlier hypotheses (don't repeat)\n{earlier}"
    )
    messages = [{"role": "system", "content": HYPOTHESIS_SYSTEM},
                {"role": "user", "content": prompt}]
    reply = llm.complete(messages)
    hyp, errors = parse_hypothesis(reply.text, target, observable)
    if errors:
        retry = "Your reply was invalid:\n" + "\n".join(errors) + "\nReply again with one corrected JSON object."
        messages = messages + [{"role": "assistant", "content": reply.text},
                               {"role": "user", "content": retry}]
        reply = llm.complete(messages)
        hyp, errors = parse_hypothesis(reply.text, target, observable)
    return (None if errors else hyp), errors


# First and last line of a def, decorators included.
def _def_span(node: ast.AST) -> tuple[int, int]:
    return min([d.lineno for d in node.decorator_list] + [node.lineno]), node.end_lineno


# Source of the top-level def `target` in `code` (decorators included), or None if there isn't one.
def function_source(code: str, target: str) -> Optional[str]:
    code = textwrap.dedent(code)
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target:
            start, end = _def_span(node)
            return "\n".join(code.splitlines()[start - 1:end])
    return None


# Once a hypothesis is confirmed, it builds a prompt telling the LLM what was confirmed and asks it to rewrite that function.
# Takes the last ```python block that defines the target and keeps only that def: any other functions in the
# block are ignored, so what gets tested here is exactly what MGDebugger stores as the new function.
def ask_fix(llm: LLM, program: str, target: str, hyp: dict, rnd: Round) -> Optional[str]:
    prompt = (
        f"## Program\n{program}\n\n"
        f"## Confirmed hypothesis\n{hyp['hypothesis']}\n"
        f"Observed: {rnd.observed}\n\n"
        f"## Reply\nRewrite ONLY {target}, same name and parameters, in one ```python block."
    )
    reply = llm.complete([{"role": "system", "content": FIX_SYSTEM},
                          {"role": "user", "content": prompt}])
    for block in reversed(re.findall(r"```python\s*(.*?)```", reply.text, re.DOTALL)):
        source = function_source(block, target)
        if source:
            return source
    return None


# Takes the LLM proposed replacement and splices it into the original program's source text.
# Parses the program with ast to find which lines the old function occupied (decorators included),
# and swaps them out for the new ones. Every other line stays as it was.
def replace_function(program: str, target: str, new_source: str) -> str:
    tree = ast.parse(program)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target:
            start, end = _def_span(node)
            lines = program.splitlines(keepends=True)
            return "".join(lines[:start - 1] + [new_source.rstrip("\n") + "\n"] + lines[end:])
    raise ValueError(f"no function named {target!r} found")


def _short(text: str, limit: int = 100) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


# the main loop
# run every test once; if all already pass, there's nothing to do
# otherwise focus on the first failing test, remembering what it actually returned
# loop up to k times by asking for a hypothesis, running the code with tracing, and judging against reality.
# if a hypothesis is confirmed, ask for a fix and re-run all tests on the original program with only the target replaced
# every round adds a note to memory (rejected, or confirmed but the fix failed) so the LLM won't retry the same idea


def debug_node(program: str, target: str, tests: list[dict], llm: LLM, k: int = DEFAULT_K,
               timeout: float = DEFAULT_TIMEOUT) -> NodeResult:
    baseline = [run_test(program, target, t, timeout) for t in tests]
    if all(passed for passed, _ in baseline):
        return NodeResult(status="already_passing")

    focus_index = next(i for i, (passed, _) in enumerate(baseline) if not passed)
    focus, actual = tests[focus_index], baseline[focus_index][1]
    observable = observable_names(program, target)
    memory: list[str] = []
    rounds: list[Round] = []
    any_confirmed = False

    for n in range(1, k + 1):
        hyp, errors = ask_hypothesis(llm, program, target, focus, actual, memory, observable)
        if hyp is None:
            rounds.append(Round(n, None, {}, "invalid", "; ".join(errors), validation_errors=errors))
            continue

        run = run_traced(program, call_expr_from_input(target, focus["input"]), target, hyp["observe"],
                         timeout=timeout)
        verdict, reason = judge(hyp, run)
        observed = {name: extract_observed_values(run, name) for name in hyp["observe"]}
        rnd = Round(n, hyp, observed, verdict, reason, run_status=run.get("status", ""))
        rounds.append(rnd)

        outcome = "REJECTED"
        if verdict == "confirmed":
            any_confirmed = True
            new_fn = ask_fix(llm, program, target, hyp, rnd)
            if not new_fn:
                outcome = f"CONFIRMED, but the reply had no ```python block defining {target}"
            else:
                new_program = replace_function(program, target, new_fn)
                fix_results = [run_test(new_program, target, t, timeout) for t in tests]
                if all(passed for passed, _ in fix_results):
                    return NodeResult(status="fixed", fixed_function=new_fn, rounds=rounds)
                failures = [f"[{i}] got {_short(got)}" for i, (passed, got) in enumerate(fix_results) if not passed]
                more = f" (and {len(failures) - 3} more)" if len(failures) > 3 else ""
                outcome = "CONFIRMED, but the fix failed: " + "; ".join(failures[:3]) + more

        memory.append(f'Round {n}: "{hyp["hypothesis"]}" | {reason} | {outcome}')

    return NodeResult(status="fix_failed" if any_confirmed else "no_confirmed", rounds=rounds)


# wraps the openai client pointed at Anthropic's OpenAI-compatible endpoint


class ClaudeLLM:
    def __init__(self, api_key: str, model: str = "claude-haiku-5-5"):
        from openai import OpenAI
        self._client = OpenAI(base_url="https://api.anthropic.com/v1/", api_key=api_key)
        self._model = model

    def complete(self, messages: list[dict]) -> LLMReply:
        resp = self._client.chat.completions.create(model=self._model, messages=messages, max_tokens=2000)
        return LLMReply(text=resp.choices[0].message.content or "")
