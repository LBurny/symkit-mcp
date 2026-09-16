"""r20 wave-3 operation semantics: gradient coordinates and transform variables.

Two silent-wrong-value defects are pinned here (engine level, plus the
``math()`` surface that triggers them):

* ``gradient`` unconditionally routed through ``sympy.vector``'s CoordSys3D.
  Declared variables that are *not* spatial coordinates (``S``, ``I``, ``u``)
  were matched **by name** into the ``N.x/N.y/N.z`` basis, so
  ``gradient("-beta*S*I/N", "S,I")`` came back as an ``N.i/N.j`` vector built
  from the coordinate symbols — a wrong value with ``success: true``.  Red
  line: a subset of ``{x, y, z}`` keeps the vector-basis semantics (r13); every
  other symbol name means plain partial derivatives, and a declared coordinate
  missing from the expression is a named failure, never a silent rewrite.

* ``ilaplace``/``laplace`` handed ``variable`` straight to SymPy as the
  transform variable without checking it is even in the expression.  A user
  passing the time-domain ``t`` to ``ilaplace`` (whose ``variable`` is the
  frequency-domain symbol) got ``V0*DiracDelta(t)/(s*(C1*R1*s + 1))`` with
  ``success: true``.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit.domain.entities import Expression
from symkit.domain.expression_parser import parse_expression_string
from symkit.infrastructure.sympy_engine import SymPyEngine
from symkit_mcp.tools.math import register_math_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _engine() -> SymPyEngine:
    return SymPyEngine()


def _parse(text: str) -> Expression:
    expr = _engine().parse(text)
    assert expr.is_valid, expr.error
    return expr


def _math() -> Any:
    mcp = MockMCP()
    register_math_tools(mcp)
    return mcp.tools["math"]


def _partials(result: Expression) -> list[Any]:
    value = result.sympy_expr
    assert isinstance(value, sp.Tuple), value
    return list(value)


# --------------------------------------------------------------------------
# Defect 1: gradient must not rewrite non-spatial symbols into N.x/N.y/N.z.
# --------------------------------------------------------------------------


def test_gradient_non_spatial_multi_coord_returns_partials() -> None:
    """``gradient`` on ordinary symbols is plain partial differentiation."""
    res = _engine().gradient(_parse("-beta*S*I/N"), ["S", "I"])
    assert res.is_valid, res.error
    rendered = str(res.sympy_expr)
    assert "N.i" not in rendered and "N.x" not in rendered, rendered
    dS, dI = _partials(res)
    assert sp.simplify(dS - (-sp.Symbol("beta") * sp.Symbol("I") / sp.Symbol("N"))) == 0
    assert sp.simplify(dI - (-sp.Symbol("beta") * sp.Symbol("S") / sp.Symbol("N"))) == 0


def test_gradient_non_spatial_single_coord_returns_derivative() -> None:
    """One symbolic coordinate yields the derivative itself (not a 1-tuple)."""
    res = _engine().gradient(_parse("u**2"), ["u"])
    assert res.is_valid, res.error
    assert res.sympy_expr == 2 * sp.Symbol("u")
    assert not isinstance(res.sympy_expr, sp.Tuple)


def test_gradient_non_spatial_missing_coord_fails_loud() -> None:
    """A declared coordinate absent from the expression is named, not dropped."""
    res = _engine().gradient(_parse("u**2"), ["u", "v"])
    assert not res.is_valid
    assert "v" in res.error and "not in the expression" in res.error, res.error
    # The failure names the free symbols the caller should have used.
    assert "u" in res.error, res.error


def test_tool_gradient_non_spatial_symbols_do_not_touch_the_basis() -> None:
    """Black-box: ``math('gradient', ..., variable='S,I')`` must be correct."""
    math = _math()
    res = math("gradient", "-beta*S*I/N", variable="S,I", session=False)
    assert res["success"], res
    rendered = res["expression"]
    assert "N.i" not in rendered and "N.x" not in rendered, rendered
    # Two partial derivatives, one per declared coordinate.
    parsed, error = parse_expression_string(rendered)
    assert error is None, error
    assert isinstance(parsed, tuple) and len(parsed) == 2, rendered

    single = math("gradient", "u**2", variable="u", session=False)
    assert single["success"], single
    assert sp.sympify(single["expression"]) == 2 * sp.Symbol("u"), single


def test_gradient_spatial_subset_keeps_vector_basis() -> None:
    """Red line: coordinates drawn from {x, y, z} keep the sympy.vector form."""
    res = _engine().gradient(_parse("x**2 + y**2 + z**2"), ["x", "y", "z"])
    assert res.is_valid, res.error
    assert str(res.sympy_expr) == "2*N.x*N.i + 2*N.y*N.j + 2*N.z*N.k", res.sympy_expr


def test_gradient_spatial_partial_subset_keeps_vector_basis() -> None:
    """A spatial subset (here just ``x``) still emits the basis form (r13)."""
    res = _engine().gradient(_parse("x**2 + y**2"), ["x"])
    assert res.is_valid, res.error
    assert str(res.sympy_expr) == "2*N.x*N.i", res.sympy_expr


def test_gradient_spatial_field_missing_component_does_not_fail() -> None:
    """r13 regression guard: ``x**2 + y**2`` with coords x,y,z stays a success."""
    res = _engine().gradient(_parse("x**2 + y**2"), ["x", "y", "z"])
    assert res.is_valid, res.error
    math = _math()
    tool_res = math("gradient", "x**2 + y**2", variable="x,y,z", session=False)
    assert tool_res["success"], tool_res
    assert tool_res["expression"] == "2*N.x*N.i + 2*N.y*N.j", tool_res


# --------------------------------------------------------------------------
# Defect 2: transform variables must belong to the expression.
# --------------------------------------------------------------------------


_ILAPLACE_INPUT = "V0/(s*(1 + s*R1*C1))"


def test_ilaplace_wrong_frequency_variable_fails_clearly() -> None:
    """``t`` is the output variable, not the frequency-domain transform var."""
    res = _engine().inverse_laplace_transform(
        _parse(_ILAPLACE_INPUT), "t", "t"
    )
    assert not res.is_valid
    assert "'t'" in res.error, res.error
    assert "frequency" in res.error.lower(), res.error


def test_ilaplace_correct_frequency_variable_succeeds() -> None:
    res = _engine().inverse_laplace_transform(
        _parse(_ILAPLACE_INPUT), "s", "t"
    )
    assert res.is_valid, res.error
    assert res.sympy_expr.has(sp.Heaviside), res.sympy_expr


def test_laplace_wrong_time_variable_fails_clearly() -> None:
    """Symmetric check: ``laplace``'s ``variable`` is the time-domain symbol."""
    res = _engine().laplace_transform(_parse("1/(s + k)"), "t", "s")
    assert not res.is_valid
    assert "'t'" in res.error, res.error
    assert "time" in res.error.lower(), res.error


def test_laplace_correct_time_variable_succeeds() -> None:
    res = _engine().laplace_transform(_parse("exp(-a*t)"), "t", "s")
    assert res.is_valid, res.error
    assert res.sympy_expr == 1 / (sp.Symbol("a") + sp.Symbol("s"))


def test_tool_ilaplace_variable_semantics() -> None:
    """Black-box: ``variable='t'`` refuses; ``variable='s'`` transforms."""
    math = _math()
    wrong = math("ilaplace", _ILAPLACE_INPUT, variable="t", session=False)
    assert not wrong["success"], wrong
    assert "t" in wrong["error"], wrong

    right = math("ilaplace", _ILAPLACE_INPUT, variable="s", session=False)
    assert right["success"], right
    assert "DiracDelta" not in right["expression"], right


def test_tool_laplace_variable_semantics() -> None:
    math = _math()
    ok = math("laplace", "exp(-a*t)", variable="t", session=False)
    assert ok["success"], ok
    assert ok["expression"] == "1/(a + s)", ok

    wrong = math("laplace", "exp(-a*t)", variable="x", session=False)
    assert not wrong["success"], wrong
