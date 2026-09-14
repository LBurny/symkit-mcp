"""`session_show` and `session_complete` must agree on what the derivation produced.

`complete()` reports the derivation's outcome rather than the last step (so a
trailing evalf probe does not become the answer), but `session_show` kept
reporting the raw current expression. The two tools then answered the same
question differently in 4 of 5 cards of the 2026-09-12 pure-formula round.
"""

from __future__ import annotations

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools import session as session_tools


def _tools() -> dict:
    mcp = MockMCP()
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    return mcp.tools


class TestOutcomeReporting:
    def test_show_agrees_with_complete(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](name="outcome-agreement")
        tools["session_load_formula"](expression="a+b", formula_id="f1")
        tools["math"](operation="expand", expression="(a+b)**2", session=True)
        tools["math"](operation="evalf", expression="1/3", session=True)

        show = tools["session_show"]()
        complete = tools["session_complete"](
            auto_save=False, require_target_match=False
        )

        assert show["result_expression"] == complete["final_expression"]
        assert show["result_latex"] == complete["final_latex"]
        # The raw current expression stays visible, but under its own name.
        assert show["latex"] == "0.333333333333333"
        assert show["result_expression"] == "a**2 + 2*a*b + b**2"

    def test_zero_self_check_is_the_outcome_for_all_sources(
        self, fresh_session_manager
    ):
        """r14 task-08: the closing step outputs ``0`` but used to be skipped.

        ``session_show.result_expression`` and ``session_complete.final_expression``
        must report the zero convergence step, not the earlier unevaluated
        symbolic step.
        """
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](name="zero-convergence")
        tools["session_load_formula"](expression="c*x + t", formula_id="f1")
        tools["math"](
            operation="simplify",
            expression="c*x + t - (c*x + t)",
            session=True,
        )
        tools["session_add_note"](note="residual is exactly zero")

        show = tools["session_show"]()
        complete = tools["session_complete"](
            auto_save=False, require_target_match=False
        )

        assert show["result_expression"] == complete["final_expression"] == "0"
        assert show["result_latex"] == complete["final_latex"]
