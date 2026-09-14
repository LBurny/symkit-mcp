"""ilaplace must not hand back a silent ``nan`` at the damping boundary.

r14 task-10: the second-order step response
``wn**2/(s*(s**2 + 2*zeta*wn*s + wn**2))`` is transformed to the underdamped
closed form unconditionally (no Piecewise, no branch condition). The form
carries ``1/sqrt(1 - zeta**2)``, so substituting the critical-damping value
``zeta = 1`` produced ``nan`` inside a ``success:true`` envelope — the user had
to notice and issue a separate reduced-denominator call.

The underdamped path must stay byte-for-byte unchanged; the singular case must
surface as a structured error instead of a silent nan.
"""

from __future__ import annotations

from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py

_STEP_RESPONSE = "wn**2/(s*(s**2 + 2*zeta*wn*s + wn**2))"


def _tools():
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _underdamped_result(tools):
    res = tools["math"](
        operation="ilaplace",
        expression=_STEP_RESPONSE,
        variable="s",
        with_respect_to="t",
        session=False,
    )
    assert res["success"], res
    return res["expression"]


def test_ilaplace_underdamped_path_unchanged(fresh_session_manager):
    """zeta = 1/2 stays a finite closed form; only the boundary errors out."""
    _ = fresh_session_manager
    tools = _tools()
    expr = _underdamped_result(tools)
    sub = tools["math"](
        operation="substitute",
        expression=expr,
        substitution={"zeta": "1/2"},
        session=False,
    )
    assert sub["success"], sub
    assert "nan" not in sub["expression"].lower(), sub


def test_critical_damping_substitution_reports_structured_error(
    fresh_session_manager,
):
    """zeta = 1 must not yield a silent nan; the message must name the case."""
    _ = fresh_session_manager
    tools = _tools()
    expr = _underdamped_result(tools)
    sub = tools["math"](
        operation="substitute",
        expression=expr,
        substitution={"zeta": "1"},
        session=False,
    )
    assert not sub["success"], sub
    assert "nan" not in str(sub.get("expression", "")).lower(), sub
    error = sub["error"].lower()
    assert "zeta" in error or "critical" in error, sub


def test_ilaplace_nan_result_is_rejected(fresh_session_manager):
    """A transform that evaluates to nan is a structured failure, not a
    success carrying an unusable expression."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="ilaplace",
        expression="nan",
        variable="s",
        with_respect_to="t",
        session=False,
    )
    assert not res["success"], res
    assert "nan" in res["error"].lower(), res
