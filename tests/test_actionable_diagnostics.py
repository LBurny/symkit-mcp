"""P5 UX: verification and errors must tell the agent what to do next.

Two black-box findings:

* A one-sided limit (``direction="+"``/``"-"``) is computed correctly, then
  reported INCONCLUSIVE because the verifier probed *both* sides of the point
  and the other side legitimately disagrees.  The message gave the agent no way
  to tell "your limit is wrong" from "you asked for a one-sided limit".
* ``dsolve`` with a ``variable`` that does not appear in the ODE surfaced
  SymPy's raw "is not a solvable differential equation in v(t)" — which reads
  as if the equation were unsolvable, when the real problem is that
  ``variable='u'`` does not match the ``v(t)`` in the input.
"""

from __future__ import annotations

import json

from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py


def _tools():
    # ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _last_step():
    sess = _state.get_session()
    assert sess is not None
    return sess.steps[-1]


def _verification(step) -> dict:
    return json.loads(step.verification_result) if step.verification_result else {}


# ── One-sided limits ────────────────────────────────────────────────────────


def test_right_sided_limit_is_verified(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("limit_right")

    res = tools["math"](
        operation="limit",
        expression="1/x",
        variable="x",
        point="0",
        direction="+",
        session=True,
    )
    assert res["success"], res
    assert res["expression"] == "oo", res
    assert _verification(_last_step())["status"] == "verified", _verification(_last_step())


def test_left_sided_limit_is_verified(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("limit_left")

    res = tools["math"](
        operation="limit",
        expression="1/x",
        variable="x",
        point="0",
        direction="-",
        session=True,
    )
    assert res["success"], res
    assert res["expression"] == "-oo", res
    assert _verification(_last_step())["status"] == "verified", _verification(_last_step())


def test_two_sided_limit_still_verified(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("limit_two_sided")

    tools["math"](operation="limit", expression="sin(x)/x", variable="x", point="0")
    assert _verification(_last_step())["status"] == "verified", _verification(_last_step())


def test_limit_direction_is_archived(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("limit_archive")

    tools["math"](
        operation="limit",
        expression="1/x",
        variable="x",
        point="0",
        direction="+",
        session=True,
    )
    step = _last_step()
    assert step.input_expressions.get("limit_direction") == "+", step.input_expressions


def _limit_step(direction: str, output_srepr: str):
    import sympy as sp

    from symkit.domain.derivation_session import DerivationStep, OperationType

    return DerivationStep(
        step_number=1,
        operation=OperationType.LIMIT,
        description="limit probe",
        input_expressions={"original": "1/x", "limit_direction": direction},
        output_expression="-oo",
        output_latex="-\\infty",
        output_srepr=output_srepr,
        input_srepr=sp.srepr(sp.Symbol("x") ** -1),
        sympy_command="limit(expr, x, 0)",
    )


def test_one_sided_limit_verification_message_names_the_side():
    """A one-sided mismatch must say which side was checked."""
    import sympy as sp

    from symkit.domain.step_verifier import StepVerifier

    step = _limit_step("+", sp.srepr(-sp.oo))  # wrong: 1/x -> +oo on the right
    result = StepVerifier().verify_step(step)

    assert result.status.value == "inconclusive"
    assert "right-sided" in result.message.lower(), result.message


def test_two_sided_limit_mismatch_suggests_the_direction_parameter():
    """A two-sided mismatch must suggest ``direction``, not just fail."""
    import sympy as sp

    from symkit.domain.step_verifier import StepVerifier

    step = _limit_step("+-", sp.srepr(sp.oo))  # 1/x is not two-sided at 0
    result = StepVerifier().verify_step(step)

    assert result.status.value == "inconclusive"
    assert "direction=" in result.message, result.message


# ── dsolve variable mismatch ────────────────────────────────────────────────


def test_dsolve_variable_mismatch_names_the_function_in_the_input(
    fresh_session_manager,
):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("dsolve_mismatch")

    res = tools["math"](
        operation="dsolve",
        expression="Derivative(v(t), t) = -k*v(t)",
        variable="u",
        with_respect_to="t",
        session=False,
    )
    assert not res["success"], res
    assert "v" in res["error"], res["error"]
    assert "variable" in res["error"].lower(), res["error"]


def test_dsolve_with_matching_variable_still_works(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("dsolve_match")

    res = tools["math"](
        operation="dsolve",
        expression="Derivative(v(t), t) = -k*v(t)",
        variable="v",
        with_respect_to="t",
        session=False,
    )
    assert res["success"], res
    assert "exp(-k*t)" in res["expression"], res
