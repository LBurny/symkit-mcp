"""Invariant I2: verification must reconstruct the archived object, not re-parse
the display string.

``str(expr)`` is a *display* format and is not guaranteed to round-trip.  For
``E``/``I`` the parser deliberately protects the names as user variables
(run-020: ``E``/``I`` are usually Young's modulus / current in a derivation
tool), so re-parsing the display string ``"Eq(x, I)"`` yields ``Symbol('I')``
while the archived object holds the imaginary unit.  Verification then reports
a false FAILED with residual ``I**2 + 1``.

The archived ``srepr`` (``"Equality(Symbol('x'), I)"``) *does* round-trip:
``sympify`` resolves ``I`` against the full SymPy namespace.  Verification must
prefer it, exactly as ``DerivationSession._safe_load_expression`` already does.
"""

from __future__ import annotations

from pathlib import Path

import sympy as sp

from symkit.domain.derivation_session import DerivationSession
from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py


def _make_tools():
    # ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _verified(step) -> bool:
    import json

    result = json.loads(step.verification_result) if step.verification_result else {}
    return bool(result.get("is_verified"))


# ── Imaginary unit ──────────────────────────────────────────────────────────


def test_solve_imaginary_solution_is_verified(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("ei_imaginary", goal="solve x**2 + 1 = 0")

    res = tools["math"](operation="solve", expression="x**2 + 1", variable="x")
    assert res["success"], res
    assert "I" in res["expression"]

    step = _state.get_session().steps[-1]
    assert _verified(step), (
        f"imaginary solution flagged as {step.status.value}: {step.verification_result}"
    )


# ── Euler's number ──────────────────────────────────────────────────────────


def test_euler_constant_output_is_verified(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("ei_euler", goal="simplify exp(1)")

    res = tools["math"](operation="simplify", expression="exp(1)")
    assert res["success"], res
    assert res["expression"] == "E"

    step = _state.get_session().steps[-1]
    assert _verified(step), (
        f"E output flagged as {step.status.value}: {step.verification_result}"
    )


def test_verify_step_prefers_srepr_for_reserved_atoms():
    """Direct verifier check: the archived srepr wins over the display string."""
    from symkit.domain.derivation_session import DerivationStep, OperationType
    from symkit.domain.step_verifier import StepVerifier

    step = DerivationStep(
        step_number=1,
        operation=OperationType.SOLVE,
        description="solve x**2 + 1 = 0",
        input_expressions={"equation": "x**2 + 1"},
        output_expression="Eq(x, I)",
        output_latex="x = i",
        output_srepr=sp.srepr(sp.Eq(sp.Symbol("x"), sp.I)),
        input_srepr=sp.srepr(sp.Symbol("x") ** 2 + 1),
        sympy_command="solve(x**2 + 1, x)",
    )
    result = StepVerifier().verify_step(step)
    assert result.is_verified, result.message


# ── Unevaluated operations in the input ─────────────────────────────────────


def test_simplify_of_unevaluated_derivative_is_verified():
    """A correct simplify step must not fail because its input was unevaluated.

    ``simplify(Derivative(tanh(x**4), x))`` yields the evaluated derivative, but
    ``simplify(Derivative(...) - <evaluated>)`` does not reduce to zero, so the
    identically-zero residual was reported as a changed value and the chain
    became `failed` (task-15 step 12).
    """
    from symkit.domain.derivation_session import DerivationStep, OperationType
    from symkit.domain.step_verifier import StepVerifier

    x = sp.Symbol("x")
    unevaluated = sp.Derivative(sp.tanh(x**4), x)
    evaluated = 4 * x**3 * (1 - sp.tanh(x**4) ** 2)
    step = DerivationStep(
        step_number=1,
        operation=OperationType.SIMPLIFY,
        description="simplify an unevaluated derivative",
        input_expressions={"original": "Derivative(tanh(x**4), x)"},
        output_expression=str(evaluated),
        output_latex="",
        output_srepr=sp.srepr(evaluated),
        input_srepr=sp.srepr(unevaluated),
        sympy_command="math('simplify', ...)",
    )
    result = StepVerifier().verify_step(step)
    assert result.is_verified, f"{result.status.value}: {result.message}"


# ── Persistence round-trip ──────────────────────────────────────────────────


def test_verification_survives_persistence_roundtrip(fresh_session_manager, tmp_path):
    manager = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("ei_persist", goal="solve x**2 + 1 = 0")
    tools["math"](operation="solve", expression="x**2 + 1", variable="x")

    session = _state.get_session()
    path = manager.sessions_dir / "ei_persist.json" if hasattr(
        manager, "sessions_dir"
    ) else Path(tmp_path) / "ei_persist.json"
    saved = session.save(path)
    reloaded = DerivationSession.load(saved)

    result = reloaded.verify_step(1)
    assert result["success"], result
    assert result["verification_status"] == "verified", result


# ── LaTeX-derived symbol names (not valid Python identifiers) ───────────────


def test_verifier_reconstructs_symbols_that_are_not_valid_python(
    fresh_session_manager,
):
    """``str(Symbol('mu_{t}'))`` is not parseable; the archived srepr is."""
    _ = fresh_session_manager
    from symkit.domain.derivation_session import DerivationStep, OperationType
    from symkit.domain.step_verifier import StepVerifier

    mu = sp.Symbol("mu_{t}")
    step = DerivationStep(
        step_number=1,
        operation=OperationType.DIFFERENTIATE,
        description="d/dt mu_{t}**2",
        input_expressions={"original": str(mu**2)},
        output_expression=str(2 * mu),
        output_latex="2 \\mu_{t}",
        output_srepr=sp.srepr(2 * mu),
        input_srepr=sp.srepr(mu**2),
        sympy_command="diff(mu_{t}**2, mu_{t})",
        # differentiation verifies against the differentiation variable
    )
    result = StepVerifier().verify_step(step)
    assert result.status.value != "failed", (
        f"LaTeX symbol round-trip flagged as failed: {result.message}"
    )
