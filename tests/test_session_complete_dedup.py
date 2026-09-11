"""session_complete: deterministic staging ids, idempotent re-save, instant indexing."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit.application.formula_catalog import FormulaCatalog  # noqa: E402
from symkit.infrastructure import derivation_repository as repo_mod  # noqa: E402
from symkit.infrastructure.formula_files import YamlFormulaFileSource  # noqa: E402
from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore  # noqa: E402
from symkit_mcp.tools import _state  # noqa: E402
from symkit_mcp.tools import formula as formula_tools  # noqa: E402
from symkit_mcp.tools import math as math_tools  # noqa: E402
from symkit_mcp.tools import session as session_tools  # noqa: E402

# MockMCP is provided by conftest.py
# ruff: noqa: F821


@pytest.fixture
def env(fresh_session_manager, tmp_path, monkeypatch):
    """Wire a tmp-backed catalog whose staging dir matches the test repository."""
    _ = fresh_session_manager
    repo = repo_mod.get_repository()
    staging = repo._formulas_dir  # noqa: SLF001
    seed, curated = tmp_path / "seed", tmp_path / "curated"
    seed.mkdir()
    curated.mkdir()
    store = SqliteFormulaIndexStore(tmp_path / "index.sqlite3")
    store.open()
    catalog = FormulaCatalog(
        store, YamlFormulaFileSource(),
        seed_dir=seed, staging_dir=staging, curated_dir=curated,
    )
    monkeypatch.setattr(_state, "_catalog", catalog)
    mcp = MockMCP()
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    formula_tools.register_formula_tools(mcp)
    yield SimpleNamespace(mcp=mcp.tools, catalog=catalog, staging=staging)
    store.close()


def _derive_and_complete(tools, name: str, expression: str) -> dict:
    tools["session_start"](name)
    tools["session_load_formula"](expression)
    return tools["session_complete"](auto_save=True, description=f"{name} derivation")


class TestDeterministicStagingIds:
    def test_id_shape(self, env):
        result = _derive_and_complete(env.mcp, "pendulum", "T = 2*pi*sqrt(l/g)")
        assert result.get("saved_id"), result
        assert re.fullmatch(r"pendulum-[0-9a-f]{6}", result["saved_id"])

    def test_same_content_twice_single_entry(self, env):
        first = _derive_and_complete(env.mcp, "pendulum", "T = 2*pi*sqrt(l/g)")
        second = _derive_and_complete(env.mcp, "pendulum", "T = 2*pi*sqrt(l/g)")
        assert second["saved_id"] == first["saved_id"]
        yamls = list(env.staging.rglob("*.yaml"))
        assert len(yamls) == 1

    def test_different_content_different_id(self, env):
        first = _derive_and_complete(env.mcp, "pendulum", "T = 2*pi*sqrt(l/g)")
        second = _derive_and_complete(env.mcp, "pendulum", "T = 2*pi*sqrt(l/(2*g))")
        assert second["saved_id"] != first["saved_id"]
        assert len(list(env.staging.rglob("*.yaml"))) == 2

    def test_session_ids_merged_on_resave(self, env):
        _derive_and_complete(env.mcp, "pendulum", "T = 2*pi*sqrt(l/g)")
        second = _derive_and_complete(env.mcp, "pendulum", "T = 2*pi*sqrt(l/g)")
        repo = repo_mod.get_repository()
        saved = repo.get(second["saved_id"])
        assert saved is not None
        assert len(saved.session_ids) == 2


class TestInstantIndexing:
    def test_complete_immediately_searchable(self, env):
        result = _derive_and_complete(env.mcp, "pendulum", "T = 2*pi*sqrt(l/g)")
        hits = env.mcp["formula_search"]("pendulum", tier="staging")
        ids = [r["id"] for r in hits["results"]]
        assert result["saved_id"] in ids

    def test_search_by_expression_content(self, env):
        _derive_and_complete(env.mcp, "pendulum", "T = 2*pi*sqrt(l/g)")
        hits = env.mcp["formula_search"]("sqrt", tier="staging")
        assert hits["results"], "expression content must be searchable"
