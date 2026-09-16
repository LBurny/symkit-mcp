"""The response must disclose the assumption set a call actually ran under.

G10 (field card task-03): ``math(..., session=True, assumptions=[...])``
persists those assumptions into the session scope (documented), so later steps
that declare nothing have their results changed by the leaked assumptions — yet
the response only reported the per-call ``assumptions_applied`` parameter.  A
conditional and an unconditional result were indistinguishable on the wire.

``assumptions_applied`` stays the per-call parameter; ``assumptions_effective``
reports the merged view actually used and ``assumptions_from_session`` names the
ones the caller did not pass this call.
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


class TestEffectiveAssumptionsDisclosed:
    def test_second_call_discloses_session_scope_assumptions(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("g10")
        first = tools["math"](
            "simplify", "sqrt(x**2)", assumptions=["x is positive"], session=True
        )
        assert first["success"], first
        assert first["assumptions_applied"] == {"x": ["positive"]}, first
        assert first["assumptions_effective"]["x"] == ["positive"], first

        second = tools["math"]("simplify", "sqrt(a**2)", session=True)
        assert second["success"], second
        assert second.get("assumptions_applied", {}) == {}, second
        assert second.get("assumptions_effective", {}).get("x") == ["positive"], second
        assert "x" in second.get("assumptions_from_session", []), second

    def test_per_call_assumptions_do_not_persist_without_session(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        first = tools["math"](
            "simplify", "sqrt(x**2)", assumptions=["x is positive"], session=False
        )
        assert first["success"], first
        assert first["assumptions_effective"]["x"] == ["positive"], first

        second = tools["math"]("simplify", "sqrt(a**2)", session=False)
        assert second["success"], second
        assert not second.get("assumptions_effective"), second
        assert not second.get("assumptions_from_session"), second

    def test_no_assumptions_reports_no_effective_set(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"]("simplify", "x**2", session=False)
        assert res["success"], res
        assert not res.get("assumptions_effective"), res
