"""Invariant I3: the session's assumption engine is the source of truth for math.

Assumptions could be set four ways — ``assume()`` (session layer),
``assume_for_step()`` (step layer), domain defaults loaded at session start,
and per-call ``math(assumptions=...)`` — but only two of them reached the math
path.  ``assume_for_step("k positive")`` and the domain defaults were written
to ``AssumptionEngine`` and then silently ignored by ``math()``, which read
only ``MathContext``.  The user's stated assumption and the computed result
disagreed.

Now the effective assumption set for a math call is the session engine's merged
assumptions with the explicit context (per-call or ``assume()``) layered on
top.
"""

from __future__ import annotations

from symkit_mcp.tools import _state
from symkit_mcp.tools.assumptions import register_assumption_tools
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py


def _tools():
    # ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    register_math_tools(mcp)
    register_assumption_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


# ── Step-level assumptions ──────────────────────────────────────────────────


def test_step_assumption_reaches_math(fresh_session_manager):
    """``assume_for_step`` must affect the very next ``math()`` call."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("step_assume")

    assert tools["assume_for_step"](["k", "positive"])["success"]
    res = tools["math"](operation="simplify", expression="sqrt(k**2)", session=False)

    assert res["success"], res
    assert res["expression"] == "k", (
        f"step-level assumption ignored by math: got {res['expression']!r}"
    )


def test_clearing_step_assumptions_restores_default_behaviour(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("step_assume_clear")

    tools["assume_for_step"](["k", "positive"])
    assert tools["math"](
        operation="simplify", expression="sqrt(k**2)", session=False
    )["expression"] == "k"

    tools["clear_step_assumptions"]()
    res = tools["math"](operation="simplify", expression="sqrt(k**2)", session=False)
    assert res["success"], res
    assert res["expression"] == "sqrt(k**2)", (
        f"step assumption survived clear_step_assumptions: {res['expression']!r}"
    )


# ── Domain defaults ─────────────────────────────────────────────────────────


def test_domain_default_assumption_reaches_math(fresh_session_manager):
    """Thermodynamics declares ``T`` positive; math must see it."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("domain_assume", domain="thermodynamics")

    res = tools["math"](operation="simplify", expression="sqrt(T**2)", session=False)

    assert res["success"], res
    assert res["expression"] == "T", (
        f"domain default assumption ignored by math: got {res['expression']!r}"
    )


def test_unknown_symbol_is_unaffected_by_domain_defaults(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("domain_assume_other", domain="thermodynamics")

    res = tools["math"](operation="simplify", expression="sqrt(z**2)", session=False)
    assert res["success"], res
    assert res["expression"] == "sqrt(z**2)", res


# ── Precedence and existing behaviour ───────────────────────────────────────


def test_global_assume_still_reaches_math(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("global_assume")
    tools["assume"]({"k": "positive"})

    res = tools["math"](operation="simplify", expression="sqrt(k**2)", session=False)
    assert res["success"], res
    assert res["expression"] == "k", res


def test_per_call_assumption_still_reaches_math_without_session(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()

    res = tools["math"](
        operation="simplify",
        expression="sqrt(k**2)",
        assumptions=["k is positive"],
        session=False,
    )
    assert res["success"], res
    assert res["expression"] == "k", res


def test_math_is_unaffected_when_no_session_exists(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()

    res = tools["math"](operation="simplify", expression="sqrt(k**2)", session=False)
    assert res["success"], res
    assert res["expression"] == "sqrt(k**2)", res


def test_session_assumptions_do_not_leak_between_sessions(fresh_session_manager):
    """A second session must not inherit the first session's step assumptions."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("leak_a")
    tools["assume_for_step"](["k", "positive"])
    tools["session_start"]("leak_b")

    res = tools["math"](operation="simplify", expression="sqrt(k**2)", session=False)
    assert res["success"], res
    assert res["expression"] == "sqrt(k**2)", (
        f"assumption leaked across sessions: {res['expression']!r}"
    )


def test_per_call_assumption_overrides_step_assumption(fresh_session_manager):
    """A per-call assumption is more specific than a step-level one.

    Unioning the two made them conflict and silently drop both: with a step
    ``x positive`` and a per-call ``x is negative``, ``solve(x**2 - 4)``
    returned ``x = 2`` instead of ``x = -2``.
    """
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("override")
    tools["assume_for_step"](["x", "positive"])

    res = tools["math"](
        operation="solve",
        expression="x**2 - 4",
        variable="x",
        assumptions=["x is negative"],
        session=False,
    )
    assert res["success"], res
    assert res["expression"] == "Eq(x, -2)", res


def test_per_call_real_assumption_replaces_step_positive(fresh_session_manager):
    """``x is real`` must not inherit the step's ``x positive``."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("override_real")
    tools["assume_for_step"](["x", "positive"])

    res = tools["math"](
        operation="simplify",
        expression="Abs(x)",
        assumptions=["x is real"],
        session=False,
    )
    assert res["success"], res
    assert res["expression"] == "Abs(x)", res


def test_effective_context_is_not_mutated(fresh_session_manager):
    """Merging engine assumptions must not write them into the global context."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("no_mutation")
    tools["assume_for_step"](["k", "positive"])
    tools["math"](operation="simplify", expression="sqrt(k**2)", session=False)

    assert _state.get_context().assumptions == {}, (
        f"engine assumptions leaked into MathContext: {_state.get_context().assumptions}"
    )
