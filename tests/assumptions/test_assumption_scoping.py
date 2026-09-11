"""Per-call assumption scoping (run-013 design decision).

Assumptions passed to ``math()`` must respect the ``session`` flag:
``session=false`` applies them to that call only (stateless calls are truly
side-effect free); ``session=true`` persists them to the shared context AND
the session's assumption engine so the step verifier can see them.  Removing
assumptions is possible via ``unassume`` / ``clear_assumptions``.
"""

from __future__ import annotations

from symkit_mcp.tools.assumptions import register_assumption_tools
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools():
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    register_assumption_tools(mcp)
    return mcp.tools


def test_stateless_assumptions_apply_but_do_not_leak(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="simplify",
        expression="sqrt(x**2)",
        assumptions=["x positive"],
        session=False,
    )
    assert res["success"], res
    # Applied within the call...
    assert res["expression"] == "x"
    assert res["assumptions_applied"] == {"x": ["positive"]}
    # ...and gone afterwards: no leak into the shared context.
    shown = tools["show_assumptions"]()
    assert shown["assumptions"] == {}


def test_stateless_call_sees_persisted_assumptions(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["assume"]({"z": "positive"})
    res = tools["math"](
        operation="simplify", expression="sqrt(z**2)", session=False
    )
    assert res["success"], res
    assert res["expression"] == "z"
    assert "assumptions_applied" not in res


def test_session_assumptions_persist_and_reach_verifier(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("scoping")
    res = tools["math"](
        operation="simplify",
        expression="Eq(sqrt(x**2), x)",
        assumptions=["x positive"],
        session=True,
    )
    assert res["success"], res
    assert res["expression"] == "True"
    assert res["assumptions_applied"] == {"x": ["positive"]}
    # Persisted in the shared context...
    shown = tools["show_assumptions"]()
    assert shown["assumptions"].get("x", {}).get("positive") is True
    # ...and visible to the step verifier: the identity is now confirmed
    # instead of "assumptions the verifier cannot confirm".
    verified = tools["session_verify_step"](step_number=res["step"])
    assert verified["verification_status"] == "verified", verified


def test_unassume_removes_from_context_and_session_engine(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("unassume_scope")
    tools["assume"]({"x": "positive", "y": "real"})
    removed = tools["unassume"](["x"])
    assert removed["success"], removed
    shown = tools["show_assumptions"]()
    assert "x" not in shown["assumptions"]
    assert shown["assumptions"].get("y", {}).get("real") is True
    engine_view = tools["list_assumptions"](level="session")
    assert "x" not in engine_view["assumptions"]
    assert "y" in engine_view["assumptions"]


def test_unassume_restores_default_behavior(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["assume"]({"z": "positive"})
    assert tools["math"](
        operation="simplify", expression="sqrt(z**2)", session=False
    )["expression"] == "z"
    tools["unassume"](["z"])
    assert tools["math"](
        operation="simplify", expression="sqrt(z**2)", session=False
    )["expression"] == "sqrt(z**2)"  # no longer collapses to z


def test_clear_assumptions_resets_scope(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("clear_scope")
    tools["assume"]({"a": "positive", "b": "real"})
    cleared = tools["clear_assumptions"]()
    assert cleared["success"], cleared
    assert tools["show_assumptions"]()["assumptions"] == {}
    engine_view = tools["list_assumptions"](level="session")
    assert engine_view["assumptions"] == {}


def test_unassume_works_without_session(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["assume"]({"w": "positive"})
    removed = tools["unassume"](["w"])
    assert removed["success"], removed
    assert tools["show_assumptions"]()["assumptions"] == {}
