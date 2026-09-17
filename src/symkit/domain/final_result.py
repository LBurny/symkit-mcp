"""Interpretation of a derivation's headline result and recorded equations.

Pure domain helpers shared by :mod:`symkit.domain.derivation_session` and
:mod:`symkit.domain.step_verifier`: headline selection, content-checking of a
hand-recorded ``Eq(a, b)``, identity reporting, numeric-residual predicates and
definite-integral verdicts.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import sympy as sp
from sympy.logic.boolalg import BooleanFalse, BooleanTrue

from symkit.domain.expr_io import safe_load_expression
from symkit.domain.numeric_evidence import (
    is_numerically_zero as is_numerically_zero,
)
from symkit.domain.numeric_evidence import numeric_residual_verdict
from symkit.domain.numeric_evidence import (
    scaled_numeric_zero as scaled_numeric_zero,
)
from symkit.domain.recorded_claim import numeric_difference_verdict
from symkit.domain.value_objects import VerificationStatus
from symkit.domain.verifier_heuristics import (
    bare_symbol_definition,
    matrix_equality,
    mixed_matrix_verdict,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from symkit.domain.derivation_session import DerivationStep


def evaluate_pending(expr: sp.Basic) -> sp.Basic:
    """Evaluate unevaluated operations (``Derivative``/``Integral``/``Sum``).

    ``doit()`` runs first (task-15 step 12).  A ``Subs`` node is exempt —
    ``doit()`` drops its binding and fabricates a phantom difference (task-08) —
    so surviving ``Subs`` forms are canonicalised with :func:`canonicalize_dummies`.
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

    Independently built identical ``Subs`` bindings carry different anonymous
    dummies that SymPy 1.14 does not cancel; a shared index compares equal.
    """
    mapping = {
        dummy: sp.Dummy(dummy.name, dummy_index=_dummy_index_for(dummy.name))
        for dummy in expr.atoms(sp.Dummy)
    }
    return expr.xreplace(mapping) if mapping else expr


def _dummy_index_for(name: str) -> int:
    """Stable per-name dummy index (process-independent)."""
    return int.from_bytes(name.encode("utf-8"), "big") % (2**31 - 1)


def equations_equivalent(left_diff: sp.Basic, right_diff: sp.Basic) -> bool:
    """Whether two equations differ only by a nonzero constant factor.

    ``sympy.simplify`` normalizes an equation by dividing by its leading
    coefficient (``Eq(2*x, 3*x)`` -> ``Eq(x, 0)``, sign flipped); exact
    comparison called the tool's own output a failed step (r17 audit5).
    """
    if right_diff == 0 or left_diff == 0:
        return bool(sp.simplify(left_diff) == 0 and sp.simplify(right_diff) == 0)
    ratio = sp.simplify(left_diff / right_diff)
    return bool(ratio.is_number and ratio.is_finite and ratio != 0)


def equation_identity(expr: sp.Equality) -> dict[str, Any]:
    """Whether an operation's equation input is an identity, with its difference.

    Three-state: ``True`` on an *exact* reduced zero, ``False`` when rational
    substitution confirms nonzero, ``None`` (``UNKNOWN``) otherwise — unproven,
    not false (task-17).  Sampling never certifies an identity (r18): agreement
    at sample points stays ``UNKNOWN``, because branch-cut identities such as
    ``sqrt(a*b) == sqrt(a)*sqrt(b)`` hold on the positive reals yet fail for
    complex ``a``, ``b``.
    """
    diff = _reduce_identity_difference(
        sp.simplify(evaluate_pending(expr.lhs) - evaluate_pending(expr.rhs))
    )
    result: dict[str, Any] = {"difference": str(diff)}
    if diff == 0:
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

    ``simplify`` does not expand ``cos(6*x)``, so a true identity looked nonzero
    (task-17 step 15).  ``expand(..., trig=True)``/``trigsimp`` are tried once
    each; only an *exact* zero is returned — a candidate that merely samples to
    zero cannot promote the residual (r18).
    """
    for candidate in (sp.expand(diff, trig=True), sp.trigsimp(diff)):
        reduced = sp.simplify(candidate)
        if reduced == 0:
            return reduced
    return diff


_DERIVATIVE_VACUOUS_MESSAGE = (
    "Recorded equation is not verified: its derivative terms evaluate to zero on plain symbols"
    " (no functional dependence declared), so both sides collapse to 0 and the identity check"
    " is vacuous — unverified, not verified. Declare fields as functions of their variables (e.g."
    " u_t_i(t, x_i)) or record the equation's meaning in notes."
)

