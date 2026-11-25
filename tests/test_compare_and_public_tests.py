"""hdmg/compare.py (value comparison) and hdmg/public_tests.py (parsing given tests)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from hdmg.compare import from_repr, sequences_equal, values_equal  # noqa: E402
from hdmg.public_tests import parse_assert, parse_public_tests     # noqa: E402


# ---- comparison ---------------------------------------------------------------------------------
def test_tuple_matches_list_and_nested():
    assert values_equal((2.0, 2.2), [2.0, 2.2])
    assert values_equal([(1, 2), (3, 4)], [[1, 2], [3, 4]])


def test_sets_compare_as_sorted_lists():
    assert values_equal({3, 1}, [1, 3])
    assert values_equal(from_repr("{3, 1}"), [1, 3])


def test_float_tolerance_and_int_float():
    assert values_equal(0.1 + 0.2, 0.3)
    assert values_equal(1, 1.0)
    assert not values_equal(0.3, 0.31)


def test_booleans_only_equal_booleans():
    assert not values_equal(True, 1)
    assert not values_equal([1, 0], [True, False])
    assert values_equal(None, None) and not values_equal(None, 0)


def test_round_digits():
    assert values_equal(-0.49999999, -0.5, ndigits=2)
    assert not values_equal(-0.49, -0.5, ndigits=2)


def test_dict_keys_as_json_would():
    assert values_equal({1: "a"}, {"1": "a"})


def test_truncated_repr_stays_text_and_never_matches_a_value():
    text = "'aaaaaaaa...<truncated>"
    assert from_repr(text) == text
    assert not sequences_equal([from_repr(text)], ["aaaaaaaa"])


def test_strings_are_not_lists():
    assert not values_equal("ab", ["a", "b"])


# ---- parsing given tests -------------------------------------------------------------------------
PROG = '''
def encode_cyclic(s):
    return s[1:] + s[:1]

def decode_cyclic(s):
    return s[-1:] + s[:-1]

def find_zero(xs):
    return -0.5

def longest(strings):
    return None
'''


def test_equality_assert():
    case, _ = parse_assert("assert find_zero([1, 2]) == -0.5", "find_zero", ["xs"], PROG)
    assert case["input"] == {"xs": [1, 2]} and case["expected_output"] == -0.5 and "round" not in case


def test_round_wrapper_is_kept_with_its_digits():
    case, _ = parse_assert("assert round(find_zero([1, 2]), 2) == -0.5", "find_zero", ["xs"], PROG)
    assert case["input"] == {"xs": [1, 2]} and case["round"] == 2


def test_is_none():
    case, _ = parse_assert("assert longest([]) is None", "longest", ["strings"], PROG)
    assert case["input"] == {"strings": []} and case["expected_output"] is None


def test_argument_that_calls_a_helper_is_evaluated():
    case, _ = parse_assert("assert decode_cyclic(encode_cyclic('abc')) == 'abc'", "decode_cyclic", ["s"], PROG)
    assert case["input"] == {"s": "bca"}


def test_unsupported_forms_are_reported_not_dropped_silently():
    parsed, skipped = parse_public_tests(["assert len(longest([])) == 0", "x = 1"], "longest", PROG)
    assert parsed == [] and len(skipped) == 2 and all(s["reason"] for s in skipped)


def test_mcnemar_exact():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    from compare_runs import mcnemar_exact
    assert mcnemar_exact(0, 0) == 1.0
    assert abs(mcnemar_exact(0, 6) - 2 / 64) < 1e-12      # all 6 discordant pairs favour one side
    assert abs(mcnemar_exact(3, 3) - 1.0) < 1e-12
