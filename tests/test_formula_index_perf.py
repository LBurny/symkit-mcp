"""Performance smoke test for the persistent formula index.

Builds 500 synthetic YAML entries and asserts a cold index build and a
query stay within generous time budgets (guardrails against accidental
quadratic behavior, not microbenchmarks).
"""

from __future__ import annotations

import time

import pytest
import yaml

from symkit.application.formula_catalog import FormulaCatalog
from symkit.infrastructure.formula_files import YamlFormulaFileSource
from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore

N = 500


@pytest.fixture
def catalog(tmp_path):
    seed, staging, curated = (tmp_path / t for t in ("seed", "staging", "curated"))
    for d in (seed, staging, curated):
        d.mkdir()
    for i in range(N):
        d = curated / "synthetic"
        d.mkdir(exist_ok=True)
        (d / f"formula_{i:04d}.yaml").write_text(
            yaml.dump({
                "id": f"formula_{i:04d}",
                "name": f"Synthetic formula number {i}",
                "sympy_str": f"y_{i} = x_{i}**2 + {i}",
                "category": "synthetic",
                "tags": ["synthetic", f"group_{i % 10}"],
            }),
            encoding="utf-8",
        )
    store = SqliteFormulaIndexStore(tmp_path / "index.sqlite3")
    store.open()
    c = FormulaCatalog(
        store, YamlFormulaFileSource(),
        seed_dir=seed, staging_dir=staging, curated_dir=curated,
    )
    yield c
    store.close()


def test_cold_build_and_search_budgets(catalog):
    start = time.perf_counter()
    report = catalog.reindex()
    build_s = time.perf_counter() - start
    assert report.added == N
    assert build_s < 5.0, f"cold build of {N} entries took {build_s:.2f}s"

    start = time.perf_counter()
    results = catalog.search("synthetic formula", limit=5)
    search_ms = (time.perf_counter() - start) * 1000
    assert results
    assert search_ms < 100, f"search took {search_ms:.1f}ms"