_DEFINITION_NOT_IDENTITY_MESSAGE = (
    "Recorded equation is not verified: {shape}, so this reads as a definition or naming"
    " convention, which is not checkable as an identity. The sides nevertheless differ by"
    " {diff} at tested points. Record a definition as its right-hand expression or in"
    " notes; a derived identity needs sides that share symbols."
)

def _definition_shape(expr: sp.Equality) -> str | None:
    """Definitional-closure wording, or ``None`` for an identity claim.

    A definitional closure names a new quantity the left side lacks: the
    bare-name case ``E_t == e_t + ...`` or the compound case
    ``rho_b*u_t_i == rho_b*u_b_i + m_i`` (task-07), where the RHS introduces
    unknowns the LHS does not carry.
    """
    lhs_symbols = {str(s) for s in expr.lhs.free_symbols}
    introduced = sorted(str(s) for s in expr.rhs.free_symbols if str(s) not in lhs_symbols)
    if introduced:
        return f"the right side introduces {', '.join(introduced)}, absent from the left"
    if isinstance(expr.lhs, sp.Symbol) and str(expr.lhs) not in lhs_symbols:
        return "the left side is a name absent from the right"
    return None


def recorded_step_verdict(expr: sp.Basic | None) -> tuple[VerificationStatus, str]:
    """Status and message for a manually recorded (CUSTOM) step's output.

    A recorded ``Eq(a, b)`` is content-checked on ``a - b``: an *exact* zero
    verifies, rational-substitution-nonzero fails (disproven), anything else
    stays inconclusive — unproven, not disproven.  Sampling never certifies a
    recorded identity (r18).  Exempt from the falsification branches, because
    there the check cannot mean anything: a definitional closure (the RHS names
    a symbol the LHS lacks), a derivative equation whose terms collapse to zero,
    and a zero-free-symbol difference that is an unevaluated application.
    """
    if isinstance(expr, sp.Equality):
        matrix = matrix_equality(expr.lhs, expr.rhs) or mixed_matrix_verdict(expr)
        if matrix is not None:
            return matrix
        lhs_eval = evaluate_pending(expr.lhs)
        rhs_eval = evaluate_pending(expr.rhs)
        if (
            (expr.lhs.has(sp.Derivative) or expr.rhs.has(sp.Derivative))
            and lhs_eval == 0
            and rhs_eval == 0
        ):
            return VerificationStatus.INCONCLUSIVE, _DERIVATIVE_VACUOUS_MESSAGE
        diff = _reduce_identity_difference(sp.simplify(lhs_eval - rhs_eval))
        if diff == 0:
            return VerificationStatus.VERIFIED, "Identity verified: both sides are equal"
        if not diff.free_symbols:
            return numeric_difference_verdict(diff)
        shape = _definition_shape(expr)
        if shape is not None:
            return (
                VerificationStatus.INCONCLUSIVE,
                _DEFINITION_NOT_IDENTITY_MESSAGE.format(shape=shape, diff=diff),
            )
        definition = bare_symbol_definition(expr, diff)
        if definition is not None:
            return VerificationStatus.INCONCLUSIVE, definition
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


