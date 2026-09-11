"""Tests for YAML layer path safety and writing.

The library root must contain every file the catalog writes: an id, category,
or promote target that escapes it is a path-traversal defect, not a valid
entry (found by the sandbox probe).
"""

from __future__ import annotations

import pytest
import yaml

from symkit.application.formula_catalog import FormulaCatalog
from symkit.domain.formula_library import FormulaEntry
from symkit.infrastructure.formula_files import (
    UnsafeFormulaPathError,
    YamlFormulaFileSource,
    write_entry_yaml,
)
from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore


@pytest.fixture
def env(tmp_path):
    seed, staging, curated = (tmp_path / t for t in ("seed", "staging", "curated"))
    for d in (seed, staging, curated):
        d.mkdir()
    store = SqliteFormulaIndexStore(tmp_path / "index.sqlite3")
    store.open()
    catalog = FormulaCatalog(
        store, YamlFormulaFileSource(),
        seed_dir=seed, staging_dir=staging, curated_dir=curated,
    )
    yield catalog, curated, staging, tmp_path
    store.close()


def _entry(fid: str, category: str = "lab") -> FormulaEntry:
    return FormulaEntry(id=fid, name=fid, sympy_str="a = 1", category=category)


class TestWritePathSafety:
    @pytest.mark.parametrize("bad_id", [
        "../../escaped",
        "..",
        "sub/dir/entry",
        "..\\escaped",
        "/absolute",
        "C:/absolute",
    ])
    def test_traversal_id_rejected(self, env, bad_id):
        catalog, curated, _, tmp_path = env
        with pytest.raises(UnsafeFormulaPathError):
            catalog.add_entry(_entry(bad_id))
        # Nothing may be written outside the curated root.
        assert not (tmp_path / "escaped.yaml").exists()
        assert not (curated.parent / "escaped.yaml").exists()

    @pytest.mark.parametrize("bad_category", ["../../outside", "..", "a/../../b"])
    def test_traversal_category_rejected(self, env, bad_category):
        catalog, curated, _, tmp_path = env
        with pytest.raises(UnsafeFormulaPathError):
            catalog.add_entry(_entry("safe_id", category=bad_category))
        assert not (tmp_path / "outside").exists()
        assert not (curated.parent / "outside").exists()

    def test_promote_traversal_new_id_rejected(self, env):
        catalog, curated, staging, tmp_path = env
        (staging / "lab").mkdir(parents=True, exist_ok=True)
        (staging / "lab" / "stg1.yaml").write_text(
            yaml.dump({"id": "stg1", "name": "Staging", "sympy_str": "z = 1",
                       "category": "lab"}),
            encoding="utf-8",
        )
        catalog.ensure_fresh()
        with pytest.raises(UnsafeFormulaPathError):
            catalog.promote("stg1", new_id="../../promo_escaped")
        assert not (tmp_path / "promo_escaped.yaml").exists()
        assert not (curated.parent / "promo_escaped.yaml").exists()

    def test_normal_write_still_works(self, env):
        catalog, curated, _, _ = env
        indexed = catalog.add_entry(_entry("ok_entry", category="fluid"))
        assert (curated / "fluid" / "ok_entry.yaml").exists()
        assert indexed.id == "ok_entry"

    def test_write_entry_yaml_direct(self, tmp_path):
        root = tmp_path / "lib"
        root.mkdir()
        path = write_entry_yaml(root, _entry("direct", category="cat"))
        assert path == root / "cat" / "direct.yaml"
        assert path.exists()
