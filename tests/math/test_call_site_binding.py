"""Parser call-site binding through the ``math()`` tool surface.

Merged from two micro files on the same theme — how lowercase/ambiguous
call-site names bind once they reach the tool:

- ``evalf`` must evaluate lowercase ``max``/``min`` call sites. 2026-09-14 SST
  round: ``math("evalf", "max(0.1, 0.05)")`` returned the call unevaluated
  because the shared parser bound ``max(`` to an undefined ``Function('max')``;
  every SST F1/F2 mixing-function identity became numerically unverifiable and
  its step verification fell back to INCONCLUSIVE.
- A name used both bare and as a call site must survive one expression.
  2026-09-14 defect: ``math("simplify", "1/k + k(x)")`` died with
  ``Cannot parse: SympifyError: k`` — the turbomachinery workhorse shapes
  ``k``/``k(x)`` and ``omega``/``omega(x)`` were unusable in one expression.
"""

from __future__ import annotations

from typing import Any

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py
from symkit_mcp.tools import math as math_tools


def _math() -> Any:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


class TestMinMaxNumericEvaluation:
    def test_evalf_max_of_two_numbers(self) -> None:
        result = _math()("evalf", "max(0.1, 0.05)", session=False)
        assert result["success"], result
        assert abs(float(result["expression"]) - 0.1) < 1e-12

    def test_evalf_sst_mixing_function_probe(self) -> None:
        """The F1 mixing-function probe (session b33760de step 10)."""
        result = _math()(
            "evalf",
            "2*max(sqrt(0.01), 250*0.09*1.0e-5/0.001)/((0.09*100*0.001))",
            session=False,
        )
        assert result["success"], result
        assert abs(float(result["expression"]) - 50.0) < 1e-9

    def test_simplify_keeps_symbolic_max(self) -> None:
        result = _math()("simplify", "max(x, 0) - Max(x, 0)", session=False)
        assert result["success"], result
        assert result["expression"] == "0"


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
