# The LLM guesses, the code judges
# Improvement upon the research paper where there was merely execution simulation

# Imports ast 
# Imports json to parse the LLM's structured replies

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

# Imports the sandbox/tracer module functions for running code safely

try:
    from .sandbox import run_call, run_traced, call_expr_from_input
except ImportError:
    from sandbox import run_call, run_traced, call_expr_from_input
    

# Box holding the raw text that comes back from the LLM
@dataclass
class LLMReply:
	text: str
	

# Says that anything that has a .complete(messages) -> LLMReply method counts as an LLm	
class LLM(Protocol):
	def complete(self, messages: list[dict]) -> LLMReply: ...
	

# Records a trip through the loop: the hypothesis proposed, the observation when the code ran, and if the hypothesis was confirmed or rejected, as well as the reason
@dataclass
class Round: 
    n: int
    hypothesis: dict
    observed: dict
    verdict: str       
    reason: str
    
# Final answer for one function: did it end up fixed, was it already passing, or did it run out of rounds
@dataclass
class NodeResult: 
	status: str
	fixed_function: Optional[str] = None
	rounds: list[Round] = field(default_factory=list)
	
# running the code

# Ground truth function
# Builds the function call, runs it in the sandbox, and checks the output against the expected answer. 

def run_test(program: str, target: str, test: dict) -> bool:
    call_expr = call_expr_from_input(target, test["input"])
    res = run_call(program, call_expr, timeout=5)
    return res.get("status") == "ok" and res.get("result") == test["expected_output"]
    
# For each variable name, it pulls the list of real values that variable took during a traced run. 

def extract_observed_values(run_result: dict, name: str) -> list:
	trace = run_result.get("trace") or {}
	return [e["value"] for e in trace.get("events", []) if e["call"] == 0 and e["var"] == name]
	
	
# Compares LLM predictions against what actually happened

def judge(hyp: dict, run_result: dict) -> tuple[str, str]:
	reasons = []
	ok = True
	
	for name in hyp["observe"]:
		observed = extract_observed_values(run_result, name)
		predicted = hyp["expect"][name]
		matched = observed == predicted
		if not matched:
			ok = False
		reasons.append(f"{name}: predicted {predicted!r}, observed {observed!r}")
	return ("confirmed" if ok else "rejected"), "; ".join(reasons)

# Instructions sent to the lLM
# Instructions tells the LLM to propose one hypothesis, and predict specific variable values. 

HYPOTHESIS_SYSTEM = (
    "You debug Python by forming hypotheses and predicting what the code will do. "
    "Propose a SINGLE hypothesis about why the test fails, and predict the exact values "
    "named variables will take when the current buggy code runs, if you're right. "
    "Reply with one JSON object: "
    '{"hypothesis": "...", "observe": ["name1"], "expect": {"name1": [1, 2]}, "why": "..."} '
    "in a ```json block."
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
  
    
# Builds the prompt sent to the LLM (the program source, the function under test, which test is failing, and earlier hypothesis)
# Pulls the JSON block from the reply and parses it
    
def ask_hypothesis(llm: LLM, program: str, target: str, test: dict, memory: list[str]) -> Optional[dict]:
    prompt = (
        f"## Program\n{program}\n\n"
        f"## Function under test: {target}\n\n"
        f"## Failing test\n{call_expr_from_input(target, test['input'])} "
        f"expected {test['expected_output']!r}\n\n"
        f"## Earlier hypotheses (don't repeat)\n{memory or 'none'}"
    )
    reply = llm.complete([{"role": "system", "content": HYPOTHESIS_SYSTEM},
                          {"role": "user", "content": prompt}])
    block = extract_fenced(reply.text, "json")
    if block is None:
        return None
    try:
        return json.loads(block)
    except json.JSONDecodeError:
        return None
       
        
# Once a hypothesis is confirmed, it builds a prompt telling the LLM what was confirmed and asks it to rewrite that function. 
def ask_fix(llm: LLM, program: str, target: str, hyp: dict, rnd: Round) -> Optional[str]:
    prompt = (
        f"## Program\n{program}\n\n"
        f"## Confirmed hypothesis\n{hyp['hypothesis']}\n"
        f"Observed: {rnd.observed}\n\n"
        f"## Reply\nRewrite ONLY {target}, same name and parameters, in one ```python block."
    )
    reply = llm.complete([{"role": "system", "content": FIX_SYSTEM},
                          {"role": "user", "content": prompt}])
    return extract_fenced(reply.text, "python")
        

# Takes the LLM proposed replacement and splices it into the original program's source text. 
# Parses the program with ast to find which lines the old function occupied, and swaps them out for the new ones. 
def replace_function(program: str, target: str, new_source: str) -> str:
    tree = ast.parse(program)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == target:
            lines = program.splitlines(keepends=True)
            new_lines = lines[:node.lineno - 1] + [new_source + "\n"] + lines[node.end_lineno:]
            return "".join(new_lines)
    raise ValueError(f"no function named {target!r} found")


# the main loop
# if all tests already pass, there's nothing to do
# if not all tests are passing, pick one failing test to focus on
# loop up to k times by asking for a hypothesis, running the code with tracing, and judging against reality. 
# if a hypothesis is confirmed, ask for a fix and re-run tests on updated code
# If the fix doesn't pass or the hypothesis was rejected, it adds a note to memory so it won't retry the same hypothesis


def debug_node(program: str, target: str, tests: list[dict], llm: LLM, k: int = 3) -> NodeResult:
    if all(run_test(program, target, t) for t in tests):
        return NodeResult(status="already_passing")
 
    focus = next(t for t in tests if not run_test(program, target, t))
    memory: list[str] = []
    rounds: list[Round] = []
 
    for n in range(1, k + 1):
        hyp = ask_hypothesis(llm, program, target, focus, memory)
        if hyp is None:
            continue 
 
        run = run_traced(program, call_expr_from_input(target, focus["input"]), target, hyp["observe"])
        verdict, reason = judge(hyp, run)
        observed = {name: extract_observed_values(run, name) for name in hyp["observe"]}
        rnd = Round(n, hyp, observed, verdict, reason)
        rounds.append(rnd)
 
        if verdict == "confirmed":
            new_fn = ask_fix(llm, program, target, hyp, rnd)
            if new_fn:
                new_program = replace_function(program, target, new_fn)
                if all(run_test(new_program, target, t) for t in tests):
                    return NodeResult(status="fixed", fixed_function=new_fn, rounds=rounds)
 
        memory.append(f'Round {n}: "{hyp["hypothesis"]}" -> {verdict} ({reason})')
 
    return NodeResult(status="no_confirmed", rounds=rounds)
 
 
# wraps the openai client pointed 

 
class ClaudeLLM:
    def __init__(self, api_key: str, model: str = "claude-haiku-5-5"):
        from openai import OpenAI
        self._client = OpenAI(base_url="https://api.anthropic.com/v1/", api_key=api_key)
        self._model = model
 
    def complete(self, messages: list[dict]) -> LLMReply:
        resp = self._client.chat.completions.create(model=self._model, messages=messages, max_tokens=2000)
        return LLMReply(text=resp.choices[0].message.content or "")
        
        
        
        
        
        