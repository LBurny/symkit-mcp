"""Lifecycle of the shared formula catalog in `symkit_mcp.tools._state`."""

import pytest

from symkit.application.formula_catalog import FormulaCatalog
from symkit.infrastructure.formula_files import YamlFormulaFileSource
from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore
from symkit_mcp.tools import _state


@pytest.fixture
def injected_catalog(tmp_path):
    store = SqliteFormulaIndexStore(tmp_path / "index.db")
    store.open()
    catalog = FormulaCatalog(
        store=store,
        file_source=YamlFormulaFileSource(),
        seed_dir=tmp_path / "seed",
        staging_dir=tmp_path / "staging",
        curated_dir=tmp_path / "curated",
    )
    previous = _state._catalog
    _state.set_catalog(catalog)
    yield store
    _state.set_catalog(previous)


def test_reset_catalog_closes_the_store(injected_catalog):
    """An open SQLite connection holds file locks on Windows; dropping the
    catalog without closing it leaks them."""
    store = injected_catalog

    _state.reset_catalog()

    with pytest.raises(RuntimeError, match="store is not open"):
        store.all()
