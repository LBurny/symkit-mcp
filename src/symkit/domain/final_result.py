"""Interpretation of a derivation's headline result and manually recorded equations.

Pure domain helpers shared by :mod:`symkit.domain.derivation_session` and
:mod:`symkit.domain.step_verifier`:

* :func:`select_headline` picks the outcome a completed session should report
  when trailing steps failed verification;
* :func:`recorded_step_verdict` content-checks a hand-recorded ``Eq(a, b)``;
* :func:`equation_identity` reports whether an operation's equation input is an
  identity (auxiliary information only);
* :func:`is_numerically_zero` / :func:`evaluate_pending` are the shared
  symbolic-residual predicates, and :func:`symbol_names` /
  :func:`candidate_names` name the symbols an outcome selection compares.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import sympy as sp
from sympy.logic.boolalg import BooleanFalse, BooleanTrue

from symkit.domain.expr_io import safe_load_expression
from symkit.domain.value_objects import VerificationStatus

if TYPE_CHECKING:
    from collections.abc import Sequence

    from symkit.domain.derivation_session import DerivationStep


# Numeric residual tolerance for symbolic verification. Symbolic derivation
# diffs are dimensionless algebraic residuals; machine-precision noise from
# float inputs must not flip a correct step to FAILED.
_NUM_ZERO_TOL = 1e-9


def evaluate_pending(expr: sp.Basic) -> sp.Basic:
    """Evaluate unevaluated operations (``Derivative``/``Integral``/``Sum``).

    ``doit()`` first: a ``simplify`` step over an unevaluated derivative only
    reduces to zero once the derivative is evaluated (task-15 step 12).  A
    ``Subs`` node is exempt — ``doit()`` drops its binding and fabricates a
    phantom difference between identical expressions (task-08 steps 8/9) — so
    surviving ``Subs`` forms are canonicalised with
    :func:`canonicalize_dummies`.
    """
    if expr.has(sp.Subs):
        return canonicalize_dummies(expr)
    try:
        evaluated = expr.doit()
    except Exception:  # pragma: no cover - doit may fail on exotic objects
        return expr
    return canonicalize_dummies(evaluated) if evaluated.has(sp.Subs) else evaluated


def canonicalize_dummies(expr: sp.Basic) -> sp.Basic:
    """Give every ``Dummy`` a name-derived, deterministic ``dummy_index``.

    Two identical ``Subs`` bindings produced independently carry different
    anonymous dummies that SymPy 1.14 does not cancel in a difference; a
    shared index makes the forms compare equal without changing the math.
    """
    mapping = {
        dummy: sp.Dummy(dummy.name, dummy_index=_dummy_index_for(dummy.name))
        for dummy in expr.atoms(sp.Dummy)
    }
    return expr.xreplace(mapping) if mapping else expr


def _dummy_index_for(name: str) -> int:
    """Stable per-name dummy index (process-independent)."""
    return int.from_bytes(name.encode("utf-8"), "big") % (2**31 - 1)


def is_numerically_zero(diff: sp.Basic) -> bool:
    """True if ``diff`` is exactly zero, or numerically zero within tolerance.

    Symbolic differences must simplify to exact zero; purely numeric ones are
    compared in floating point with an absolute tolerance of 1e-9; symbol-bearing
    ones are *sampled* before refusal — float-path noise (a one-ULP power
    exponent drift between two evaluation paths, 2026-09-14 turbine round) must
    not flip a correct step.  Matrix-valued differences are checked entrywise:
    ``Matrix == 0`` is not a Python truth value (2026-09-12 black-box round).
    """
    if isinstance(diff, sp.MatrixExpr) and not isinstance(diff, sp.MatrixBase):
        diff = diff.as_explicit()
    if isinstance(diff, sp.MatrixBase):
        return all(is_numerically_zero(entry) for entry in diff)
    if diff == 0:
        return True
    if diff.free_symbols:
        return _sampled_zero(diff, _NUM_ZERO_TOL) is True
    try:
        return abs(complex(diff.evalf())) < _NUM_ZERO_TOL
    except (TypeError, ValueError):
        return False


def equation_identity(expr: sp.Equality) -> dict[str, Any]:
    """Whether an operation's equation input is an identity, with its difference.

    Three-state: ``True`` when the difference reduces to zero, ``False`` when
    rational substitution confirms it is nonzero, ``None`` (``UNKNOWN``) when
    it neither reduces nor is falsified — unproven, not false (task-17).
    """
    diff = sp.simplify(evaluate_pending(expr.lhs) - evaluate_pending(expr.rhs))
    result: dict[str, Any] = {"difference": str(diff)}
    if is_numerically_zero(diff):
        result["is_identity"] = True
        result["verdict"] = "TRUE"
        return result
    numeric = numeric_residual_verdict(diff)
    result["is_identity"] = False if numeric is True else None
    result["verdict"] = "FALSE" if numeric is True else "UNKNOWN"
    if numeric is True:
        result["numeric_evidence"] = "difference is clearly nonzero at tested points"
    elif numeric is False:
        result["numeric_evidence"] = "numerically consistent with zero at tested points"
    else:
        result["numeric_evidence"] = "numeric residual test could not run"
    return result


def _reduce_identity_difference(diff: sp.Basic) -> sp.Basic:
    """Reduce an identity residual, adding trig expansions plain ``simplify`` misses.

    ``simplify(cos(6*x) - (32*cos(x)**6 - ...))`` does not expand ``cos(6*x)``,
    so a true identity looked nonzero (task-17 step 15).  ``expand(..., trig=True)``
    and ``trigsimp`` are tried once each; the first that reaches zero is returned.
    """
    for candidate in (sp.expand(diff, trig=True), sp.trigsimp(diff)):
        reduced = sp.simplify(candidate)
        if is_numerically_zero(reduced):
            return reduced
    return diff


def recorded_step_verdict(expr: sp.Basic | None) -> tuple[VerificationStatus, str]:
    """Status and message for a manually recorded (CUSTOM) step's output.

    A recorded ``Eq(a, b)`` is content-checked on ``a - b``: zero verifies,
    rational-substitution-nonzero fails (disproven), anything else stays
    inconclusive — unproven, not disproven.  A trig-aware reduction runs first
    (task-17).  Non-equation outputs keep their truth-value verdict or the
    historical "no automatic verification" verdict.
    """
    if isinstance(expr, sp.Equality):
        diff = _reduce_identity_difference(
            sp.simplify(evaluate_pending(expr.lhs) - evaluate_pending(expr.rhs))
        )
        if is_numerically_zero(diff):
            return VerificationStatus.VERIFIED, "Identity verified: both sides are equal"
        if not diff.free_symbols:
            return VerificationStatus.FAILED, f"Equation is false: the sides differ by {diff}"
        if numeric_residual_verdict(diff) is True:
            return (
                VerificationStatus.FAILED,
                f"Recorded equation is not an identity: the sides differ by {diff}, "
                "and the difference is nonzero at tested points (disproven).",
            )
        return (
            VerificationStatus.INCONCLUSIVE,
            f"Recorded equation is not verified: the sides differ by {diff}, and the "
            "difference neither reduced to zero nor was falsified numerically — unproven, "
            "not disproven. If this step records a definition or model equation rather than "
            "a derived identity, say so in notes/limitations.",
        )
    if isinstance(expr, (BooleanTrue, BooleanFalse, bool)):
        if bool(expr):
            return VerificationStatus.VERIFIED, "Identity verified: both sides are equal"
        return VerificationStatus.FAILED, "Equation is false: the two sides are not equal"
    return (
        VerificationStatus.INCONCLUSIVE,
        "Custom step: no automatic verification available",
    )


def symbol_names(expr: sp.Basic) -> set[str]:
    """Names of free symbols plus applied-function names (``V(t)`` → ``V``)."""
    from sympy.core.function import AppliedUndef

    names = {str(s) for s in expr.free_symbols}
    names.update(str(f.func) for f in expr.atoms(AppliedUndef))
    return names


def extract_variable_from_command(command: str, operation: str) -> str | None:
    """Extract the operation variable from ``sympy_command``."""
    if operation == "differentiate":
        match = re.search(r"diff\(expr,\s*(\w+)(?:,\s*\d+)?\)", command)
        return match.group(1) if match else None
    if operation == "integrate":
        match = re.search(r"integrate\(expr,\s*(?:\(\s*)?(\w+)", command)
        if match is None or match.group(1) == "None":
            # The wrapper records an omitted variable as the placeholder
            # ``None``; that is not a symbol name (r16 task-06 step 33).
            return None
        return match.group(1)
    return None


def extract_order_from_command(command: str) -> int:
    """The differentiation order in ``diff(expr, x, 2)``; 1 when omitted."""
    match = re.search(r"diff\(expr,\s*\w+\s*,\s*(\d+)\s*\)", command)
    return int(match.group(1)) if match else 1


_NUMERIC_SAMPLES = (
    sp.Integer(2),
    sp.Integer(3),
    sp.Integer(5),
    sp.Integer(-2),
    sp.Integer(7),
    sp.Integer(-3),
    sp.Rational(1, 2),
    sp.Rational(-1, 2),
)


def _sample_value(symbol: sp.Symbol, index: int) -> sp.Basic | None:
    """A sample value compatible with ``symbol``'s assumptions, or None."""
    for offset in range(len(_NUMERIC_SAMPLES)):
        value = _NUMERIC_SAMPLES[(index + offset) % len(_NUMERIC_SAMPLES)]
        if symbol.is_positive and value <= 0:
            continue
        if symbol.is_negative and value >= 0:
            continue
        if symbol.is_nonnegative and value < 0:
            continue
        if symbol.is_nonpositive and value > 0:
            continue
        return value
    return None


