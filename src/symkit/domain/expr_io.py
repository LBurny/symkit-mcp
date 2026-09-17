"""Expression reconstruction from archived records.

Invariant I2: an expression that was already computed must be rebuilt from the
archived object, never re-parsed from its display string.  ``str(expr)`` is a
presentation format and does not always round-trip:

* ``str(E)`` / ``str(I)`` re-parse to ``Symbol('E')`` / ``Symbol('I')`` because
  the parser deliberately protects those names as user variables (run-020).
* ``str(Symbol('mu_{t}'))`` is not valid Python at all (LaTeX-derived symbols).

``srepr`` is the machine-readable counterpart and does round-trip, so it is
always tried first.  The display string and the unified user parser remain as
fallbacks for records written before ``srepr`` archiving existed.

This module is pure domain: it depends only on SymPy and the domain parser.
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp
from sympy.integrals.risch import NonElementaryIntegral

_SREPR_HEAD = re.compile(r"^\s*([A-Z][A-Za-z0-9_]*)\(")

_KNOWN_CONSTRUCTORS = frozenset(
    {
        "Add", "Mul", "Pow", "Rational", "Integer", "Float", "Symbol",
        "Function", "Equality", "Unequality", "GreaterThan", "LessThan",
        "StrictGreaterThan", "StrictLessThan", "Derivative", "Integral",
        "Sum", "Product", "Limit", "ImmutableDenseMatrix",
        "ImmutableSparseMatrix", "MutableDenseMatrix", "MutableSparseMatrix",
        "Lambda", "Tuple", "Dict", "NonElementaryIntegral",
    }
)


def is_srepr_form(text: str) -> bool:
    """True when ``text`` has an srepr constructor head (whitelist-gated)."""
    if not isinstance(text, str):
        return False
    match = _SREPR_HEAD.match(text)
    return match is not None and match.group(1) in _KNOWN_CONSTRUCTORS


def try_load_srepr(text: str) -> sp.Basic | None:
    """Load ``text`` when it is an srepr constructor form, else ``None``.

    ``python_exec`` returns a result's ``srepr``; pasting that string into any
    expression field must rebuild the object — assumptions on symbols included
    (``Symbol('c', positive=True)``) — which the restricted text grammar
    rejects.  Detection is a constructor-name whitelist, so ordinary text never
    reaches this path; any load failure returns ``None`` and the caller falls
    back to the normal grammar.
    """
    if not is_srepr_form(text):
        return None
    try:
        # Same trust level as safe_load_expression's sympify path: the string
        # is machine-shaped srepr, and the whitelist keeps prose out.
        return _basic_or_none(
            sp.sympify(
                text, locals={"NonElementaryIntegral": NonElementaryIntegral}
            )
        )
    except Exception:
        return None


def _plain_integrals(expr: sp.Basic) -> sp.Basic:
    """Replace ``NonElementaryIntegral`` nodes with plain ``Integral`` nodes.

    sympy returns ``NonElementaryIntegral`` for an integrand with no elementary
    antiderivative (e.g. ``x**x``).  Its limits are stored as a bare ``Tuple``,
    so ``sp.diff`` recurses into that Tuple and dies with ``AttributeError:
    'Tuple' object has no attribute 'diff'`` — the verifier's reverse check
    crashed and the recording layer swallowed the step (r21 G6).  A plain
    ``Integral`` with the same function and limits is mathematically identical
    and differentiates correctly.
    """
    if not expr.has(NonElementaryIntegral):
        return expr
    return expr.replace(
        lambda node: isinstance(node, NonElementaryIntegral),
        lambda node: sp.Integral(node.function, *node.limits),
    )


def _basic_or_none(candidate: Any) -> sp.Basic | None:
    """Return ``candidate`` as a normalized SymPy Basic, else ``None``.

    ``sympify`` can return non-Basic containers (e.g. ``(1, 2)`` from legacy
    comma parses); callers must never receive an atom-less container.  A loaded
    expression is also normalized so every ``NonElementaryIntegral`` becomes a
    plain ``Integral`` — see :func:`_plain_integrals`.
    """
    if not isinstance(candidate, sp.Basic):
        return None
    return _plain_integrals(candidate)


def safe_load_expression(
    expr_str: str,
    srepr_str: str = "",
) -> sp.Basic | None:
    """Rebuild a stored expression, preferring the archived ``srepr``.

    Args:
        expr_str: The display string (``str(expr)``) as stored.
        srepr_str: The archived ``sp.srepr(expr)``, when available.

    Returns:
        The reconstructed SymPy object, or ``None`` when every strategy fails.
    """
    if srepr_str:
        try:
            # ``sympify`` does not know ``NonElementaryIntegral`` and would
            # silently rebuild the node as an undefined function whose second
            # argument is a ``Tuple`` — the object ``sp.diff`` crashes on (r21
            # G6).  Teach it the class; ``_basic_or_none`` then normalizes it.
            loaded = _basic_or_none(
                sp.sympify(
                    srepr_str,
                    locals={"NonElementaryIntegral": NonElementaryIntegral},
                )
            )
            if loaded is not None:
                return loaded
        except Exception:
            pass

    try:
        from symkit.domain.expression_parser import build_reserved_local_dict

        # ``sympify``'s own namespace folds ``E`` → exp(1) and ``I`` → 1j, so a
        # stored display string re-parsed that way came back as Euler's number:
        # str ``E`` + latex ``e`` (r19 F20 fingerprint).  The parser protects
        # ``E``/``I``/``Q``/``O`` as user variables (run-020), so protect the
        # same names here; only strings that actually use one are affected.
        protected = build_reserved_local_dict(expr_str)
        loaded = _basic_or_none(
            sp.sympify(expr_str, locals=protected) if protected else sp.sympify(expr_str)
        )
        if loaded is not None:
            return loaded
    except Exception:
        pass

    try:
        from symkit.domain.expression_parser import parse_user_expression

        # The unified parser returns a non-Basic container for legacy comma /
        # dict forms (``{a: 6}`` -> a Python ``dict``); guard the exit like the
        # two above so this function's contract holds on every path.
        loaded = _basic_or_none(parse_user_expression(expr_str)[0])
        if loaded is not None:
            return loaded
    except Exception:
        pass

    return None


def evaluated_form(expr: sp.Basic) -> sp.Basic:
    """Re-evaluate structurally-unevaluated nodes.

    The user parser leaves some arithmetic unevaluated, so ``/2`` arrives as
    ``Pow(2, -1)`` while an expression that has already been through the engine
    holds ``Rational(1, 2)``.  ``subs`` matches structurally, so a substitution
    key in the first form silently fails to apply to the second, and a correct
    step is reported FAILED (2026-09-12 black-box round).  Round-tripping
    through ``srepr`` forces evaluation without changing the value.
    """
    try:
        return sp.sympify(sp.srepr(expr))
    except Exception:
        return expr


def dense_matrix_form(expr: sp.Basic) -> sp.Basic:
    """Collapse a symbolic matrix expression into a dense matrix.

    ``Matrix(A)*Matrix(A) - c*Matrix(A) + k*Identity(n)`` stays a ``MatAdd``
    with the ``Identity`` term unabsorbed, and ``.evalf()`` then recurses until
    Python raises ``RecursionError`` -- an uncaught crash at the tool boundary
    (2026-09-12 pure-formula black-box round).  ``as_explicit()`` adds the term
    into the matrix, which both evaluates and makes a true Cayley-Hamilton
    residual come out as the zero matrix.  Non-matrix input is returned as-is.
    """
    if isinstance(expr, sp.MatrixExpr) and not isinstance(expr, sp.MatrixBase):
        try:
            return expr.as_explicit()
        except Exception:
            return expr
    return expr


def substitution_pairs(
    input_expressions: dict[str, str],
) -> list[tuple[str, str]] | None:
    """The ``key = value`` substitution pairs of a recorded step, losslessly.

    Prefers the archived JSON map.  The human-readable ``replacement`` string is
    comma-joined, so a value containing a comma — ``Rational(1,6)``,
    ``Eq(a, b)``, any multi-argument call — splits into fragments and the
    verifier reported a false "Could not parse replacement expression".  The
    string form is only a fallback for records written before the map was
    archived.
    """
    import json

    raw_map = input_expressions.get("replacement_map")
    if raw_map:
        try:
            mapping = json.loads(raw_map)
        except (TypeError, ValueError):
            mapping = None
        if isinstance(mapping, dict) and mapping:
            return [(str(k), str(v)) for k, v in mapping.items()]

    replacement_str = input_expressions.get("replacement", "")
    if not replacement_str:
        return None
    pairs: list[tuple[str, str]] = []
    for part in replacement_str.split(","):
        left, sep, right = part.strip().partition("=")
        if not sep or not left.strip() or not right.strip():
            return None
        pairs.append((left.strip(), right.strip()))
    return pairs or None
