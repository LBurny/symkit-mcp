"""
Derivation Results Repository

Manages DERIVED formulas — new formulas created through
verified derivation processes.

What belongs here:
✅ Derived formulas from any mathematical domain
✅ Results of symbolic derivation sessions
✅ Verified and reusable formula artifacts

What does NOT belong here:
❌ Basic textbook formulas → Use sympy-mcp or look them up
❌ Standard physical constants → Use formula_constants()
❌ Raw user input → Temporary and session-scoped
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sympy import Basic, sympify

from symkit.domain.paths import user_derived_dir


@dataclass
class DerivationResult:
    """
    A formula that was derived and verified through SymKit.

    This represents the OUTPUT of a derivation process, not a textbook formula.
    """

    # Identification
    id: str
    name: str
    expression: str  # SymPy expression string
    version: str = "1.0.0"
    variables: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Derivation provenance
    derived_from: list[str] = field(default_factory=list)  # Base formulas used
    derivation_steps: list[str] = field(default_factory=list)  # Step descriptions
    assumptions: list[str] = field(default_factory=list)

    # Verification status
    verified: bool = False
    verification_method: str = ""  # e.g., "reverse_derivative", "dimensional_analysis"
    verified_at: str | None = None

    # Metadata
    category: str = ""
    domain: str = ""  # Math domain tag (e.g., "fluid_dynamics", "quantum_mechanics")
    tags: list[str] = field(default_factory=list)
    description: str = ""
    application_context: str = ""  # When/where to use this formula
    limitations: list[str] = field(default_factory=list)

    # References
    references: list[str] = field(default_factory=list)
    author: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_sympy(self) -> Basic:
        """Convert expression string to SymPy expression."""
        return sympify(self.expression)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "expression": self.expression,
            "variables": self.variables,
            "derived_from": self.derived_from,
            "derivation_steps": self.derivation_steps,
            "assumptions": self.assumptions,
            "verified": self.verified,
            "verification_method": self.verification_method,
            "verified_at": self.verified_at,
            "category": self.category,
            "tags": self.tags,
            "domain": self.domain,
            "description": self.description,
            "application_context": self.application_context,
            "limitations": self.limitations,
            "references": self.references,
            "author": self.author,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DerivationResult":
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "DerivationResult":
        """Create from YAML string."""
        data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)


class DerivationRepository:
    """
    Repository for storing and retrieving derived formulas.

    Derivation results can be:
    1. Registered programmatically during a session
    2. Loaded from YAML files in formulas/ directory
    3. Saved for future reuse
    """

    def __init__(self, formulas_dir: Path | None = None):
        self._results: dict[str, DerivationResult] = {}
        self._formulas_dir = formulas_dir

        if formulas_dir and formulas_dir.exists():
            self._load_from_directory(formulas_dir)

    def _load_from_directory(self, directory: Path) -> None:
        """Load derivation results from YAML files."""
        for yaml_file in directory.rglob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "id" in data:
                        result = DerivationResult.from_dict(data)
                        self._results[result.id] = result
            except Exception:
                pass  # Skip invalid files

    def register(self, result: DerivationResult) -> None:
        """Register a new derivation result."""
        self._results[result.id] = result

    def get(self, result_id: str) -> DerivationResult | None:
        """Get a derivation result by ID."""
        return self._results.get(result_id)

    def list_all(self, category: str | None = None) -> list[str]:
        """List all derivation result IDs."""
        if category is None:
            return list(self._results.keys())
        return [rid for rid, r in self._results.items() if r.category == category]

    def search(self, query: str) -> list[DerivationResult]:
        """Search derivation results by keyword."""
        results = []
        query_lower = query.lower()
        for result in self._results.values():
            if (
                query_lower in result.name.lower()
                or query_lower in result.description.lower()
                or any(query_lower in tag.lower() for tag in result.tags)
            ):
                results.append(result)
        return results

    def save(self, result_id: str, directory: Path | None = None) -> Path:
        """Save a derivation result to YAML file."""
        result = self._results.get(result_id)
        if result is None:
            raise ValueError(f"Derivation result '{result_id}' not found")

        save_dir = directory or self._formulas_dir
        if save_dir is None:
            raise ValueError("No directory specified for saving")

        # Create category subdirectory
        category_dir = save_dir / result.category if result.category else save_dir
        category_dir.mkdir(parents=True, exist_ok=True)

        # Save as YAML
        file_path = category_dir / f"{result.id}.yaml"
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(result.to_dict(), f, default_flow_style=False, allow_unicode=True)

        return file_path

    def update(
        self,
        result_id: str,
        **updates: Any,
    ) -> DerivationResult:
        """
        Update a derivation result's metadata.

        Args:
            result_id: The ID of the derivation result to update
            **updates: Fields to update (description, clinical_context, tags, etc.)

        Returns:
            Updated DerivationResult

        Raises:
            ValueError: If result_id not found
        """
        result = self._results.get(result_id)
        if result is None:
            raise ValueError(f"Derivation result '{result_id}' not found")

        # Update allowed fields
        allowed_fields = {
            "name",
            "description",
            "domain",
            "application_context",
            "assumptions",
            "limitations",
            "references",
            "tags",
            "category",
            "version",
            "verified",
            "verification_method",
            "verified_at",
        }

        for key, value in updates.items():
            if key in allowed_fields and hasattr(result, key):
                setattr(result, key, value)

        return result

    def delete(self, result_id: str, delete_file: bool = True) -> bool:
        """
        Delete a derivation result.

        Args:
            result_id: The ID of the derivation result to delete
            delete_file: Whether to delete the YAML file (default: True)

        Returns:
            True if deleted, False if not found
        """
        result = self._results.get(result_id)
        if result is None:
            return False

        # Delete from memory
        del self._results[result_id]

        # Delete file if requested
        if delete_file and self._formulas_dir:
            category_dir = (
                self._formulas_dir / result.category if result.category else self._formulas_dir
            )
            file_path = category_dir / f"{result_id}.yaml"
            if file_path.exists():
                file_path.unlink()

        return True

    def stats(self) -> dict[str, Any]:
        """Get repository statistics."""
        categories: dict[str, int] = {}
        verified_count = 0

        for result in self._results.values():
            cat = result.category or "uncategorized"
            categories[cat] = categories.get(cat, 0) + 1
            if result.verified:
                verified_count += 1

        return {
            "total": len(self._results),
            "verified": verified_count,
            "unverified": len(self._results) - verified_count,
            "categories": categories,
        }


# Default location for derived formula results (output of session_complete).
# Resolves to a per-user data directory so results persist across runs from any
# working directory after ``pip install``. Tests override via ``get_repository``
# reset / explicit ``formulas_dir``.
DEFAULT_DERIVED_PATH = user_derived_dir()

# Global repository instance
_repository: DerivationRepository | None = None


def get_repository(formulas_dir: Path | None = None) -> DerivationRepository:
    """Get the global derivation repository instance.

    The first call constructs the singleton at ``formulas_dir`` (or the default
    per-user derived-formula directory if omitted). Subsequent calls return the
    same instance regardless of ``formulas_dir``; tests that need isolation
    reset ``_repository`` to ``None`` before invoking this.
    """
    global _repository
    if _repository is None:
        _repository = DerivationRepository(formulas_dir or DEFAULT_DERIVED_PATH)
    return _repository
