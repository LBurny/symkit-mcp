"""
Shared state module for MCP tool modules.

All tools share the same derivation session and math context globals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from symkit.domain.derivation_session import DerivationSession, SessionManager, get_session_manager
from symkit.domain.value_objects import MathContext

if TYPE_CHECKING:
    from symkit.application.formula_catalog import FormulaCatalog

# Session management
_manager: SessionManager | None = None
_current_session: DerivationSession | None = None

# Math context (assumptions, coordinate system, etc.)
_current_context: MathContext = MathContext()

# Formula catalog (persistent index over the YAML layers)
_catalog: FormulaCatalog | None = None


def get_manager() -> SessionManager:
    global _manager
    if _manager is None:
        # Default to the per-user sessions directory (CWD-independent). Pass
        # no explicit dir so SessionManager picks up user_sessions_dir().
        _manager = get_session_manager()
    return _manager


def get_session() -> DerivationSession | None:
    return _current_session


def set_session(session: DerivationSession | None) -> None:
    """Bind the current session and scope the shared assumption context to it.

    Assumptions are session-scoped: starting/resuming a session other than the
    one currently bound resets the context, and ending a session (~``None``)
    reclaims its assumptions.  A context created with no session carries the
    legacy global assumptions and is adopted as-is by the next session, so
    ``assume`` before ``session_start`` keeps working (r16 task-20 S-2).
    """
    global _current_session, _current_context
    previous = _current_session
    _current_session = session
    if session is None or (
        previous is not None and previous.session_id != session.session_id
    ):
        _current_context = MathContext()


def get_context() -> MathContext:
    return _current_context


def set_context(ctx: MathContext) -> None:
    global _current_context
    _current_context = ctx


def get_catalog() -> FormulaCatalog:
    """Return the shared formula catalog, building it on first call.

    Composition root for the formula index: wires the SQLite store, the YAML
    file source, and the three layer directories, then reconciles the index
    with disk so the first query is already fresh.
    """
    global _catalog
    if _catalog is None:
        from symkit.application.formula_catalog import FormulaCatalog
        from symkit.domain.paths import (
            bundled_seed_library_dir,
            user_derived_dir,
            user_index_path,
            user_library_dir,
        )
        from symkit.infrastructure.formula_files import YamlFormulaFileSource
        from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore

        store = SqliteFormulaIndexStore(user_index_path())
        store.open()
        _catalog = FormulaCatalog(
            store,
            YamlFormulaFileSource(),
            seed_dir=bundled_seed_library_dir(),
            staging_dir=user_derived_dir(),
            curated_dir=user_library_dir(),
        )
        _catalog.ensure_fresh()
    return _catalog


def set_catalog(catalog: FormulaCatalog | None) -> None:
    global _catalog
    _catalog = catalog


def reset_catalog() -> None:
    """Drop the shared catalog (tests); closes the index connection so the
    SQLite file lock is released (Windows). Does not delete the index file."""
    global _catalog
    if _catalog is not None:
        _catalog.store.close()
    _catalog = None
