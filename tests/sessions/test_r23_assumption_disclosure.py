"""Round-23 F10: session_complete must disclose that session assumptions are gone.

Probe references: audit2b (assume -> record -> complete left ``warnings`` empty;
the following ``math(session=false)`` silently lost ``c is positive``).
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools._state import set_session
from tests.conftest import MockMCP


def _tools() -> dict[str, Any]:
    from symkit_mcp.tools.assumptions import register_assumption_tools
    from symkit_mcp.tools.math import register_math_tools
    from symkit_mcp.tools.session import register_session_tools

    mcp = MockMCP()
    register_session_tools(mcp)
    register_math_tools(mcp)
    register_assumption_tools(mcp)
    return mcp.tools


def test_complete_discloses_discarded_session_assumptions(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="f10")
    tools["assume"](["c is positive"])
    tools["session_record_step"](expression="sqrt(c**2)", description="record")

    done = tools["session_complete"](auto_save=False)

    assert done["success"] is True
    warnings = " ".join(done.get("warnings") or [])
    assert "assumptions no longer apply" in warnings, done.get("warnings")
    assert "c is positive" in warnings, done.get("warnings")

    # The assumption really is gone from future (stateless) calls.
    after = tools["math"]("simplify", "sqrt(c**2)", session=False)
    assert after["expression"] == "sqrt(c**2)"


def test_complete_without_assumptions_adds_no_disclosure(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="f10-clean")
    tools["session_record_step"](expression="x + x", description="record")

    done = tools["session_complete"](auto_save=False)

    assert not any(
        "assumptions no longer apply" in w for w in done.get("warnings") or []
    ), done.get("warnings")


def test_assumption_viewers_agree_the_session_discarded_them(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="f10-views")
    tools["assume"](["c is positive"])
    tools["session_record_step"](expression="sqrt(c**2)", description="record")
    tools["session_complete"](auto_save=False)

    shown = tools["show_assumptions"]()
    assert "discarded" in shown["message"], shown["message"]
    assert "session" in shown["message"].lower()

    listed = tools["list_assumptions"]()
    assert listed["success"] is False
    assert "discarded" in listed["error"], listed["error"]
    assert "session" in listed["error"].lower()


def teardown_function() -> None:
    set_session(None)