def _sampled_zero(diff: sp.Basic, tol: float) -> bool | None:
    """Joint-sample a symbol-bearing residual; ``None`` when uncertifiable.

    A residual that simplification cannot reduce may still be float-path noise
    (a one-ULP exponent drift, 2026-09-14 turbine round).  All assumption-
    compatible joint samples under ``tol`` certify zero; one nonzero refutes.
    """
    if diff.has(sp.Derivative, sp.Integral, sp.Sum):
        # Unevaluated operators cannot be meaningfully sampled (task-19).
        return None
    symbols = [
        s
        for s in sorted(diff.free_symbols, key=str)
        if s.name not in ("E", "I") and s.is_extended_real is not False
    ]
    if not symbols or len(symbols) > 3:
        return None
    for trial in range(5 if len(symbols) == 1 else 4):
        substitution: dict[sp.Symbol, sp.Basic] = {}
        for index, symbol in enumerate(symbols):
            value = _sample_value(symbol, trial + index)
            if value is None:
                break
            substitution[symbol] = value
        if len(substitution) != len(symbols):
            return None
        candidate = diff.subs(substitution)
        if candidate.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
            return None
        try:
            evaluated = complex(candidate.evalf())
        except (TypeError, ValueError):
            return None
        if abs(evaluated) >= tol:
            return False
    return True


