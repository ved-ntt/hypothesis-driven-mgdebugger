"""A fake OpenAI-compatible server for testing the pipeline wiring with no model.

  python scripts/mock_llm_server.py --mode noop    # never fixes anything
  python scripts/mock_llm_server.py --mode oracle --seeds <seed.jsonl>   # "fixes" with the canonical solution

Decompose: echoes the code back (one function). Derive tests: returns the gold tests.
Debug: noop returns the function unchanged; oracle returns the canonical solution.
It only checks plumbing (calls, logging, scoring); its results mean nothing.
"""
import argparse, json, re
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
    return "```python\npass\n```"


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
