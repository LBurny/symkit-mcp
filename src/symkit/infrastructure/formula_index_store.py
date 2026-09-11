"""SQLite FTS5-backed persistent formula index.

Implements the domain ``FormulaIndexStore`` port. The database is a
*rebuildable cache* over the YAML formula layers: corruption or schema
drift (``PRAGMA user_version`` mismatch) is handled by deleting the file
or dropping the tables and rebuilding from source.

Search routing: exact id/name/alias matches use normalized SQL columns;
tokens of length >= 3 go through the FTS5 trigram index (CJK and Latin
substrings); shorter tokens fall back to SQL LIKE on a normalized flat
text column.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from symkit.domain.formula_index import (
    GENERIC_TERMS,
    SEARCH_STOPWORDS,
    IndexedFormula,
    ManifestEntry,
    SearchHit,
)

_DASHES = "-‐‑‒–—―−﹣－"

# Bump when the schema changes; the index is rebuildable, so a mismatch
# simply drops and recreates the tables.
_SCHEMA_VERSION = 2


def _norm_key(text: str) -> str:
    """Normalize for exact/substring comparison: NFKC, lower, dash/underscore→space."""
    text = unicodedata.normalize("NFKC", text).lower()
    for ch in _DASHES:
        text = text.replace(ch, " ")
    text = text.replace("_", " ")
    return " ".join(text.split())


def _like_escape(token: str) -> str:
    """Escape LIKE wildcards so tokens match literally."""
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _fts_body(f: IndexedFormula) -> str:
    parts = [
        f.id, f.name, *f.aliases, *f.tags, f.description,
        f.domain, f.category, f.sympy_str,
    ]
    return _norm_key(" ".join(p for p in parts if p))


_SCHEMA = """
CREATE TABLE IF NOT EXISTS formulas (
  id TEXT PRIMARY KEY,
  id_norm TEXT NOT NULL DEFAULT '',
  tier TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  name_norm TEXT NOT NULL DEFAULT '',
  aliases_norm TEXT NOT NULL DEFAULT '[]',
  flat_text TEXT NOT NULL DEFAULT '',
  domain TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  verified INTEGER NOT NULL DEFAULT 0,
  content_hash TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT ''
);
CREATE VIRTUAL TABLE IF NOT EXISTS formulas_fts USING fts5(
  entry_id UNINDEXED, body, tokenize='trigram'
);
CREATE TABLE IF NOT EXISTS manifest (
  path TEXT PRIMARY KEY,
  mtime REAL NOT NULL,
  size INTEGER NOT NULL,
  entry_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS idx_formulas_hash ON formulas(content_hash);
CREATE INDEX IF NOT EXISTS idx_formulas_tier ON formulas(tier);
CREATE INDEX IF NOT EXISTS idx_formulas_name_norm ON formulas(name_norm);
"""

_DROP = """
DROP TABLE IF EXISTS formulas;
DROP TABLE IF EXISTS formulas_fts;
DROP TABLE IF EXISTS manifest;
DROP TABLE IF EXISTS meta;
"""

_UPSERT_SQL = """
INSERT INTO formulas (id, id_norm, tier, name, name_norm, aliases_norm, flat_text,
                      domain, category, verified, content_hash, source_path,
                      payload, updated_at)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(id) DO UPDATE SET
  id_norm=excluded.id_norm, tier=excluded.tier, name=excluded.name,
  name_norm=excluded.name_norm, aliases_norm=excluded.aliases_norm,
  flat_text=excluded.flat_text, domain=excluded.domain, category=excluded.category,
  verified=excluded.verified, content_hash=excluded.content_hash,
  source_path=excluded.source_path, payload=excluded.payload,
  updated_at=excluded.updated_at
"""


class SqliteFormulaIndexStore:
    """SQLite implementation of the formula index storage port."""

    def __init__(self, index_path: Path):
        self._path = Path(index_path)
        self._memory = str(index_path) == ":memory:"
        self._conn: sqlite3.Connection | None = None

    # ── lifecycle ────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the database, creating the schema; rebuild if corrupted/stale."""
        if not self._memory:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._connect()
            self._create_schema()
            self._require().execute("SELECT count(*) FROM formulas").fetchone()
        except sqlite3.DatabaseError:
            if self._memory:
                raise
            self._discard_files()
            self._connect()
            self._create_schema()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def clear(self) -> None:
        conn = self._require()
        with conn:
            conn.execute("DELETE FROM formulas")
            conn.execute("DELETE FROM formulas_fts")
            conn.execute("DELETE FROM manifest")

    def _connect(self) -> None:
        # check_same_thread=False: the MCP server warms the catalog up in a
        # worker thread but serves tool calls on the asyncio loop thread.
        # Tool handlers are serialized by the loop, so the single connection
        # is never used concurrently.
        target = ":memory:" if self._memory else str(self._path)
        self._conn = sqlite3.connect(target, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if not self._memory:
            self._conn.execute("PRAGMA journal_mode=WAL")

    def _create_schema(self) -> None:
        assert self._conn is not None
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        with self._conn:
            if version != _SCHEMA_VERSION:
                self._conn.executescript(_DROP)
            self._conn.executescript(_SCHEMA)
            self._conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    def _discard_files(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        for suffix in ("", "-wal", "-shm"):
            self._path.with_suffix(self._path.suffix + suffix).unlink(missing_ok=True)

    def _require(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("store is not open")
        return self._conn

    # ── writes ───────────────────────────────────────────────────────────

    def upsert_many(self, entries: list[IndexedFormula]) -> None:
        conn = self._require()
        now = datetime.now().isoformat()
        with conn:
            for e in entries:
                aliases_norm = json.dumps(
                    [_norm_key(a) for a in e.aliases], ensure_ascii=False
                )
                body = _fts_body(e)
                conn.execute(
                    _UPSERT_SQL,
                    (
                        e.id,
                        _norm_key(e.id),
                        e.tier,
                        e.name,
                        _norm_key(e.name),
                        aliases_norm,
                        body,
                        e.domain,
                        e.category,
                        1 if e.verified else 0,
                        e.content_hash,
                        e.source_path,
                        json.dumps(e.to_dict(), ensure_ascii=False),
                        now,
                    ),
                )
                conn.execute("DELETE FROM formulas_fts WHERE entry_id = ?", (e.id,))
                conn.execute(
                    "INSERT INTO formulas_fts (entry_id, body) VALUES (?, ?)",
                    (e.id, body),
                )

    def remove_ids(self, ids: list[str]) -> None:
        conn = self._require()
        with conn:
            for fid in ids:
                conn.execute("DELETE FROM formulas WHERE id = ?", (fid,))
                conn.execute("DELETE FROM formulas_fts WHERE entry_id = ?", (fid,))
                conn.execute("DELETE FROM manifest WHERE entry_id = ?", (fid,))

    # ── reads ────────────────────────────────────────────────────────────

    def get(self, formula_id: str) -> IndexedFormula | None:
        row = self._require().execute(
            "SELECT payload FROM formulas WHERE id = ?", (formula_id,)
        ).fetchone()
        return IndexedFormula.from_dict(json.loads(row["payload"])) if row else None

    def all(self) -> list[IndexedFormula]:
        rows = self._require().execute("SELECT payload FROM formulas").fetchall()
        return [IndexedFormula.from_dict(json.loads(r["payload"])) for r in rows]

    def search(
        self,
        query: str,
        *,
        tier: str | None = None,
        domain: str | None = None,
        category: str | None = None,
        prelimit: int = 200,
    ) -> list[SearchHit]:
        q = _norm_key(query)
        if not q and not tier and not domain and not category:
            return []
        where, params = self._filters("", tier, domain, category)
        if not q:
            rows = self._select_rows(where, params)
            return [
                SearchHit(self._to_formula(r), "browse", 0.5) for r in rows[:prelimit]
            ]

        conn = self._require()
        hits: dict[str, SearchHit] = {}
        tokens = [t.replace('"', "") for t in q.split() if t.replace('"', "")]
        where_sql = f" AND {where}" if where else ""

        # Exact id / name matches via normalized columns. These bypass the
        # discriminative-token rule: an entry literally named "law" still
        # resolves for the query "law".
        for column, kind in (("id_norm", "exact_id"), ("name_norm", "exact_name")):
            rows = conn.execute(
                f"SELECT payload FROM formulas WHERE {column} = ?{where_sql}",
                [q, *params],
            ).fetchall()
            for row in rows:
                f = self._to_formula(row)
                hits.setdefault(f.id, SearchHit(f, kind, 1.0))
        # Exact alias: JSON-array LIKE narrows candidates, Python confirms.
        like_pat = f'%"{_like_escape(q)}"%'
        rows = conn.execute(
            "SELECT payload FROM formulas WHERE aliases_norm LIKE ? ESCAPE '\\'"
            + where_sql,
            [like_pat, *params],
        ).fetchall()
        for row in rows:
            f = self._to_formula(row)
            if any(_norm_key(a) == q for a in f.aliases):
                hits.setdefault(f.id, SearchHit(f, "exact_alias", 1.0))

        basis = self._match_basis(tokens)
        if basis:
            long_basis = [t for t in basis if len(t) >= 3]
            short_basis = [t for t in basis if len(t) < 3]
            if long_basis:
                self._fts_hits(long_basis, tokens, tier, domain, category, hits)
            if short_basis or not long_basis:
                clauses = " AND ".join(["flat_text LIKE ? ESCAPE '\\'"] * len(tokens))
                sql = "SELECT payload, flat_text FROM formulas"
                sql += f" WHERE {clauses}{where_sql}" if clauses else f" WHERE {where}"
                rows = conn.execute(
                    sql, [f"%{_like_escape(t)}%" for t in tokens] + params
                ).fetchall()
                for row in rows:
                    f = self._to_formula(row)
                    if self._qualifies(row["flat_text"], tokens, basis):
                        hits.setdefault(f.id, SearchHit(f, "like", 0.35))
        return list(hits.values())[:prelimit]

    # ── manifest / stats ─────────────────────────────────────────────────

    def manifest(self) -> dict[str, ManifestEntry]:
        rows = self._require().execute(
            "SELECT path, mtime, size, entry_id FROM manifest"
        ).fetchall()
        return {
            r["path"]: ManifestEntry(r["path"], r["mtime"], r["size"], r["entry_id"])
            for r in rows
        }

    def set_manifest(self, entries: list[ManifestEntry]) -> None:
        conn = self._require()
        with conn:
            conn.execute("DELETE FROM manifest")
            conn.executemany(
                "INSERT INTO manifest (path, mtime, size, entry_id) VALUES (?,?,?,?)",
                [(e.path, e.mtime, e.size, e.entry_id) for e in entries],
            )
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('last_sync', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (datetime.now().isoformat(),),
            )

    def stats(self) -> dict[str, Any]:
        conn = self._require()
        total = conn.execute("SELECT count(*) AS c FROM formulas").fetchone()["c"]
        tiers = {
            r["tier"]: r["c"]
            for r in conn.execute(
                "SELECT tier, count(*) AS c FROM formulas GROUP BY tier"
            )
        }
        dup_rows = conn.execute(
            "SELECT content_hash, count(*) AS c FROM formulas "
            "WHERE content_hash != '' GROUP BY content_hash HAVING c > 1"
        ).fetchall()
        last_sync = conn.execute(
            "SELECT value FROM meta WHERE key = 'last_sync'"
        ).fetchone()
        return {
            "path": str(self._path),
            "total": total,
            "tiers": tiers,
            "duplicate_groups": len(dup_rows),
            "duplicate_entries": sum(r["c"] - 1 for r in dup_rows),
            "last_sync": last_sync["value"] if last_sync else None,
        }

    # ── internals ────────────────────────────────────────────────────────

    def _filters(
        self, prefix: str, tier: str | None, domain: str | None, category: str | None
    ) -> tuple[str, list[str]]:
        clauses: list[str] = []
        params: list[str] = []
        for column, value in (("tier", tier), ("domain", domain), ("category", category)):
            if value:
                clauses.append(f"{prefix}{column} = ?")
                params.append(value)
        return (" AND ".join(clauses), params)

    def _select_rows(self, where: str, params: list[str]) -> list[sqlite3.Row]:
        sql = "SELECT payload FROM formulas"
        if where:
            sql += " WHERE " + where
        return self._require().execute(sql, params).fetchall()

    @staticmethod
    def _match_basis(tokens: list[str]) -> list[str]:
        """Return the tokens that may justify a non-exact hit.

        Discriminative tokens always may. A query made *entirely* of generic
        domain nouns keeps the legacy low-relevance behaviour; a query whose
        only stopwords are function words justifies nothing at all.
        """
        content = [t for t in tokens if t not in SEARCH_STOPWORDS]
        if content:
            return content
        if tokens and all(t in GENERIC_TERMS for t in tokens):
            return list(tokens)
        return []

    @staticmethod
    def _qualifies(flat_text: str, tokens: list[str], basis: list[str]) -> bool:
        """A row matches only if every token is present *and* a basis token is."""
        return (
            all(t in flat_text for t in tokens)
            and any(b in flat_text for b in basis)
        )

    def _fts_hits(
        self,
        long_basis: list[str],
        tokens: list[str],
        tier: str | None,
        domain: str | None,
        category: str | None,
        hits: dict[str, SearchHit],
    ) -> None:
        match = " OR ".join(f'"{t}"' for t in long_basis)
        where, params = self._filters("f.", tier, domain, category)
        sql = (
            "SELECT f.payload, f.flat_text, bm25(formulas_fts) AS bm "
            "FROM formulas_fts JOIN formulas f ON f.id = formulas_fts.entry_id "
            "WHERE formulas_fts MATCH ?"
        )
        if where:
            sql += " AND " + where
        rows = self._require().execute(sql, [match, *params]).fetchall()
        # FTS matched on basis tokens; still require every query token present
        # so a partial match on a narrowed query does not leak through.
        rows = [r for r in rows if all(t in r["flat_text"] for t in tokens)]
        if not rows:
            return
        bms = [r["bm"] for r in rows]
        best, worst = min(bms), max(bms)
        for row in rows:
            f = self._to_formula(row)
            if f.id in hits:
                continue
            rel = 1.0 if best == worst else (row["bm"] - worst) / (best - worst)
            hits[f.id] = SearchHit(f, "fts", 0.5 + 0.2 * rel)

    @staticmethod
    def _to_formula(row: sqlite3.Row) -> IndexedFormula:
        return IndexedFormula.from_dict(json.loads(row["payload"]))
