"""Narrow ``solve`` normalization for equation lists (r23 G1).

``docs/recommended-system-prompt.md`` advertises ``solve`` systems as
``"eq1, eq2"`` or ``"[eq1, eq2]"`` with ``variable="x, y"``.  The expression
form (implicit ``= 0``) always worked, but the shared expression parser reads a
top-level comma/bracket list as a single expression, so every list whose
elements carried an explicit ``=`` failed with "cannot assign to expression
here" before the dispatcher's system branch could run.

Only the ``solve`` branch calls :func:`equation_list_expressions`: an equation
list is rewritten to the ``lhs - rhs`` expression list the existing system
branch already consumes, so no other operation's parse path changes.  Anything
that is not a top-level list with an equation element returns ``None`` and
keeps the pre-existing parse path untouched.

Return contract:

- ``None`` — not an equation list; use the normal parse path.
- ``dict`` — curated rejection (malformed element or inequality), ready to
  return from the tool.
- ``list`` — parsed ``lhs - rhs`` expressions for the system branch.
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp
from sympy.core.relational import Equality, Relational

from symkit.domain.assumption_binding import apply_assumptions
from symkit.domain.expression_parser import parse_user_expression
from symkit.domain.value_objects import MathContext
from symkit_mcp.tools._op_helpers import inequality_solve_error

#: A standalone assignment/equality ``=`` (also ``==``), never ``<=``/``>=``/``!=``.
_EQUATION_MARK = re.compile(r"(?<![<>!])=")


def _bracket_inner(text: str) -> str | None:
    """Return the inside of a ``[...]`` spanning the whole string, else ``None``."""
    if len(text) < 2 or text[0] != "[" or text[-1] != "]":
        return None
    depth = 0
    for index, char in enumerate(text):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                return None
    return text[1:-1] if depth == 0 else None


def _split_top_level(text: str) -> list[str]:
    """Split on commas outside ``()``/``[]``/``{}`` so ``f(x, y)`` stays whole."""
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def _equation_list_parts(expr_str: Any) -> list[str] | None:
    """Split a top-level comma/bracket list, or ``None`` when it is not one."""
    if not isinstance(expr_str, str):
        return None
    text = expr_str.strip()
    inner = _bracket_inner(text)
    if inner is not None:
        text = inner.strip()
    parts = _split_top_level(text)
    if len(parts) < 2 and inner is None:
        return None
    if not any(_EQUATION_MARK.search(part) for part in parts):
        return None
    return parts


def equation_list_expressions(
    expr_str: Any, context: MathContext | None = None
) -> list[sp.Basic] | dict[str, Any] | None:
    """Normalize a top-level ``solve`` equation list; see the module docstring."""
    parts = _equation_list_parts(expr_str)
    if parts is None:
        return None

    expressions: list[sp.Basic] = []
    for part in parts:
        parsed, error = parse_user_expression(part, convert_equation=True)
        if parsed is None:
            detail = f" ({error})" if error else ""
            return {
                "success": False,
                "error": f"Cannot parse equation '{part}' in the system{detail}",
            }
        if isinstance(parsed, Relational) and not isinstance(parsed, Equality):
            return inequality_solve_error(parsed)
        if not isinstance(parsed, sp.Basic):
            return {
                "success": False,
                "error": (
                    f"Cannot parse equation '{part}' in the system: it is not a "
                    "symbolic equation"
                ),
            }
        expressions.append(parsed.lhs - parsed.rhs if isinstance(parsed, Equality) else parsed)

    if context is not None:
        expressions = [apply_assumptions(e, context.assumptions) for e in expressions]
    return expressions
