"""r23 G2: ``series`` order semantics.

Two defects:

1. The tool default ``order=1`` was meaningless for ``series`` (it returns just
   ``O(x)``), so a caller who omitted ``order`` got a useless result. The
   default is now operation-specific: 1 for ``diff``, SymPy's 6 terms for
   ``series``.
2. An inline ``series(expr, x, p, n)`` already carries its own order and an
   ``sp.Order`` term. The outer call must return it unchanged instead of
   re-truncating it to the outer order or raising ``ValueError``
   ("Could not calculate 8 terms ...").

Red lines pinned here: the r23 ``tan(x)`` order-8 regression, explicit
variable/point/order behavior, ``diff``'s default order of 1, non-series
integrands, and the already-``O(...)`` input with an explicit larger order.
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py

SIN6 = "x - x**3/6 + x**5/120 + O(x**6)"
TAN8 = "x + x**3/3 + 2*x**5/15 + 17*x**7/315 + O(x**8)"
EXP5 = "1 + x + x**2/2 + x**3/6 + x**4/24 + O(x**5)"


def _math() -> Any:
    mcp = MockMCP()  # noqa: F821
    register_math_tools(mcp)
    return mcp.tools["math"]


class TestSeriesDefaultOrder:
    def test_series_without_order_expands_six_terms(self) -> None:
        result = _math()("series", "sin(x)", session=False)

        assert result["success"] is True, result
        assert result["expression"] == SIN6

    def test_series_without_order_with_variable_expands_six_terms(self) -> None:
        result = _math()("series", "sin(x)", variable="x", session=False)

        assert result["success"] is True, result
        assert result["expression"] == SIN6


class TestInlineSeriesOrderPreserved:
    def test_inline_series_matches_direct_order(self) -> None:
        inline = _math()("series", "series(sin(x), x, 0, 6)", session=False)
        direct = _math()("series", "sin(x)", order=6, session=False)

        assert inline["success"] is True, inline
        assert direct["success"] is True, direct
        assert inline["expression"] == direct["expression"] == SIN6

    def test_inline_exp_series_five_terms(self) -> None:
        result = _math()("series", "series(exp(x), x, 0, 5)", session=False)

        assert result["success"] is True, result
        assert result["expression"] == EXP5

    def test_explicit_order_on_existing_series_does_not_raise(self) -> None:
        """An ``O(...)`` input plus an explicit order must not trigger SymPy's
        "Could not calculate 8 terms" ValueError; the series is returned as is."""
        result = _math()(
            "series", "series(sin(x), x, 0, 6)", order=8, session=False
        )

        assert result["success"] is True, result
        assert result["expression"] == SIN6


class TestSeriesRegressionRedLines:
    def test_explicit_order_unchanged(self) -> None:
        result = _math()("series", "tan(x)", order=8, session=False)

        assert result["success"] is True, result
        assert result["expression"] == TAN8

    def test_explicit_variable_point_order_unchanged(self) -> None:
        result = _math()(
            "series", "exp(-x)", variable="x", point="0", order=4, session=False
        )

        assert result["success"] is True, result
        assert "O(x**4)" in result["expression"]

    def test_non_series_expression_unchanged(self) -> None:
        result = _math()("series", "1/(1-x)", order=4, session=False)

        assert result["success"] is True, result
        assert result["expression"] == "1 + x + x**2 + x**3 + O(x**4)"

    def test_diff_default_order_still_one(self) -> None:
        first = _math()("diff", "sin(x)", variable="x", session=False)
        second = _math()("diff", "sin(x)", variable="x", order=2, session=False)

        assert first["success"] is True, first
        assert first["expression"] == "cos(x)"
        assert second["success"] is True, second
        assert second["expression"] == "-sin(x)"


class TestSeriesProvenance:
    def test_recorded_defaults_do_not_render_none(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        from symkit_mcp.tools.session import register_session_tools

        mcp = MockMCP()  # noqa: F821
        register_math_tools(mcp)
        register_session_tools(mcp)
        mcp.tools["session_start"]("g2-provenance")

        mcp.tools["math"]("diff", "sin(x)", variable="x", session=True)
        mcp.tools["math"]("series", "sin(x)", session=True)

        session = _state.get_session()
        assert session is not None
        commands = [step.sympy_command for step in session.steps]
        assert all("None" not in command for command in commands), commands
        assert "diff(expr, x)" in commands
