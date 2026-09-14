"""Translate SymPy equalities in the rational-algebra fragment to Lean 4 statements."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import sympy as sp

from symkit.domain.lean_types import LeanStatement, UntranslatableError

_IDENT_RE = re.compile(r"^[A-Za-z_α-ωΑ-Ω][A-Za-z0-9_α-ωΑ-Ω']*$")
_SLUG_RE = re.compile(r"[^0-9A-Za-z_]+")


@dataclass(frozen=True)
class _Bindings:
    """Sanitized variable names plus the nonzero facts extracted from assumptions."""

    names: dict[sp.Symbol, str]
    hypotheses: tuple[str, ...]
    covered: frozenset[sp.Symbol]


def translate_equality(
    lhs: sp.Basic,
    rhs: sp.Basic,
    *,
    assumptions: Mapping[str, Mapping[str, bool]] | None = None,
    name: str = "symkit_step",
) -> LeanStatement:
    """Translate ``lhs = rhs`` into a LeanStatement.

    Only the rational-algebra fragment is supported; anything outside it raises
    UntranslatableError with a user-readable reason.
    """
    if isinstance(lhs, sp.Equality) or isinstance(rhs, sp.Equality):
        raise UntranslatableError("equality-to-equality rewrites need linear_combination (v2)")
    target_type = "ℂ" if (lhs.has(sp.I) or rhs.has(sp.I)) else "ℝ"
    lane = "field" if (_needs_field(lhs) or _needs_field(rhs)) else "ring"
    bindings = _bindings(lhs, rhs, assumptions or {}, target_type, lane)

    def render(expr: sp.Basic) -> str:
        return _to_lean(expr, target_type, bindings.names)

    return LeanStatement(
        name,
        target_type,
        tuple(bindings.names.values()),
        bindings.hypotheses,
        render(lhs),
        render(rhs),
        lane,
    )


def clear_denominators(lhs: sp.Basic, rhs: sp.Basic) -> tuple[sp.Basic, sp.Basic]:
    """Return the numerator forms of both sides over a common denominator.

    Used as the field-lane fallback: ``field_simp`` sometimes leaves an
    ``unsolved goals`` state even though the denominator-free polynomial
    identity is provable by ``ring``.  ``together(...).as_numer_denom()[0]``
    keeps the numerator's algebraic structure: a plain expansion can collapse
    a true identity to ``0 = 0``, which certifies nothing visible (r16
    acceptance task-15).
    """
    lhs_num = sp.together(lhs).as_numer_denom()[0]
    rhs_num = sp.together(rhs).as_numer_denom()[0]
    return lhs_num, rhs_num


def _bindings(
    lhs: sp.Basic,
    rhs: sp.Basic,
    assumptions: Mapping[str, Mapping[str, bool]],
    target_type: str,
    lane: str,
) -> _Bindings:
    names = _sanitize_symbols(sorted(lhs.free_symbols | rhs.free_symbols, key=str))
    # A pure ring identity is unconditional over a field: ``x ≠ 0`` and order
    # facts can never be needed, so emitting them would only put an unrelated
    # global assumption into the kernel goal (r16 task-15).
    if lane == "field":
        symbol_facts, covered = _symbol_hypotheses(names, assumptions, target_type)
    else:
        symbol_facts, covered = [], frozenset()
    denominator_facts = _denominator_hypotheses(
        (lhs, rhs), names, covered, target_type, symbol_facts
    )
    return _Bindings(names, (*symbol_facts, *denominator_facts), covered)


def _to_lean(expr: sp.Basic, target_type: str, names: Mapping[sp.Symbol, str]) -> str:
    if expr is sp.I:
        return "Complex.I"
    if isinstance(expr, sp.Symbol):
        return names[expr]
    if isinstance(expr, sp.Integer):
        return f"({expr} : {target_type})"
    if isinstance(expr, sp.Rational):
        return f"(({expr.p} : {target_type}) / ({expr.q} : {target_type}))"
    if isinstance(expr, sp.Float):
        return _float_to_lean(expr, target_type)
    if isinstance(expr, sp.Add):
        return "(" + " + ".join(_to_lean(a, target_type, names) for a in expr.args) + ")"
    if isinstance(expr, sp.Mul):
        return _mul_to_lean(expr, target_type, names)
    if isinstance(expr, sp.Pow):
        return _pow_to_lean(expr, target_type, names)
    raise UntranslatableError(f"unsupported construct: {type(expr).__name__}")


def _float_to_lean(expr: sp.Float, target_type: str) -> str:
    value = float(expr)
    if value.is_integer():
        return f"({int(value)} : {target_type})"
    raise UntranslatableError(f"float literal {expr} (use an exact rational instead)")


def _mul_to_lean(expr: sp.Mul, target_type: str, names: Mapping[sp.Symbol, str]) -> str:
    args = expr.args
    if len(args) == 2 and args[0] == -1:
        return f"(-{_to_lean(args[1], target_type, names)})"
    return "(" + " * ".join(_to_lean(a, target_type, names) for a in args) + ")"


def _pow_to_lean(expr: sp.Pow, target_type: str, names: Mapping[sp.Symbol, str]) -> str:
    exponent = expr.exp
    if not isinstance(exponent, sp.Integer):
        raise UntranslatableError(f"non-integer exponent {exponent}")
    n = int(exponent)
    base = _to_lean(expr.base, target_type, names)
    if n >= 0:
        return f"({base} ^ {n})"
    if n == -1:
        return f"((1 : {target_type}) / {base})"
    return f"((1 : {target_type}) / ({base} ^ {-n}))"


def _sanitize_symbols(symbols: Sequence[sp.Symbol]) -> dict[sp.Symbol, str]:
    """Map symbols to valid, deterministic Lean identifiers (illegal -> sym_N)."""
    names: dict[sp.Symbol, str] = {}
    used: set[str] = set()
    counter = 0
    for symbol in symbols:
        raw = str(symbol)
        if _IDENT_RE.match(raw) and raw not in used:
            candidate = raw
        else:
            counter += 1
            candidate = f"sym_{counter}"
            while candidate in used:
                counter += 1
                candidate = f"sym_{counter}"
        names[symbol] = candidate
        used.add(candidate)
    return names


def _symbol_hypotheses(
    names: Mapping[sp.Symbol, str],
    assumptions: Mapping[str, Mapping[str, bool]],
    target_type: str,
) -> tuple[list[str], frozenset[sp.Symbol]]:
    """Render the session's per-symbol facts as Lean binders.

    ``positive``/``negative`` become the strict inequalities the user asked for
    (they imply nonzero, so such symbols also cover denominators); ``nonzero``
    becomes ``≠ 0``; ``nonnegative`` becomes ``0 ≤ x`` and does *not* by itself
    cover a denominator. Ordered facts are only valid over the reals.
    """
    ordered = target_type == "ℝ"
    rendered: list[str] = []
    covered: set[sp.Symbol] = set()
    for symbol, identifier in names.items():
        facts = assumptions.get(str(symbol), {})
        if facts.get("positive") is True:
            rendered.append(
                f"h_{identifier} : {identifier} > 0"
                if ordered
                else f"h_{identifier} : {identifier} ≠ 0"
            )
            covered.add(symbol)
        elif facts.get("negative") is True:
            rendered.append(
                f"h_{identifier} : {identifier} < 0"
                if ordered
                else f"h_{identifier} : {identifier} ≠ 0"
            )
            covered.add(symbol)
        elif facts.get("nonzero") is True:
            rendered.append(f"h_{identifier} : {identifier} ≠ 0")
            covered.add(symbol)
        if facts.get("nonnegative") is True and facts.get("positive") is not True:
            rendered.append(
                f"h_{identifier}_nonneg : 0 ≤ {identifier}"
                if ordered
                else f"h_{identifier}_nonneg : {identifier} ≠ 0"
            )
    return rendered, frozenset(covered)


def _nonzero_factors(base: sp.Basic) -> list[sp.Basic]:
    """Flatten a denominator base into factors whose nonzeroness is needed."""
    if isinstance(base, sp.Mul):
        factors: list[sp.Basic] = []
        for arg in base.args:
            factors.extend(_nonzero_factors(arg))
        return factors
    if isinstance(base, sp.Pow) and isinstance(base.exp, sp.Integer) and base.exp > 0:
        return [base.base]
    return [base]


def _hyp_identifier(text: str, used: set[str]) -> str:
    """Build a unique, valid Lean binder name from a rendered denominator."""
    slug = _SLUG_RE.sub("_", text).strip("_") or "den"
    if not (slug[0].isalpha() or slug[0] == "_"):
        slug = f"d_{slug}"
    candidate = f"h_{slug}"
    counter = 1
    while candidate in used:
        counter += 1
        candidate = f"h_{slug}_{counter}"
    return candidate


def _denominator_hypotheses(
    exprs: tuple[sp.Basic, ...],
    names: Mapping[sp.Symbol, str],
    covered: frozenset[sp.Symbol],
    target_type: str,
    existing: Sequence[str],
) -> list[str]:
    """Bind every denominator factor nonzero so ``field_simp`` can clear it.

    Symbol factors must already carry a nonzero-ish assumption from the session;
    compound factors (e.g. ``x + 1`` split out of ``1/(x*(x+1))``) earn a
    generated ``≠ 0`` binder. Both the scan order and the generated names are
    sorted so a given statement is always rendered — and any failure reported —
    identically.
    """
    bases: dict[str, sp.Basic] = {}
    for expr in exprs:
        for power in expr.atoms(sp.Pow):
            exponent = power.exp
            if isinstance(exponent, sp.Integer) and exponent.is_negative:
                base = power.base
                if base.free_symbols:
                    bases.setdefault(sp.srepr(base), base)
    used_names = {fact.split(" : ", 1)[0] for fact in existing}
    factors: list[sp.Basic] = []
    for _, base in sorted(bases.items(), key=lambda item: item[0]):
        factors.extend(
            factor for factor in _nonzero_factors(base) if factor.free_symbols
        )
    missing = [f for f in factors if isinstance(f, sp.Symbol) and f not in covered]
    if missing:
        # Name every factor that has no user-supplied nonzero assumption in one
        # pass; reporting only the first made a multi-factor denominator
        # (e.g. x*(x+1)) look like it needed a single assumption (r16 task-15).
        uncovered = [
            factor
            for factor in factors
            if not (isinstance(factor, sp.Symbol) and factor in covered)
        ]
        listed = ", ".join(dict.fromkeys(str(factor) for factor in uncovered))
        raise UntranslatableError(
            f"denominator factors {listed} have no nonzero assumption in this "
            f"statement; call assume(<factor>, nonzero) before certifying"
        )
    rendered: list[str] = []
    for factor in factors:
        if isinstance(factor, sp.Symbol):
            continue  # already carried by its symbol-level assumption
        identifier = _hyp_identifier(str(factor), used_names)
        used_names.add(identifier)
        rendered.append(
            f"{identifier} : {_to_lean(factor, target_type, names)} ≠ 0"
        )
    return rendered


def _needs_field(expr: sp.Basic) -> bool:
    """True when ``expr`` divides by a variable (integer Pow with symbolic base)."""
    for power in expr.atoms(sp.Pow):
        exponent = power.exp
        if (
            isinstance(exponent, sp.Integer)
            and exponent.is_negative
            and power.base.free_symbols
        ):
            return True
    return False
