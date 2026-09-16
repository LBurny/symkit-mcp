"""Reserved singleton names must not leak into call sites or complex literals.

G8 (field card task-01): ``I`` is protected as an ordinary symbol, but SymPy's
``auto_number`` expands the complex literal ``1j`` into ``1*I`` as a *name*, so
the protected ``I`` binding captured it — ``simplify("1j - I")`` folded to ``0``
while ``I*2`` correctly stayed ``2*I``.  ``1j`` must be the imaginary unit and
``I`` an ordinary symbol, in the same expression.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit.domain.expression_parser import parse_user_expression
from symkit_mcp.tools.math import register_math_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    register_math_tools(mcp)
    return mcp.tools


class TestComplexLiteralNotHijacked:
    def test_parse_keeps_imaginary_unit_and_symbol_apart(self) -> None:
        expr, error = parse_user_expression("1j - I")
        assert error is None, error
        assert expr is not None
        assert expr.has(sp.I), sp.srepr(expr)
        assert expr.has(sp.Symbol("I")), sp.srepr(expr)
        assert sp.simplify(expr) != 0, sp.srepr(expr)

    def test_simplify_1j_minus_I_is_not_zero(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"]("simplify", "1j - I", session=False)
        assert res["success"], res
        assert res["expression"] != "0", res

    def test_symbol_I_alone_is_unchanged(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _tools()["math"]("simplify", "I*2", session=False)
        assert res["success"], res
        assert res["expression"] == "2*I", res
        expr, _ = parse_user_expression("I*2")
        assert expr is not None
        assert expr.has(sp.Symbol("I")) and not expr.has(sp.I)

    def test_sqrt_negative_one_minus_I_keeps_symbol_I(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"]("simplify", "sqrt(-1) - I", session=False)
        assert res["success"], res
        assert res["expression"] != "0", res
        expr, _ = parse_user_expression("sqrt(-1) - I")
        assert expr is not None and expr.has(sp.Symbol("I"))
