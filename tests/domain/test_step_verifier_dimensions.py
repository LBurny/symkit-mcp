"""Dimensional-analysis wiring tests (Wave B1).

``StepVerifier.verify_step`` stays untouched (modularity ratchet); the
dimension check composes as a post-processor:
``apply_dimension_check(verify_step(...), input, output, unit_map)``.
"""

from __future__ import annotations

from sympy import sympify

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.dimensional_analysis import apply_dimension_check
from symkit.domain.step_verifier import (
    StepVerifier,
    verification_result_from_json,
    verification_result_to_json,
)
from symkit.domain.value_objects import VerificationStatus

UNITS = {"rho": "kg/m^3", "v": "m/s"}


def _make_step(operation: OperationType, original: str, output: str) -> DerivationStep:
    return DerivationStep(
        step_number=1,
        operation=operation,
        description="test step",
        input_expressions={"original": original},
        output_expression=output,
        output_latex=output,
        sympy_command="",
    )


def _verify_with_units(step: DerivationStep, unit_map: dict[str, str]):
    result = StepVerifier().verify_step(step)
    return apply_dimension_check(
        result,
        sympify(step.input_expressions["original"]),
        sympify(step.output_expression),
        unit_map,
    )


def test_inconsistent_step_fails_with_unit_map():
    step = _make_step(OperationType.SIMPLIFY, "rho + v", "rho + v")

    result = _verify_with_units(step, UNITS)

    assert result.status is VerificationStatus.FAILED
    assert result.dimension_check is False
    assert result.details.get("dimension_issues")


def test_consistent_step_verified_with_unit_map():
    step = _make_step(OperationType.SIMPLIFY, "rho*v", "v*rho")

    result = _verify_with_units(step, UNITS)

    assert result.status is VerificationStatus.VERIFIED
    assert result.dimension_check is True


def test_without_unit_map_behaviour_unchanged():
    step = _make_step(OperationType.SIMPLIFY, "rho + v", "rho + v")

    result = StepVerifier().verify_step(step)

    assert result.status is VerificationStatus.VERIFIED
    assert result.dimension_check is None


def test_unknown_units_do_not_fail_step():
    step = _make_step(OperationType.SIMPLIFY, "rho + v", "rho + v")

    # `v` has no unit information: unknown, not a failure.
    result = _verify_with_units(step, {"rho": "kg/m^3"})

    assert result.status is VerificationStatus.VERIFIED
    assert result.dimension_check is None


def test_dimension_failure_is_serialisable():
    step = _make_step(OperationType.SIMPLIFY, "rho + v", "rho + v")

    result = _verify_with_units(step, UNITS)
    restored = verification_result_from_json(verification_result_to_json(result))

    assert restored.status is VerificationStatus.FAILED
    assert restored.dimension_check is False


# --- D3: a zero RHS must not fail a correct ODE step ------------------------

ODE_UNITS = {"C": "farad", "R": "ohm", "V": "volt", "v_C": "volt", "t": "s"}


def test_ode_step_with_zero_rhs_is_not_dimensionally_failed():
    step = _make_step(
        OperationType.DSOLVE,
        "C*R*Derivative(v_C(t), t) + v_C(t) - V",
        "Eq(C*R*Derivative(v_C(t), t) + v_C(t) - V, 0)",
    )

    result = _verify_with_units(step, ODE_UNITS)

    assert result.dimension_check is not False, result.details
    assert result.status is not VerificationStatus.FAILED


def test_equation_with_two_mismatched_nonzero_sides_still_fails():
    """Task-06 trap: neither side is zero, so the mismatch must survive."""
    step = _make_step(OperationType.SIMPLIFY, "v", "Eq(v**2, v0**2 + 2*a*t)")
    units = {"v": "m/s", "v0": "m/s", "a": "m/s^2", "t": "s"}

    result = _verify_with_units(step, units)

    assert result.dimension_check is False, result.details
    assert result.status is VerificationStatus.FAILED


# --- A symbol without declared units is unknown, never fabricated -----------


def test_symbol_without_declared_unit_is_unknown():
    """``p`` has no unit here; it must not inherit a domain default.

    Task-09: an unregistered symbol whose name collides with a domain catalogue
    entry was assigned that entry's unit, fabricating an inconsistency and
    failing a correct step.
    """
    step = _make_step(OperationType.SIMPLIFY, "p + z", "p + z")

    result = _verify_with_units(step, {"z": "m"})

    assert result.status is not VerificationStatus.FAILED
    assert result.dimension_check is None, result.details
    assert "p" not in result.details.get("dimensions", {})
