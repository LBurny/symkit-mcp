"""`evalf` on symbolic matrix expressions.

`Matrix(M)*Matrix(M) - 16*Matrix(M) + 3*Identity(3)` blew up with an uncaught
SymPy `RecursionError` (2026-09-12 pure-formula black-box round): `MatAdd`
keeps the `Identity` term unabsorbed and `.evalf()` recurses on it. Expanding
the expression with `as_explicit()` collapses the term and evaluates normally --
and is also what makes a true Cayley-Hamilton residual come out as the zero
matrix.
"""

from __future__ import annotations

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py
from symkit_mcp.tools import math as math_tools

A = "Matrix([[1,2,3],[4,5,6],[7,8,10]])"


def _tools() -> dict:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools


class TestEvalfMatrixExpressions:
    def test_identity_term_does_not_crash(self):
        result = _tools()["math"](
            operation="evalf",
            expression=f"{A}*{A} - 16*{A} + 3*Identity(3)",
        )

        assert result["success"] is True, result
        assert "17." in result["expression"] or "17" in result["expression"]

    def test_cayley_hamilton_residual_is_the_zero_matrix(self):
        result = _tools()["math"](
            operation="evalf",
            expression=f"{A}*{A}*{A} - 16*{A}*{A} - 12*{A} + 3*Identity(3)",
        )

        assert result["success"] is True, result
        assert "0" in result["expression"]
        assert "17" not in result["expression"]

    def test_plain_matrix_arithmetic_still_evaluates(self):
        result = _tools()["math"](operation="evalf", expression=f"{A}*{A}")

        assert result["success"] is True
        assert "30." in result["expression"]
