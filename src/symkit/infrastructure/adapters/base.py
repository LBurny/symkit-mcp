"""
Base Adapter - Base class for formula adapters

Defines the unified interface for all formula source adapters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sympy import Expr


@dataclass
class FormulaInfo:
    """
    Unified format for formula information

    All adapters should return this format so that upper layers can handle it uniformly.
    """

    # Identification
    id: str  # Unique identifier (e.g., Wikidata Q number)
    name: str  # Formula name

    # Mathematical representation
    expression: Expr | str  # SymPy expression or string
    latex: str = ""  # LaTeX representation
    sympy_str: str = ""  # SymPy string representation

    # Variable definitions
    variables: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Format: {"rho": {"description": "density", "unit": "kg/m³", "type": "variable"}}

    # Metadata
    source: str = ""  # Source ("wikidata", "biomodels", "scipy")
    category: str = ""  # Category
    description: str = ""  # Description
    tags: list[str] = field(default_factory=list)

    # Links
    url: str = ""  # Original source URL
    references: list[str] = field(default_factory=list)

    # Extra data (source-specific)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "expression": str(self.expression),
            "latex": self.latex,
            "sympy_str": self.sympy_str,
            "variables": self.variables,
            "source": self.source,
            "category": self.category,
            "description": self.description,
            "tags": self.tags,
            "url": self.url,
            "references": self.references,
            "extra": self.extra,
        }


class BaseAdapter(ABC):
    """
    Base class for formula adapters

    All formula sources (Wikidata, BioModels, SciPy, etc.) should inherit from this class.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Adapter source name."""
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[FormulaInfo]:
        """
        Search for formulas

        Args:
            query: Search keyword
            limit: Maximum number of results to return

        Returns:
            List of matching formulas
        """
        ...

    @abstractmethod
    def get_formula(self, formula_id: str) -> FormulaInfo | None:
        """
        Get details of a single formula

        Args:
            formula_id: Formula identifier

        Returns:
            Formula information or None
        """
        ...

    def list_categories(self) -> list[str]:
        """List all categories (optional implementation)."""
        return []

    def list_formulas(self, category: str | None = None) -> list[str]:  # noqa: ARG002
        """List formula IDs (optional implementation)."""
        return []
