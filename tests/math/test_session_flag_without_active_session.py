"""r18 C3: ``math(..., session=True)`` must say when no session captured the step.

Without ``session_start`` the call silently returned the mathematical result
with no ``step`` and no note, so a client following the recommended session
workflow believed the step had been recorded. The result must flag that it was
not, while leaving the math and the ``session=False`` path untouched.
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _math_tool() -> Any:
    mcp = MockMCP()  # noqa: F821
    register_math_tools(mcp)
    return mcp.tools["math"]


def test_session_true_without_active_session_reports_not_recorded(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    assert _state.get_session() is None

    result = _math_tool()("simplify", "x + x", session=True)

    assert result["success"] is True
    assert result["expression"] == "2*x"
    assert result["latex"] == "2 x"
    assert result["session_recorded"] is False
    assert "step" not in result and "session_id" not in result
    assert any(
        "no derivation session is active" in w for w in result.get("warnings", [])
    )


def test_session_false_stays_clean_of_session_chatter(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager

    result = _math_tool()("simplify", "x + x", session=False)

    assert result["success"] is True
    assert result["expression"] == "2*x"
    assert "session_recorded" not in result
    assert not result.get("warnings")


def test_session_true_with_active_session_records_normally(fresh_session_manager: Any) -> None:
    """The happy path is unchanged: a live session still captures the step."""
    _ = fresh_session_manager
    from symkit_mcp.tools.session import register_session_tools

    mcp = MockMCP()  # noqa: F821
    register_math_tools(mcp)
    register_session_tools(mcp)
    mcp.tools["session_start"]("c3-active")

    result = mcp.tools["math"]("simplify", "x + x", session=True)

    assert result["step"] == 1
    assert result["session_id"]
    assert "session_recorded" not in result
