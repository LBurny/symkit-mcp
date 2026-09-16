"""``math`` must parse parenthesized Leibniz derivatives, not mis-read them.

B13 field report (compressible RANS derivation): ``∂(p*u1**2)/∂x1`` silently
degraded to ``Function('d')(...)/Symbol('dx1')`` — success:true, zero warnings,
and a LaTeX rendering that mimics a real derivative. The parenthesized form
must agree with the bare ``du1/dx1`` form, which parses as a Derivative.
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools import math as math_tools

# MockMCP is provided by conftest.py


def _math_tool() -> Any:
    # ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def test_paren_form_agrees_with_bare_form() -> None:
    tool = _math_tool()
    bare = tool("simplify", "du1/dx1", session=False)
    paren = tool("simplify", "d(u1)/dx1", session=False)
    assert paren["success"] is True, paren
    assert paren["expression"] == bare["expression"], (paren, bare)


def test_compound_paren_form_is_not_a_garbage_fraction() -> None:
    result = _math_tool()("simplify", "∂(p*u1**2)/∂x1", session=False)
    assert result["success"] is True, result
    blob = f"{result.get('expression', '')} {result.get('latex', '')} {result.get('srepr', '')}"
    assert "Function('d')" not in blob, result
    assert "dx1" not in blob, result
