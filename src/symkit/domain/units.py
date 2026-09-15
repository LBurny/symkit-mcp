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
    ("µ", "u"),  # U+00B5 MICRO SIGN
    ("μ", "u"),  # U+03BC GREEK SMALL LETTER MU
)

# Whole-token respellings applied before the character substitutions above.
# These are spellings a domain author actually writes whose dimension is
# unambiguous but whose token is absent from the SymPy namespace; without them
# the symbol degrades to "unknown" and the whole expression goes inconclusive.
_TOKEN_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("degC", "K"), ("celsius", "K"), ("°C", "K"), ("℃", "K"),
    ("degF", "K"), ("fahrenheit", "K"), ("°F", "K"), ("℉", "K"),
    ("°", "deg"),  # U+00B0 DEGREE SIGN (angle, dimensionless)
)

# Names that denote "no unit known" rather than a parse failure.
_UNKNOWN_SENTINELS = frozenset({"", "-"})

# Unit strings that explicitly assert "this quantity is dimensionless".  The
# formula write path requires a non-empty unit, using ``"-"`` for a
# dimensionless or unknown quantity, so the analyser has to read ``"-"`` as an
# assertion rather than as missing information.
_DIMENSIONLESS_MARKERS = frozenset({"-", "1", "dimensionless", "unitless", "none", "无量纲", "%", "‰", "ppm"})


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
    """Fold display glyphs and respellings down to plain Python arithmetic."""
    normalized = text.strip()
    if normalized in _UNKNOWN_SENTINELS:
        return ""
    for old, new in _TOKEN_SUBSTITUTIONS:
        normalized = normalized.replace(old, new)
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


def dimension_dependencies(unit_expr: sp.Basic) -> dict[str, int] | None:
    """Base-quantity dimension vector for a SymPy unit expression.

    Keys are base-quantity names (``mass``, ``length``, ``time``, ...).  ``{}``
    means dimensionless; ``None`` means the vector is not expressible as
    integer base powers (``sqrt(m)``, ``m**(1/3)``) or the input cannot be
    resolved at all.

    ``None`` and ``{}`` must stay distinct: rounding a fractional power to
    ``length ** 0`` reports a dimensioned quantity as dimensionless, which is
    worse than admitting the unit is unknown.
    """
    try:
        dimensional = SI.get_dimensional_expr(unit_expr)
        raw = SI.get_dimension_system().get_dimensional_dependencies(dimensional)
    except Exception:
        return None
    powers = {str(dim.name): sp.Rational(power) for dim, power in raw.items()}
    # SI defines the steradian as a dimensionless derived unit; SymPy gives it a
    # dimension of its own, which would leak a non-base name into a vector whose
    # contract says "keys are base quantities".
    powers.pop("steradian", None)
    if any(power.q != 1 for power in powers.values()):
        return None
    return {name: int(power) for name, power in powers.items()}
