"""Round-16 (r16) verdict-semantics regression tests.

Each case reproduces a real false verdict from the black-box round 16 sandbox
(tasks 01/06/08/17/19) and pins the corrected semantics:

* an operator step over a *plain* difference form never reports "the asserted
  identity is FALSE" — it is at most ``suspect_identity: "unreduced"`` and keeps
  ``status: verified``;
* ``numeric_residual_verdict`` refuses to falsify a residual carrying an
  unevaluated ``Sum``/``Integral`` (the bound variable cannot be sampled);
* a manually recorded ``Eq`` gets a trig-aware reduction first, so a true
  identity SymPy does not expand verifies while a genuinely false one FAILS;
* ``equation_identity`` is three-state (TRUE / FALSE / UNKNOWN);
* a bare definite ``Integral`` passed to ``integrate`` is checked by numeric
  quadrature instead of an invalid reverse differentiation.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.expression_parser import parse_expression_string
from symkit.domain.final_result import (
    equation_identity,
    numeric_residual_verdict,
    recorded_step_verdict,
)
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus


def _archived_step(
    operation: OperationType,
    input_expression: str,
    output_expression: str,
    sympy_command: str = "",
) -> DerivationStep:
    """A step whose ``input_srepr`` mirrors the live recorder exactly."""
    parsed, _ = parse_expression_string(input_expression, convert_equation=True)
    output, _ = parse_expression_string(output_expression, convert_equation=True)
    assert parsed is not None and output is not None
    return DerivationStep(
        step_number=1,
        operation=operation,
        description="r16 verdict regression",
        input_expressions={"original": str(parsed)},
        output_expression=output_expression,
        output_latex=output_expression,
        sympy_command=sympy_command,
        input_srepr=sp.srepr(parsed),
        output_srepr=sp.srepr(output),
    )


class TestDifferenceFormNeverFalse:
    """task-08/task-19: a plain expression is not an asserted identity."""

    def test_task08_lorentz_invariant_simplification(self) -> None:
        # step 3/20: simplify(E^2 - p^2 c^2) -> c^4 m^2 is correct, and the
        # user never asserted the difference is zero.
        step = _archived_step(
            OperationType.SIMPLIFY,
            "c**4*m**2/(1 - u**2/c**2) - c**2*m**2*u**2/(1 - u**2/c**2)",
            "c**4*m**2",
        )
        result = StepVerifier().verify_step(step)
        assert result.status == VerificationStatus.VERIFIED
        assert result.details.get("suspect_identity") != "numeric"
        assert "asserted identity is FALSE" not in result.message

    def test_task08_velocity_addition_simplification(self) -> None:
        # step 11/21: simplify((c - v)/(1 - v/c)) -> c.
        step = _archived_step(
            OperationType.SIMPLIFY,
            "(c - v)/(1 - v/c)",
            "c",
        )
        result = StepVerifier().verify_step(step)
        assert result.status == VerificationStatus.VERIFIED
        assert result.details.get("suspect_identity") != "numeric"
        assert "asserted identity is FALSE" not in result.message

    def test_task19_numeric_series_result(self) -> None:
        # step 25/26: simplify(-log(2)) and simplify(-pi**2/12) are correct
        # results, not identity claims.
        for expression in ("-log(2)", "-pi**2/12"):
            step = _archived_step(OperationType.SIMPLIFY, expression, expression)
            result = StepVerifier().verify_step(step)
            assert result.status == VerificationStatus.VERIFIED
            assert result.details.get("suspect_identity") != "numeric"
            assert "asserted identity is FALSE" not in result.message

    def test_numeric_residual_verdict_skips_unevaluated_sum(self) -> None:
        # task-19: the residual contains an unevaluated Sum over a free bound
        # variable, so sampling cannot falsify it.
        n = sp.Symbol("n")
        residual = sp.Sum((-1) ** n / n, (n, 1, sp.oo)) - (-sp.log(2))
        assert numeric_residual_verdict(residual) is None

    def test_numeric_residual_verdict_skips_unevaluated_integral(self) -> None:
        x = sp.Symbol("x")
        residual = sp.Integral(sp.exp(-x**2), (x, 0, sp.oo)) - sp.sqrt(sp.pi) / 2
        assert numeric_residual_verdict(residual) is None


class TestRecordedEquationVerdicts:
    """task-17: true identity verifies, buried false identity FAILS."""

    def test_true_cos6x_identity_verifies(self) -> None:
        x = sp.Symbol("x")
        expr = sp.Eq(
            sp.cos(6 * x),
            32 * sp.cos(x) ** 6 - 48 * sp.cos(x) ** 4 + 18 * sp.cos(x) ** 2 - 1,
        )
        status, message = recorded_step_verdict(expr)
        assert status == VerificationStatus.VERIFIED
        assert "Identity verified" in message

    def test_false_cos6x_identity_fails(self) -> None:
        x = sp.Symbol("x")
        # task-17 step 4: cos^4 was transcribed as cos^5.
        expr = sp.Eq(
            (2 * sp.cos(x) ** 2 - 1) ** 3,
            8 * sp.cos(x) ** 6 - 12 * sp.cos(x) ** 5 + 6 * sp.cos(x) ** 2 - 1,
        )
        status, message = recorded_step_verdict(expr)
        assert status == VerificationStatus.FAILED
        assert "not an identity" in message

    def test_undecidable_definition_stays_inconclusive(self) -> None:
        expr = sp.Eq(sp.Function("f")(sp.Symbol("x")), sp.cos(sp.Symbol("x")))
        status, message = recorded_step_verdict(expr)
        assert status == VerificationStatus.INCONCLUSIVE
        assert "unproven, not disproven" in message
        assert "not an identity" not in message


class TestEquationIdentityThreeState:
    def test_true_identity(self) -> None:
        a, b = sp.symbols("a b")
        result = equation_identity(sp.Eq((a + b) ** 2, a**2 + 2 * a * b + b**2))
        assert result["is_identity"] is True
        assert result["verdict"] == "TRUE"

    def test_false_identity(self) -> None:
        a, b = sp.symbols("a b")
        result = equation_identity(sp.Eq((a + b) ** 2, a**2 + b**2))
        assert result["is_identity"] is False
        assert result["verdict"] == "FALSE"

    def test_unreduced_but_numerically_consistent_is_unknown(self) -> None:
        # Plain simplify cannot expand cos(6*x), yet sampling says the
        # difference is zero — unproven, not false.
        x = sp.Symbol("x")
        result = equation_identity(
            sp.Eq(
                sp.cos(6 * x),
                32 * sp.cos(x) ** 6 - 48 * sp.cos(x) ** 4 + 18 * sp.cos(x) ** 2 - 1,
            )
        )
        assert result["is_identity"] is None
        assert result["verdict"] == "UNKNOWN"
        assert "consistent with zero" in result["numeric_evidence"]


class TestDefiniteIntegralNoFalseFailure:
    """task-06 step 15: a correct definite integral must not be FAILED."""

    def test_nested_definite_integral_is_verified(self) -> None:
        x, y = sp.symbols("x y")
        nested = sp.Integral(
            x**2 + y**2,
            (y, -sp.sqrt(1 - x**2), sp.sqrt(1 - x**2)),
            (x, -1, 1),
        )
        step = DerivationStep(
            step_number=15,
            operation=OperationType.INTEGRATE,
            description="nested definite integral",
            input_expressions={"original": str(nested)},
            output_expression="pi/2",
            output_latex="pi/2",
            sympy_command="integrate(expr, None)",
            input_srepr=sp.srepr(nested),
            output_srepr=sp.srepr(sp.pi / 2),
        )
        result = StepVerifier().verify_step(step)
        assert result.status == VerificationStatus.VERIFIED
        assert result.reverse_check is True
