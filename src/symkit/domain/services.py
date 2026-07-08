"""
SymKit Domain Services

Domain services encapsulate domain logic that doesn't naturally
fit within a single entity or value object.
"""

from abc import ABC, abstractmethod
from typing import Any

from symkit.domain.entities import Derivation, Expression
from symkit.domain.value_objects import MathContext, VerificationResult


class SymbolicEngine(ABC):
    """
    Abstract interface for symbolic computation engine.

    This is a domain service interface - the actual implementation
    lives in the infrastructure layer (e.g., SymPyEngine).
    """

    @abstractmethod
    def parse(self, expr_str: str, context: MathContext | None = None) -> Expression:
        """Parse a string into an Expression."""
        ...

    @abstractmethod
    def simplify(self, expr: Expression, context: MathContext | None = None) -> Expression:
        """Simplify an expression."""
        ...

    @abstractmethod
    def differentiate(
        self, expr: Expression, variable: str, order: int = 1, context: MathContext | None = None
    ) -> Expression:
        """Differentiate an expression."""
        ...

    @abstractmethod
    def integrate(
        self,
        expr: Expression,
        variable: str,
        lower: Any = None,
        upper: Any = None,
        context: MathContext | None = None,
    ) -> Expression:
        """Integrate an expression."""
        ...

    @abstractmethod
    def solve(
        self, equation: Expression, variable: str, context: MathContext | None = None
    ) -> list[Expression]:
        """Solve an equation for a variable."""
        ...

    @abstractmethod
    def substitute(
        self, expr: Expression, substitutions: dict[str, Any], context: MathContext | None = None
    ) -> Expression:
        """Substitute values into an expression."""
        ...

    @abstractmethod
    def equals(
        self, expr1: Expression, expr2: Expression, context: MathContext | None = None
    ) -> bool:
        """Check if two expressions are mathematically equal."""
        ...

    # ═══════════════════════════════════════════════════════════════
    # Vector Calculus
    # ═══════════════════════════════════════════════════════════════

    @abstractmethod
    def gradient(self, expr: Expression, coords: list[str],
                 context: MathContext | None = None) -> Expression:
        """Compute gradient of a scalar field."""
        ...

    @abstractmethod
    def divergence(self, expr: Expression, coords: list[str],
                   context: MathContext | None = None) -> Expression:
        """Compute divergence of a vector field."""
        ...

    @abstractmethod
    def curl(self, expr: Expression, coords: list[str],
             context: MathContext | None = None) -> Expression:
        """Compute curl of a vector field."""
        ...

    @abstractmethod
    def laplacian(self, expr: Expression, coords: list[str],
                  context: MathContext | None = None) -> Expression:
        """Compute Laplacian of a scalar field."""
        ...

    # ═══════════════════════════════════════════════════════════════
    # Matrix Operations
    # ═══════════════════════════════════════════════════════════════

    @abstractmethod
    def matrix_det(self, expr: Expression,
                   context: MathContext | None = None) -> Expression:
        """Compute determinant of a matrix."""
        ...

    @abstractmethod
    def matrix_inv(self, expr: Expression,
                   context: MathContext | None = None) -> Expression:
        """Compute inverse of a matrix."""
        ...

    @abstractmethod
    def matrix_eigenvals(self, expr: Expression,
                         context: MathContext | None = None) -> list[Expression]:
        """Compute eigenvalues of a matrix."""
        ...

    @abstractmethod
    def matrix_eigenvects(self, expr: Expression,
                          context: MathContext | None = None) -> list[dict[str, Any]]:
        """Compute eigenvectors of a matrix."""
        ...

    # ═══════════════════════════════════════════════════════════════
    # ODE, Limits, Series
    # ═══════════════════════════════════════════════════════════════

    @abstractmethod
    def dsolve(self, ode: Expression, func: str, var: str,
               context: MathContext | None = None) -> Expression:
        """Solve an ordinary differential equation."""
        ...

    @abstractmethod
    def limit(self, expr: Expression, var: str, point: str,
              direction: str = "+-",
              context: MathContext | None = None) -> Expression:
        """Compute limit of an expression."""
        ...

    @abstractmethod
    def series(self, expr: Expression, var: str, point: str,
               order: int = 6,
               context: MathContext | None = None) -> Expression:
        """Compute series expansion of an expression."""
        ...

    # ═══════════════════════════════════════════════════════════════
    # Integral Transforms
    # ═══════════════════════════════════════════════════════════════

    @abstractmethod
    def laplace_transform(self, expr: Expression, time_var: str, freq_var: str,
                          context: MathContext | None = None) -> Expression:
        """Compute Laplace transform of an expression."""
        ...

    @abstractmethod
    def inverse_laplace_transform(self, expr: Expression, freq_var: str, time_var: str,
                                  context: MathContext | None = None) -> Expression:
        """Compute inverse Laplace transform of an expression."""
        ...

    @abstractmethod
    def fourier_transform(self, expr: Expression, space_var: str, freq_var: str,
                          context: MathContext | None = None) -> Expression:
        """Compute Fourier transform of an expression."""
        ...

    @abstractmethod
    def inverse_fourier_transform(self, expr: Expression, freq_var: str, space_var: str,
                                  context: MathContext | None = None) -> Expression:
        """Compute inverse Fourier transform of an expression."""
        ...


class Verifier(ABC):
    """
    Abstract interface for derivation verification.

    Verifies that mathematical derivations are correct.
    """

    @abstractmethod
    def verify_step(
        self,
        step_input: Expression,
        step_output: Expression,
        operation: str,
        context: MathContext | None = None,
    ) -> VerificationResult:
        """Verify a single derivation step."""
        ...

    @abstractmethod
    def verify_derivation(
        self, derivation: Derivation, context: MathContext | None = None
    ) -> VerificationResult:
        """Verify an entire derivation."""
        ...

    @abstractmethod
    def check_dimensions(
        self, expr: Expression, expected_dimension: str | None = None
    ) -> VerificationResult:
        """Check dimensional consistency."""
        ...


class FormulaRepository(ABC):
    """
    Abstract interface for formula knowledge base.

    Provides access to known formulas and their derivations.
    """

    @abstractmethod
    def find_formula(self, name: str, domain: str | None = None) -> dict[str, Any] | None:
        """Find a formula by name."""
        ...

    @abstractmethod
    def list_formulas(
        self, domain: str | None = None, tags: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """List available formulas."""
        ...

    @abstractmethod
    def get_derivation(self, formula_name: str) -> Derivation | None:
        """Get the derivation of a formula if available."""
        ...