def numeric_residual_verdict(residual: sp.Basic) -> bool | None:
    """Substitute rationals into ``residual`` to test an asserted identity.

    Returns ``True`` when a well-defined sample is clearly nonzero (numerically
    falsified), ``False`` when at least two samples land within tolerance of
    zero, ``None`` when the test cannot run — a ``None`` is never "false".  An
    unevaluated aggregate (``Sum``/``Integral``) always returns ``None``: its
    bound variable cannot be sampled (task-19).
    """
    if residual.has(sp.Sum, sp.Integral):
        return None
    if residual.is_number:
        try:
            return abs(complex(residual.evalf(20))) > 1e-10
        except (TypeError, ValueError):
            return None
    symbols = [
        s
        for s in sorted(residual.free_symbols, key=str)
        # ``E``/``I`` are parser-protected variable names that also denote
        # constants; substituting a rational for them is not reliable.
        if s.name not in ("E", "I") and s.is_extended_real is not False
    ]
    if not symbols:
        return None
    samples: list[float] = []
    for trial in range(4):
        substitution: dict[sp.Symbol, sp.Basic] = {}
        for index, symbol in enumerate(symbols):
            value = _sample_value(symbol, trial + index)
            if value is None:
                break
            substitution[symbol] = value
        if len(substitution) != len(symbols):
            continue
        candidate = residual.subs(substitution)
        if candidate.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
            continue
        try:
            evaluated = complex(sp.N(candidate, 20))
        except (TypeError, ValueError):
            continue
        if abs(evaluated.imag) > 1e-12 * max(1.0, abs(evaluated.real)):
            continue
        samples.append(evaluated.real)
        if abs(evaluated.real) > 1e-10 * max(1.0, abs(evaluated.real)):
            return True
    return False if len(samples) >= 2 else None


def matching_variable(name: str, *expressions: sp.Basic) -> sp.Symbol:
    """The symbol named ``name`` as it occurs in ``expressions``.

    Verification must differentiate/integrate with respect to the *same* symbol
    object the archived expression carries.  A bare ``sp.Symbol(name)`` is a
    different object once assumptions apply, so the derivative silently becomes
    zero (task-09: ``d/dV log(V)`` reported as ``0``).
    """
    for expression in expressions:
        for symbol in expression.free_symbols:
            if str(symbol) == name:
                return symbol
    return sp.Symbol(name)


