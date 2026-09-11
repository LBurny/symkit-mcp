"""Quarantine junk staging formulas (test scaffolding, e2e residue).

Junk rules: ``author`` ending in ``_test``, names used by test fixtures
(``verified_test`` / ``inconclusive_test``), or names/ids containing
``e2e_test`` / ``mcp_e2e``. Matches are moved to ``<staging>/_quarantine/``
(skipped by the index scanner); nothing is deleted.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from symkit.infrastructure.formula_files import scan_formula_files

_JUNK_NAMES = {"verified_test", "inconclusive_test"}


def _is_junk(data: dict[str, Any]) -> bool:
    author = str(data.get("author", "") or "")
    name = str(data.get("name", "") or "")
    fid = str(data.get("id", "") or "")
    if author.endswith("_test"):
        return True
    if name in _JUNK_NAMES:
        return True
    return "e2e_test" in name or "mcp_e2e" in name or "mcp_e2e" in fid


@dataclass
class PrunePlan:
    """Planned quarantine moves plus the files that stay."""

    moves: list[tuple[Path, Path]] = field(default_factory=list)
    kept: list[Path] = field(default_factory=list)


def plan_prune(staging_dir: Path) -> PrunePlan:
    """Plan quarantine moves for junk entries under ``staging_dir``."""
    plan = PrunePlan()
    for path in scan_formula_files(staging_dir):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            data = None
        if isinstance(data, dict) and _is_junk(data):
            rel = path.relative_to(staging_dir)
            plan.moves.append((path, staging_dir / "_quarantine" / rel))
        else:
            plan.kept.append(path)
    return plan


def execute_prune(plan: PrunePlan) -> int:
    """Execute the planned moves; returns the number of files moved."""
    moved = 0
    for src, dst in plan.moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved += 1
    return moved
