"""``session_complete`` payload regression (operator feedback, 2026-09-16).

A 29-step session returned a 55.6 KB completion record: every step's full
``input_expressions`` / ``output_expression`` / ``output_latex`` was embedded
even though ``session_get_steps`` already serves those, the client truncated
the payload to a 2 KB preview, and the operator never saw ``target_reached:
false`` or the target-mismatch warning it carried.  The completion return now
carries a compact ``steps_summary`` (full records stay behind
``session_get_steps``) and reports ``warnings`` / ``target_reached`` ahead of
the bulk fields, so even a truncated preview shows them.
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP / fresh_session_manager are provided by conftest.py
# ruff: noqa: F821


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _two_step_session(tools: dict[str, Any], name: str, **start_kwargs: Any) -> None:
    tools["session_start"](name, **start_kwargs)
    tools["math"]("simplify", "x + x", session=True)
    tools["math"]("expand", "(x + 1)**2", session=True)


def test_steps_are_summarized_not_embedded(fresh_session_manager) -> None:
    _ = fresh_session_manager
    tools = _tools()
    _two_step_session(tools, "payload-slim")
    res = tools["session_complete"]()
    assert res["success"], res
    assert "steps" not in res, sorted(res)
    rows = res["steps_summary"]
    assert [r["step_number"] for r in rows] == [1, 2]
    assert rows[0]["operation"] == "simplify"
    assert rows[0]["status"] == "verified"
    assert set(rows[0]) == {"step_number", "operation", "status"}


def test_warnings_precede_the_bulk_fields(fresh_session_manager) -> None:
    _ = fresh_session_manager
    tools = _tools()
    _two_step_session(
        tools,
        "payload-order",
        goal="reach an unrelated target",
        target_expression="sqrt(omega0**2 - 2*beta**2)",
    )
    res = tools["session_complete"]()
    assert res["success"], res
    keys = list(res)
    assert keys.index("warnings") < keys.index("steps_summary"), keys
    assert keys.index("target_reached") < keys.index("steps_summary"), keys
    assert res["target_reached"] is False
    assert any(
        "does not match the derivation target" in w for w in res["warnings"]
    ), res["warnings"]


def test_auto_save_still_records_step_descriptions(fresh_session_manager) -> None:
    """The library write must read the chain from the session, not the payload."""
    _ = fresh_session_manager
    tools = _tools()
    _two_step_session(tools, "payload-autosave")
    res = tools["session_complete"](description="twice identity", auto_save=True)
    assert res["success"], res
    assert res.get("saved_id"), res
    assert not any(
        "save failed" in w for w in res.get("warnings", [])
    ), res["warnings"]
