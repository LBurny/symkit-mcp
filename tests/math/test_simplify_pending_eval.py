"""The ``simplify`` operation must evaluate pending operations first.

G11 (field card task-05): ``simplify`` over an unevaluated derivative residual
that is exactly zero returned a literal ``X - X`` left uncollapsed
(``C1*sin(x) + C2*cos(x) - (C1*sin(x) + C2*cos(x))``) — byte-identical on
rerun — while feeding the output back into simplify gave ``0``.

The parser keeps ``Derivative(Add(...), (x, 2))`` unevaluated by design (the
diff→Derivative preprocessing, r13); ``Derivative(Add).doit()`` produces the
undistributed ``Mul(-1, Add(...))`` form that ``sp.simplify`` cannot flatten.
Evaluating pending operations before simplifying fixes it without changing the
semantics of genuinely unevaluated derivatives.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit.infrastructure.sympy_engine import SymPyEngine
from symkit_mcp.tools.math import register_math_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    register_math_tools(mcp)
    return mcp.tools


class TestZeroDerivativeResidualSimplifiesToZero:
    def test_trig_residual_collapses(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            "simplify",
            "diff(C1*sin(x)+C2*cos(x),x,2) + C1*sin(x)+C2*cos(x)",
            session=False,
        )
        assert res["success"], res
        assert res["expression"] == "0", res

    def test_exp_residual_collapses(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            "simplify",
            "diff((C1+C2*x)*exp(-x),x,2) + 2*diff((C1+C2*x)*exp(-x),x)"
            " + (C1+C2*x)*exp(-x)",
            session=False,
        )
        assert res["success"], res
        assert res["expression"] == "0", res


class TestUnevaluatedDerivativesUnchanged:
    def test_undefined_function_derivative_stays_unevaluated(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            "simplify", "Derivative(f(x), (x, 2))", session=False
        )
        assert res["success"], res
        assert res["expression"] == "Derivative(f(x), (x, 2))", res

    def test_mixed_partial_still_evaluates(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            "simplify", "Derivative(sin(x*y), x, y)", session=False
        )
        assert res["success"], res
        x, y = sp.Symbol("x"), sp.Symbol("y")
        expected = sp.cos(x * y) - x * y * sp.sin(x * y)
        assert sp.simplify(sp.sympify(res["expression"]) - expected) == 0, res

    def test_engine_simplify_evaluates_pending_derivative(self) -> None:
        engine = SymPyEngine()
        parsed = engine.parse(
            "diff(C1*sin(x)+C2*cos(x),x,2) + C1*sin(x)+C2*cos(x)"
        )
        assert parsed.is_valid, parsed.error
        out = engine.simplify(parsed)
        assert out.is_valid, out.error
        assert out.sympy_expr == 0
