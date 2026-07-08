"""
Shared state module for MCP tool modules.

All tools share the same derivation session and math context globals.
"""

from __future__ import annotations

from symkit.domain.derivation_session import DerivationSession, SessionManager, get_session_manager
from symkit.domain.value_objects import MathContext

# Session management
_manager: SessionManager | None = None
_current_session: DerivationSession | None = None

# Math context (assumptions, coordinate system, etc.)
_current_context: MathContext = MathContext()


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
    global _current_session
    _current_session = session


def get_context() -> MathContext:
    return _current_context


def set_context(ctx: MathContext) -> None:
    global _current_context
    _current_context = ctx
