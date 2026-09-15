"""Equation equivalence and warning hygiene in StepVerifier (r17 round).

Two defects from the 2026-09-14 complex-theorem black-box round:

* ``sympy.simplify`` normalizes an equation by moving everything to one side and
  dividing by the leading coefficient, so ``Eq(2*x, 3*x)`` comes back as
  ``Eq(x, 0)`` — the difference flips sign.  The verifier compared differences
  for exact equality and called the tool's own output "Simplify changes
  expression value" (FAILED), dragging the session to ``overall: failed``.
* The "contains division" warning was a substring test on the rendered output,
  so any fractional coefficient (``4*x**3/3``) raised a denominator warning on
  an expression with no division at all.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.final_result import equations_equivalent
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus


def _step(
    operation: OperationType,
    input_expr: sp.Basic,
    output_expr: sp.Basic,
    sympy_command: str = "",
    key: str = "equation",
) -> DerivationStep:
    return DerivationStep(
        step_number=1,
        operation=operation,
        description="r17 regression step",
        input_expressions={key: str(input_expr)},
        output_expression=str(output_expr),
        output_latex="",
        sympy_command=sympy_command,
        input_srepr=sp.srepr(input_expr),
        output_srepr=sp.srepr(output_expr),
    )


class TestEquationScaleNormalization:
    """A rescaled equation is the same equation."""

    def test_sign_flipped_normalization_is_verified(self):
        x = sp.Symbol("x")
        step = _step(OperationType.SIMPLIFY, sp.Eq(2 * x, 3 * x), sp.Eq(x, 0))
        result = StepVerifier().verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED, result.message

    def test_scaled_normalization_is_verified(self):
        x = sp.Symbol("x")
        step = _step(OperationType.SIMPLIFY, sp.Eq(2 * x - 4, 0), sp.Eq(x, 2))
        result = StepVerifier().verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED, result.message

    def test_cubic_equation_normalization_is_verified(self):
        x = sp.Symbol("x")
        step = _step(
            OperationType.SIMPLIFY,
            sp.Eq(8 * x**3 - 12 * x, 2 * x * (4 * x**2 - 2) - 6 * x),
            sp.Eq(x, 0),
        )
        result = StepVerifier().verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED, result.message

    def test_different_equation_still_fails(self):
        x = sp.Symbol("x")
        step = _step(OperationType.SIMPLIFY, sp.Eq(2 * x, 3 * x), sp.Eq(x, 1))
        result = StepVerifier().verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.FAILED


class TestDivisionWarningHygiene:
    """The denominator warning follows the algebra, not the rendered string."""

    def test_fractional_coefficient_is_not_a_division_warning(self):
        x, t = sp.symbols("x t")
        output = 1 + 2 * t * x + t**2 * (sp.Rational(4, 3) * x**3 - 2 * x)
        step = _step(OperationType.SERIES, sp.exp(2 * x * t - t**2), output, key="original")
        result = StepVerifier().verify_step(step, prior_expr=None)
        assert not [w for w in result.details.get("warnings", []) if "division" in w], result.details

    def test_symbolic_denominator_still_warns(self):
        x = sp.Symbol("x")
        step = _step(OperationType.SIMPLIFY, sp.Function("f")(x), 1 / x, key="original")
        result = StepVerifier().verify_step(step, prior_expr=None)
        assert [w for w in result.details.get("warnings", []) if "division" in w], result.details


class TestReverseIntegrationStaysBounded:
    """A high-order derivative must not wedge the verifier (r17 task-01).

    ``math("diff", "(1 - 2*x*t + t**2)**(-1/2)", variable="t", order=4)`` returns
    in 0.02s with ``session=False`` but hung the single-process server for 15+
    minutes with the default ``session=True``: the differentiation check reverse
    integrates the output once per order, and the *second* ``sympy.integrate`` on
    the 701-operation intermediate never returns. The check now stops when the
    expression grows past the cap and reports INCONCLUSIVE instead.
    """

    def test_fourth_order_nested_power_derivative_terminates(self):
        x, t = sp.symbols("x t")
        source = (1 - 2 * x * t + t**2) ** sp.Rational(-1, 2)
        step = _step(
            OperationType.DIFFERENTIATE,
            source,
            sp.diff(source, t, 4),
            sympy_command="diff(expr, t, 4)",
            key="original",
        )
        result = StepVerifier().verify_step(step, prior_expr=source)
        assert result.status == VerificationStatus.INCONCLUSIVE
        assert "skipped" in result.message.lower()

    def test_first_order_derivative_still_verifies(self):
        x, t = sp.symbols("x t")
        source = (1 - 2 * x * t + t**2) ** sp.Rational(-1, 2)
        step = _step(
            OperationType.DIFFERENTIATE,
            source,
            sp.diff(source, t),
            sympy_command="diff(expr, t)",
            key="original",
        )
        result = StepVerifier().verify_step(step, prior_expr=source)
        assert result.status == VerificationStatus.VERIFIED, result.message


class TestEquationEquivalenceSymmetry:
    """``equations_equivalent`` must treat both sides alike (r17 review).

    The structural-zero shortcut only looked at the right-hand difference, so
    ``equiv(0, sin(x)**2 + cos(x)**2 - 1)`` was False while the mirrored call
    was True — two forms of the same all-zero equation disagreed.
    """

    def test_zero_sides_are_compared_symmetrically(self):
        x = sp.Symbol("x")
        trig_zero = sp.sin(x) ** 2 + sp.cos(x) ** 2 - 1  # simplifies to 0, is not 0

        assert equations_equivalent(trig_zero, sp.Integer(0))
        assert equations_equivalent(sp.Integer(0), trig_zero)
        assert equations_equivalent(trig_zero, trig_zero)

    def test_distinct_expressions_stay_distinct(self):
        x, y = sp.symbols("x y")
        assert not equations_equivalent(x, y)
        assert not equations_equivalent(sp.Integer(0), x)
