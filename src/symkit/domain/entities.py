"""
SymKit Domain Entities

Entities are objects with identity that persist over time.
"""

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExpressionType(str, Enum):
    """Type of mathematical expression."""

    ALGEBRAIC = "algebraic"
    CALCULUS = "calculus"
    EQUATION = "equation"
    MATRIX = "matrix"
    UNKNOWN = "unknown"


@dataclass
class Expression:
    """
    A mathematical expression entity.

    This is the core entity representing any mathematical expression
    that can be manipulated symbolically.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    raw: str = ""  # Original string representation
    latex: str = ""  # LaTeX representation
    sympy_expr: Any = None  # SymPy expression object
    expr_type: ExpressionType = ExpressionType.UNKNOWN

    @property
    def is_valid(self) -> bool:
        """Check if expression was successfully parsed."""
        return self.sympy_expr is not None


@dataclass
class DerivationStep:
    """
    A single step in a mathematical derivation.

    Each step represents one transformation with its justification.
    """

    step_number: int
    operation: str  # e.g., "substitute", "simplify", "differentiate"
    input_expr: Expression
    output_expr: Expression
    justification: str = ""  # Human-readable explanation
    rule_applied: str = ""  # Formal rule name


@dataclass
class Derivation:
    """
    A complete mathematical derivation.

    Contains the full chain of steps from premise to conclusion.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = ""  # What we're trying to derive
    premises: list[Expression] = field(default_factory=list)
    steps: list[DerivationStep] = field(default_factory=list)
    conclusion: Expression | None = None
    is_verified: bool = False

    @property
    def is_complete(self) -> bool:
        """Check if derivation reached a conclusion."""
        return self.conclusion is not None

    def add_step(self, step: DerivationStep) -> None:
        """Add a step to the derivation."""
        self.steps.append(step)

    def get_step_count(self) -> int:
        """Get number of steps in derivation."""
        return len(self.steps)
