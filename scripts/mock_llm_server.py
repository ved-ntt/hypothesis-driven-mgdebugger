"""A fake OpenAI-compatible server for testing the pipeline wiring with no model.

  python scripts/mock_llm_server.py --mode noop    # never fixes anything
  python scripts/mock_llm_server.py --mode oracle --seeds <seed.jsonl>   # "fixes" with the canonical solution

Decompose: echoes the code back (one function). Derive tests: returns the gold tests.
Debug: noop returns the function unchanged; oracle returns the canonical solution.
Variant B: hypotheses predict a value the first argument keeps (usually confirmed); fixes as above.
Variant C: a breakpoint on the entry function's first statement that always diverges; fixes as above.
It only checks plumbing (calls, logging, scoring); its results mean nothing.
"""
import argparse, ast, json, re
from http.server import BaseHTTPRequestHandler, HTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=18889)
ap.add_argument("--mode", choices=["noop", "oracle"], default="noop")
ap.add_argument("--seeds", default=None)
args = ap.parse_args()

CANON = {}
if args.seeds:
    for line in open(args.seeds):
        p = json.loads(line)
        CANON[p["entry_point"]] = p["prompt"] + p["canonical_solution"]


def between(text, start, end):
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = text.find(end, i)
    return text[i:j if j >= 0 else None].strip()


def answer(prompt):
    if "Convert the following Python code" in prompt:
        code = between(prompt, "### Original Code:", "### Instructions:")
        return "Analysis: single function.\n```python\n" + code + "\n```"
    if "Generate the same number of test cases" in prompt:
        gold = between(prompt, "### Gold Test Cases for the main function", "### Function to generate")
        return "```json\n" + json.dumps({"test_cases": json.loads(gold)}) + "\n```"
    if "Debug the following Python function" in prompt:
        code = between(prompt, "### Function:", "### Test Cases:")
        name = re.search(r"def\s+(\w+)", code).group(1)
        if args.mode == "oracle" and name in CANON:
            code = CANON[name]
        return "Trace: ...\n```python\n" + code + "\n```"
    if "## Program (numbered lines)" in prompt or prompt.startswith("Your breakpoint reply was invalid"):
        return "```json\n" + json.dumps(mock_breakpoints(prompt)) + "\n```"
    if "## Breakpoint evidence" in prompt:
        # Variant C fix prompt: noop returns the function unchanged, oracle the canonical one
        name = re.search(r"Rewrite ONLY (\w+)", prompt).group(1)
        program = between(prompt, "## Program", "## Failing test")
        code = CANON.get(name) if args.mode == "oracle" else None
        if code is None:
            node = next((n for n in ast.parse(program).body if getattr(n, "name", None) == name), None)
            code = ast.get_source_segment(program, node) if node else "pass"
        return "```python\n" + code + "\n```"
    if "## Failing test" in prompt or prompt.startswith("Your reply was invalid"):
        return "```json\n" + json.dumps(mock_hypothesis(prompt)) + "\n```"
    if "## Confirmed hypothesis" in prompt:
        # Variant B fix prompt: noop returns the target unchanged (the fix fails), oracle the canonical one
        name = re.search(r"Rewrite ONLY (\w+)", prompt).group(1)
        code = CANON.get(name) if args.mode == "oracle" else None
        return "```python\n" + (code or between(prompt, "## Program", "## Confirmed hypothesis")) + "\n```"
    return "```python\npass\n```"


def mock_hypothesis(prompt):
    """Variant B hypothesis prompt. Predicts that the first keyword argument of the failing call keeps
    its input value, which a real run confirms unless the target reassigns it, so a mock run goes
    through trace, verdict and the fix step. Falls back to a prediction that is always rejected."""
    hyp = {"hypothesis": "mock", "observe": ["__return__"], "expect": {"__return__": []}, "why": "mock"}
    try:
        call = ast.parse(between(prompt, "## Failing test", " expected "), mode="eval").body
        kw = call.keywords[0]
        value = ast.literal_eval(kw.value)
        json.dumps(value)
        hyp.update(observe=[kw.arg], expect={kw.arg: [value]})
    except (SyntaxError, ValueError, TypeError, AttributeError, IndexError):
        pass
    return hyp


def mock_breakpoints(prompt):
    """Variant C localize prompt (and its retry, which repeats nothing, so reuse the first prompt's
    listing if present). Breaks on the first statement of the last function with an expectation no
    real value matches, so every mock round diverges and goes on to the fix step."""
    listing = between(prompt, "## Program (numbered lines)", "## Failing test")
    program = "\n".join(re.sub(r"^\s*\d+ \|", "", l)[1:] if re.match(r"^\s*\d+ \| ", l)
                         else re.sub(r"^\s*\d+ \|", "", l) for l in listing.splitlines())
    rounds = between(prompt, "## Earlier rounds", "\x00")
    used = set(int(x) for x in re.findall(r"line (\d+) `", rounds))
    line = 1
    try:
        funcs = [n for n in ast.parse(program).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        stmts = [st.lineno for st in ast.walk(funcs[-1]) if isinstance(st, ast.stmt) and st is not funcs[-1]
                 and not (isinstance(st, ast.Expr) and isinstance(getattr(st, "value", None), ast.Constant))]
        line = next((l for l in sorted(set(stmts)) if l not in used), stmts[0])
    except (SyntaxError, IndexError):
        pass
    return {"breakpoints": [{"line": line, "expr": "len(str(1))", "expect": [99]}], "why": "mock"}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][-1]["content"]
        text = answer(prompt)
        resp = {"id": "mock", "object": "chat.completion", "created": 0, "model": body.get("model", "mock"),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": len(prompt) // 4, "completion_tokens": len(text) // 4,
                          "total_tokens": (len(prompt) + len(text)) // 4}}
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
