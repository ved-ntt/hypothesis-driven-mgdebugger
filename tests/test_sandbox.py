"""Tracer + sandbox tests. The palindrome case is the worked example in the proposal deck."""
import time
from sandbox import run_call, run_traced, sequences, call_expr_from_input
from tracer import VariableTracer, RETURN

BUGGY = '''
def is_palindrome(t):
    return t == t[::-1]

def find_longest_suffix(s):
    suffix_start = 0
    for i in range(len(s)):
        if is_palindrome(s[i:]):
            suffix_start = i
    return suffix_start

def build_result(s, start):
    return s + s[:start][::-1]

def make_palindrome(s):
    if not s:
        return ''
    return build_result(s, find_longest_suffix(s))
'''

FIXED = BUGGY.replace('''    suffix_start = 0
    for i in range(len(s)):
        if is_palindrome(s[i:]):
            suffix_start = i
    return suffix_start''', '''    for i in range(len(s)):
        if is_palindrome(s[i:]):
            return i
    return 0''')


def test_public_test_fails_on_buggy_code():
    r = run_call(BUGGY, "make_palindrome('cata')")
    assert r["status"] == "ok" and r["result"] == "catatac"


def test_h1_rejected_loop_starts_at_zero():
    r = run_traced(BUGGY, "find_longest_suffix('cata')", "find_longest_suffix", ["i"])
    assert sequences(r)["i"] == [0, 1, 2, 3]          # H1 predicted [1, 2, 3]: rejected


def test_h2_confirmed_overwrites():
    r = run_traced(BUGGY, "find_longest_suffix('cata')", "find_longest_suffix", ["suffix_start"])
    seq = sequences(r)
    assert seq["suffix_start"] == [0, 1, 3]            # H2 predicted [0, 1, 3]: confirmed
    assert seq[RETURN] == [3]


def test_fix_passes():
    assert run_call(FIXED, "find_longest_suffix('cata')")["result"] == 1
    assert run_call(FIXED, "make_palindrome('cata')")["result"] == "catac"


def test_trace_target_when_called_from_parent():
    # observing a subfunction while running the root call
    r = run_traced(BUGGY, "make_palindrome('cata')", "find_longest_suffix", ["suffix_start"])
    assert sequences(r)["suffix_start"] == [0, 1, 3]


def test_infinite_loop_is_a_timeout_observation():
    t0 = time.time()
    r = run_call("def f():\n    while True:\n        pass\n", "f()", timeout=2)
    assert r["status"] == "timeout" and time.time() - t0 < 6


def test_exception_is_an_observation():
    r = run_traced("def f(x):\n    y = x + 1\n    return 10 // (y - 2)\n", "f(1)", "f", ["y"])
    assert r["status"] == "exception" and "ZeroDivisionError" in r["exception"]
    assert sequences(r)["y"] == [2]


def test_program_stdout_does_not_break_result():
    r = run_call("def f():\n    print('noise')\n    return 5\n", "f()")
    assert r["result"] == 5 and "noise" in r["stdout"]


def test_mutation_is_snapshotted():
    code = "def f():\n    xs = []\n    for k in range(3):\n        xs.append(k)\n    return xs\n"
    r = run_traced(code, "f()", "f", ["xs"])
    assert sequences(r)["xs"] == [[], [0], [0, 1], [0, 1, 2]]


def test_recursion_first_call_only_and_all_calls():
    code = "def fact(n):\n    acc = n\n    if n <= 1:\n        return 1\n    return acc * fact(n - 1)\n"
    first = run_traced(code, "fact(3)", "fact", ["acc"])
    assert first["trace"]["calls_seen"] == 1 and sequences(first)[RETURN] == [6]
    every = run_traced(code, "fact(3)", "fact", ["acc"], calls="all")
    assert every["trace"]["calls_seen"] == 3 and sequences(every, call=2)["acc"] == [1]


def test_large_values_are_truncated_and_events_capped():
    code = "def f():\n    s = ''\n    for k in range(2000):\n        s += 'x'\n    return len(s)\n"
    r = run_traced(code, "f()", "f", ["s"], max_events=50, max_repr=40)
    assert r["trace"]["truncated"] and len(r["trace"]["events"]) == 50
    assert all(len(e["repr"]) <= 40 + len("...<truncated>") for e in r["trace"]["events"])


def test_non_json_values_keep_repr():
    r = run_traced("def f():\n    s = {3, 1}\n    return s\n", "f()", "f", ["s"])
    assert sequences(r, as_repr=True)["s"] == ["{1, 3}"]


def test_syntax_error_in_candidate():
    r = run_call("def f(:\n    pass\n", "f()")
    assert r["status"] == "exception" and "SyntaxError" in r["exception"]


def test_call_expr_matches_mgdebugger_inputs():
    assert call_expr_from_input("f", {"s": "cata", "k": 2}) == "f(s='cata', k=2)"
    assert call_expr_from_input("g", [1, 2]) == "g([1, 2])"


def test_tracer_in_process():
    def g(n):
        total = 0
        for k in range(n):
            total += k
        return total
    with VariableTracer("g", ["total"]) as t:
        g(4)
    assert t.sequences()["total"] == [0, 1, 3, 6]
