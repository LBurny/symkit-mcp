"""r23 G2: ``SymPyEngine.series`` order semantics (engine level).

The engine must accept ``order=None`` (SymPy's own 6-term default), and must
return an expression that already carries an ``sp.Order`` term unchanged -- it
is already a series, so re-expanding it to the outer order either truncates it
(``order=1`` -> ``O(x)``) or raises ValueError (``order=8``).
"""

from __future__ import annotations

import pytest
import sympy as sp

from symkit.infrastructure.sympy_engine import SymPyEngine

SIN6 = "x - x**3/6 + x**5/120 + O(x**6)"
EXP5 = "1 + x + x**2/2 + x**3/6 + x**4/24 + O(x**5)"
TAN8 = "x + x**3/3 + 2*x**5/15 + 17*x**7/315 + O(x**8)"


@pytest.fixture
def engine() -> SymPyEngine:
    return SymPyEngine()


def test_default_order_is_six_terms(engine: SymPyEngine) -> None:
    expr = engine.parse("sin(x)")

    result = engine.series(expr, "x", "0")

    assert result.is_valid
    assert result.raw == SIN6


def test_none_order_uses_sympy_default(engine: SymPyEngine) -> None:
    expr = engine.parse("sin(x)")

    result = engine.series(expr, "x", "0", None)

    assert result.is_valid
    assert result.raw == SIN6


def test_preexpanded_series_is_returned_unchanged(engine: SymPyEngine) -> None:
    expr = engine.parse("series(sin(x), x, 0, 6)")
    assert expr.sympy_expr.has(sp.Order)

    result = engine.series(expr, "x", "0", 1)

    assert result.is_valid
    assert result.raw == SIN6


def test_preexpanded_series_with_larger_order_does_not_raise(
    engine: SymPyEngine,
) -> None:
    """The old behavior raised ValueError ("Could not calculate 8 terms ...")."""
    expr = engine.parse("series(sin(x), x, 0, 6)")

    result = engine.series(expr, "x", "0", 8)

    assert result.is_valid
    assert result.raw == SIN6


def test_preexpanded_exp_series_unchanged(engine: SymPyEngine) -> None:
    expr = engine.parse("series(exp(x), x, 0, 5)")

    result = engine.series(expr, "x", "0", None)

    assert result.is_valid
    assert result.raw == EXP5


def test_explicit_order_unchanged(engine: SymPyEngine) -> None:
    expr = engine.parse("tan(x)")

    result = engine.series(expr, "x", "0", 8)

    assert result.is_valid
    assert result.raw == TAN8
