"""``assume`` accepts the same clause-list form as ``math``/``assume_for_step``.

2026-09-14 defect: the assumption tools disagreed about input shape —
``assume`` required a dict while ``math(assumptions=[...])`` and
``assume_for_step([...])`` required lists. ``assume`` now accepts both, with
the dict form staying canonical and unparsable clauses rejected up-front
(all-or-nothing: nothing is applied when any clause fails to parse).
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools.math import register_math_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools() -> dict:
    mcp = MockMCP()
    register_math_tools(mcp)
    return mcp.tools


class TestAssumeInputForms:
    def test_dict_form_sets_assumption(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _tools()
        result = tools["assume"]({"x": "positive"})
        assert result["success"] is True, result
        assert result["assumptions_applied"]["x"] == ["positive"]

    def test_list_form_sets_assumption(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _tools()
        result = tools["assume"](["x is positive", "t is real"])
        assert result["success"] is True, result
        assert result["assumptions_applied"]["x"] == ["positive"]

    def test_list_form_affects_later_math(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["assume"](["x is positive"])
        result = tools["math"]("simplify", "sqrt(x**2)", session=False)
        assert result["success"] is True, result
        assert result["expression"] == "x"

    def test_unparsable_list_clause_rejected_atomically(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        result = tools["assume"](["x is positive", "???"])
        assert result["success"] is False, result
        # Nothing was applied from the failed batch.
        assert "assumptions_applied" not in result or not result.get(
            "assumptions_applied"
        )
