"""FormulaCatalog — application-layer orchestration over the formula index.

Coordinates the three YAML layers (seed / staging / curated), the persistent
index store, and the file source. All index mutations flow through
``ensure_fresh``'s manifest diff so there is exactly one sync code path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from symkit.domain.formula_index import (
    TIER_CURATED,
    TIER_SEED,
    TIER_STAGING,
    FormulaIndexStore,
    IndexedFormula,
    ManifestEntry,
    RankedResult,
    SyncReport,
)
from symkit.domain.formula_library import MODELED_FIELDS, FormulaEntry
from symkit.domain.formula_ranker import rank_hits
from symkit.infrastructure.formula_identity import content_hash, slugify, structural_hash

# Identifier tokens worth probing the text channel with; shorter names (single
# physics variables like ``v``, ``g``) carry no retrieval signal.
_IDENTIFIER_RE = re.compile(r"[^\W\d]\w*", re.UNICODE)
_TEXT_TOKEN_MIN = 3
# Ranked text hits below this score are noise, not "similar" formulas.
_TEXT_SCORE_THRESHOLD = 0.5


def _text_probe(expression_str: str) -> str:
    """Extract discriminative identifier tokens from an expression string."""
    tokens = [
        tok for tok in _IDENTIFIER_RE.findall(expression_str)
        if len(tok) >= _TEXT_TOKEN_MIN
    ]
    return " ".join(dict.fromkeys(tokens))


class FormulaFileSource(Protocol):
    """Port for scanning and loading formula YAML files."""

    def scan(self, root: Path) -> list[Path]: ...
    def load(self, path: Path, tier: str) -> IndexedFormula | None: ...


def _promotable_extra(src: IndexedFormula) -> dict[str, Any]:
    """Metadata the index does not model, read back from the staging YAML.

    ``promote`` rewrites the entry through :class:`FormulaEntry`, which models
    only part of a stored entry. Without this passthrough the rewrite dropped
    ``verified: true`` — along with assumptions, limitations, derivation_steps
    and session_ids — from the promoted copy.
    """
    if not src.source_path:
        return {}
    try:
        data = yaml.safe_load(Path(src.source_path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if key not in MODELED_FIELDS}


@dataclass
class FormulaCatalog:
    """Coordinates YAML layers and the persistent index store."""

    store: FormulaIndexStore
    file_source: FormulaFileSource
    seed_dir: Path
    staging_dir: Path
    curated_dir: Path

    # ── sync ─────────────────────────────────────────────────────────────

    def ensure_fresh(self) -> SyncReport:
        """Reconcile the index with the YAML layers via manifest diff."""
        report = SyncReport()
        old = self.store.manifest()
        seen: set[str] = set()
        batch: list[IndexedFormula] = []
        manifest_rows: list[ManifestEntry] = []
        for tier, root in (
            (TIER_SEED, self.seed_dir),
            (TIER_STAGING, self.staging_dir),
            (TIER_CURATED, self.curated_dir),
        ):
            for path in self.file_source.scan(root):
                key = str(path)
                seen.add(key)
                st = path.stat()
                prev = old.get(key)
                if prev and prev.mtime == st.st_mtime and prev.size == st.st_size:
                    manifest_rows.append(prev)
                    continue
                loaded = self.file_source.load(path, tier)
                if loaded is None:
                    report.failed += 1
                    report.failed_paths.append(key)
                    continue
                batch.append(loaded)
                manifest_rows.append(ManifestEntry(key, st.st_mtime, st.st_size, loaded.id))
                if prev:
                    report.updated += 1
                else:
                    report.added += 1
        stale_ids = [m.entry_id for p, m in old.items() if p not in seen]
        if batch:
            # Order matters: curated upserts last, winning same-id overrides.
            self.store.upsert_many(batch)
        if stale_ids:
            self.store.remove_ids(stale_ids)
        if batch or stale_ids:
            # Nothing changed → keep the existing manifest untouched so
            # read-path ensure_fresh calls stay cheap.
            self.store.set_manifest(manifest_rows)
        report.removed = len(stale_ids)
        return report

    def reindex(self) -> SyncReport:
        """Drop all index rows and rebuild from the YAML layers."""
        self.store.clear()
        return self.ensure_fresh()

    # ── reads ────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        tier: str | None = None,
        domain: str | None = None,
        category: str | None = None,
        limit: int = 10,
    ) -> list[RankedResult]:
        self.ensure_fresh()
        hits = self.store.search(query, tier=tier, domain=domain, category=category)
        return rank_hits(hits, limit=limit)

    def get(self, formula_id: str) -> IndexedFormula | None:
        self.ensure_fresh()
        return self.store.get(formula_id)

    def all(self) -> list[IndexedFormula]:
        self.ensure_fresh()
        return self.store.all()

    def stats(self) -> dict[str, Any]:
        self.ensure_fresh()
        return self.store.stats()

    def find_similar(
        self,
        expression_str: str,
        *,
        limit: int = 3,
        exclude_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find formulas similar to ``expression_str``.

        Returns ``[{"id", "name", "tier", "score", "match"}]`` where ``match``
        is ``"structural"`` (alpha-invariant fingerprint hit) or ``"text"``
        (FTS fallback on discriminative expression tokens). ``exclude_id`` and
        entries whose ``content_hash`` equals the probe's are never returned.
        """
        self.ensure_fresh()
        digest = structural_hash(expression_str)
        own_content = content_hash(expression_str)
        seen: set[str] = set()
        results: list[dict[str, Any]] = []

        def _skip(f: IndexedFormula) -> bool:
            return f.id == exclude_id or (bool(own_content) and f.content_hash == own_content)

        if digest:
            for f in self.store.find_by_structural_hash(digest):
                if _skip(f):
                    continue
                seen.add(f.id)
                results.append(
                    {"id": f.id, "name": f.name, "tier": f.tier,
                     "score": 1.0, "match": "structural"}
                )
        if len(results) < limit:
            probe = _text_probe(expression_str)
            if probe:
                ranked = rank_hits(self.store.search(probe), limit=limit + len(seen) + 10)
                for r in ranked:
                    if len(results) >= limit:
                        break
                    f = r.formula
                    if f.id in seen or _skip(f) or r.score < _TEXT_SCORE_THRESHOLD:
                        continue
                    seen.add(f.id)
                    results.append(
                        {"id": f.id, "name": f.name, "tier": f.tier,
                         "score": round(r.score, 4), "match": "text"}
                    )
        return results[:limit]

    # ── writes ───────────────────────────────────────────────────────────

    def add_entry(self, entry: FormulaEntry) -> IndexedFormula:
        """Write a curated YAML and make it searchable immediately."""
        from symkit.infrastructure.formula_files import write_entry_yaml

        write_entry_yaml(self.curated_dir, entry)
        self.ensure_fresh()
        indexed = self.store.get(entry.id)
        assert indexed is not None  # write_entry_yaml + ensure_fresh guarantee it
        return indexed

    def remove_entry(self, formula_id: str) -> list[str]:
        """Remove a formula's YAML and index row. Seeds are read-only."""
        # Reconcile first: the entry may have been written by hand or by
        # another process since the last refresh.
        self.ensure_fresh()
        row = self.store.get(formula_id)
        if row is None or row.tier == TIER_SEED:
            return []
        root = self.staging_dir if row.tier == TIER_STAGING else self.curated_dir
        if row.source_path:
            path = Path(row.source_path)
            try:
                path.relative_to(root)
            except ValueError:
                return []
            path.unlink(missing_ok=True)
        self.ensure_fresh()
        return [row.tier]

    def promote(
        self,
        formula_id: str,
        *,
        new_id: str | None = None,
        name: str | None = None,
        aliases: list[str] | None = None,
        tags: list[str] | None = None,
        description: str | None = None,
        domain: str | None = None,
        category: str | None = None,
    ) -> IndexedFormula:
        """Promote a staging formula into the curated tier."""
        from symkit.infrastructure.formula_files import write_entry_yaml

        # Reconcile first: the staging entry may have been written by hand or
        # by another process since the last refresh.
        self.ensure_fresh()
        src = self.store.get(formula_id)
        if src is None:
            raise ValueError(f"Formula '{formula_id}' not found")
        if src.tier != TIER_STAGING:
            raise ValueError(
                f"Only staging formulas can be promoted; '{formula_id}' is {src.tier}"
            )
        target_id = new_id or slugify(name or src.name) or src.id
        if target_id != src.id and self.store.get(target_id) is not None:
            raise ValueError(f"Formula id '{target_id}' already exists")

        entry = FormulaEntry(
            id=target_id,
            name=name or src.name,
            sympy_str=src.sympy_str,
            latex=src.latex,
            domain=domain or src.domain,
            category=category or src.category or "uncategorized",
            description=description or src.description,
            aliases=list(aliases) if aliases is not None else list(src.aliases),
            tags=list(tags) if tags is not None else list(src.tags),
            variables=dict(src.variables),
            references=list(src.references),
            extra=_promotable_extra(src),
        )
        write_entry_yaml(self.curated_dir, entry, curated=True)
        if src.source_path:
            staging_path = Path(src.source_path)
            try:
                staging_path.relative_to(self.staging_dir)
            except ValueError:
                staging_path = None  # type: ignore[assignment]
            if staging_path is not None:
                staging_path.unlink(missing_ok=True)
        self.ensure_fresh()
        promoted = self.store.get(target_id)
        assert promoted is not None
        return promoted
