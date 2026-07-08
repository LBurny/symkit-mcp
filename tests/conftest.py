"""Shared pytest fixtures for the SymKit test suite.

These fixtures replace the MockMCP class and the fresh_session_manager /
fresh_manager helpers that were previously duplicated across ~11 test modules.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

# Ensure src/ is importable for tests run outside an installed-editable context.
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from symkit.domain.derivation_session import SessionManager  # noqa: E402
from symkit.domain.value_objects import MathContext  # noqa: E402
from symkit.infrastructure import derivation_repository  # noqa: E402
from symkit_mcp.tools import _state  # noqa: E402


class MockMCP:
    """Mock MCP server that collects tools registered via the @mcp.tool() decorator.

    Mirrors the subset of the FastMCP surface that tests exercise: each
    registered tool function is stored by name in ``self.tools`` and can be
    invoked directly.
    """

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, **_kwargs: Any) -> Any:
        def decorator(func: Any) -> Any:
            self.tools[func.__name__] = func
            return func

        return decorator


@pytest.fixture
def fresh_manager(fresh_session_manager: SessionManager) -> SessionManager:
    """Alias for :func:`fresh_session_manager` (legacy name used by some modules)."""
    return fresh_session_manager


@pytest.fixture
def fresh_session_manager() -> Iterator[SessionManager]:
    """Provide a fresh SessionManager in a temporary directory and patch global state.

    Patches ``symkit_mcp.tools._state`` so that the single process-wide
    ``_manager`` / ``_current_session`` / ``_current_context`` point at the
    temporary manager for the duration of the test, then restores the originals
    on teardown to prevent cross-test contamination.

    Also resets the global ``DerivationRepository`` singleton to a fresh empty
    repository rooted at the same temp dir, so sessions do not load real
    persisted derived formulas from the working directory (data-isolation).
    """
    original_manager: SessionManager | None = _state._manager
    original_session = _state._current_session
    original_context = _state._current_context
    original_repository = derivation_repository._repository
    with TemporaryDirectory() as tmp_dir:
        manager = SessionManager(Path(tmp_dir))
        _state._manager = manager
        _state._current_session = None
        _state._current_context = MathContext()
        # Point the global derived-formula repository at an empty temp dir so
        # recommenders do not surface formulas persisted by other tests/runs.
        derivation_repository._repository = derivation_repository.DerivationRepository(
            Path(tmp_dir) / "derived"
        )
        yield manager
    _state._manager = original_manager
    _state._current_session = original_session
    _state._current_context = original_context
    derivation_repository._repository = original_repository


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Inject ``MockMCP`` into each test module's namespace.

    Test modules reference ``MockMCP`` directly (``mcp = MockMCP()``) and rely
    on it being "provided by conftest.py". pytest only auto-injects fixtures,
    not module-level names, so expose ``MockMCP`` explicitly here to keep the
    test files import-free.
    """
    for item in items:
        module = getattr(item, "module", None)
        if module is not None and not hasattr(module, "MockMCP"):
            setattr(module, "MockMCP", MockMCP)
