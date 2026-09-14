"""Call-site name handling for the shared expression parser.

Hosted here so ``expression_parser`` stays within its frozen ratchet size
(bylaw §5.1). Two concerns:

1. Lowercase ``max(...)``/``min(...)`` call sites are rewritten to SymPy's
   auto-evaluating ``Max``/``Min``. Left as unknown calls they bound to
   ``Function('max')``, which blocked every numeric verdict over SST-style
   mixing functions (2026-09-14 SST derivation round).
2. A name used both as a bare symbol and as a call site in the same
   expression (``1/z + z(x)``) cannot share one ``local_dict`` entry: binding
   it to a ``Function`` makes ``1/z`` unparseable ("SympifyError: z"). The
   call sites are renamed to ``<name>__call`` and bound to
   ``Function('<name>')`` so the bare occurrence keeps its plain ``Symbol``
   (2026-09-14 defect #6).
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp

# Matches ``name(`` call sites, excluding attribute access (``a.name(``).
_UNDEFINED_FUNC_CALL_RE: re.Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9_.])([A-Za-z_][A-Za-z0-9_]*)\s*\("
)

# Namespace that already has native semantics when called: every public SymPy
# name (``sin``, ``sqrt``, ``Eq``, ``Derivative``, ``beta``, ...) plus Python
# keywords/constants that ``parse_expr`` may legitimately encounter.
_KNOWN_CALLABLE_NAMESPACE: frozenset[str] = frozenset(
    set(dir(sp)) | {"and", "or", "not", "True", "False"}
)

_CALL_RENAME_SUFFIX = "__call"


def protect_min_max_calls(expr_str: str) -> str:
    """Rewrite lowercase ``max(``/``min(`` call sites to ``Max``/``Min``.

    ``Max``/``Min`` auto-evaluate numeric arguments, keep symbolic arguments
    symbolic, and are verified numerically like any other expression; plain
    ``sympify`` already evaluated these via the Python builtins, so the
    shared parser only lacked the same treatment. Uppercase ``Max``/``Min``
    and identifiers like ``maxwell(`` are untouched.
    """
    result = re.sub(r"(?<![A-Za-z0-9_.])max\s*\(", "Max(", expr_str)
    return re.sub(r"(?<![A-Za-z0-9_.])min\s*\(", "Min(", result)


def _bare_usage_re(name: str) -> re.Pattern[str]:
    """A whole-identifier occurrence of ``name`` that is NOT a call site."""
    return re.compile(
        r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_.])(?!\s*\()"
    )


def split_dual_use_call_sites(
    expr_str: str, exclude: set[str] | frozenset[str] = frozenset()
) -> tuple[str, dict[str, str]]:
    """Rename call sites of names that also occur as bare symbols.

    Returns ``(rewritten, {temp_name: original_name})``. The caller binds each
    ``temp_name`` to ``sp.Function(original_name)`` so the parsed expression
    still prints as ``z(x)`` while the bare ``z`` parses to a plain Symbol.
    Names with native SymPy semantics, protected bindings, or constants are
    left alone, and a name whose ``<name>__call`` form already occurs is left
    untouched (graceful fallback to the historical behavior).
    """
    call_sites = set(_UNDEFINED_FUNC_CALL_RE.findall(expr_str))
    dual_use = [
        name
        for name in sorted(call_sites)
        if name not in _KNOWN_CALLABLE_NAMESPACE
        and name not in exclude
        and _bare_usage_re(name).search(expr_str) is not None
    ]
    if not dual_use:
        return expr_str, {}
    renames: dict[str, str] = {}
    rewritten = expr_str
    for name in dual_use:
        temp = name + _CALL_RENAME_SUFFIX
        if re.search(
            r"(?<![A-Za-z0-9_])" + re.escape(temp) + r"(?![A-Za-z0-9_])",
            expr_str,
        ):
            return expr_str, {}
        rewritten = re.sub(
            r"(?<![A-Za-z0-9_.])" + re.escape(name) + r"\s*\(",
            temp + "(",
            rewritten,
        )
        renames[temp] = name
    return rewritten, renames


def build_undefined_function_local_dict(
    expr: str, exclude: set[str] | frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Bind unknown ``name(`` call sites to SymPy undefined ``Function``s.

    Red line: function notation must never degrade to implicit
    multiplication. ``v(t)`` is the function v evaluated at t, not ``v*t``.
    Names already bound by other protection layers (``exclude``), known to
    SymPy, or listed as constants keep their existing semantics. Bare names
    without a call site are unaffected and remain Symbols.
    """
    local_dict: dict[str, Any] = {}
    for name in set(_UNDEFINED_FUNC_CALL_RE.findall(expr)):
        if (
            name in _KNOWN_CALLABLE_NAMESPACE
            or name in exclude
        ):
            continue
        local_dict[name] = sp.Function(name)
    return local_dict
