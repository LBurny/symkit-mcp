"""r18 C2: the unreduced-difference warning must not claim an unwritten save.

With ``session_complete(auto_save=false)`` nothing is written to the formula
library, yet the response still said "the formula is saved with verified=false".
The unreduced-difference half is true and must stay; only the save claim follows
the actual flag.
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools() -> dict[str, Any]:
    mcp = MockMCP()  # noqa: F821
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _suspect_session(tools: dict[str, Any], name: str) -> None:
    tools["session_start"](name)
    # The identity is false: the difference is nonzero, so the step carries
    # details.suspect_identity="unreduced".
    tools["math"](operation="expand", expression="(x + y)**2 - x**2 - y**2", session=True)


def _suspect_warning(result: dict[str, Any]) -> str:
    matches = [w for w in result.get("warnings", []) if "unreduced difference" in w]
    assert matches, result.get("warnings")
    return matches[0]


def test_auto_save_false_warning_does_not_claim_a_save(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    _suspect_session(tools, "c2-no-save")

    result = tools["session_complete"](auto_save=False)

    warning = _suspect_warning(result)
    assert "suspect_identity" in warning  # the true half is preserved
    assert "auto_save=false" in warning
    assert "nothing was saved" in warning
    assert "the formula is saved" not in warning
    assert "saved_to" not in result


def test_auto_save_true_warning_still_reports_the_save(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    _suspect_session(tools, "c2-save")

    result = tools["session_complete"](auto_save=True)

    warning = _suspect_warning(result)
    assert warning == (
        "1 step(s) recorded an unreduced difference (suspect_identity); "
        "the formula is saved with verified=false"
    )
