"""Assumption-clause text validation for the MCP tools (r19 F23).

``math(assumptions=[...])`` and ``assume([...])`` accept
``"<symbol> is <properties>"`` clauses.  An *expression-valued* entry such as
``"Omega**2*b**2 + (Omega**2*m - k)**2 is positive"`` used to be split on
whitespace and applied as a symbol named ``Omega**2*b**2`` with the meaningless
properties ``+``, ``(Omega**2*m``, ``-``, ... — a silent no-op that reported
``assumptions_applied`` as if it had worked.  Kept out of ``math.py`` (near its
size limit) and out of the domain whitelist module.
"""

from __future__ import annotations

from symkit.domain.assumption_binding import ASSUMPTION_KEYWORDS

# Characters that can only appear in an expression, not in a symbol name or a
# property keyword; their presence marks the clause as expression-valued.
_EXPRESSION_CHARS = frozenset("()+-*/^=<>|[],")

_HINT = "declare the variable instead (e.g. 'Omega is positive')"


def expression_valued_assumption(clause: str) -> str | None:
    """Curated rejection for a clause that is not an assumption clause (F23).

    Returns ``None`` when the entry is a recognizable
    ``<symbol> is/has <properties>`` (or ``<symbol> <properties>``) clause, or
    when it is merely unparseable and the caller's legacy warning applies.  An
    expression-valued entry — operators/parentheses, or a first token that is
    not a symbol name — gets a curated message naming the remedy.
    """
    text = clause.strip()
    if not text:
        return None
    parts = text.split()
    properties = parts[2:] if len(parts) >= 3 and parts[1] in ("is", "has") else parts[1:]
    well_formed = (
        parts[0].isidentifier()
        and bool(properties)
        and all(prop in ASSUMPTION_KEYWORDS for prop in properties)
    )
    if well_formed:
        return None
    if any(ch in _EXPRESSION_CHARS for ch in text):
        return f"expression-valued assumption {text!r} is not supported; {_HINT}"
    return None
