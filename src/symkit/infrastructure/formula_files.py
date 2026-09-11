"""YAML file scanning/loading/writing for the formula library layers.

Scanning skips directories and files whose names start with ``_`` or ``.``
(``_quarantine`` lives under the staging dir and must never be indexed).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from symkit.domain.formula_index import IndexedFormula
from symkit.domain.formula_library import FormulaEntry
from symkit.domain.formula_paths import UnsafeFormulaPathError, safe_entry_path
from symkit.infrastructure.formula_identity import content_hash

__all__ = [
    "UnsafeFormulaPathError",
    "YamlFormulaFileSource",
    "load_indexed",
    "scan_formula_files",
    "write_entry_yaml",
]


def scan_formula_files(root: Path) -> list[Path]:
    """Return indexable YAML files under ``root`` (skips ``_``/``.`` prefixed parts)."""
    if not root.exists():
        return []
    out: list[Path] = []
    for path in sorted(root.rglob("*.yaml")):
        rel = path.relative_to(root)
        if any(part.startswith(("_", ".")) for part in rel.parts):
            continue
        out.append(path)
    return out


def load_indexed(path: Path, tier: str) -> IndexedFormula | None:
    """Load one YAML file into an IndexedFormula; None if unreadable or id-less."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("id"):
        return None
    entry = FormulaEntry.from_dict(data, source_path=path)
    indexed = IndexedFormula.from_entry(
        entry,
        tier=tier,
        content_hash=content_hash(entry.sympy_str or entry.latex),
        verified=bool(data.get("verified", False)),
        application_context=str(data.get("application_context", "") or ""),
        derivation_steps=[str(s) for s in (data.get("derivation_steps") or [])],
    )
    indexed.created_at = str(data.get("created_at", "") or "")
    return indexed


def write_entry_yaml(root: Path, entry: FormulaEntry) -> Path:
    """Persist an entry as ``<root>/<category>/<id>.yaml``; return the path.

    Raises :class:`UnsafeFormulaPathError` before touching the filesystem if
    the id or category would escape ``root``.
    """
    target_path = safe_entry_path(root, entry.category, entry.id)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as f:
        yaml.dump(entry.to_dict(), f, allow_unicode=True, sort_keys=False)
    entry.source_path = target_path
    return target_path


class YamlFormulaFileSource:
    """File-source adapter injected into FormulaCatalog (testable seam)."""

    def scan(self, root: Path) -> list[Path]:
        return scan_formula_files(root)

    def load(self, path: Path, tier: str) -> IndexedFormula | None:
        return load_indexed(path, tier)
