"""Live version of smoke_test_basic.py — uses the real Claude API instead of
ScriptedLLM. Run this on your own machine (WSL), not in any sandboxed session.

Setup, once:
  pip install openai
  export HDMG_API_KEY="sk-ant-..."        # your real key, as an env var — never hardcode it here

Then just:
  python3 live_demo.py
"""
import os
import sys

sys.path.insert(0, "hdmg")
sys.path.insert(0, ".")
from hdmg.hypothesis_loop import debug_node, ClaudeLLM

PROGRAM = """def is_palindrome(t):
    return t == t[::-1]

def find_longest_suffix(s):
    suffix_start = 0
    for i in range(len(s)):
        if is_palindrome(s[i:]):
            suffix_start = i
    return suffix_start
"""

TESTS = [{"input": {"s": "cata"}, "expected_output": 1}]

api_key = os.environ.get("HDMG_API_KEY")
if not api_key:
    sys.exit("Set HDMG_API_KEY first, e.g.:  export HDMG_API_KEY=\"sk-ant-...\"")

llm = ClaudeLLM(api_key=api_key)
result = debug_node(PROGRAM, "find_longest_suffix", TESTS, llm=llm)

print("status:", result.status)
for r in result.rounds:
    print(f"\n  round {r.n}:")
    print(f"    hypothesis: {r.hypothesis.get('hypothesis')}")
    print(f"    verdict:    {r.verdict}")
    print(f"    reason:     {r.reason}")

if result.fixed_function:
    print("\n--- fixed function ---")
    print(result.fixed_function)
else:
    print("\nNo fix confirmed within the round limit.")