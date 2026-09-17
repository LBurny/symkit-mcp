"""Round-19 (r19) black-box regressions: verifier advisory gating and recovery.

Three shipped defects are pinned here:

* F1 — the ``suspect_identity`` advisory fired on a plain three-term sum with
  two subtracted compounds (an ordinary simplification, not an ``A - B``
  identity claim), and its wording never named its referent.  The advisory must
  fire only for a genuine two-sided difference, and say so.
* F9 — ``simplify("Eq(0, 5)")`` collapses to ``False`` at parse time; the step
  then reported ``"boolean value preserved"`` / verified, so a DISPROVEN
  equation read green in the chain.  The archived claim must be recovered and
  the step must FAIL, while ``Eq(0, 0)`` stays verified.
* F11 — reverse integration could not confirm a derivative of order >= 3,
  because the integration-constant ambiguity of an order-``n`` antiderivative
  spans polynomials of degree < ``n``, not only constants.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.expression_parser import parse_expression_string
from symkit.domain.final_result import suspect_identity_warning
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus

# MockMCP / fresh_session_manager are provided by conftest.py
# ruff: noqa: F821


def _archived(
    operation: OperationType,
    input_expression: str,
    output_expression: str,
    sympy_command: str = "",
) -> DerivationStep:
    """A live-recorder-shaped archived step (``input_srepr`` present).

    ``original`` keeps the *user's* text, as the recorder does; ``str(parsed)``
    reorders a difference, which the r23 F4 written-form gate must reject.
    """
    parsed, _ = parse_expression_string(input_expression, convert_equation=True)
    out, _ = parse_expression_string(output_expression, convert_equation=True)
    assert parsed is not None and out is not None
    return DerivationStep(
        step_number=1,
        operation=operation,
        description="r19 regression",
        input_expressions={"original": input_expression},
        output_expression=output_expression,
        output_latex=output_expression,
        sympy_command=sympy_command,
        input_srepr=sp.srepr(parsed),
        output_srepr=sp.srepr(out),
    )


class TestDifferenceFormGateNarrowing:
    """F1: only a genuine two-sided ``A - B`` earns the advisory."""

    def test_three_term_sum_with_two_negatives_is_not_an_asserted_difference(self) -> None:
        # One positive compound plus two subtracted compounds is an ordinary
        # simplification, not a claim that ``A - B`` vanishes.
        step = _archived(
            OperationType.SIMPLIFY,
            "8*a*tr/(27*b*(3*b*vr - b)) - a*pr/(27*b**2) - a/(9*b**2*vr**2)",
            "a*(-pr*vr**2*(3*vr - 1) + 8*tr*vr**2 - 9*vr + 3)"
            "/(27*b**2*vr**2*(3*vr - 1))",
        )
        result = StepVerifier().verify_step(step)
        assert result.status == VerificationStatus.VERIFIED
        assert "suspect_identity" not in result.details
        assert "did not reduce to zero" not in result.message

    def test_two_operand_sub_keeps_advisory_and_names_the_ab_referent(self) -> None:
        # A literal ``A - B`` whose value is genuinely nonzero keeps the
        # advisory, but the wording must name the referent.
        step = _archived(
            OperationType.SIMPLIFY,
            "5*x*(3*x**2/2-1/2)/3 - 2*x/3",
            "x*(5*x**2 - 3)/2",
        )
        result = StepVerifier().verify_step(step)
        assert result.status == VerificationStatus.VERIFIED
        assert result.details.get("suspect_identity") == "unreduced"
        assert "the input has the form A - B" in result.message
        assert "does not assert the identity A = B" in result.message
        assert "asserted identity is FALSE" not in result.message

    def test_genuine_two_sided_difference_still_fires(self) -> None:
        for input_expression, output_expression in (
            ("sin(x+y)-(sin(x)+sin(y))", "-sin(x) - sin(y) + sin(x + y)"),
            ("sqrt(a**2 + b**2) - (a + b)", "-a - b + sqrt(a**2 + b**2)"),
        ):
            step = _archived(OperationType.SIMPLIFY, input_expression, output_expression)
            result = StepVerifier().verify_step(step)
            assert result.details.get("suspect_identity") == "unreduced", input_expression
            assert "the input has the form A - B" in result.message

    def test_leading_negative_form_still_escapes_the_advisory(self) -> None:
        # ``-x**2 + x*(x + 1)`` is identical to ``x``; a *leading* negated
        # compound is ordinary algebra, never an asserted ``A - B``.
        step = _archived(OperationType.SIMPLIFY, "-x**2 + x*(x + 1)", "x")
        result = StepVerifier().verify_step(step)
        assert result.status == VerificationStatus.VERIFIED
        assert "suspect_identity" not in result.details
        assert "did not reduce to zero" not in result.message

    def test_suspect_identity_warning_names_the_ab_form(self) -> None:
        warning = suspect_identity_warning([3, 7])
        assert "2 step(s)" in warning
        assert "A - B difference forms" in warning
        assert "suspect_identity_steps" in warning

    def test_three_term_session_step_is_not_surfaced_as_suspect(
        self, fresh_session_manager: object
    ) -> None:
        _ = fresh_session_manager
        from symkit_mcp.tools.math import register_math_tools
        from symkit_mcp.tools.session import register_session_tools

        mcp = MockMCP()
        register_math_tools(mcp)
        register_session_tools(mcp)
        tools = mcp.tools
        tools["session_start"]("r19-three-term")
        tools["math"](
            operation="simplify",
            expression="8*a*tr/(27*b*(3*b*vr - b)) - a*pr/(27*b**2) - a/(9*b**2*vr**2)",
            session=True,
        )
        result = tools["session_verify_session"]()
        assert result["suspect_identity_steps"] == []
        assert not any("suspect_identity_steps" in w for w in result.get("warnings", []))


class TestBooleanEquationClaimRecovery:
    """F9: a collapsed disproven equation must not read as verified."""

    @staticmethod
    def _collapsed_step(claim: str, verdict: sp.Basic) -> DerivationStep:
        return DerivationStep(
            step_number=1,
            operation=OperationType.SIMPLIFY,
            description="r19 collapsed equation",
            input_expressions={"operation": "simplify", "original": claim},
            output_expression=str(verdict),
            output_latex=str(verdict),
            sympy_command="simplify(expr)",
            input_srepr=sp.srepr(verdict),
            output_srepr=sp.srepr(verdict),
        )

    def test_disproven_equation_collapse_fails(self) -> None:
        result = StepVerifier().verify_step(self._collapsed_step("Eq(0, 5)", sp.false))
        assert result.status == VerificationStatus.FAILED
        assert result.details.get("suspect_identity") == "numeric"
        assert "FALSE" in result.message
        assert "0" in result.message and "5" in result.message

    def test_true_equation_collapse_stays_verified(self) -> None:
        result = StepVerifier().verify_step(self._collapsed_step("Eq(0, 0)", sp.true))
        assert result.status == VerificationStatus.VERIFIED
        assert "asserted equation holds" in result.message

    def test_disproven_equation_session_is_not_overall_verified(
        self, fresh_session_manager: object
    ) -> None:
        _ = fresh_session_manager
        from symkit_mcp.tools.math import register_math_tools
        from symkit_mcp.tools.session import register_session_tools

        mcp = MockMCP()
        register_math_tools(mcp)
        register_session_tools(mcp)
        tools = mcp.tools
        tools["session_start"]("r19-eq-collapse")
        tools["math"](operation="simplify", expression="Eq(0, 5)", session=True)
        summary = tools["session_verify_session"]()
        assert summary["overall"] == "failed"
        assert summary["failed_steps"] == [1]


class TestReverseIntegrationHigherOrder:
    """F11: order >= 3 differentiation must be confirmed by reverse integration."""

    def test_cubic_derivative_of_order_three_verifies(self) -> None:
        step = _archived(
            OperationType.DIFFERENTIATE,
            "(x**2 - 1)**3/48",
            "x*(5*x**2 - 3)/2",
            sympy_command="diff(expr, x, 3)",
        )
        result = StepVerifier().verify_step(step)
        assert result.status == VerificationStatus.VERIFIED
        assert result.reverse_check is True

    def test_wrong_higher_order_derivative_is_not_verified(self) -> None:
        # The order-th derivative test admits only the integration-constant
        # ambiguity (degree < order), not an arbitrary error.
        step = _archived(
            OperationType.DIFFERENTIATE,
            "(x**2 - 1)**3/48",
            "x*(5*x**2 - 3)/2 + x**3",
            sympy_command="diff(expr, x, 3)",
        )
        result = StepVerifier().verify_step(step)
        assert result.status == VerificationStatus.INCONCLUSIVE

    def test_oversized_reverse_integration_still_refuses(self) -> None:
        big = sp.Add(*[sp.Symbol("x") ** i for i in range(400)])
        assert sp.count_ops(big) > 300
        step = _archived(
            OperationType.DIFFERENTIATE,
            "x",
            str(big),
            sympy_command="diff(expr, x)",
        )
        result = StepVerifier().verify_step(step)
        assert result.status == VerificationStatus.INCONCLUSIVE
        assert "Reverse integration skipped" in result.message
        assert "size budget" in result.message


class TestF37DirectRecomputation:
    """F37 (wave 3): a branching antiderivative must not blind the diff check."""

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