def matching_variable(name: str, *expressions: sp.Basic) -> sp.Symbol:
    """The symbol named ``name`` as it occurs in ``expressions``.

    Verification must use the *same* symbol object the archive carries: a bare
    ``sp.Symbol(name)`` differs once assumptions apply, silently zeroing the
    derivative (task-09: ``d/dV log(V)`` reported as ``0``).
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

    An inert indefinite ``Integral(f, x)`` input is checked against its
    integrand ``f``, not the wrapper.  An omitted command variable
    (``integrate(expr, None)``) falls back to the engine's default when
    unambiguous (r16 task-06 step 33).  ``None`` means unresolvable.
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


def _unreduced_phrase(residual: sp.Basic) -> str:
    """Honest wording for a nonzero residual in a non-asserted operator step.

    The referent is named explicitly — *the input's* form ``A - B`` — because the
    old text said only "the difference", which could read as a tool-invented
    residual (r19 F1).  A constant residual was decided by exact arithmetic and
    is reported by value; claiming sampling for it invented evidence (r18 audit5).
    """
    if residual.free_symbols:
        return (
            "the input has the form A - B and its value did not reduce to zero (it "
            "is numerically nonzero at tested points); an operator step does not "
            "assert the identity A = B — record it as an equation for a definitive "
            "true/false verdict"
        )
    return (
        f"the input has the form A - B and its value did not reduce to zero; it "
        f"evaluates to the exact value {residual} (no sampling needed), and an "
        "operator step does not assert the identity A = B — record it as an "
        "equation for a definitive true/false verdict"
    )


def classify_suspect_identity(
    residual: sp.Basic, *, asserted: bool = False
) -> tuple[str, str]:
    """Grade a nonzero identity residual: numerically false vs merely unproven.

    Returns ``(kind, phrase)``.  A plain operator step over ``A - B`` never
    *asserts* an identity, so it is never graded ``"numeric"``/FALSE, only
    ``"unreduced"``.  Only an explicit assertion (``asserted=True``) may be
    confirmed false by rational substitution, and its wording says so.
    """
    numeric = numeric_residual_verdict(residual)
    if asserted and numeric is True:
        return (
            "numeric",
            "the recorded difference is numerically nonzero, so the asserted "
            "identity is FALSE (confirmed by numeric substitution)",
        )
    if numeric is True:
        return ("unreduced", _unreduced_phrase(residual))
    return (
        "unreduced",
        "the input has the form A - B; the difference did not reduce to zero "
        "(simplifier limitation) — identity unproven, not disproven — record it "
        "as an equation for a definitive true/false verdict",
    )


def boolean_equation_verdict(
    operation: str, expr: sp.Equality
) -> tuple[VerificationStatus, str, dict[str, Any]]:
    """Verdict for an operator that collapsed an asserted equation to a boolean.

    An *exact* symbolic zero verifies the identity; sampling cannot certify it
    (r18).  A residual that rational substitution confirms nonzero is an
    *asserted* identity that does not hold, so the step FAILS and carries
    ``suspect_identity: "numeric"`` (task-17).  Anything else is INCONCLUSIVE,
    since the verifier cannot see the assumptions behind a ``True`` return.
    """
    diff = sp.simplify(expr.lhs - expr.rhs)
    if diff == 0:
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


def asserted_equation_verdict(
    operation: str, lhs: sp.Basic, rhs: sp.Basic
) -> tuple[VerificationStatus, str, dict[str, Any]]:
    """Verdict for a boolean-collapsed step that archived an explicit equation.

    An operator that collapsed an asserted ``A = B`` to a boolean must be judged
    on the claim, not on the boolean it preserved — a DISPROVEN equation
    otherwise read as a green "boolean value preserved" step (r19 F9).  Runs
    :func:`boolean_equation_verdict` on the recovered claim; two concrete
    matrices are compared directly (r23 F7).
    """
    matrix = matrix_equality(lhs, rhs)
    if matrix is not None:
        status, message = matrix
        if status == VerificationStatus.VERIFIED:
            return (
                status,
                f"{operation.capitalize()} verified: the asserted matrix equation holds",
                {},
            )
        return status, f"{operation.capitalize()} failed: {message}", {}
    status, message, details = boolean_equation_verdict(
        operation, sp.Eq(lhs, rhs, evaluate=False)
    )
    if status == VerificationStatus.VERIFIED:
        return (
            status,
            f"{operation.capitalize()} verified: the asserted equation holds",
            details,
        )
    if status == VerificationStatus.FAILED:
        return (
            status,
            f"{operation.capitalize()} failed: the asserted equation is FALSE "
            f"({lhs} ≠ {rhs}); the difference is numerically nonzero at tested "
            "points",
            details,
        )
    return status, message, details


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

    An indefinite integral has ``(x,)``; a definite one ``(x, lo, hi)``.  Only
    the latter need the numeric path in
    :meth:`StepVerifier._verify_integration`: reverse differentiation is invalid
    because a definite integral does not depend on its bound variable.
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
    mislead).  Unevaluated ``Integral`` nodes are evaluated first, because
    ``sp.N`` leaves a nested symbolic-bound integral inert (task-06).
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
        "Numeric quadrature could not confirm the stated result; oscillatory or "
        "slowly convergent integrands can mislead quadrature",
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
        f"{len(flagged)} step(s) submitted A - B difference forms whose values did "
        "not reduce to zero; see suspect_identity_steps"
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

    Walks backwards past failed and empty steps, preferring a symbolic output
    over a trailing numeric probe.  ``(None, ...)`` when every step failed.
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

    ``(current, {})`` unchanged when no failed step was skipped, so a session
    without a failed step keeps its historical response exactly.
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
