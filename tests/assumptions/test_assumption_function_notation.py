"""Invariant I1: assumptions must never influence parsing.

An assumption is a *property of a symbol*, applied after the syntax tree has
been built.  When assumptions were injected into the parser's ``local_dict``
before parsing (run-024), a name that appeared as a function call site
(``k(x)``) was bound to ``Symbol('k', positive=True)`` instead of a
``Function``, and SymPy's implicit multiplication silently rewrote the call
into a product: ``k(x)`` → ``k*x``.  Function notation must survive every
assumption set, on every entry point.

The companion control tests assert the feature still works where it should:
a bare symbol (no call site) must still carry its assumptions.
"""

from __future__ import annotations

import sympy as sp
from sympy.core.function import AppliedUndef

from symkit.domain.value_objects import MathContext
from symkit.infrastructure.sympy_engine import SymPyEngine
from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py


def _make_tools():
    # ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _ctx_with_assumption(name: str, **props: bool) -> MathContext:
    return MathContext().with_assumption(name, **props)


# ── Engine entry point (SymPyEngine.parse) ──────────────────────────────────


def test_engine_parse_keeps_function_notation_under_assumption():
    engine = SymPyEngine()
    expr = engine.parse("k(x)", _ctx_with_assumption("k", positive=True)).sympy_expr

    assert expr is not None
    assert isinstance(expr, AppliedUndef), f"k(x) degraded to {expr!r}"
    assert expr.func.__name__ == "k"
    assert expr.free_symbols == {sp.Symbol("x")}


def test_engine_parse_keeps_function_notation_for_common_physics_symbols():
    engine = SymPyEngine()
    for name, expr_str in (("v", "v(t)"), ("p", "p(T)"), ("mu", "mu(T)")):
        expr = engine.parse(
            expr_str, _ctx_with_assumption(name, positive=True)
        ).sympy_expr
        assert expr is not None, f"{expr_str} failed to parse under assumption on {name}"
        assert isinstance(expr, AppliedUndef), f"{expr_str} degraded to {expr!r}"


# ── Parser entry point (caller-supplied local_dict) ─────────────────────────


def test_parser_call_site_is_not_overridden_by_caller_symbol_binding():
    """A caller ``local_dict`` must not be able to turn ``k(x)`` into ``k*x``."""
    from symkit.domain.expression_parser import parse_expression_string

    parsed, error = parse_expression_string(
        "k(x)",
        convert_equation=True,
        local_dict={"k": sp.Symbol("k", positive=True)},
    )
    assert error is None, error
    assert isinstance(parsed, AppliedUndef), f"k(x) degraded to {parsed!r}"


def test_parser_still_honours_caller_binding_for_non_call_sites():
    """The protection is scoped to call sites only — plain symbols still bind."""
    from symkit.domain.expression_parser import parse_expression_string

    parsed, error = parse_expression_string(
        "k*x",
        convert_equation=True,
        local_dict={"k": sp.Symbol("k", positive=True)},
    )
    assert error is None, error
    k_sym = next(s for s in parsed.free_symbols if s.name == "k")
    assert k_sym.is_positive is True


# ── MCP entry point (assume() then math()) ──────────────────────────────────


def test_math_tool_assume_does_not_corrupt_function_notation(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("assume_fn_notation", goal="check function notation")
    assert tools["assume"]({"k": "positive"})["success"]

    res = tools["math"](operation="simplify", expression="k(x)", session=False)

    assert res["success"], res
    assert "k(x)" in res["expression"], f"expected k(x), got {res['expression']!r}"
    assert "*" not in res["expression"].replace("**", "")


def test_math_tool_per_call_assumption_does_not_corrupt_function_notation(
    fresh_session_manager,
):
    _ = fresh_session_manager
    tools = _make_tools()

    res = tools["math"](
        operation="simplify",
        expression="v(t)",
        assumptions=["v is positive"],
        session=False,
    )

    assert res["success"], res
    assert "v(t)" in res["expression"], f"expected v(t), got {res['expression']!r}"


def test_math_tool_differentiate_function_notation_under_assumption(
    fresh_session_manager,
):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["assume"]({"k": "positive"})

    res = tools["math"](
        operation="diff", expression="k(x)", variable="x", session=False
    )

    assert res["success"], res
    # d/dx k(x) — the derivative of an undefined function, not of k*x.
    assert res["expression"] in {"Derivative(k(x), x)", "Derivative(k(x), (x, 1))"}, (
        f"unexpected derivative {res['expression']!r}"
    )


# ── Controls: assumptions must still apply to genuine symbols ───────────────


def test_engine_parse_still_applies_assumption_to_bare_symbol():
    engine = SymPyEngine()
    expr = engine.parse("k*x", _ctx_with_assumption("k", positive=True)).sympy_expr

    assert expr is not None
    k_sym = next(s for s in expr.free_symbols if s.name == "k")
    assert k_sym.is_positive is True


def test_math_tool_assumption_still_reaches_simplify(fresh_session_manager):
    """The original purpose of assumptions (run-021) must keep working."""
    _ = fresh_session_manager
    tools = _make_tools()
    tools["assume"]({"x": "positive"})

    res = tools["math"](operation="simplify", expression="sqrt(x**2)", session=False)

    assert res["success"], res
    assert res["expression"] == "x", f"expected x, got {res['expression']!r}"


def test_session_assumption_is_cleaned_up(fresh_session_manager):
    """Guard against the assumption leaking out of this module's tests."""
    _ = fresh_session_manager
    assert _state.get_context().assumptions == {}
