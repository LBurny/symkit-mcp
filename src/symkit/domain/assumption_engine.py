"""AssumptionEngine — Multi-level assumption and constraint engine.

Manages symbol assumptions at different levels (global / domain / session / step)
during derivation, supporting priority-based merging, conflict detection, and
dynamic application.

An assumption that cannot be honored is refused, never stored silently:
:func:`validate_assumption_clause` is the shared gate (a non-symbol key such as
``"V - n*b"`` and a pseudo-property token such as ``less`` both used to land in
the layers and never take effect — r20 wave-3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from keyword import iskeyword
from typing import Any

from symkit.domain.assumption_binding import (
    ASSUMPTION_KEYWORDS,
)
from symkit.domain.assumption_binding import (
    CONFLICT_PAIRS as _CONFLICT_PAIRS,
)
from symkit.domain.math_domain import DOMAIN_ASSUMPTION_HINTS, MathDomain

_INEQUALITY_HINT = (
    "declare supported properties (positive, real, ...) with assume and record "
    "the constraint in the session notes/limitations instead"
)


def _inequality_clause(props: list[str]) -> str | None:
    """The clause text when it uses relational/function-call syntax, else ``None``.

    SymPy's assumption system stores boolean properties only, so ``abs(v) < c``
    (split into ``abs(v)``, ``<``, ``c``) can never take effect; accepting it
    silently made the operator believe the constraint was in force (r21 G13).
    """
    if any(any(ch in prop for ch in "<>()") for prop in props):
        return " ".join(props).strip()
    return None


def validate_assumption_clause(key: str, props: list[str]) -> str | None:
    """Return an error message when key is not a plain symbol name or any
    property token is outside the supported vocabulary; None when valid.

    A clause carrying relational/function-call syntax is refused with the
    inequality limitation named explicitly (r21 G13).
    """
    if not isinstance(key, str) or not key.isidentifier() or iskeyword(key):
        return (
            f"assumptions can only be set on plain symbols; '{key}' is not a symbol"
        )
    constraint = _inequality_clause(props)
    if constraint is not None:
        return (
            "sympy assumptions cannot express inequality constraints like "
            f"'{constraint}'; {_INEQUALITY_HINT}"
        )
    unknown = [prop for prop in props if prop not in ASSUMPTION_KEYWORDS]
    if unknown:
        supported = ", ".join(sorted(ASSUMPTION_KEYWORDS))
        return (
            f"unknown assumption properties for '{key}': "
            f"{', '.join(unknown)}; supported: {supported}"
        )
    return None


class AssumptionLevel(str, Enum):
    """Assumption level."""

    GLOBAL = "global"
    DOMAIN = "domain"
    SESSION = "session"
    STEP = "step"


@dataclass
class AssumptionLayer:
    """A single assumption layer."""

    level: AssumptionLevel
    assumptions: dict[str, dict[str, bool]] = field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "assumptions": self.assumptions,
            "source": self.source,
        }


class AssumptionEngine:
    """Multi-level assumption engine."""

    def __init__(self, domain: MathDomain | str = MathDomain.GENERAL) -> None:
        if isinstance(domain, str):
            domain = MathDomain.from_string(domain)
        self.domain = domain
        self._layers: dict[AssumptionLevel, AssumptionLayer] = {
            AssumptionLevel.GLOBAL: AssumptionLayer(
                level=AssumptionLevel.GLOBAL,
                source="global_context",
            ),
            AssumptionLevel.DOMAIN: AssumptionLayer(
                level=AssumptionLevel.DOMAIN,
                source=f"domain:{domain.value}",
            ),
            AssumptionLevel.SESSION: AssumptionLayer(
                level=AssumptionLevel.SESSION,
                source="session",
            ),
            AssumptionLevel.STEP: AssumptionLayer(
                level=AssumptionLevel.STEP,
                source="current_step",
            ),
        }
        # Load domain defaults
        for name, prop in DOMAIN_ASSUMPTION_HINTS.get(domain, {}).items():
            props = prop.split()
            self.assume(name, *props, level=AssumptionLevel.DOMAIN)

    def assume(
        self,
        name: str,
        *properties: str,
        level: AssumptionLevel = AssumptionLevel.SESSION,
    ) -> str | None:
        """Add an assumption at the given level.

        Returns an error message and stores nothing when the clause cannot be
        honored; callers that surface a receipt (``assume``/``assume_for_step``)
        should turn it into ``{"success": False, "error": error}``.  ``None``
        means the assumption was applied.
        """
        error = validate_assumption_clause(name, list(properties))
        if error is not None:
            return error
        layer = self._layers[level]
        if name not in layer.assumptions:
            layer.assumptions[name] = {}
        for prop in properties:
            layer.assumptions[name][prop] = True
        return None

    def unassume(
        self,
        name: str,
        *properties: str,
        level: AssumptionLevel = AssumptionLevel.SESSION,
    ) -> None:
        """Remove assumptions from the given level."""
        layer = self._layers[level]
        if name not in layer.assumptions:
            return
        if not properties:
            del layer.assumptions[name]
            return
        for prop in properties:
            layer.assumptions[name].pop(prop, None)
        if not layer.assumptions[name]:
            del layer.assumptions[name]

    def get_assumptions(
        self,
        level: AssumptionLevel | None = None,
    ) -> dict[str, dict[str, bool]]:
        """Get assumptions for the specified level or the merged assumptions."""
        if level is not None:
            return dict(self._layers[level].assumptions)

        merged: dict[str, dict[str, bool]] = {}
        # Merge from lowest to highest priority (later overrides earlier)
        for lvl in (
            AssumptionLevel.GLOBAL,
            AssumptionLevel.DOMAIN,
            AssumptionLevel.SESSION,
            AssumptionLevel.STEP,
        ):
            for name, props in self._layers[lvl].assumptions.items():
                if name not in merged:
                    merged[name] = {}
                merged[name].update(props)
        return merged

    def get_assumptions_for_symbol(self, name: str) -> dict[str, bool]:
        """Merge all assumptions for a symbol by priority."""
        result: dict[str, bool] = {}
        for lvl in (
            AssumptionLevel.GLOBAL,
            AssumptionLevel.DOMAIN,
            AssumptionLevel.SESSION,
            AssumptionLevel.STEP,
        ):
            props = self._layers[lvl].assumptions.get(name)
            if props:
                result.update(props)
        return result

    def detect_conflicts(self) -> list[dict[str, Any]]:
        """Detect conflicts in merged assumptions."""
        conflicts = []
        merged = self.get_assumptions()
        for name, props in merged.items():
            active = {p for p, v in props.items() if v}
            for a, b in _CONFLICT_PAIRS:
                if a in active and b in active:
                    conflicts.append({
                        "symbol": name,
                        "conflict": (a, b),
                        "message": f"'{name}' is both {a} and {b}",
                    })
        return conflicts

    def list_layers(self) -> list[AssumptionLayer]:
        """List all assumption layers."""
        return list(self._layers.values())

    def clear_level(self, level: AssumptionLevel) -> None:
        """Clear assumptions for a level."""
        self._layers[level].assumptions = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain.value,
            "layers": [layer.to_dict() for layer in self._layers.values()],
            "merged_assumptions": self.get_assumptions(),
            "conflicts": self.detect_conflicts(),
        }