def reverse_integration_operands(
    input_expr: sp.Basic, output_expr: sp.Basic, command: str
) -> tuple[sp.Symbol, sp.Basic] | None:
    """Resolve ``(variable, expected integrand)`` for reverse differentiation.

    An inert indefinite ``Integral(f, x)`` input (the engine evaluated it into
    the antiderivative) is checked against its integrand ``f``, not the wrapper.
    An omitted command variable (``integrate(expr, None)``) falls back to the
    engine's default, inferred from the expression when unambiguous (r16
    task-06 step 33: a correct erfi antiderivative was FAILED against its own
    ``Integral`` wrapper).  ``None`` means the variable could not be resolved.
    """
    if (
        isinstance(input_expr, sp.Integral)
        and len(input_expr.limits) == 1
        and len(input_expr.limits[0]) == 1
    ):
        var_name: str | None = str(input_expr.limits[0][0])
        expected: sp.Basic = input_expr.function
    else:
        var_name = extract_variable_from_command(command, "integrate")
        expected = input_expr
    if var_name is None:
        names = {
            str(s)
            for s in (input_expr.free_symbols | output_expr.free_symbols)
        }
        if len(names) == 1:
            var_name = next(iter(names))
        elif "x" in names:
            var_name = "x"
    if var_name is None:
        return None
    return matching_variable(var_name, input_expr, output_expr), expected


def classify_suspect_identity(
    residual: sp.Basic, *, asserted: bool = False
) -> tuple[str, str]:
    """Grade a nonzero identity residual: numerically false vs merely unproven.

    Returns ``(kind, phrase)``.  A plain operator step over a difference form
    (``A - B``) never *asserts* an identity — the user may simply be asking for
    a simplification — so it is never graded ``"numeric"``/FALSE, only
    ``"unreduced"``.  Only an explicit equation assertion (``asserted=True``)
    may be confirmed false by rational substitution, and its wording says so.
    """
    numeric = numeric_residual_verdict(residual)
    if asserted and numeric is True:
        return (
            "numeric",
            "the recorded difference is numerically nonzero, so the asserted "
            "identity is FALSE (confirmed by numeric substitution)",
        )
    if numeric is True:
        return (
            "unreduced",
            "the difference did not reduce to zero (simplifier limitation); it is "
            "numerically nonzero at tested points, but an operator step over a plain "
            "expression does not assert an identity — record it as an equation for a "
            "definitive true/false verdict",
        )
    return (
        "unreduced",
        "the difference did not reduce to zero (simplifier limitation); identity "
        "unproven, not disproven — record it as an equation for a definitive "
        "true/false verdict",
    )


def boolean_equation_verdict(
    operation: str, expr: sp.Equality
) -> tuple[VerificationStatus, str, dict[str, Any]]:
    """Verdict for an operator that collapsed an asserted equation to a boolean.

    Symbolically zero verifies the identity.  A residual that rational
    substitution confirms nonzero is an *asserted* identity that does not hold,
    so the step FAILS and carries ``suspect_identity: "numeric"`` — status and
    wording agree (task-17).  Anything else stays INCONCLUSIVE, since the
    verifier cannot see the assumptions that made the operator return ``True``.
    """
    diff = sp.simplify(expr.lhs - expr.rhs)
    if is_numerically_zero(diff):
        return (
            VerificationStatus.VERIFIED,
            f"{operation.capitalize()} verified: expression is an identity",
            {},
        )
    if numeric_residual_verdict(diff) is True:
        kind, phrase = classify_suspect_identity(diff, asserted=True)
        return (
            VerificationStatus.FAILED,
            f"{operation.capitalize()} failed: {phrase}",
            {"suspect_identity": kind},
        )
    return (
        VerificationStatus.INCONCLUSIVE,
        f"{operation} returned True; the identity holds under assumptions the "
        "verifier cannot confirm",
        {},
    )


def residual_verdict(residual: sp.Basic) -> VerificationStatus:
    """VERIFIED when substitution says zero, FAILED when nonzero, else INCONCLUSIVE."""
    verdict = numeric_residual_verdict(residual)
    if verdict is False:
        return VerificationStatus.VERIFIED
    if verdict is True:
        return VerificationStatus.FAILED
    return VerificationStatus.INCONCLUSIVE


