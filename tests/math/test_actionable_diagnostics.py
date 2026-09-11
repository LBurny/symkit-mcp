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


def test_sign_decision_failure_suggests_assumptions(fresh_session_manager):
    """A limit that needs sign information must say how to supply it.

    ``limit(terminal velocity, t -> oo)`` fails with SymPy's "Result depends on
    the sign of ...", which names the symbols but not the remedy.
    """
    _ = fresh_session_manager
    tools = _tools()

    res = tools["math"](
        operation="limit",
        expression="sqrt(2*g*m/(A*C_d*rho))*tanh(t*sqrt(A*C_d*g*rho/(2*m)))",
        variable="t",
        point="oo",
        session=False,
    )
    assert not res["success"], res
    assert "assumptions=" in res["error"], res["error"]


def test_sign_decision_failure_resolves_with_assumptions(fresh_session_manager):
    """The suggested remedy must actually work."""
    _ = fresh_session_manager
    tools = _tools()

    res = tools["math"](
        operation="limit",
        expression="sqrt(2*g*m/(A*C_d*rho))*tanh(t*sqrt(A*C_d*g*rho/(2*m)))",
        variable="t",
        point="oo",
        assumptions=["A is positive", "C_d is positive", "g is positive",
                     "m is positive", "rho is positive"],
        session=False,
    )
    assert res["success"], res
    assert "sqrt(2)" in res["expression"], res


# ── Substitution mapping must survive values containing commas ──────────────


def test_substitution_with_comma_in_value_is_verified(fresh_session_manager):
    """``Rational(1,6)`` contains a comma; the mapping must not be split on it.

    The human-readable ``replacement`` string is comma-joined, so splitting it
    on ``","`` fragments any value that itself contains a comma and produced a
    false "Could not parse replacement expression" (task-02 step 23).
    """
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("sub_comma")

    res = tools["math"](
        operation="substitute",
        expression="L_fw*c_w1*(nu_tilde/d)**2",
        substitution={"L_fw": "(1 + c_w3**6)**Rational(1,6)"},
        session=True,
    )
    assert res["success"], res

    step = _last_step()
    assert "replacement_map" in step.input_expressions, step.input_expressions
    assert _verification(step)["status"] == "verified", _verification(step)


def test_substitution_with_multi_argument_call_is_verified(fresh_session_manager):
    """A multi-argument replacement (``Max(a, b)``) has the same failure mode."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("sub_max")

    res = tools["math"](
        operation="substitute",
        expression="x + y",
        substitution={"x": "Max(y, 0)"},
        session=True,
    )
    assert res["success"], res
    assert _verification(_last_step())["status"] == "verified", _verification(_last_step())


def test_legacy_comma_string_still_verifies():
    """Records written before the JSON map must keep verifying."""
    import sympy as sp

    from symkit.domain.derivation_session import DerivationStep, OperationType
    from symkit.domain.step_verifier import StepVerifier

    x, y = sp.Symbol("x"), sp.Symbol("y")
    step = DerivationStep(
        step_number=1,
        operation=OperationType.SUBSTITUTE,
        description="legacy record",
        input_expressions={"original": "x + y", "replacement": "x = 2"},
        output_expression=str(sp.Integer(2) + y),
        output_latex="",
        output_srepr=sp.srepr(sp.Integer(2) + y),
        input_srepr=sp.srepr(x + y),
        sympy_command="math('substitute', ...)",
    )
    result = StepVerifier().verify_step(step)
    assert result.is_verified, f"{result.status.value}: {result.message}"


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
