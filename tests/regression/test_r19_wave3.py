"""Round-19 wave-3 regressions: F32, F35, F37.

Three acceptance-found defects pinned here:

* F37 — differentiation verification was blind whenever the reverse
  antiderivative branched (a ``Piecewise`` because the parameter symbols carry
  no assumptions).  A direct recomputation channel must decide such steps, while
  a genuinely wrong derivative still does not verify.
* F32 — ``session_start`` had no ``target_expression`` parameter, so an explicit
  target was swallowed by the schema and the goal recorded ``null``.
* F35 — ``solve`` leaked a raw ``TypeError`` (``'FunctionClass' and 'Integer'``)
  for bracketed systems whose solution values are compound expressions.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.expression_parser import parse_expression_string
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP / fresh_session_manager are provided by conftest.py
# ruff: noqa: F821


def _archived(
    operation: OperationType,
    input_expression: str,
    output_expression: str,
    sympy_command: str = "",
) -> DerivationStep:
    """A live-recorder-shaped archived step (``input_srepr`` present)."""
    parsed, _ = parse_expression_string(input_expression, convert_equation=True)
    out, _ = parse_expression_string(output_expression, convert_equation=True)
    assert parsed is not None and out is not None
    return DerivationStep(
        step_number=1,
        operation=operation,
        description="r19 wave3 regression",
        input_expressions={"original": str(parsed)},
        output_expression=output_expression,
        output_latex=output_expression,
        sympy_command=sympy_command,
        input_srepr=sp.srepr(parsed),
        output_srepr=sp.srepr(out),
    )


class TestF37DirectRecomputation:
    """F37: a branching antiderivative must not blind the differentiation check."""

    _INPUT = "Vs + (C1*sin(omegad*t) + C2*cos(omegad*t))*exp(-alpha*t)"

    def test_correct_derivative_verifies_without_assumptions(self) -> None:
        # Bare parameter symbols: reverse_integrate returns a Piecewise and the
        # old comparison concluded nothing (the RLC sandbox card hit this 3/3).
        derivative = str(sp.diff(sp.sympify(self._INPUT), sp.Symbol("t")))
        step = _archived(
            OperationType.DIFFERENTIATE, self._INPUT, derivative, sympy_command="diff(expr, t)"
        )
        result = StepVerifier().verify_step(step)
        assert result.status is VerificationStatus.VERIFIED, result.message
        assert result.reverse_check is True
        assert "direct recomputation" in result.message

    def test_wrong_derivative_is_not_verified(self) -> None:
        wrong = (
            "-alpha*(C1*sin(omegad*t) + C2*cos(omegad*t))*exp(-alpha*t) "
            "+ (C1*omegad*cos(omegad*t) - C2*omegad*sin(omegad*t))*exp(-alpha*t) "
            "+ omegad**3"
        )
        step = _archived(
            OperationType.DIFFERENTIATE, self._INPUT, wrong, sympy_command="diff(expr, t)"
        )
        result = StepVerifier().verify_step(step)
        assert result.status is not VerificationStatus.VERIFIED


class TestF32StartTargetExpression:
    """F32: ``session_start`` must accept an explicit ``target_expression``."""

    def _tools(self) -> dict[str, Any]:
        mcp = MockMCP()
        math_tools.register_math_tools(mcp)
        register_session_tools(mcp)
        return mcp.tools

    def test_target_expression_is_recorded_verbatim(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = self._tools()
        target = "Omega_res = sqrt(omega0**2 - 2*beta**2)"
        res = tools["session_start"](
            "wave3-target",
            goal="derive the resonance frequency of the driven oscillator",
            target_expression=target,
        )
        assert res["success"], res
        assert res["goal"]["target_expression"] == target, res["goal"]

    def test_target_expression_drives_progress_match(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = self._tools()
        tools["session_start"](
            "wave3-target-progress",
            goal="derive the resonance frequency condition",
            target_expression="sqrt(omega0**2 - 2*beta**2)",
        )
        res = tools["math"]("simplify", "sqrt(omega0**2 - 2*beta**2)", session=True)
        assert res["success"], res
        progress = tools["session_show"]()["progress"]
        assert progress["matches_target"] is True, progress

    def test_passing_neither_keeps_tri_state_null(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = self._tools()
        tools["session_start"]("wave3-target-null", goal="derive the terminal velocity")
        res = tools["math"]("simplify", "x + x", session=True)
        assert res["success"], res
        progress = tools["session_show"]()["progress"]
        assert progress["matches_target"] is None, progress


class TestF35SolveAppliedFunctionLeak:
    """F35: solve must curate the raw operand TypeError."""

    _SYSTEM = (
        "[A*(omega0**2 - Omega**2) + 2*B*Omega*beta - f(t), "
        "B*(omega0**2 - Omega**2) - 2*A*Omega*beta]"
    )

    def _math(self) -> Any:
        mcp = MockMCP()
        math_tools.register_math_tools(mcp)
        return mcp.tools["math"]

    def test_bracket_system_with_applied_function_is_curated(
        self, fresh_session_manager
    ) -> None:
        _ = fresh_session_manager
        res = self._math()("solve", self._SYSTEM, variable="A,B", session=False)
        assert res["success"] is False, res
        assert "FunctionClass" not in res["error"], res["error"]
        assert "unsupported operand" not in res["error"], res["error"]
        assert "Solve failed" not in res["error"], res["error"]
        assert "applied function" in res["error"], res["error"]
        assert "dsolve" in res["error"], res["error"]

    def test_genuine_no_solution_stays_no_solution(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        res = self._math()("solve", "[x+y-1, x+y-2]", variable="x,y", session=False)
        assert res["success"] is False, res
        assert "No solution found" in res["error"], res["error"]
