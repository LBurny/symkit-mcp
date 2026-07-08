"""AssumptionEngine — Multi-level assumption and constraint engine.

Manages symbol assumptions at different levels (global / domain / session / step)
during derivation, supporting priority-based merging, conflict detection, and
dynamic application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from symkit.domain.math_domain import DOMAIN_ASSUMPTION_HINTS, MathDomain


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


# Conflicting property pairs: cannot both hold
_CONFLICT_PAIRS: list[tuple[str, str]] = [
    ("positive", "negative"),
    ("positive", "zero"),
    ("negative", "zero"),
    ("real", "imaginary"),
    ("integer", "irrational"),
]


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
    ) -> None:
        """Add an assumption at the given level."""
        layer = self._layers[level]
        if name not in layer.assumptions:
            layer.assumptions[name] = {}
        for prop in properties:
            layer.assumptions[name][prop] = True

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
