"""evalf must evaluate lowercase ``max``/``min`` call sites.

2026-09-14 SST round: ``math("evalf", "max(0.1, 0.05)")`` returned the call
unevaluated because the shared parser bound ``max(`` to an undefined
``Function('max')``; every SST F1/F2 mixing-function identity became
numerically unverifiable and its step verification fell back to INCONCLUSIVE.
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools import math as math_tools

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py


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
