"""The math dispatcher must consume or explicitly flag every parameter.

Fail-loud discipline: parameters that do not apply to the requested
operation produce a warning instead of being silently ignored; assumption
clauses accept both ``"x is positive"`` and ``"x positive"`` and malformed
clauses produce warnings rather than vanishing.
"""

from __future__ import annotations

from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools():
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def test_evalf_applies_substitution(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="evalf",
        expression="sqrt(2*g*m/(rho*C_d*A))",
        substitution={"m": 1, "g": 9.81, "rho": 1.225, "C_d": 0.47, "A": 0.5},
        session=False,
    )
    assert res["success"], res
    assert abs(float(res["expression"]) - 8.25557877930607) < 1e-9


def test_two_word_assumption_format_applies(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="v_t**2 - 1 == 0",
        variable="v_t",
        assumptions=["v_t positive"],
        session=False,
    )
    assert res["success"], res
    assert res["solution"] == "1"


def test_three_word_assumption_format_still_applies(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="v_t**2 - 1 == 0",
        variable="v_t",
        assumptions=["v_t is positive"],
        session=False,
    )
    assert res["success"], res
    assert res["solution"] == "1"


def test_malformed_assumption_produces_warning(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="simplify", expression="x + x", assumptions=["banana"], session=False
    )
    assert res["success"]
    assert any("banana" in w for w in res.get("warnings", []))


def test_unused_parameter_produces_warning(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="simplify", expression="x + x", point="3", session=False
    )
    assert res["success"]
    assert any("'point'" in w and "simplify" in w for w in res.get("warnings", []))


def test_default_valued_parameters_do_not_warn(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="simplify", expression="x + x", order=1, direction="+-", session=False
    )
    assert res["success"]
    assert not res.get("warnings")
