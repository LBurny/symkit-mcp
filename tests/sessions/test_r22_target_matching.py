"""Round-22 target-matching fixes: final override and target echo (lanes A/B/C).

Probe references: audit_session.py S1 (task-01/06/07/08/09/11/15 target-match
false negatives) and S10 (task-15 natural-language target silently swallowed).
"""

from __future__ import annotations

from symkit_mcp.tools._state import set_session
from symkit_mcp.tools.session import register_session_tools
from tests.conftest import MockMCP


def _tools() -> dict:
    mcp = MockMCP()
    register_session_tools(mcp)
    return mcp.tools


def test_final_override_participates_in_target_match() -> None:
    tools = _tools()
    tools["session_start"](
        name="r22-override", goal="differentiate x^x",
        target_expression="x**x*(log(x) + 1)",
    )
    tools["session_record_step"](
        expression="x**x*(log(x)+1) = exp(x*log(x))*(log(x)+1)",
        description="cross-route identity",
    )
    done = tools["session_complete"](
        final_expression="x**x*(log(x) + 1)", auto_save=False
    )
    assert done["success"] is True
    assert done["progress"]["matches_target"] is True
    assert done["target_reached"] is True
    assert "does not match" not in " ".join(done["warnings"])


def test_override_preferred_over_chain_current() -> None:
    tools = _tools()
    tools["session_start"](
        name="r22-override-miss", goal="differentiate x^x",
        target_expression="x**x*(log(x) + 1)",
    )
    tools["session_record_step"](
        expression="x**x*(log(x)+1) = exp(x*log(x))*(log(x)+1)",
        description="identity",
    )
    # The declared deliverable does NOT match the target; the chain's current
    # expression must not rescue it.
    done = tools["session_complete"](final_expression="1 + x", auto_save=False)
    assert done["progress"]["matches_target"] is False
    assert done["target_reached"] is False


def test_target_expression_without_goal_still_sets_target() -> None:
    tools = _tools()
    started = tools["session_start"](
        name="r22-bare-target", target_expression="Z_c = 3/8"
    )
    assert started["goal"]["target_expression"] == "Z_c = 3/8"


def test_session_start_echoes_parsed_target() -> None:
    tools = _tools()
    started = tools["session_start"](
        name="r22-echo", goal="vdW critical point", target_expression="Z_c = 3/8"
    )
    assert started["target_parsed"] == "Eq(Z_c, 3/8)"


def test_session_start_warns_on_unparseable_target() -> None:
    tools = _tools()
    started = tools["session_start"](
        name="r22-bad-target", goal="x", target_expression="))(("
    )
    warnings = started.get("warnings") or []
    assert any("target" in w.lower() for w in warnings)
    assert started["goal"]["target_expression"] is None


def teardown_function() -> None:
    set_session(None)
