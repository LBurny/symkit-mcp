"""DerivationPattern — Domain-independent derivation patterns.

Abstracts domain-specific derivations into reusable general patterns so that
SymKit is not limited to a particular domain (pharmacokinetics, fluid dynamics,
etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from symkit.domain.derivation_goal import DerivationGoal


class DerivationPattern(str, Enum):
    """General derivation patterns."""

    CONSERVATION_CONSTITUTIVE = "conservation+constitutive"
    VARIATIONAL = "variational"
    OPERATOR_CORRESPONDENCE = "operator-correspondence"
    SERIES_APPROXIMATION = "series-approximation"
    EIGENMODE_ANALYSIS = "eigenmode-analysis"
    DIRECT_MANIPULATION = "direct-manipulation"

    @classmethod
    def from_string(cls, value: str) -> DerivationPattern:
        """Parse pattern from string; fallback to direct-manipulation when unrecognized."""
        try:
            return cls(value.lower().replace(" ", "-").replace("_", "-"))
        except ValueError:
            return cls.DIRECT_MANIPULATION

    @classmethod
    def from_goal(cls, goal: DerivationGoal) -> DerivationPattern:
        """Automatically select the most suitable derivation pattern based on the goal."""
        if not isinstance(goal, DerivationGoal):
            return cls.DIRECT_MANIPULATION

        text = goal.text.lower()
        if any(kw in text for kw in ("conservation", "constitutive", "continuity")):
            return cls.CONSERVATION_CONSTITUTIVE
        if any(kw in text for kw in ("variational", "energy", "minimize", "action", "lagrangian", "hamiltonian")):
            return cls.VARIATIONAL
        if any(kw in text for kw in ("operator", "correspondence", "quantization", "commutator")):
            return cls.OPERATOR_CORRESPONDENCE
        if any(kw in text for kw in ("series", "approximate", "expand", "taylor")):
            return cls.SERIES_APPROXIMATION
        if any(kw in text for kw in ("eigenmode", "eigen", "mode", "normal mode")):
            return cls.EIGENMODE_ANALYSIS
        return cls.DIRECT_MANIPULATION


@dataclass
class PatternTemplate:
    """Derivation pattern template: contains recommended steps, default assumptions, and typical verification items."""

    pattern: DerivationPattern
    description: str
    typical_steps: list[str] = field(default_factory=list)
    default_assumptions: list[str] = field(default_factory=list)
    typical_verifications: list[str] = field(default_factory=list)
    suggested_operations: list[str] = field(default_factory=list)


_PATTERN_REGISTRY: dict[DerivationPattern, PatternTemplate] = {
    DerivationPattern.CONSERVATION_CONSTITUTIVE: PatternTemplate(
        pattern=DerivationPattern.CONSERVATION_CONSTITUTIVE,
        description="Derive governing equations from conservation laws and constitutive relations",
        typical_steps=[
            "Load conservation law(s)",
            "Load constitutive relation(s)",
            "Apply simplifying assumptions",
            "Substitute constitutive into conservation",
            "Simplify to obtain governing equation",
        ],
        default_assumptions=[
            "Continuum hypothesis applies",
            "Material properties are well-defined",
        ],
        typical_verifications=[
            "dimensional_analysis",
            "boundary_degeneration",
        ],
        suggested_operations=[
            "substitute",
            "simplify",
            "diff",
            "integrate",
        ],
    ),
    DerivationPattern.VARIATIONAL: PatternTemplate(
        pattern=DerivationPattern.VARIATIONAL,
        description="Derive equations of motion from variational principles (Lagrangian/action)",
        typical_steps=[
            "Define Lagrangian or action",
            "Apply Euler-Lagrange equations",
            "Simplify to obtain equations of motion",
        ],
        default_assumptions=[
            "Action is stationary",
            "Variations vanish at boundaries",
        ],
        typical_verifications=[
            "dimensional_analysis",
            "limit_small_amplitude",
        ],
        suggested_operations=[
            "diff",
            "simplify",
            "solve",
        ],
    ),
    DerivationPattern.OPERATOR_CORRESPONDENCE: PatternTemplate(
        pattern=DerivationPattern.OPERATOR_CORRESPONDENCE,
        description="Replace classical quantities with operators to obtain quantum equations",
        typical_steps=[
            "Start from classical relation",
            "Replace quantities with operators",
            "Apply operator to wave function",
            "Simplify to obtain quantum equation",
        ],
        default_assumptions=[
            "Non-relativistic regime",
            "Wave function is sufficiently smooth",
        ],
        typical_verifications=[
            "classical_limit",
            "dimensional_analysis",
        ],
        suggested_operations=[
            "diff",
            "simplify",
        ],
    ),
    DerivationPattern.SERIES_APPROXIMATION: PatternTemplate(
        pattern=DerivationPattern.SERIES_APPROXIMATION,
        description="Obtain simplified models via series or small-parameter expansion",
        typical_steps=[
            "Identify small parameter",
            "Expand governing equation in series",
            "Truncate at desired order",
            "Simplify approximate equation",
        ],
        default_assumptions=[
            "Small parameter is much less than 1",
            "Higher-order terms are negligible",
        ],
        typical_verifications=[
            "limit_small_parameter",
            "compare_to_full_equation",
        ],
        suggested_operations=[
            "series",
            "simplify",
            "substitute",
        ],
    ),
    DerivationPattern.EIGENMODE_ANALYSIS: PatternTemplate(
        pattern=DerivationPattern.EIGENMODE_ANALYSIS,
        description="Assume specific solution forms (separation of variables / eigenmodes) to derive eigen-equations",
        typical_steps=[
            "Linearize the governing equation",
            "Assume modal solution form",
            "Substitute into linearized equation",
            "Solve eigenvalue problem",
        ],
        default_assumptions=[
            "System is linear or weakly nonlinear",
            "Boundary conditions are separable",
        ],
        typical_verifications=[
            "eigenvalue_consistency",
            "boundary_condition_check",
        ],
        suggested_operations=[
            "substitute",
            "solve",
            "simplify",
        ],
    ),
    DerivationPattern.DIRECT_MANIPULATION: PatternTemplate(
        pattern=DerivationPattern.DIRECT_MANIPULATION,
        description="Directly perform algebraic or calculus operations on expressions without a specific pattern",
        typical_steps=[
            "Load base expression(s)",
            "Apply algebraic or calculus operations",
            "Simplify result",
        ],
        default_assumptions=[],
        typical_verifications=[
            "dimensional_analysis",
        ],
        suggested_operations=[
            "simplify",
            "expand",
            "factor",
            "diff",
            "integrate",
            "substitute",
        ],
    ),
}


def get_pattern_template(pattern: DerivationPattern | str) -> PatternTemplate:
    """Get the template for the specified pattern."""
    if isinstance(pattern, str):
        pattern = DerivationPattern.from_string(pattern)
    return _PATTERN_REGISTRY.get(
        pattern, _PATTERN_REGISTRY[DerivationPattern.DIRECT_MANIPULATION]
    )


def list_patterns() -> dict[str, Any]:
    """List all available derivation patterns."""
    return {
        "patterns": [
            {
                "name": p.value,
                "description": t.description,
                "typical_steps": t.typical_steps,
                "default_assumptions": t.default_assumptions,
                "typical_verifications": t.typical_verifications,
                "suggested_operations": t.suggested_operations,
            }
            for p, t in _PATTERN_REGISTRY.items()
        ]
    }
