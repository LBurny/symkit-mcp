"""Round-23 F11: a symbolic-order Derivative step must land in the chain.

Probe reference: audit3[1] — ``math(simplify, ..., session=True)`` returned
``success: true`` with no ``step`` and buried the SymPy TypeError in warnings.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit_mcp.tools._state import set_session
from tests.conftest import MockMCP

# The exact audit3[1] input.
_AUDIT3_INPUT = (
    "M*(-n - 1)*(-t + x)**(n + 1)/(-t + x) + "
    "Sum(-k*(-t + x)**k*Derivative(f(t), (t, k))/((-t + x)*factorial(k)) + "
    "(-t + x)**k*Derivative(f(t), (t, k + 1))/factorial(k), (k, 0, n))"
)


def _tools() -> dict[str, Any]:
    from symkit_mcp.tools.math import register_math_tools
    from symkit_mcp.tools.session import register_session_tools

    mcp = MockMCP()
    register_session_tools(mcp)
    register_math_tools(mcp)
    return mcp.tools


def test_symbolic_order_derivative_step_is_recorded(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="f11")

    result = tools["math"]("simplify", _AUDIT3_INPUT, session=True)

    assert result["success"] is True
    assert result.get("step") == 1, result
    assert not any(
        "Step recording failed" in w for w in result.get("warnings") or []
    ), result.get("warnings")

    steps = tools["session_get_steps"]()
    assert steps["count"] == 1
    step = steps["steps"][0]
    assert step["operation"] == "simplify"
    assert step["output_srepr"], step
    assert step["input_srepr"], step
    assert "Derivative" in step["output_expression"]
    # The step is archived even though the verifier could not run.
    assert step["status"] == "pending_verification", step


def test_ordinary_steps_keep_their_verdict(fresh_session_manager: Any) -> None:
    """No regression: a verifiable step still gets its automatic verdict."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="f11-ordinary")
    result = tools["math"]("diff", "x**3", variable="x", session=True)
    assert result.get("step") == 1, result
    steps = tools["session_get_steps"]()["steps"]
    assert steps[0]["status"] == "success", steps[0]


def test_add_step_tolerates_a_verifier_crash() -> None:
    """Domain-level guarantee behind the tool-surface fix."""
    from symkit.domain.derivation_session import DerivationSession, OperationType

    session = DerivationSession(session_id="f11-domain", name="f11-domain")
    # The audit3[1] input and the expression ``simplify`` actually returned:
    # verifying the difference expands the Sum and raises for the symbolic order.
    produced = (
        "-M*n*(-t + x)**n - M*(-t + x)**n - "
        "(-t + x)**(n + 1)*Derivative(f(t), (t, n + 1))/((t - x)*gamma(n + 1))"
    )
    step = session._add_step(
        operation=OperationType.SIMPLIFY,
        description="symbolic-order derivative",
        input_expressions={"original": _AUDIT3_INPUT},
        output_expr=sp.sympify(produced),
        sympy_command="math('simplify', ...)",
        prior_expr=sp.sympify(_AUDIT3_INPUT),
    )

    assert session.step_count == 1
    assert step.output_srepr
    assert step.input_srepr
    assert step.status.value == "pending_verification"
    assert "inconclusive" in step.verification_result
    assert "Cannot give expansion for symbolic count" in step.verification_result


def teardown_function() -> None:
    set_session(None)
