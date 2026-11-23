"""Value comparison shared by MGDebugger's fixed harness and the hypothesis loop's verdict.

MGDebugger's evaluate() compares repr strings, so a correct function returning (2.0, 2.2) fails a
test that expects [2.0, 2.2] (tests travel as JSON, which has no tuples), and 0.30000000000000004
fails against 0.3. Both sides are normalised here before comparing:

  tuple -> list; set / frozenset -> list sorted by repr; dict keys -> str (as JSON would)
  numbers equal within rel 1e-9 / abs 1e-6; 1 == 1.0; booleans equal only booleans (True != 1)
  ndigits: round both sides first (public tests written as round(f(x), 2) == y)
"""
from __future__ import annotations

import ast
import math
from typing import Any

_MISSING = object()


def from_repr(text: str) -> Any:
    """Python value of a repr string when it is a literal (recovers tuples, sets, None), else the text."""
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return text


def normalize(value: Any) -> Any:
    if isinstance(value, tuple) or isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((normalize(v) for v in value), key=repr)
    if isinstance(value, dict):
        return {str(k): normalize(v) for k, v in value.items()}
    return value


def _equal(a: Any, b: Any, ndigits) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if ndigits is not None:
            a, b = round(a, ndigits), round(b, ndigits)
        if isinstance(a, float) and isinstance(b, float) and (math.isnan(a) or math.isnan(b)):
            return math.isnan(a) and math.isnan(b)
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y, ndigits) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k], ndigits) for k in a)
    return type(a) is type(b) and a == b


def values_equal(actual: Any, expected: Any, ndigits=None) -> bool:
    """True when actual and expected are the same value after normalising both."""
    return _equal(normalize(actual), normalize(expected), ndigits)


def sequences_equal(observed: list, predicted: list) -> bool:
    return isinstance(observed, list) and isinstance(predicted, list) and values_equal(observed, predicted)
