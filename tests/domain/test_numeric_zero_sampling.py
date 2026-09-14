"""``is_numerically_zero`` must absorb float-path noise on symbol-bearing diffs.

2026-09-14 turbine round: the verifier recomputed a substitution along a
different float path than the archived output; the combined power exponent
differed by one ULP (``0.99999999999999989`` vs ``1.0``). The residual carried
a free symbol, the no-tolerance branch flipped a correct step to FAILED, and
the failure details printed both sides as the same 15-digit string.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.final_result import is_numerically_zero


def test_float_ulp_symbolic_residual_is_zero():
    a = sp.Symbol("a", positive=True)
    diff = a**sp.Float("0.99999999999999989") - a**sp.Float("1.0")
    assert is_numerically_zero(diff)


def test_genuinely_different_power_stays_nonzero():
    a = sp.Symbol("a", positive=True)
    assert not is_numerically_zero(a - a**sp.Rational(1, 2))
    assert not is_numerically_zero(a - 2 * a)


def test_abs_difference_respects_sign_assumptions():
    apos = sp.Symbol("a", positive=True)
    areal = sp.Symbol("b", real=True)
    assert is_numerically_zero(apos - sp.Abs(apos))
    assert not is_numerically_zero(areal - sp.Abs(areal))


def test_unsamplable_expression_conservatively_false():
    x = sp.Symbol("x")
    assert not is_numerically_zero(sp.Derivative(sp.Function("f")(x), x))


def test_two_symbol_residual_needs_asymmetric_samples():
    x, y = sp.symbols("x y", positive=True)
    assert is_numerically_zero(x * y - y * x)
    # ``x - y`` vanishes only at symmetric sample points; joint sampling must
    # still catch the asymmetric ones.
    assert not is_numerically_zero(x - y)
