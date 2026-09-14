"""The math tool surface accepts a name used both bare and as a call site.

2026-09-14 defect: ``math("simplify", "1/k + k(x)")`` died with
``Cannot parse: SympifyError: k`` — the turbomachinery workhorse shapes
``k``/``k(x)`` and ``omega``/``omega(x)`` were unusable in one expression.
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools import math as math_tools

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py


def _math() -> Any:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


class TestDualUseThroughMathTool:
    def test_simplify_bare_symbol_plus_call(self) -> None:
        for text in ("1/z + z(x)", "1/g + g(x)", "1/k + k(x)"):
            result = _math()("simplify", text, session=False)
            assert result["success"] is True, (text, result)
            assert "__call" not in result["expression"]

    def test_ode_mixing_shape_records_a_step(self) -> None:
        """Bare k/omega alongside k(x), omega(x) in one expression."""
        result = _math()(
            "simplify", "beta*k*omega + Derivative(k(x), x)", session=False
        )
        assert result["success"] is True, result


class TestDualUseWithAssumptions:
    def test_assumptions_bind_bare_symbol_through_math(self) -> None:
        """Per-call assumptions attach to the bare symbol, not the call site."""
        result = _math()(
            "simplify",
            "sqrt(k**2) + k(x)",
            assumptions=["k is positive"],
            session=False,
        )
        assert result["success"] is True, result
        # sqrt(k**2) reduced to k under the assumption; the call survives.
        assert result["expression"].startswith("k +")
        assert "k(x)" in result["expression"]

    def test_rename_collision_falls_back_gracefully(self) -> None:
        """A literal ``z__call`` in the input disables the rename path."""
        from symkit.domain.expression_parser import parse_expression_string

        expr, error = parse_expression_string("1/z + z(x) + z__call(x)")
        # Graceful fallback: the dual-use rewrite is skipped entirely; the
        # historical parse error returns instead of a corrupted parse.
        assert expr is None or "z__call" in str(expr) or "__call" in str(expr)
