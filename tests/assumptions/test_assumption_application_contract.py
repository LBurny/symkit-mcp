"""Invariant I3: one implementation of "assumption → symbol", everywhere.

Before this contract, five separate code paths built assumption-bearing symbols
(engine ``_get_local_dict``, math dispatcher ``_apply_context_assumptions``,
session ``_apply_assumptions_to_expr``, verifier ``_build_symbol_dict``, and a
second parser stack inside ``_parse_ode``), each with its own property
whitelist and conflict table.  They disagreed, and the disagreements produced
silent wrong answers:

* ``laplacian(x**2 + y**2 + z**2)`` returned 4 with ``x`` positive and 2 with
  ``x, y`` positive instead of 6 — the raw ``Symbol('x')`` subs key never
  matched the assumption-bearing coordinate.
* ``laplace`` with ``t`` positive returned ``exp(-k*t)/s`` instead of
  ``1/(k+s)``, and ``fourier`` with ``x`` positive returned
  ``FourierTransform(1, x, k)*exp(-x**2)`` instead of the Gaussian — the
  transform variable was a plain Symbol while the integrand held the
  assumption-bearing one, so SymPy treated the integrand as constant.
* ``dsolve`` with ``t`` positive failed outright with "is not a solvable
  differential equation in v(t)".

These are correctness assertions, not snapshots: they hold for any
implementation that binds assumptions onto the same symbols the expression
already contains.
"""

from __future__ import annotations

import pytest
import sympy as sp

from symkit.domain.assumption_binding import (
    CONFLICT_PAIRS,
    apply_assumptions,
    resolve_assumed_symbol,
    symbol_kwargs,
)
from symkit.domain.value_objects import MathContext
from symkit.infrastructure.sympy_engine import SymPyEngine
from symkit_mcp.tools.math import register_math_tools

# MockMCP is provided by conftest.py


def _math_tool():
    # ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    register_math_tools(mcp)
    return mcp.tools["math"]


def _ctx(**assumptions: str) -> MathContext:
    ctx = MathContext()
    for name, props in assumptions.items():
        ctx = ctx.with_assumption(name, **dict.fromkeys(props.split(), True))
    return ctx


# ── The shared primitives ───────────────────────────────────────────────────


def test_resolve_assumed_symbol_is_deterministic_and_matches_engine_output():
    """The same (name, props) must yield the identical Symbol everywhere."""
    engine = SymPyEngine()
    parsed = engine.parse("x**2 + k", _ctx(x="positive", k="positive")).sympy_expr

    for name in ("x", "k"):
        expected = resolve_assumed_symbol(name, {"positive": True})
        assert expected in parsed.free_symbols
        assert expected is resolve_assumed_symbol(name, {"positive": True})


def test_apply_assumptions_ignores_function_names():
    """After parsing a call site is not a free symbol, so it cannot be rebound."""
    expr = sp.Function("k")(sp.Symbol("x"))
    result = apply_assumptions(expr, {"k": {"positive": True}, "x": {"positive": True}})

    assert isinstance(result, sp.core.function.AppliedUndef)
    assert result.func.__name__ == "k"


def test_apply_assumptions_leaves_constants_alone():
    """``I``/``E`` are numbers, not free symbols — assumptions must not touch them."""
    expr = sp.Symbol("x") + sp.I
    result = apply_assumptions(expr, {"I": {"positive": True}, "x": {"real": True}})

    assert result.has(sp.I), result
    assert not result.has(sp.Symbol("I")), result
    assert result.free_symbols == {sp.Symbol("x", real=True)}


def test_apply_assumptions_passes_non_basic_through():
    """Comma parses yield plain tuples; ``.has``/``xreplace`` would crash on them."""
    value = (sp.Symbol("x"), sp.Symbol("y"))
    assert apply_assumptions(value, {"x": {"positive": True}}) is value


def test_conflicting_assumptions_yield_a_plain_symbol():
    assert symbol_kwargs({"positive": True, "negative": True}) == {}
    assert resolve_assumed_symbol("x", {"positive": True, "negative": True}) == sp.Symbol("x")


def test_unknown_properties_are_dropped_not_passed_to_sympy():
    assert symbol_kwargs({"positive": True, "not_a_sympy_property": True}) == {
        "positive": True
    }


def test_conflict_table_has_a_single_definition():
    """The engine and the verifier must share this table, not copy it."""
    from symkit.domain import assumption_engine

    assert assumption_engine._CONFLICT_PAIRS is CONFLICT_PAIRS
    assert len(CONFLICT_PAIRS) == 5


# ── Blessed correctness fixes (assumption must not change the answer) ───────


@pytest.mark.parametrize(
    "assumptions",
    [None, ["x is positive"], ["x is negative"], ["x is real"],
     ["x is positive", "y is positive"]],
)
def test_laplacian_is_independent_of_coordinate_assumptions(assumptions):
    """laplacian(x²+y²+z²) = 6 no matter what is assumed about x/y/z."""
    math = _math_tool()
    res = math(
        operation="laplacian",
        expression="x**2 + y**2 + z**2",
        variable="x,y,z",
        assumptions=assumptions,
        session=False,
    )
    assert res["success"], res
    assert res["expression"] == "6", res


@pytest.mark.parametrize("assumptions", [None, ["t is positive"], ["t is real"]])
def test_laplace_transform_is_independent_of_time_assumptions(assumptions):
    math = _math_tool()
    res = math(
        operation="laplace",
        expression="exp(-k*t)",
        variable="t",
        with_respect_to="s",
        assumptions=assumptions,
        session=False,
    )
    assert res["success"], res
    assert res["expression"] == "1/(k + s)", res


@pytest.mark.parametrize("assumptions", [None, ["x is positive"], ["x is real"]])
def test_fourier_transform_is_independent_of_space_assumptions(assumptions):
    math = _math_tool()
    res = math(
        operation="fourier",
        expression="exp(-x**2)",
        variable="x",
        with_respect_to="k",
        assumptions=assumptions,
        session=False,
    )
    assert res["success"], res
    assert res["expression"] == "sqrt(pi)*exp(-pi**2*k**2)", res


@pytest.mark.parametrize("assumptions", [None, ["t is positive"], ["k is positive"]])
def test_dsolve_is_independent_of_variable_assumptions(assumptions):
    math = _math_tool()
    res = math(
        operation="dsolve",
        expression="Derivative(v(t), t) = -k*v(t)",
        variable="v",
        with_respect_to="t",
        assumptions=assumptions,
        session=False,
    )
    assert res["success"], res
    assert "exp(-k*t)" in res["expression"], res


@pytest.mark.parametrize(
    "operation,expr,expected",
    [
        ("gradient", "x**2 + y**2 + z**2", "2*N.x*N.i + 2*N.y*N.j + 2*N.z*N.k"),
        ("divergence", "x*y, y*z, z*x", "N.x + N.y + N.z"),
        ("curl", "y, -x, 0", "(-2)*N.k"),
    ],
)
def test_vector_calculus_is_independent_of_coordinate_assumptions(
    operation, expr, expected
):
    math = _math_tool()
    res = math(
        operation=operation,
        expression=expr,
        variable="x,y,z",
        assumptions=["x is positive"],
        session=False,
    )
    assert res["success"], res
    assert res["expression"] == expected, res
