"""Single source of truth for turning symbolic assumptions into SymPy symbols.

Invariant I1: an assumption is a *property of a symbol*, applied after the
syntax tree exists.  Parsing is pure syntax and must never see assumptions —
before this module existed, assumption symbols were injected into the parser's
``local_dict``, which let implicit multiplication rewrite a function call
``k(x)`` into ``k*x`` (run-024).  Nothing here can reintroduce that: after
parsing, a function name is not a free symbol, so :func:`apply_assumptions`
structurally cannot touch it.

Invariant I3: every place that needs an assumption-bearing symbol goes through
:func:`resolve_assumed_symbol`, and every place that applies a whole assumption
mapping to an expression goes through :func:`apply_assumptions`.  The property
whitelist and conflict table live here alone (they used to be duplicated in
``step_verifier`` and ``assumption_engine``).

Pure domain module: depends only on SymPy.
"""

from __future__ import annotations

from collections.abc import Mapping

import sympy as sp

# Symbol properties SymPy accepts as ``Symbol(..., **kwargs)``.
ASSUMPTION_KEYWORDS: frozenset[str] = frozenset({
    "real",
    "imaginary",
    "complex",
    "positive",
    "negative",
    "nonzero",
    "nonpositive",
    "nonnegative",
    "integer",
    "rational",
    "irrational",
    "finite",
    "infinite",
    "odd",
    "even",
    "prime",
    "composite",
    "extended_real",
    "extended_positive",
    "extended_negative",
    "extended_nonpositive",
    "extended_nonnegative",
    "commutative",
    "hermitian",
    "antihermitian",
})

# Property pairs that cannot both hold.  SymPy raises when a Symbol is asked to
# be both; such a symbol is instead built with no assumptions at all, so the
# step still verifies on its algebraic merits (conflicts are reported
# separately by AssumptionEngine.detect_conflicts).
CONFLICT_PAIRS: tuple[tuple[str, str], ...] = (
    ("positive", "negative"),
    ("positive", "zero"),
    ("negative", "zero"),
    ("real", "imaginary"),
    ("integer", "irrational"),
)


def active_properties(props: Mapping[str, bool]) -> set[str]:
    """The properties asserted ``True`` in ``props``."""
    return {name for name, value in props.items() if value}


def has_conflict(props: Mapping[str, bool]) -> bool:
    """True if ``props`` asserts both members of a :data:`CONFLICT_PAIRS` pair."""
    active = active_properties(props)
    return any(a in active and b in active for a, b in CONFLICT_PAIRS)


def symbol_kwargs(props: Mapping[str, bool]) -> dict[str, bool]:
    """SymPy keyword arguments for ``props``.

    Unknown property names are dropped (SymPy would raise) and a conflicting
    set yields no assumptions at all.
    """
    if has_conflict(props):
        return {}
    return {name: value for name, value in props.items() if name in ASSUMPTION_KEYWORDS}


def resolve_assumed_symbol(
    name: str,
    props: Mapping[str, bool] | None = None,
) -> sp.Symbol:
    """Build ``name`` as a Symbol carrying ``props``.

    The single constructor for assumption-bearing symbols.  ``resolve_assumed_symbol(name, p)``
    always returns the same SymPy object for the same ``(name, p)``, so a
    variable symbol built here matches the one already inside a parsed
    expression (a mismatch silently turns ``subs`` into a no-op — run-017).
    """
    return sp.Symbol(name, **symbol_kwargs(props or {}))


def apply_assumptions(
    expr: sp.Basic,
    assumptions: Mapping[str, Mapping[str, bool]] | None,
) -> sp.Basic:
    """Bind ``assumptions`` onto the free symbols of ``expr``.

    Name-based and post-parse: only free ``Symbol`` atoms are replaced.  A
    function name (``k(x)``), a constant (``I``, ``E``) and non-Basic
    containers (the tuples produced by comma-separated parses) are all left
    alone — the first two are not free symbols, and the last is not a
    ``sp.Basic``.
    """
    if not assumptions or not isinstance(expr, sp.Basic):
        return expr

    mapping: dict[sp.Symbol, sp.Symbol] = {}
    for sym in expr.free_symbols:
        props = assumptions.get(sym.name)
        if not props:
            continue
        target = resolve_assumed_symbol(sym.name, props)
        if target != sym:
            mapping[sym] = target

    return expr.xreplace(mapping) if mapping else expr
