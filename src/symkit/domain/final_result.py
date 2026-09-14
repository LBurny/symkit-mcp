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

    A ``simplify`` step whose input is an unevaluated derivative is correct when
    the output is that derivative's value, but ``simplify`` does not reduce the
    difference to zero: SymPy evaluates the ``Derivative`` and then fails to
    apply the trig identity to what is left, so an identically zero residual was
    reported as a changed value and the whole chain became ``failed``
    (task-15 step 12).  ``doit()`` first, and the difference collapses to 0.

    A ``Subs`` node is exempt: ``doit()`` on ``Mul(c**2, Subs(Derivative(
    f(xi), (xi, 2)), xi, x - c*t))`` drops the substitution binding and
    returns the bare ``Derivative(f(xi), (xi, 2))`` (SymPy 1.14).  A ``Subs``
    is already the evaluated result form, so re-evaluating it fabricated a
    phantom difference between mathematically identical expressions and FAILED
    correct chain-rule steps (task-08 steps 8/9).  Because the two
    independently computed bindings carry different anonymous dummies, the
    surviving ``Subs`` forms are then canonicalised with
    :func:`canonicalize_dummies` so the equality check can cancel them.
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

    Two mathematically identical ``Subs`` bindings produced independently (one
    by ``Derivative(...).doit()``, the other loaded from ``srepr``) use
    different anonymous dummies, and SymPy 1.14 does not cancel them in a
    difference.  Mapping same-named dummies to a shared dummy whose index is a
    pure function of the name makes the forms compare equal without changing the
    mathematics.
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
    compared in floating point with an absolute tolerance of 1e-9.  Matrix-valued
    differences are checked entrywise: ``Matrix == 0`` is not a Python truth
    value and ``complex(matrix.evalf())`` raises, so a zero-matrix difference was
    reported as changing the expression (2026-09-12 black-box round).  Symbolic
    matrix expressions are expanded first, which also absorbs a stray
    ``Identity`` term.
    """
    if isinstance(diff, sp.MatrixExpr) and not isinstance(diff, sp.MatrixBase):
        diff = diff.as_explicit()
    if isinstance(diff, sp.MatrixBase):
        return all(is_numerically_zero(entry) for entry in diff)
    if diff == 0:
        return True
    if diff.free_symbols:
        return False
    try:
        return abs(complex(diff.evalf())) < _NUM_ZERO_TOL
    except (TypeError, ValueError):
        return False


def equation_identity(expr: sp.Equality) -> dict[str, Any]:
    """Whether an operation's equation input is an identity, with its difference."""
    diff = sp.simplify(evaluate_pending(expr.lhs) - evaluate_pending(expr.rhs))
    return {"is_identity": is_numerically_zero(diff), "difference": str(diff)}


def recorded_step_verdict(expr: sp.Basic | None) -> tuple[VerificationStatus, str]:
    """Status and message for a manually recorded (CUSTOM) step's output.

    A recorded ``Eq(a, b)`` is content-checked on ``a - b``: identically zero
    verifies the identity, a nonzero numeric difference fails it, and a symbolic
    difference stays inconclusive — a model equation or definition is an axiom,
    not a derived identity.  Outputs that are not equations (or that already
    collapsed to a boolean) keep a verdict derived from their truth value, and
    anything else keeps the historical "no automatic verification" verdict.
    """
    if isinstance(expr, sp.Equality):
        diff = sp.simplify(evaluate_pending(expr.lhs) - evaluate_pending(expr.rhs))
        if is_numerically_zero(diff):
            return VerificationStatus.VERIFIED, "Identity verified: both sides are equal"
        if not diff.free_symbols:
            return VerificationStatus.FAILED, f"Equation is false: the sides differ by {diff}"
        return (
            VerificationStatus.INCONCLUSIVE,
            f"Recorded equation is not an identity: the sides differ by {diff}. "
            "If this step records a definition or model equation rather than a "
            "derived identity, say so in notes/limitations; derived equalities "
            "must simplify to zero.",
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


def is_difference_form(expr: sp.Basic | None) -> bool:
    """True when ``expr`` negates a symbol-bearing, non-atomic term.

    A negated bare symbol (``-E``) or purely numeric term (``-1*(-3)**2``) is
    ordinary arithmetic, not an asserted identity ``A - B = 0``.
    """
    if not isinstance(expr, sp.Add):
        return False
    for term in expr.args:
        if isinstance(term, sp.Mul):
            coeff, rest = term.as_coeff_Mul()
            if coeff == -1 and not isinstance(rest, sp.Atom) and rest.free_symbols:
                return True
    return False


def extract_variable_from_command(command: str, operation: str) -> str | None:
    """Extract the operation variable from ``sympy_command``."""
    if operation == "differentiate":
        match = re.search(r"diff\(expr,\s*(\w+)(?:,\s*\d+)?\)", command)
        return match.group(1) if match else None
    if operation == "integrate":
        match = re.search(r"integrate\(expr,\s*(?:\(\s*)?(\w+)", command)
        return match.group(1) if match else None
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


def numeric_residual_verdict(residual: sp.Basic) -> bool | None:
    """Substitute rationals into ``residual`` to test an asserted identity.

    Returns ``True`` when a well-defined sample is clearly nonzero (the identity
    is numerically falsified), ``False`` when at least two samples land within
    tolerance of zero, and ``None`` when the test cannot run (no samplable free
    symbols, undefined functions such as ``f(2)``, singular substitutions, or
    too few valid samples).  A ``None`` must never be reported as "false".
    """
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


def classify_suspect_identity(residual: sp.Basic) -> tuple[str, str]:
    """Grade a nonzero identity residual: numerically false vs merely unproven.

    Returns ``(kind, phrase)`` where ``kind`` is ``"numeric"`` when rational
    substitution makes the residual clearly nonzero, and ``"unreduced"`` when
    the difference never reduced but substitution is unavailable or lands on
    zero — an unreduced difference is *not* a false identity.
    """
    if numeric_residual_verdict(residual) is True:
        return (
            "numeric",
            "the recorded difference is numerically nonzero, so the asserted "
            "identity is FALSE (confirmed by numeric substitution)",
        )
    return (
        "unreduced",
        "the difference did not reduce to zero (simplifier limitation); "
        "identity unproven, not disproven",
    )


def residual_verdict(residual: sp.Basic) -> VerificationStatus:
    """VERIFIED when substitution says zero, FAILED when nonzero, else INCONCLUSIVE."""
    verdict = numeric_residual_verdict(residual)
    if verdict is False:
        return VerificationStatus.VERIFIED
    if verdict is True:
        return VerificationStatus.FAILED
    return VerificationStatus.INCONCLUSIVE


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
    """One-line disclosure for a session carrying suspect identities."""
    return (
        f"{len(flagged)} step(s) assert identities that do not hold or did not "
        "reduce; see suspect_identity_steps"
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

    Walks the chain backwards past failed steps (and steps that carry no
    output, such as notes).  A symbolic output is preferred over a trailing
    numeric probe so the headline stays the derivation's symbolic conclusion;
    the most recent non-failed output is the fallback when nothing symbolic
    survives.  Returns ``(None, ...)`` when every step failed.
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
