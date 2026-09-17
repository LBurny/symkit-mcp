"""MCP-level round-trip: a python_exec result's srepr feeds math() (r22).

The escape hatch advertises that ``result.srepr`` can be pasted into any
expression field; this locks the contract at the tool surface.
"""

from __future__ import annotations

from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py

_ZETA_SREPR = (
    "Mul(Rational(1, 2), Symbol('c', positive=True), "
    "Pow(Symbol('k', positive=True), Rational(-1, 2)), "
    "Pow(Symbol('m', positive=True), Rational(-1, 2)))"
)


def _tools():
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def test_substitute_accepts_srepr_form(fresh_session_manager) -> None:
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="substitute",
        expression=_ZETA_SREPR,
        substitution={"m": "2", "k": "8", "c": "4"},
        session=False,
    )
    assert res["success"], res
    # zeta = 4/(2*sqrt(2*8)) = 1/2
    num = tools["math"](operation="evalf", expression=res["expression"], session=False)
    assert num["success"], num
    assert abs(float(num["expression"]) - 0.5) < 1e-12


def test_srepr_assumptions_survive_into_simplify(fresh_session_manager) -> None:
    """sqrt(x**2) only collapses to x when the srepr-carried assumption holds."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="simplify",
        expression="Pow(Symbol('x', positive=True), Integer(2))",
        session=False,
    )
    assert res["success"], res
    sqrt_res = tools["math"](
        operation="simplify",
        expression="Pow(Pow(Symbol('x', positive=True), Integer(2)), Rational(1, 2))",
        session=False,
    )
    assert sqrt_res["success"], sqrt_res
    assert sqrt_res["expression"] == "x"