def definite_integral_variables(expr: sp.Basic) -> set[sp.Symbol]:
    """Bound variables of ``Integral`` nodes that carry explicit limits.

    An indefinite integral has a single-element limit tuple ``(x,)``; a
    definite one has ``(x, lo, hi)``.  Only the latter need the numeric path in
    :meth:`StepVerifier._verify_integration`: reverse differentiation is invalid
    there because a definite integral does not depend on its bound variable.
    """
    variables: set[sp.Symbol] = set()
    for integral in expr.atoms(sp.Integral):
        for limit in integral.limits:
            if len(limit) >= 3:
                variables.add(limit[0])
    return variables


def numeric_integral_verdict(input_expr: sp.Basic, output_expr: sp.Basic) -> tuple[
    VerificationStatus, str
]:
    """Recompute a definite integral and compare numerically with the stated value.

    A disagreement stays INCONCLUSIVE, never FAILED (quadrature probes can
    mislead).  The recomputation evaluates unevaluated ``Integral`` nodes first,
    because ``sp.N`` leaves a nested symbolic-bound integral inert (task-06).
    """
    try:
        expected = complex(sp.N(evaluate_pending(input_expr), 20))
        actual = complex(sp.N(output_expr, 20))
    except (TypeError, ValueError, NotImplementedError, OverflowError):
        return VerificationStatus.INCONCLUSIVE, "Numeric quadrature not possible"
    if expected != expected or actual != actual:  # NaN: comparison undefined
        return VerificationStatus.INCONCLUSIVE, "Numeric quadrature not possible"
    tol = 1e-6 * max(1.0, abs(expected))
    if abs(expected - actual) < tol:
        return VerificationStatus.VERIFIED, "Definite integral verified by numeric quadrature"
    return (
        VerificationStatus.INCONCLUSIVE,
        "Numeric quadrature disagrees with the stated definite-integral result",
    )


def _suspect_details(step: DerivationStep) -> dict[str, Any]:
    if not step.verification_result:
        return {}
    try:
        payload = json.loads(step.verification_result)
    except (TypeError, ValueError):
        return {}
    details = payload.get("details", {})
    return {str(key): value for key, value in details.items()} if isinstance(details, dict) else {}


def suspect_identity_steps(steps: Sequence[DerivationStep]) -> list[int]:
    """Step numbers whose archive flags a false or unreduced identity."""
    return [step.step_number for step in steps if _suspect_details(step).get("suspect_identity")]


def suspect_identity_warning(flagged: Sequence[int]) -> str:
    """One-line disclosure for a session carrying unreduced differences."""
    return (
        f"{len(flagged)} step(s) record a difference that did not reduce to zero; "
        "see suspect_identity_steps"
    )


def candidate_names(expr: sp.Basic, names: set[str]) -> set[str]:
    """Candidate name set extended with the Equality lhs (string form)."""
    if isinstance(expr, sp.Equality):
        names = names | {str(expr.lhs)}
    return names


def _step_failed(step: DerivationStep) -> bool:
    """Whether a step's archived verification verdict is FAILED."""
    if not step.verification_result:
        return False
    try:
        payload = json.loads(step.verification_result)
    except (TypeError, ValueError):
        return False
    return bool(payload.get("status") == VerificationStatus.FAILED.value)


def select_headline(steps: Sequence[DerivationStep]) -> tuple[str | None, bool]:
    """Last non-failed step output, and whether failed steps were skipped.

    Walks backwards past failed steps and empty steps; a symbolic output is
    preferred over a trailing numeric probe, the most recent non-failed output
    is the fallback.  Returns ``(None, ...)`` when every step failed.
    """
    skipped_failed = False
    fallback: str | None = None
    for step in reversed(steps):
        if _step_failed(step):
            skipped_failed = True
            continue
        if not step.output_expression:
            continue
        expr = safe_load_expression(step.output_expression, step.output_srepr)
        if expr is None:
            continue
        if expr.free_symbols:
            return step.output_expression, skipped_failed
        if fallback is None:
            fallback = step.output_expression
    return fallback, skipped_failed


def headline_fallback(
    current: sp.Basic | None,
    steps: Sequence[DerivationStep],
    failed_steps: Sequence[int],
) -> tuple[sp.Basic | None, dict[str, Any]]:
    """Outcome after skipping failed steps, plus the response fields to report.

    Returns ``(current, {})`` unchanged when no failed step was skipped, so a
    session without a failed step keeps its historical response exactly.
    """
    headline, skipped = select_headline(steps)
    if not skipped or headline is None:
        return current, {}
    expr = safe_load_expression(headline, "")
    if expr is None:
        return current, {}
    number = failed_steps[-1] if failed_steps else "?"
    return expr, {
        "final_expression_skipped_failed": True,
        "note": f"headline result is the last non-failed step; step {number} failed verification",
    }
