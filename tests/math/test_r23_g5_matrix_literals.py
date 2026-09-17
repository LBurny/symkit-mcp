"""Tool-surface regressions for r23 G5: ``[[...]]`` literals at every entry.

``det [[1,2],[3,4]]`` was accepted while ``simplify [[..]]**-1 * [[..]]`` and
``session_record_step("M = [[..]]")`` rejected the same syntax with
``Cannot parse``/``SympifyError``.  The shared parser now normalizes the
row-grid literal to ``Matrix([...])``, so all three entry points agree.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools.session import register_session_tools


def _math() -> Any:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def _session_tools() -> Any:
    mcp = MockMCP()
    register_session_tools(mcp)
    return mcp.tools


class TestDetEigenAcceptanceUnchanged:
    def test_det_numeric_bracket_grid(self) -> None:
        result = _math()("det", expression="[[1,2],[3,4]]", session=False)
        assert result["success"] is True, result
        assert result["expression"] == "-2"

    def test_det_symbolic_bracket_grid(self) -> None:
        result = _math()("det", expression="[[1-L,1],[1,-L]]", session=False)
        assert result["success"] is True, result
        L = sp.Symbol("L")
        assert sp.simplify(sp.sympify(result["expression"]) - (L**2 - L - 1)) == 0

    def test_eigenvals_bracket_grid(self) -> None:
        result = _math()("eigenvals", "[[2,1],[1,2]]", session=False)
        assert result["success"] is True, result
        assert len(result["eigenvalues"]) == 2

    def test_eigenvects_bracket_grid(self) -> None:
        result = _math()("eigenvects", "[[2,1],[1,2]]", session=False)
        assert result["success"] is True, result


class TestSimplifyBracketProduct:
    def test_bracket_product_is_true_matrix_multiplication(self) -> None:
        result = _math()(
            "simplify", "[[1, 2], [3, 4]]**-1 * [[1, 1], [1, 0]]", session=False
        )
        assert result["success"] is True, result
        got = sp.Matrix(sp.sympify(result["expression"]))
        assert got == sp.Matrix([[-1, -2], [1, sp.Rational(3, 2)]])

    def test_bracket_product_matches_constructor_rendering(self) -> None:
        bracket = _math()(
            "simplify", "[[1, 2], [3, 4]]**-1 * [[1, 1], [1, 0]]", session=False
        )
        ctor = _math()(
            "simplify",
            "Matrix([[1, 2], [3, 4]])**-1 * Matrix([[1, 1], [1, 0]])",
            session=False,
        )
        assert bracket["success"] is True and ctor["success"] is True
        assert bracket["expression"] == ctor["expression"]


class TestSessionRecordStepMatrixDefinition:
    def test_matrix_definition_parses_and_lands(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _session_tools()
        tools["session_start"](name="g5-matrix-def")
        result = tools["session_record_step"](
            expression="M = [[1,1],[1,0]]",
            description="matrix definition of M",
        )
        assert result["success"] is True, result
        assert result["expression"].startswith("Eq(M, Matrix(")
        assert "M" in result["expression"]
