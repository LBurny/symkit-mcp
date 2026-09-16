"""r21 Wave 1: integration-verdict and quadrature-wording regressions.

Three shipped defects reproduced black-box on the r21 sandbox cards:

* G2 (P1) a requested integral the engine could not evaluate comes back as an
  inert ``Integral`` with ``success: true``, and the step was judged VERIFIED
  ("Integration verified by differentiation") — reverse differentiation of an
  unevaluated ``Integral(f, x)`` trivially returns ``f``, so the check
  certified nothing.
* G6 (P1, crash-swallow) ``integrate(x**x, x)`` returns a sympy
  ``NonElementaryIntegral`` whose limits are a bare ``Tuple``; ``sp.diff`` on
  it dies with ``AttributeError: 'Tuple' object has no attribute 'diff'``, and
  the MCP recording layer swallowed the crash into a warning, so the step never
  landed.
* G3 (P3 wording) a definite integral whose recomputed quadrature differs was
  reported as "Numeric quadrature disagrees with the stated definite-integral
  result", blaming the result when the tool's own quadrature is unreliable for
  oscillatory or slowly convergent integrands.
"""

from __future__ import annotations

from typing import Any

import sympy as sp
from sympy.integrals.risch import NonElementaryIntegral

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.expr_io import safe_load_expression
from symkit.domain.expression_parser import parse_expression_string
from symkit.domain.final_result import numeric_integral_verdict
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus
from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP / fresh_session_manager are provided by conftest.py
# ruff: noqa: F821


def _tools() -> dict[str, Any]:
    mcp = MockMCP()  # noqa: F821
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _integrate_step(
    input_expression: str,
    output_expr: sp.Basic,
    *,
    command: str = "integrate(expr, x)",
) -> DerivationStep:
    """A live-recorder-shaped integrate step (srepr mirrors the recorder)."""
    parsed, _ = parse_expression_string(input_expression, convert_equation=True)
    assert parsed is not None
    output_str = str(output_expr)
    return DerivationStep(
        step_number=1,
        operation=OperationType.INTEGRATE,
        description="r21 integration",
        input_expressions={"original": input_expression},
        output_expression=output_str,
        output_latex=output_str,
        sympy_command=command,
        input_srepr=sp.srepr(parsed),
        output_srepr=sp.srepr(output_expr),
    )


# ---- G2: an unevaluated integral must not get a vacuous green ----------------


class TestUnevaluatedIntegralNoVacuousGreen:
    def test_exp_sin_unevaluated_integral_is_inconclusive(self) -> None:
        x = sp.Symbol("x")
        inert = sp.Integral(sp.exp(sp.sin(x)), x)
        result = StepVerifier().verify_step(
            _integrate_step("exp(sin(x))", inert)
        )
        assert result.status == VerificationStatus.INCONCLUSIVE
        assert "could not be evaluated" in result.message
        assert "trivially true" in result.message
        assert result.status != VerificationStatus.VERIFIED

    def test_inert_wrapper_input_and_output_is_inconclusive(self) -> None:
        # An ``Integral(f, x)`` input returned unchanged is the same idle case.
        x = sp.Symbol("x")
        inert = sp.Integral(sp.exp(sp.sin(x)), x)
        result = StepVerifier().verify_step(
            _integrate_step(str(inert), inert)
        )
        assert result.status == VerificationStatus.INCONCLUSIVE
        assert "trivially true" in result.message

    def test_genuinely_evaluated_indefinite_integral_still_verifies(self) -> None:
        x = sp.Symbol("x")
        result = StepVerifier().verify_step(
            _integrate_step("x**2", x**3 / 3)
        )
        assert result.status == VerificationStatus.VERIFIED
        assert result.reverse_check is True

    def test_definite_integral_unchanged(self) -> None:
        result = StepVerifier().verify_step(
            _integrate_step(
                "x**2", sp.Rational(1, 3), command="integrate(expr, (x, 0, 1))"
            )
        )
        assert result.status == VerificationStatus.VERIFIED


# ---- G6: NonElementaryIntegral must load as a differentiable plain Integral --


class TestNonElementaryIntegralNormalization:
    def test_safe_load_normalizes_non_elementary_integral(self) -> None:
        x = sp.Symbol("x")
        stored = NonElementaryIntegral(x**x, x)
        loaded = safe_load_expression(str(stored), sp.srepr(stored))
        assert loaded is not None
        assert type(loaded).__name__ == "Integral"
        assert not isinstance(loaded, NonElementaryIntegral)
        assert sp.diff(loaded, x) == x**x

    def test_non_elementary_step_lands_with_conclusive_verdict(self) -> None:
        x = sp.Symbol("x")
        stored = NonElementaryIntegral(x**x, x)
        result = StepVerifier().verify_step(
            _integrate_step("x**x", stored)
        )
        assert result.status == VerificationStatus.INCONCLUSIVE
        assert "trivially true" in result.message

    def test_integrate_xx_records_without_swallowed_crash(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("r21-nonelementary")
        response = tools["math"](
            operation="integrate", expression="x**x", variable="x", session=True
        )
        assert response["success"] is True
        warnings = response.get("warnings", [])
        assert not any("Step recording failed" in w for w in warnings), warnings
        assert response.get("step") == 1
        session = _state.get_session()
        assert session is not None and len(session.steps) == 1
        verify = tools["session_verify_step"](1)
        assert verify["verification_status"] == "inconclusive"


# ---- G3: honest wording when the tool's own quadrature is unreliable ---------


class TestQuadratureWording:
    def test_mismatch_blames_quadrature_not_the_result(self) -> None:
        x = sp.Symbol("x")
        # integral_0^inf e^{i x}/x dx has principal value i*pi/2; sympy leaves
        # it unevaluated and its raw quadrature is unreliable, so the stated
        # result must not be reported as a disagreement.
        inert = sp.Integral(sp.exp(sp.I * x) / x, (x, 0, sp.oo))
        status, message = numeric_integral_verdict(inert, sp.I * sp.pi / 2)
        assert status == VerificationStatus.INCONCLUSIVE
        assert "could not confirm" in message
        assert "oscillatory" in message
        assert "disagrees with the stated" not in message

    def test_agreeing_result_still_verifies(self) -> None:
        x = sp.Symbol("x")
        inert = sp.Integral(x**2, (x, 0, 1))
        status, _message = numeric_integral_verdict(inert, sp.Rational(1, 3))
        assert status == VerificationStatus.VERIFIED
