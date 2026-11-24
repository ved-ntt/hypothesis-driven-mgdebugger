"""Run untrusted code in a separate Python process, with a timeout and memory cap.

Two entry points:
  run_call(code, call_expr)                         -> what the call returned / printed / raised
  run_traced(code, call_expr, func_name, variables) -> the same, plus a VariableTracer record
  run_breakpoints(code, call_expr, breakpoints)     -> the same, plus every breakpoint hit (variant L)

A timeout or exception is an observation, not an error: it comes back in "status".
Upstream MGDebugger runs code with exec() in a thread of the debugger's own process;
a timed-out thread there keeps running. Here the child process is killed.
"""
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_MARK = "@@HDMG_RESULT@@"

# The same imports MGDebugger prepends to every program (utils.STARTING_CODE)
PRELUDE = "\n".join([
    "import math", "import re", "import sys", "import copy", "import datetime", "import itertools",
    "import collections", "import heapq", "import statistics", "import functools", "import hashlib",
    "import string", "from typing import *", "from collections import *", "import heapq as hq",
    "from itertools import *", "from math import *", "from statistics import *",
    "from functools import *", "from datetime import *", "from copy import *",
])

# Runs inside the child. Reads one JSON job from stdin, prints one JSON result after _MARK.
_CHILD = r'''
import io, json, sys, traceback
job = json.loads(sys.stdin.read())
sys.path.insert(0, job["pkg_dir"])
if job.get("mem_mb"):
    try:
        import resource
        lim = job["mem_mb"] * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
    except Exception:
        pass  # not available on Windows
from tracer import VariableTracer, BreakpointTracer
class _SoftTimeout(BaseException):
    pass
if job.get("soft_timeout"):
    # stop the program from inside shortly before the parent kills it, so what was recorded
    # up to then (breakpoint hits) still comes back
    import signal
    def _alarm(signum, frame):
        raise _SoftTimeout()
    try:
        signal.signal(signal.SIGALRM, _alarm)
        signal.setitimer(signal.ITIMER_REAL, job["soft_timeout"])
    except (AttributeError, ValueError):
        pass  # no SIGALRM on Windows
out = {"status": "ok", "stdout": "", "result_repr": None, "result": None}
buf = io.StringIO()
real_stdout = sys.stdout
ns = {"__name__": "__hdmg__"}
tracer = None
bp_tracer = None
try:
    sys.stdout = buf
    try:
        exec(compile(job["prelude"], "<prelude>", "exec"), ns)
    except Exception:
        pass  # e.g. numpy missing; keep going
    exec(compile(job["code"], "<candidate>", "exec"), ns)
    if job.get("breakpoints"):
        bp_tracer = BreakpointTracer([(b["line"], b["expr"]) for b in job["breakpoints"]],
                                     max_hits=job.get("max_hits", 20), max_repr=job.get("max_repr", 300))
        with bp_tracer:
            value = eval(job["call"], ns)
    elif job.get("trace"):
        t = job["trace"]
        tracer = VariableTracer(t["func"], t["variables"], calls=t.get("calls", "first"),
                                max_events=t.get("max_events", 500), max_repr=t.get("max_repr", 300))
        with tracer:
            value = eval(job["call"], ns)
    else:
        value = eval(job["call"], ns)
    out["result_repr"] = repr(value)[:2000]
    try:
        json.dumps(value); out["result"] = value
    except (TypeError, ValueError):
        pass
except _SoftTimeout:
    out["status"] = "timeout"
    out["timeout_s"] = job["soft_timeout"]
except MemoryError:
    out["status"] = "memory"
except BaseException as e:
    out["status"] = "exception"
    out["exception"] = f"{type(e).__name__}: {e}"[:1000]
    out["traceback"] = traceback.format_exc()[-2000:]
finally:
    sys.stdout = real_stdout
    if job.get("soft_timeout"):
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        except Exception:
            pass
out["stdout"] = buf.getvalue()[-2000:]
if tracer is not None:
    out["trace"] = tracer.to_dict()
if bp_tracer is not None:
    out["breakpoints"] = bp_tracer.to_list()
print(job["mark"] + json.dumps(out, default=repr))
'''


