"""r23 G11: a principal-branch antiderivative must not get a false FAILED.

``integrate(exp(-x**4), x)`` returns
``gamma(1/4)*lowergamma(1/4, x**4)/(16*gamma(5/4))``, whose derivative is
``x**3*exp(-x**4)*gamma(1/4)/(4*(x**4)**(3/4)*gamma(5/4))`` — exactly
``exp(-x**4)`` on the principal branch, because ``gamma(5/4) = gamma(1/4)/4``
and ``(x**4)**(3/4) = x**3`` there.  Plain ``simplify`` leaves the residual
``(x**3 - (x**4)**(3/4))*exp(-x**4)/(x**4)**(3/4)`` undecided, and a numeric
probe at a negative point "refutes" it, so the correct integral was recorded
as FAILED ("Differentiation of integral does not match original").

The reverse check must decide the residual symbolically under the
principal-branch (every free symbol positive) reading; a residual that carries
a branch-cut power and cannot be decided stays INCONCLUSIVE, while a genuine
mismatch with no branch-cut power is still FAILED.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.expression_parser import parse_expression_string
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus
from symkit.domain.verifier_heuristics import reverse_check_verdict
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP / fresh_session_manager are provided by conftest.py
# ruff: noqa: F821

X = sp.Symbol("x")


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _integrate_step(input_expression: str, output_expr: sp.Basic) -> DerivationStep:
    parsed, _ = parse_expression_string(input_expression, convert_equation=True)
    assert parsed is not None
    output_str = str(output_expr)
    return DerivationStep(
        step_number=1,
        operation=OperationType.INTEGRATE,
        description="r23 g11 integration",
        input_expressions={"original": input_expression},
        output_expression=output_str,
        output_latex=output_str,
        sympy_command="integrate(expr, x)",
        input_srepr=sp.srepr(parsed),
        output_srepr=sp.srepr(output_expr),
    )


class TestG11PrincipalBranchAntiderivative:
    def test_black_box_exp_minus_x4_is_verified(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](name="g11-exp-minus-x4")
        recorded = tools["math"](
            "integrate", "exp(-x**4)", variable="x", session=True
        )
        assert recorded["success"], recorded
        verified = tools["session_verify_step"](recorded["step"])
        assert verified["verification_status"] != "failed", verified
        assert verified["verification_status"] == "verified", verified
        assert (
            verified["verification_message"] == "Integration verified by differentiation"
        ), verified["verification_message"]

    def test_principal_branch_antiderivative_verifies(self) -> None:
        antiderivative = sp.integrate(sp.exp(-X**4), X)
        result = StepVerifier().verify_step(
            _integrate_step("exp(-x**4)", antiderivative)
        )
        assert result.status == VerificationStatus.VERIFIED, result.message
        assert result.reverse_check is True
        assert result.message == "Integration verified by differentiation"


class TestG11GenuineFailuresSurvive:
    def test_wrong_antiderivative_still_fails(self) -> None:
        # d/dx(x**3) = 3*x**2 != x**2; the residual has no branch-cut power.
        result = StepVerifier().verify_step(_integrate_step("x**2", X**3))
        assert result.status == VerificationStatus.FAILED, result.message

    def test_heuristic_wrong_derivative_fails(self) -> None:
        result = reverse_check_verdict(2 * X, X**2)
        assert result.status == VerificationStatus.FAILED, result.message


class TestG11BranchAmbiguityIsNotDisproof:
    def test_branch_cut_residual_is_inconclusive_not_failed(self) -> None:
        # ``sqrt(x**2)`` is a branch-cut power; positive sampling settles
        # neither side of ``sqrt(x**2) == 2``.
        result = reverse_check_verdict(sp.sqrt(X**2), sp.Integer(2))
        assert result.status == VerificationStatus.INCONCLUSIVE, result.message
