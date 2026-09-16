"""Step recording must archive the same object that was returned to the client.

Merged from four files on recording/provenance fidelity:

- Archive/response divergence regression: the recorded step was re-parsed from
  ``str(result)`` and function notation like ``v(t)`` was corrupted into
  ``t*v`` in the session JSON while the live response was right.
- ``math()`` provenance (r16 tasks 01/03/14/15/16): ``dimension`` records a
  step, ``parse``/``cancel`` keep their own labels, an ``evalf`` substitution
  archives the substituted point.
- Operation provenance (2026-09-12 complex round): matrix calls keep their own
  name beside the coarse ``matrix_op`` bucket, an unknown
  ``session_load_formula(source=...)`` label is reported not dropped, and an
  unrecognized ``session_start(pattern=...)`` is reported not swapped.
- r16 task-20: a system ``solve`` step must not brick explain/verify/complete
  with a ``'tuple' object has no attribute 'free_symbols'`` crash.
"""

from __future__ import annotations

import json
from typing import Any

import sympy as sp

from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _make_tools() -> dict:
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def test_dsolve_step_archive_matches_response(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("ode_check", goal="solve dv/dt = -k*v for v")
    res = tools["math"](
        operation="dsolve",
        expression="Derivative(v(t), t) = -k*v(t)",
        variable="v",
        with_respect_to="t",
    )
    assert res["success"], res
    sess = _state.get_session()
    assert sess is not None
    step = sess.steps[-1]
    # Archive and response describe the same object.
    assert step.output_expression == res["expression"]
    # Function notation survives into the archive (no t*v corruption).
    assert "Function('v')" in step.output_srepr
    assert "Mul(Symbol('t'), Symbol('v'))" not in step.output_srepr


def test_solve_returns_bare_solution_field(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("solve_check")
    res = tools["math"](
        operation="solve",
        expression="1/2*rho*C_d*A*v_t**2 == m*g",
        variable="v_t",
    )
    assert res["success"], res
    sol = res["solution"]
    # Bare RHS: never wrapped in Eq(...), consistent with the expression field.
    assert not sol.startswith("Eq(")
    assert res["expression"] == f"Eq(v_t, {sol})"
    assert "solution_latex" in res
    # The bare solution really solves the original equation.
    v_t, rho, C_d, A, m, g = sp.symbols("v_t rho C_d A m g")
    residual = sp.simplify(
        (rho * C_d * A * v_t**2 / 2 - m * g).subs(v_t, sp.sympify(sol))
    )
    assert residual == 0


def test_math_response_has_no_internal_keys(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("leak_check")
    res = tools["math"](operation="simplify", expression="x**2 + 2*x + x**2")
    assert res["success"]
    assert not any(k.startswith("_") for k in res)


def test_substitute_step_records_live_object(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("subs_check")
    res = tools["math"](
        operation="substitute",
        expression="Derivative(y(x), x) + y(x)",
        substitution={"y(x)": "0"},
    )
    assert res["success"], res
    assert res["expression"] == "0"
    sess = _state.get_session()
    assert sess is not None
    # Input archive keeps y(x) function notation, not x*y.
    assert "y(x)" in sess.steps[-1].input_expressions["original"]


# Provenance labels beside the coarse verification buckets (r16 round).
def test_dimension_call_records_a_step(fresh_session_manager) -> None:
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("dimension-provenance")

    result = tools["math"](
        "dimension", "v*t", units={"v": "m/s", "t": "s"}, session=True
    )
    assert result["success"] is True
    assert result["step"] == 1

    step = tools["session_get_steps"]()["steps"][0]
    assert step["input_expressions"]["operation"] == "dimension"
    assert step["input_expressions"]["consistent"] == "True"
    assert "length" in step["input_expressions"]["dimensions"]


def test_parse_and_cancel_keep_their_own_labels(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("labels")

    tools["math"]("parse", "x**2 + 1", session=True)
    tools["math"]("cancel", "(x**2 - 1)/(x - 1)", session=True)

    steps = tools["session_get_steps"]()["steps"]
    assert steps[0]["operation"] == "parse"
    assert steps[0]["input_expressions"]["operation"] == "parse"
    assert steps[1]["operation"] == "cancel"
    assert steps[1]["input_expressions"]["operation"] == "cancel"


def test_evalf_substitution_is_archived(fresh_session_manager) -> None:
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("evalf-anchor")

    tools["math"]("evalf", "x**2", substitution={"x": "2"}, session=True)

    step = tools["session_get_steps"]()["steps"][0]
    assert json.loads(step["input_expressions"]["input_substitution"]) == {"x": "2"}


class TestOperationProvenance:
    def test_matrix_call_keeps_its_own_name(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _make_tools()
        tools["session_start"](name="provenance")
        tools["math"](
            operation="eigenvals",
            expression="Matrix([[0, -1], [1, 0]])",
            session=True,
        )

        step = tools["session_get_steps"]()["steps"][0]

        assert step["operation"] == "matrix_op"  # coarse bucket is unchanged
        assert step["input_expressions"]["operation"] == "eigenvals"


class TestUnknownSourceLabel:
    def test_unknown_label_is_reported_not_dropped(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _make_tools()
        tools["session_start"](name="source-label")

        result = tools["session_load_formula"](
            expression="F = m*a", source="newtonian_mechanics"
        )

        assert result["success"] is True
        assert result["source"] == "user_input"
        assert result["source_detail"] == "newtonian_mechanics"
        assert any(
            "newtonian_mechanics" in w for w in result.get("warnings", [])
        ), result

    def test_known_label_needs_no_warning(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _make_tools()
        tools["session_start"](name="source-label-known")

        result = tools["session_load_formula"](expression="F = m*a", source="textbook")

        assert result["source"] == "textbook"
        assert not result.get("warnings")


class TestUnrecognizedPattern:
    def test_replacement_is_reported(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _make_tools()

        result = tools["session_start"](name="pattern", pattern="stability_analysis")

        assert result["pattern"] == "direct-manipulation"
        assert any("stability_analysis" in w for w in result.get("warnings", [])), result

    def test_known_pattern_needs_no_warning(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _make_tools()

        result = tools["session_start"](name="pattern-ok", pattern="variational")

        assert result["pattern"] == "variational"
        assert not result.get("warnings")


# A system solve step records a tuple output; traversal must survive it (r16 task-20).
_SYSTEM = "x+y+z-12, -lam+y*z, -lam+x*z, -lam+x*y"


class TestTupleSolveStep:
    def test_system_solve_then_explain_verify_complete(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        register_session_tools(mcp)
        register_math_tools(mcp)

        # A goal makes compute_progress traverse _target_coverage, the exact
        # path that used to dereference the tuple.
        mcp.tools["session_start"]("system_solve", goal="solve the nonlinear system")
        solve = mcp.tools["math"](
            "solve", _SYSTEM, variable="x,y,z,lam", session=True
        )
        assert solve["success"] is True, solve
        assert solve["step"] == 1

        explain = mcp.tools["session_explain"]()
        assert explain["success"] is True, explain

        verify = mcp.tools["session_verify_session"]()
        assert verify["success"] is True, verify

        complete = mcp.tools["session_complete"](auto_save=False)
        assert complete["success"] is True, complete
        assert complete["total_steps"] == 1
