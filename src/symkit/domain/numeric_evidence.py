"""Numeric evidence helpers: sample-based symbolic-residual predicates.

These helpers decide whether a symbolic residual is *numerically* zero or
nonzero by substituting assumption-compatible rational samples.  They live
apart from :mod:`symkit.domain.final_result` because they are pure predicates
over residuals and because sampling must stay strictly subordinate to exact
symbolic reduction: agreement at sampled points may downgrade an unreduced
residual to ``None``/UNKNOWN, never promote it to a proof of identity.

Doctrine:

* one sample that is *clearly* nonzero refutes (``numeric_residual_verdict``
  returns ``True``);
* at least two samples within tolerance are required before a residual is
  called "consistent with zero" (``False``); fewer is ``None`` (unproven);
* the tolerance scales with the magnitude of the substituted parts, so a
  sample whose terms are astronomically large is treated as ill-conditioned
  and can never manufacture a "clearly nonzero" claim from cancellation junk.
"""

from __future__ import annotations

import sympy as sp

# Numeric residual tolerance for symbolic verification.  Symbolic derivation
# diffs are dimensionless algebraic residuals; machine-precision noise from
# float inputs must not flip a correct step to FAILED.
_NUM_ZERO_TOL = 1e-9

# A sampled residual is refuted only when it is large relative to the scale of
# the substituted parts (below), never by an absolute epsilon alone.
_RESIDUAL_TOL = 1e-10

# Sample evaluation precision: comfortably above the 15-digit float path so
# catastrophic cancellation cannot be mistaken for a nonzero identity.
_SAMPLE_PRECISION = 30

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


def is_numerically_zero(diff: sp.Basic) -> bool:
    """True if ``diff`` is exactly zero, or numerically zero within tolerance.

    Symbolic differences must simplify to exact zero; purely numeric ones are
    compared in floating point with an absolute tolerance of 1e-9; symbol-bearing
    ones are *sampled* before refusal — float-path noise (a one-ULP power
    exponent drift between two evaluation paths, 2026-09-14 turbine round) must
    not flip a correct step.  Matrix-valued differences are checked entrywise:
    ``Matrix == 0`` is not a Python truth value (2026-09-12 black-box round).

    This predicate is about operator fidelity, not identity proof.  Callers that
    must certify an *identity* (``equation_identity``, ``recorded_step_verdict``)
    require an exact zero instead: sampling only ever downgrades.
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


def scaled_numeric_zero(diff: sp.Basic, *references: sp.Basic) -> bool:
    """True when a pure-numeric residual vanishes *relative to operand scale*.

    The absolute 1e-9 floor of :func:`is_numerically_zero` misjudges
    substitutions whose operands are far from 1: substituting float constants
    into ``(G*M*T**2/(4*pi**2))**(1/3)`` lands near 4.2e7, where double-precision
    rounding alone is already ~1e-8 (r22 task-06).  The residual must be below
    ``_NUM_ZERO_TOL * max(1, |references|)``; anything symbolic stays False.
    """
    if diff.free_symbols:
        return False
    try:
        residual = abs(complex(diff.evalf()))
        scale = max([1.0, *(abs(complex(ref.evalf())) for ref in references)])
    except (TypeError, ValueError, AttributeError):
        return False
    return residual <= _NUM_ZERO_TOL * scale


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


def _sample_scale(candidate: sp.Basic) -> float | None:
    """Magnitude of the substituted parts, for a relative/conditioning tolerance.

    The cancellation error of a sample is bounded by the size of the terms that
    cancel; a residual of ``1e40*sin(x)**2 + 1e40*cos(x)**2 - 1e40`` at an
    integer sample is meaningful only down to roughly ``1e40 * 10**-precision``.
    Returns ``None`` when a part is non-finite, so the sample is discarded.
    """
    scale = 1.0
    for term in sp.Add.make_args(candidate):
        try:
            magnitude = abs(complex(sp.N(term, _SAMPLE_PRECISION)))
        except (TypeError, ValueError, NotImplementedError, OverflowError, RecursionError):
            return None
        if magnitude != magnitude or magnitude == float("inf"):
            return None
        scale += magnitude
    return scale


def numeric_residual_verdict(residual: sp.Basic) -> bool | None:
    """Substitute rationals into ``residual`` to test an asserted identity.

    Returns ``True`` when a well-defined sample is clearly nonzero *relative to
    the scale of its terms* (numerically falsified), ``False`` when at least two
    samples land within tolerance of zero, ``None`` when the test cannot run — a
    ``None`` is never "false".  An unevaluated aggregate (``Sum``/``Integral``)
    always returns ``None``: its bound variable cannot be sampled (task-19).
    """
    if residual.has(sp.Sum, sp.Integral):
        return None
    if residual.is_number:
        try:
            return abs(complex(residual.evalf(_SAMPLE_PRECISION))) > _RESIDUAL_TOL
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
    accepted = 0
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
        scale = _sample_scale(candidate)
        if scale is None:
            continue
        try:
            evaluated = complex(sp.N(candidate, _SAMPLE_PRECISION))
        except (
            TypeError,
            ValueError,
            NotImplementedError,
            OverflowError,
            RecursionError,
        ):
            continue
        if evaluated.real != evaluated.real or evaluated.imag != evaluated.imag:
            continue
        if abs(evaluated.imag) > 1e-12 * scale:
            continue
        accepted += 1
        if abs(evaluated.real) > _RESIDUAL_TOL * scale:
            return True
    return False if accepted >= 2 else None
