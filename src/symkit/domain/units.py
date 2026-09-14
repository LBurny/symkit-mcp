"""Unit-string parsing and SI dimensional dependencies.

Formula-library units are display-oriented strings such as ``kg/m^3``,
``Pa·s`` (U+00B7 middle dot) and ``J/(mol·K)``.  This module normalises those
strings and resolves them against the SymPy SI unit namespace so the rest of
the domain can reason about dimensions without depending on a formatting
convention.
"""

from __future__ import annotations

from typing import Any

import sympy as sp
from sympy.parsing.sympy_parser import parse_expr
from sympy.physics.units import Unit
from sympy.physics.units.systems.si import SI

# Display glyphs that appear in hand-written / library unit strings.
_CHAR_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("·", "*"),  # U+00B7 MIDDLE DOT
    ("⋅", "*"),  # U+22C5 DOT OPERATOR
    ("×", "*"),  # U+00D7 MULTIPLICATION SIGN
    ("²", "**2"),
    ("³", "**3"),
    ("^", "**"),
    ("（", "("),
    ("）", ")"),
)

# Names that denote "no unit known" rather than a parse failure.
_UNKNOWN_SENTINELS = frozenset({"", "-"})

# Unit strings that explicitly assert "this quantity is dimensionless".  The
# formula write path requires a non-empty unit, using ``"-"`` for a
# dimensionless or unknown quantity, so the analyser has to read ``"-"`` as an
# assertion rather than as missing information.
_DIMENSIONLESS_MARKERS = frozenset({"-", "1", "dimensionless", "unitless", "none", "无量纲"})


def is_dimensionless_marker(text: str) -> bool:
    """True when ``text`` explicitly declares a dimensionless quantity."""
    return isinstance(text, str) and text.strip().lower() in _DIMENSIONLESS_MARKERS


def _unit_namespace() -> dict[str, Any]:
    """SymPy SI unit namespace keyed by every exported unit name."""
    return {
        name: value
        for name, value in vars(sp.physics.units).items()
        if isinstance(value, Unit)
    }


_UNIT_NAMESPACE: dict[str, Any] = _unit_namespace()


def _normalize_unit_text(text: str) -> str:
    """Fold display glyphs down to plain Python arithmetic syntax."""
    normalized = text.strip()
    if normalized in _UNKNOWN_SENTINELS:
        return ""
    for old, new in _CHAR_SUBSTITUTIONS:
        normalized = normalized.replace(old, new)
    return "".join(normalized.split())


def parse_unit(text: str) -> sp.Expr | None:
    """Parse a display-oriented unit string into a SymPy unit expression.

    ``None`` is returned for unknown, empty or ``"-"`` inputs, and for any
    string that fails to parse; this function never raises.
    """
    if not isinstance(text, str):
        return None
    normalized = _normalize_unit_text(text)
    if not normalized:
        return None
    try:
        parsed = parse_expr(normalized, local_dict=dict(_UNIT_NAMESPACE))
    except Exception:
        return None
    if not isinstance(parsed, sp.Expr) or parsed.free_symbols:
        # A free symbol means a name outside the unit namespace leaked in.
        return None
    return parsed


def dimension_dependencies(unit_expr: sp.Basic) -> dict[str, int]:
    """Base-quantity dimension vector for a SymPy unit expression.

    Keys are base-quantity names (``mass``, ``length``, ``time``, ...);
    dimensionless expressions yield ``{}``.  Unresolvable inputs yield ``{}``
    rather than raising.
    """
    try:
        dimensional = SI.get_dimensional_expr(unit_expr)
        raw = SI.get_dimension_system().get_dimensional_dependencies(dimensional)
    except Exception:
        return {}
    return {str(dim.name): int(power) for dim, power in raw.items()}
