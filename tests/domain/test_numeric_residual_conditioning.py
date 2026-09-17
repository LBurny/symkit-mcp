"""r18 honesty regression: numeric-residual conditioning, sampling, wording.

Merged from two files on the numeric-evidence predicates:

Defect B1b (orchestrator round 18): ``math("simplify", "sec(x)**2 - tan(x)**2")``
returns ``1``; the step difference ``sec(x)**2 - tan(x)**2 - 1`` reduces to ``0``
under the same build's ``simplify``.  The user-visible verification message still
said the difference "did not reduce to zero (simplifier limitation); it is
numerically nonzero at tested points".

Root cause: ``numeric_residual_verdict`` accepted a sample as "clearly nonzero"
when ``abs(value) > 1e-10 * max(1, abs(value))`` — a tolerance scaled by the
residual's own value, so any nonzero magnitude (including arithmetic cancellation
junk) refuted.  The tolerance now scales with the magnitude of the substituted
parts, an ill-conditioned sample (huge terms) can no longer manufacture a
nonzeroness claim, and a constant residual is reported as its exact value rather
than as sampling evidence.

Doctrine preserved: one clearly nonzero sample refutes, at least two samples are
needed to certify "consistent with zero", and ``Sum``/``Integral`` stay ``None``.

Sampling tolerance (2026-09-14 turbine round): ``is_numerically_zero`` must
absorb float-path noise on symbol-bearing residuals — the verifier recomputed a
substitution along a different float path than the archived output, the combined
power exponent differed by one ULP, and the no-tolerance branch flipped a
correct step to FAILED.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.final_result import (
    classify_suspect_identity,
    is_numerically_zero,
    numeric_residual_verdict,
)
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus


class TestConditioningTolerance:
    def test_true_sec_tan_difference_is_not_refuted(self) -> None:
        x = sp.Symbol("x")
        residual = sp.sec(x) ** 2 - sp.tan(x) ** 2 - 1
        assert numeric_residual_verdict(residual) is not True

    def test_ill_conditioned_sample_is_not_refuted(self) -> None:
        # The residual is exactly -1, but its terms are ~1e20: a 30-digit sample
        # cannot resolve 1 part in 1e20, so this must not be called "clearly
        # nonzero".  The old absolute test refuted it from cancellation scale.
        x = sp.Symbol("x")
        big = sp.Rational(10**20)
        residual = big * (sp.sin(x) ** 2 + sp.cos(x) ** 2) - big - 1
        assert numeric_residual_verdict(residual) is not True

    def test_genuine_nonzero_constant_is_still_refuted(self) -> None:
        assert numeric_residual_verdict(sp.Integer(1)) is True
        assert numeric_residual_verdict(sp.Integer(1) - 2) is True

    def test_genuine_nonzero_symbolic_residual_is_still_refuted(self) -> None:
        x, y = sp.symbols("x y")
        assert numeric_residual_verdict(2 * x) is True
        assert numeric_residual_verdict(x - y) is True

    def test_unevaluated_aggregates_stay_unrefuted(self) -> None:
        n = sp.Symbol("n")
        x = sp.Symbol("x")
        assert numeric_residual_verdict(sp.Sum((-1) ** n / n, (n, 1, sp.oo))) is None
        assert (
            numeric_residual_verdict(sp.Integral(sp.exp(-x**2), (x, 0, sp.oo))) is None
        )


class TestResidualWording:
    def test_constant_residual_has_no_sampling_claim(self) -> None:
        kind, phrase = classify_suspect_identity(sp.Integer(1), asserted=False)
        assert kind == "unreduced"
        assert "numerically nonzero at tested points" not in phrase
        assert "exact value 1" in phrase

    def test_symbolic_residual_keeps_sampling_wording(self) -> None:
        x = sp.Symbol("x")
        _kind, phrase = classify_suspect_identity(2 * x, asserted=False)
        assert "numerically nonzero at tested points" in phrase

    def test_asserted_false_constant_is_graded_numeric(self) -> None:
        kind, phrase = classify_suspect_identity(sp.Integer(-1), asserted=True)
        assert kind == "numeric"
        assert "FALSE" in phrase


class TestSuspectMessageHonesty:
    """End-to-end: the ``sec^2 - tan^2`` step message stops overclaiming."""

    def _step(self) -> DerivationStep:
        x = sp.Symbol("x")
        input_expr = sp.sec(x) ** 2 - sp.tan(x) ** 2
        return DerivationStep(
            step_number=1,
            operation=OperationType.SIMPLIFY,
            description="r18 audit5 case A",
            # The recorder archives the *user's* text; ``str(parsed)`` would
            # render this as ``-tan(x)**2 + sec(x)**2``, which the r23 F4
            # written-form gate correctly rejects as ordinary algebra.
            input_expressions={"original": "sec(x)**2 - tan(x)**2"},
            output_expression="1",
            output_latex="1",
            sympy_command="simplify(sec(x)**2 - tan(x)**2)",
            input_srepr=sp.srepr(input_expr),
            output_srepr=sp.srepr(sp.Integer(1)),
        )

    def test_message_does_not_claim_numerically_nonzero(self) -> None:
        result = StepVerifier().verify_step(self._step())
        assert result.status == VerificationStatus.VERIFIED
        assert result.details.get("suspect_identity") == "unreduced"
        assert "numerically nonzero" not in result.message
        assert "exact value 1" in result.message

    def test_genuinely_false_difference_is_still_flagged_numerically(self) -> None:
        # A faithful simplification of a false identity keeps the true warning.
        step = DerivationStep(
            step_number=1,
            operation=OperationType.SIMPLIFY,
            description="r18 control",
            input_expressions={"original": "cos(2*x) - (1 - 2*sin(2*x)**2)"},
            output_expression="-8*sin(x)**4 + 6*sin(x)**2",
            output_latex="-8*sin(x)**4 + 6*sin(x)**2",
            sympy_command="",
        )
        result = StepVerifier().verify_step(step)
        assert result.details.get("suspect_identity") == "unreduced"
        assert "numerically nonzero at tested points" in result.message


# Float-path noise absorption (2026-09-14 turbine round).
def test_float_ulp_symbolic_residual_is_zero():
    a = sp.Symbol("a", positive=True)
    diff = a**sp.Float("0.99999999999999989") - a**sp.Float("1.0")
    assert is_numerically_zero(diff)


def test_genuinely_different_power_stays_nonzero():
    a = sp.Symbol("a", positive=True)
    assert not is_numerically_zero(a - a**sp.Rational(1, 2))
    assert not is_numerically_zero(a - 2 * a)


def test_abs_difference_respects_sign_assumptions():
    apos = sp.Symbol("a", positive=True)
    areal = sp.Symbol("b", real=True)
    assert is_numerically_zero(apos - sp.Abs(apos))
    assert not is_numerically_zero(areal - sp.Abs(areal))


def test_unsamplable_expression_conservatively_false():
    x = sp.Symbol("x")
    assert not is_numerically_zero(sp.Derivative(sp.Function("f")(x), x))


def test_two_symbol_residual_needs_asymmetric_samples():
    x, y = sp.symbols("x y", positive=True)
    assert is_numerically_zero(x * y - y * x)
    # ``x - y`` vanishes only at symmetric sample points; joint sampling must
    # still catch the asymmetric ones.
    assert not is_numerically_zero(x - y)
