"""Regression: ``Subs`` bindings must survive equality normalization.

Task-08 §4-A: a mathematically correct chain-rule ``simplify`` step

    ∂²ₜ f(x − ct)  =  c² · f''(x − ct)

was reported FAILED because the verifier applied ``doit()`` to the already
evaluated ``Subs`` result; SymPy's ``Mul(c**2, Subs(Derivative(f(ξ), (ξ, 2)),
ξ, x−ct)).doit()`` drops the substitution binding and returns the bare
``Derivative(f(ξ), (ξ, 2))``, so the residual became a phantom difference
``c²·(Subs(...) − Derivative(...))``.

These tests pin the correct behaviour: the ``Subs`` form (which is exactly what
``Derivative(...).doit()`` produces) must verify against the unevaluated
``Derivative`` input, while a genuinely changed value must still FAIL.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.assumption_engine import AssumptionEngine
from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus


def _assumptions() -> AssumptionEngine:
    engine = AssumptionEngine()
    engine.assume("c", "positive", "real")
    return engine


def _subs_chain_rule(var: str, extra: int = 1) -> sp.Basic:
    """The archived output of ``diff(f(x - c*t), var, 2)``.

    ``extra`` scales the result so a wrong output can be built from the same
    shape (the factor must make the step genuinely wrong).
    """
    c = sp.Symbol("c", positive=True, real=True)
    t, x = sp.Symbol("t"), sp.Symbol("x")
    f = sp.Function("f")
    dummy = sp.Dummy("xi_1")
    body = sp.Derivative(f(dummy), (dummy, 2))
    inner = sp.Subs(body, dummy, x - c * t)
    return extra * c**2 * inner if var == "t" else extra * inner


def _step(var: str, output: sp.Basic) -> DerivationStep:
    c = sp.Symbol("c", positive=True, real=True)
    t, x = sp.Symbol("t"), sp.Symbol("x")
    f = sp.Function("f")
    original = sp.Derivative(f(x - c * t), (var, 2))
    return DerivationStep(
        step_number=1,
        operation=OperationType.SIMPLIFY,
        description="chain-rule factor",
        input_expressions={"operation": "simplify", "original": str(original)},
        output_expression=str(output),
        output_latex=sp.latex(output),
        sympy_command="math('simplify', ...)",
        output_srepr=sp.srepr(output),
        input_srepr=sp.srepr(original),
    )


def test_time_chain_rule_subs_output_verifies() -> None:
    result = StepVerifier().verify_step(
        _step("t", _subs_chain_rule("t")), assumption_engine=_assumptions()
    )
    assert result.status is VerificationStatus.VERIFIED, result.details


def test_space_chain_rule_subs_output_verifies() -> None:
    result = StepVerifier().verify_step(
        _step("x", _subs_chain_rule("x")), assumption_engine=_assumptions()
    )
    assert result.status is VerificationStatus.VERIFIED, result.details


def test_scaled_subs_output_still_fails() -> None:
    """A wrong factor must not be waved through by the Subs normalization."""
    result = StepVerifier().verify_step(
        _step("t", _subs_chain_rule("t", extra=2)), assumption_engine=_assumptions()
    )
    assert result.status is VerificationStatus.FAILED
    assert result.details.get("difference")


def test_plain_value_change_still_fails() -> None:
    x = sp.Symbol("x")
    step = DerivationStep(
        step_number=1,
        operation=OperationType.SIMPLIFY,
        description="wrong simplify",
        input_expressions={"operation": "simplify", "original": "x + x"},
        output_expression="3*x",
        output_latex="3 x",
        sympy_command="math('simplify', ...)",
        output_srepr=sp.srepr(3 * x),
        input_srepr=sp.srepr(2 * x),
    )
    result = StepVerifier().verify_step(step)
    assert result.status is VerificationStatus.FAILED