def _run(job, timeout):
    job = dict(job, pkg_dir=_HERE, mark=_MARK)
    try:
        proc = subprocess.run([sys.executable, "-I", "-c", _CHILD], input=json.dumps(job),
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "timeout_s": timeout}
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(_MARK):
            return json.loads(line[len(_MARK):])
    # child died before printing (segfault, os._exit, memory kill...)
    return {"status": "crash", "returncode": proc.returncode, "stderr": proc.stderr[-2000:]}


def run_call(code, call_expr, timeout=5, mem_mb=512, prelude=PRELUDE):
    """Execute `code`, then evaluate `call_expr` (e.g. "make_palindrome('cata')")."""
    return _run({"code": code, "call": call_expr, "prelude": prelude, "mem_mb": mem_mb}, timeout)


def run_traced(code, call_expr, func_name, variables, timeout=5, mem_mb=512, calls="first",
               max_events=500, max_repr=300, prelude=PRELUDE):
    """run_call, plus every value `variables` take inside `func_name` during the call."""
    trace = {"func": func_name, "variables": list(variables), "calls": calls,
             "max_events": max_events, "max_repr": max_repr}
    return _run({"code": code, "call": call_expr, "prelude": prelude, "mem_mb": mem_mb,
                 "trace": trace}, timeout)


def run_breakpoints(code, call_expr, breakpoints, timeout=5, mem_mb=512, max_hits=20, max_repr=300,
                    prelude=PRELUDE):
    """run_call, plus the value of each breakpoint's expression every time its line is reached.

    breakpoints: [{"line": int, "expr": str}], line numbers counted in `code` from 1. The result's
    "breakpoints" lists, per breakpoint, its hits [{"seq", "repr"}] in execution order."""
    return _run({"code": code, "call": call_expr, "prelude": prelude, "mem_mb": mem_mb,
                 "breakpoints": [{"line": int(b["line"]), "expr": str(b["expr"])} for b in breakpoints],
                 "max_hits": max_hits, "max_repr": max_repr,
                 "soft_timeout": max(0.5, min(timeout - 1.0, timeout * 0.8))}, timeout)


_SCRIPT_CHILD = r'''
import sys
if len(sys.argv) > 1 and int(sys.argv[1]):
    try:
        import resource
        lim = int(sys.argv[1]) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
    except Exception:
        pass
code = sys.stdin.read()
try:
    exec(compile(code, "<script>", "exec"), {"__name__": "__hdmg__"})
except AssertionError as e:
    print("@@HDMG_FAIL@@AssertionError: " + str(e)[:500]); sys.exit(3)
except MemoryError:
    print("@@HDMG_FAIL@@MemoryError"); sys.exit(4)
except BaseException as e:
    print("@@HDMG_FAIL@@" + type(e).__name__ + ": " + str(e)[:500]); sys.exit(5)
'''


def run_script(code, timeout=10, mem_mb=1024):
    """Run a whole script (program + asserts) in a child process. Returns (passed, reason).

    Used by MGDebugger's evaluate_simple / evaluate_given_tests under the fixed harness: upstream
    exec()s the script in a thread of the debugger itself, and a timed-out thread keeps running,
    so a buggy program with an infinite loop that allocates grows until the OS kills the run."""
    try:
        proc = subprocess.run([sys.executable, "-I", "-c", _SCRIPT_CHILD, str(mem_mb)], input=code,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout} s"
    if proc.returncode == 0:
        return True, ""
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("@@HDMG_FAIL@@"):
            return False, line[len("@@HDMG_FAIL@@"):]
    return False, f"exit code {proc.returncode}: {proc.stderr[-300:]}"


def sequences(result, call=0, as_repr=False):
    """{var: [values]} from a run_traced result (first call by default)."""
    out = {}
    for e in (result.get("trace") or {}).get("events", []):
        if e["call"] == call:
            out.setdefault(e["var"], []).append(e["repr"] if as_repr else e["value"])
    return out


def call_expr_from_input(func_name, test_input):
    """Build a call from an MGDebugger test-case input, the way utils.evaluate does:
    a dict is keyword arguments, anything else is passed as the single argument."""
    if isinstance(test_input, dict):
        args = ", ".join(f"{k}={v!r}" for k, v in test_input.items())
    else:
        args = repr(test_input)
    return f"{func_name}({args})"
