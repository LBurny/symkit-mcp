"""
SymKit Domain Value Objects

Value objects are immutable objects defined by their attributes.
They have no identity and are compared by value.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SimplificationLevel(str, Enum):
    """Level of simplification to apply."""

    NONE = "none"
    BASIC = "basic"  # Combine like terms
    FULL = "full"  # Full algebraic simplification
    TRIGONOMETRIC = "trigonometric"  # Trig identities
    RADICAL = "radical"  # Simplify radicals


class VerificationStatus(str, Enum):
    """Status of a verification check."""

    VERIFIED = "verified"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"


class CoordinateSystem(str, Enum):
    """Coordinate system type."""

    CARTESIAN = "cartesian"
    CYLINDRICAL = "cylindrical"
    SPHERICAL = "spherical"


@dataclass(frozen=True)
class MathContext:
    """
    Context for mathematical operations.

    Immutable configuration that affects how expressions are processed.
    """

    # Variable assumptions
    assumptions: dict[str, dict[str, bool]] = field(default_factory=dict)
    # e.g., {"x": {"real": True, "positive": True}}

    # Numerical precision
    precision: int = 15

    # Simplification settings
    simplify_level: SimplificationLevel = SimplificationLevel.BASIC

    # Whether to evaluate numerically when possible
    evaluate_numerically: bool = False

    # Domain restrictions (e.g., "real", "complex", "integer")
    domain: str = "complex"

    # Coordinate system for vector calculus
    coordinate_system: CoordinateSystem = CoordinateSystem.CARTESIAN

    def with_assumption(self, var: str, **assumptions: bool) -> "MathContext":
        """Create new context with additional assumption."""
        new_assumptions = dict(self.assumptions)
        new_assumptions[var] = {**new_assumptions.get(var, {}), **assumptions}
        return MathContext(
            assumptions=new_assumptions,
            precision=self.precision,
            simplify_level=self.simplify_level,
            evaluate_numerically=self.evaluate_numerically,
            domain=self.domain,
            coordinate_system=self.coordinate_system,
        )


@dataclass(frozen=True)
class VerificationResult:
    """
    Result of verifying a mathematical derivation or calculation.

    Immutable result object containing verification details.
    """

    status: VerificationStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    # Specific checks performed
    dimension_check: bool | None = None
    reverse_check: bool | None = None
    boundary_check: bool | None = None

    @property
    def is_verified(self) -> bool:
        """Check if verification passed."""
        return self.status == VerificationStatus.VERIFIED

    @classmethod
    def success(cls, message: str = "Verification passed") -> "VerificationResult":
        """Create a successful verification result."""
        return cls(status=VerificationStatus.VERIFIED, message=message)

    @classmethod
    def failure(cls, message: str, **details: Any) -> "VerificationResult":
        """Create a failed verification result."""
        return cls(status=VerificationStatus.FAILED, message=message, details=details)


@dataclass(frozen=True)
class CalculationResult:
    """
    Result of a symbolic calculation.

    Contains the result expression and metadata about the calculation.
    """

    success: bool
    result: str = ""  # String representation
    latex: str = ""  # LaTeX representation
    steps: list[str] = field(default_factory=list)  # Calculation steps
    error: str = ""  # Error message if failed

    # Performance metrics
    computation_time_ms: float = 0.0

    @classmethod
    def from_error(cls, error: str) -> "CalculationResult":
        """Create a failed calculation result."""
        return cls(success=False, error=error)
