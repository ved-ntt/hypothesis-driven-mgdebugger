"""Record selected local variables of one function while it runs.

This is the "observe" half of the hypothesis loop: the LLM names a function and a few
variables, and we record each value those variables take, in order, plus the return
value and any exception. Nothing else is recorded, so the observation stays small.
"""
import copy
import json
import sys

RETURN = "__return__"
EXCEPTION = "__exception__"


def _snapshot(value, max_repr):
    """A copy of the value (so later mutation doesn't change history) and a short repr."""
    try:
        frozen = copy.deepcopy(value)
    except Exception:
        frozen = value
    text = repr(frozen)
    if len(text) > max_repr:
        text = text[:max_repr] + "...<truncated>"
    try:
        json.dumps(frozen)
        jsonable = frozen
    except (TypeError, ValueError):
        jsonable = None
    return frozen, text, jsonable


class VariableTracer:
    """Records changes to `variables` inside every call of `func_name`.

    calls="first" records only the outermost first call (useful for recursion);
    calls="all" records every call, tagged with a call index.
    """

    def __init__(self, func_name, variables, calls="first", max_events=500, max_repr=300):
        self.func_name = func_name
        self.variables = list(variables)
        self.calls = calls
        self.max_events = max_events
        self.max_repr = max_repr
        self.events = []          # one dict per recorded change, in order
        self.truncated = False
        self._call_index = -1
        self._active = {}         # frame id -> call index
        self._last = {}           # (call index, var) -> last frozen value

    # sys.settrace protocol ---------------------------------------------------------
    def _global(self, frame, event, arg):
        if event == "call" and frame.f_code.co_name == self.func_name:
            if self.calls == "first" and self._call_index >= 0:
                return None
            self._call_index += 1
            self._active[id(frame)] = self._call_index
            return self._local
        return None

    def _local(self, frame, event, arg):
        idx = self._active.get(id(frame))
        if idx is None:
            return None
        if event in ("line", "return"):
            self._record_locals(frame, idx)
        if event == "return":
            # arg is None both for "return None" and for an exception unwinding;
            # the exception event (if any) has already been recorded
            self._add(idx, RETURN, arg, frame.f_lineno)
            self._active.pop(id(frame), None)
        elif event == "exception":
            exc_type, exc_value, _ = arg
            self._add(idx, EXCEPTION, f"{exc_type.__name__}: {exc_value}", frame.f_lineno)
        return self._local

    # recording ---------------------------------------------------------------------
    def _record_locals(self, frame, idx):
        local_vars = frame.f_locals
        for name in self.variables:
            if name in local_vars:
                value = local_vars[name]
                key = (idx, name)
                if key in self._last:
                    try:
                        if self._last[key] == value and type(self._last[key]) is type(value):
                            continue
                    except Exception:
                        pass
                frozen, _, _ = _snapshot(value, self.max_repr)
                self._last[key] = frozen
                self._add(idx, name, value, frame.f_lineno)

    def _add(self, idx, name, value, line):
        if len(self.events) >= self.max_events:
            self.truncated = True
            return
        _, text, jsonable = _snapshot(value, self.max_repr)
        self.events.append({"call": idx, "var": name, "line": line, "repr": text, "value": jsonable})

    # public API --------------------------------------------------------------------
    def __enter__(self):
        self._previous = sys.gettrace()
        sys.settrace(self._global)
        return self

    def __exit__(self, *exc):
        sys.settrace(self._previous)
        return False

    def sequences(self, call=0, as_repr=False):
        """{var: [values in order]} for one call (default: the first)."""
        out = {}
        for e in self.events:
            if e["call"] == call:
                out.setdefault(e["var"], []).append(e["repr"] if as_repr else e["value"])
        return out

    def to_dict(self):
        return {"func": self.func_name, "variables": self.variables, "calls_seen": self._call_index + 1,
                "events": self.events, "truncated": self.truncated}
