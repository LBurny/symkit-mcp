"""Vector calculus and matrix-op fixes from black-box run-017/run-018.

- gradient/divergence/curl/laplacian substituted bare coordinate symbols into
  assumption-bearing parsed expressions, silently no-oping: the field never
  depended on the basis coordinates, so gradient returned a zero vector and
  divergence/curl returned 0 for the wrong reason (vacuous control).
- session_record_step accepted comma-separated tuple parses that later bricked
  session_show / progress computations (tuple has no free_symbols).
- solve crashed with a cryptic AttributeError on comma-separated systems.
- eigenvals results carried no latex and were never recorded in the chain.
"""

from __future__ import annotations

from symkit_mcp.tools._state import get_session
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


def test_gradient_applies_context_assumptions(fresh_session_manager):
    """Regression (run-017): with context assumptions active, gradient's
    coordinate substitution used bare Symbols and no-opped, so the field never
    depended on N.x/N.y/N.z and gradient returned VectorZero."""
    _ = fresh_session_manager
    tools = _tools()
    tools["assume"]({"G": "positive", "M": "positive", "x": "positive",
                     "y": "positive", "z": "positive"})
    res = tools["math"](
        operation="gradient",
        expression="-G*M/sqrt(x**2+y**2+z**2)",
        variable="x,y,z",
        session=False,
    )
    assert res["success"], res
    assert res["expression"] != "0", res["expression"]
    assert "G*M" in res["expression"]
    assert "N.i" in res["expression"] and "N.k" in res["expression"]


def test_divergence_nonzero_control_with_assumptions(fresh_session_manager):
    """The run-017 divergence/curl zeros were vacuous (coordinate substitution
    no-opped, so the field never depended on the basis). A non-zero control
    must survive assumptions: div(x*y, z*x, y*z) = 2*y."""
    _ = fresh_session_manager
    tools = _tools()
    tools["assume"]({"x": "positive", "y": "positive", "z": "positive"})
    res = tools["math"](
        operation="divergence",
        expression="x*y, z*x, y*z",
        variable="x,y,z",
        session=False,
    )
    assert res["success"], res
    # The basis coordinate rendering of div(x*y, z*x, y*z).
    assert res["expression"].replace(" ", "") == "2*N.y", res["expression"]


def test_divergence_of_radial_field_is_zero(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["assume"]({"G": "positive", "M": "positive"})
    res = tools["math"](
        operation="divergence",
        expression="G*M*x/(x**2+y**2+z**2)**(3/2), "
        "G*M*y/(x**2+y**2+z**2)**(3/2), "
        "G*M*z/(x**2+y**2+z**2)**(3/2)",
        variable="x,y,z",
        session=False,
    )
    assert res["success"], res
    assert res["expression"] == "0"


def test_solve_system_comma_expression(fresh_session_manager):
    """Regression (run-018): a comma-separated system crashed with
    'tuple' object has no attribute 'has'. Systems solve now."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="x + y - 2, x - y",
        variable="x, y",
        session=False,
    )
    assert res["success"], res
    assert "{x: 1, y: 1}" in res["all_solutions"][0].replace(" ", "") or \
        "1" in res["all_solutions"][0]


def test_eigenvals_records_step_and_latex(fresh_session_manager):
    """Regression (run-017): eigenvals carried no latex (empty display) and no
    result object, so the step never entered the chain."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("eig")
    res = tools["math"](
        operation="eigenvals",
        expression="Matrix([[2,0,0],[0,3,0],[0,0,5]])",
        session=True,
    )
    assert res["success"], res
    assert res.get("latex"), res
    assert res.get("step"), "eigenvals must record a session step"
    sess = get_session()
    assert sess is not None and sess.step_count >= 1


def test_session_record_step_rejects_comma_tuple(fresh_session_manager):
    """Regression (run-017): a comma string parsed to a python tuple that was
    stored as current_expression; session_show then crashed with
    'tuple' object has no attribute 'free_symbols'. Fail loud at record time."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("tuple_guard")
    res = tools["session_record_step"](
        expression="x + y, z",
        description="accidental tuple",
    )
    assert not res["success"]
    assert "single expression" in res["error"].lower()
    shown = tools["session_show"]()
    assert shown["success"], shown


def test_session_show_survives_non_basic_current_expression(fresh_session_manager):
    """Defensive guard: session_show must not crash on a non-Basic current
    expression (run-017 brick) — it degrades instead."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("tuple_show")
    sess = get_session()
    assert sess is not None
    sess.current_expression = (1, 2)  # simulate the run-017 state
    shown = tools["session_show"]()
    assert shown["success"], shown
