"""r23 G10: a symbolic-exponent trig power must not wedge the integrate path.

``integrate(cos(theta)**(2*p-1)*sin(theta)**(2*q-1), (theta, 0, pi/2))`` sends
SymPy's default heurisch route into unbounded recursion (observed >510s in the
acceptance rerun; stack at ``heurisch.py:find_non_syms``). The fix detects this
narrow form (a trig power whose exponent carries a symbol other than the
integration variable) and routes it through ``meijerg=True``, returning the
unevaluated integral with a warning when no closed form is found.

The wedge contract is a subprocess test with a hard cap (hard rule 8: stall
contracts do not run in the in-process battery). Numeric trig powers and
non-trig symbolic powers must be untouched.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import sympy as sp

from symkit.infrastructure.sympy_engine import SymPyEngine

# Imported lazily inside the tests so this module still collects (and the
# subprocess wedge test still runs) while the guard is being written.
# ruff: noqa: PLC0415

_REPO_SRC = Path(__file__).resolve().parents[2] / "src"

# The wedging input from the acceptance rerun (task-10).
_WEDGE_INPUT = "cos(theta)**(2*p-1)*sin(theta)**(2*q-1)"

# Hard cap: the guarded route returns in well under a second, so anything near
# this bound means the heurisch route came back.
_CAP_SECONDS = 30.0

_CHILD = """
import faulthandler, json
faulthandler.dump_traceback_later(20, exit=False)
from symkit_mcp.tools._math_dispatch import _execute_operation

result = _execute_operation(
    "integrate",
    {expr!r},
    variable="theta",
    lower="0",
    upper="pi/2",
)
print("RESULT:" + json.dumps({{
    "success": result.get("success"),
    "expression": result.get("expression"),
    "warnings": result.get("warnings", []),
}}))
"""


def _run_in_subprocess(expression: str, cap: float = _CAP_SECONDS) -> dict[str, object]:
    """Run one definite integrate in a child process with a hard timeout."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO_SRC) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-u", "-c", _CHILD.format(expr=expression)]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=cap, env=env
        )
    except subprocess.TimeoutExpired as exc:
        stderr = (exc.stderr or "")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        raise AssertionError(
            f"integrate wedged: no result within {cap}s; child stack:\n"
            f"{stderr[-3000:]}"
        ) from exc
    payload_line = next(
        (line for line in proc.stdout.splitlines() if line.startswith("RESULT:")),
        None,
    )
    assert payload_line is not None, (
        "child produced no result",
        proc.returncode,
        proc.stdout[-2000:],
        proc.stderr[-3000:],
    )
    return json.loads(payload_line[len("RESULT:") :])


def test_symbolic_trig_power_definite_integral_returns_within_cap() -> None:
    """The wedging input must return quickly, unevaluated, with a warning."""
    payload = _run_in_subprocess(_WEDGE_INPUT)

    assert payload["success"] is True, payload
    assert "Integral" in str(payload["expression"]), payload
    assert any("heurisch" in note for note in payload["warnings"]), payload


def test_numeric_trig_power_definite_integral_still_evaluates() -> None:
    """Positive control: a numeric trig exponent must stay on the normal route."""
    payload = _run_in_subprocess("cos(theta)**2", cap=_CAP_SECONDS)

    assert payload["success"] is True, payload
    assert payload["expression"] == "pi/4", payload
    assert not payload["warnings"], payload


class TestDetectionNarrowness:
    def test_symbolic_trig_power_is_detected(self) -> None:
        from symkit.infrastructure.solution_guards import symbolic_trig_power_powers

        theta, p, q = sp.symbols("theta p q")
        powers = symbolic_trig_power_powers(
            sp.cos(theta) ** (2 * p - 1) * sp.sin(theta) ** (2 * q - 1), theta
        )
        assert powers, "symbolic trig powers must be detected"
        assert any("cos(theta)" in item for item in powers)

    def test_numeric_trig_power_is_not_detected(self) -> None:
        from symkit.infrastructure.solution_guards import symbolic_trig_power_powers

        theta = sp.Symbol("theta")
        assert symbolic_trig_power_powers(sp.cos(theta) ** 2, theta) == []

    def test_non_trig_symbolic_power_is_not_detected(self) -> None:
        from symkit.infrastructure.solution_guards import symbolic_trig_power_powers

        x, p = sp.symbols("x p")
        assert symbolic_trig_power_powers(x ** (p - 1), x) == []

    def test_exponent_with_only_the_integration_variable_is_not_detected(self) -> None:
        from symkit.infrastructure.solution_guards import symbolic_trig_power_powers

        theta = sp.Symbol("theta")
        assert symbolic_trig_power_powers(sp.cos(theta) ** theta, theta) == []


class TestGuardedDefiniteIntegral:
    def test_guarded_route_returns_unevaluated_with_warning(self) -> None:
        from symkit.infrastructure.solution_guards import guarded_definite_integral

        theta, p, q = sp.symbols("theta p q")
        integrand = sp.cos(theta) ** (2 * p - 1) * sp.sin(theta) ** (2 * q - 1)
        result, warnings = guarded_definite_integral(
            integrand, theta, sp.Integer(0), sp.pi / 2
        )
        assert result.has(sp.Integral)
        assert warnings and "heurisch" in warnings[0]

    def test_normal_integral_takes_the_default_route(self) -> None:
        from symkit.infrastructure.solution_guards import guarded_definite_integral

        theta = sp.Symbol("theta")
        result, warnings = guarded_definite_integral(
            sp.cos(theta) ** 2, theta, sp.Integer(0), sp.pi / 2
        )
        assert result == sp.pi / 4
        assert warnings == []


class TestEnginePositiveControls:
    """The engine's normal integrals must be byte-for-byte unchanged."""

    def test_numeric_trig_power_unchanged(self) -> None:
        engine = SymPyEngine()
        expr = engine.parse("cos(theta)**2")
        result = engine.integrate(expr, "theta", "0", "pi/2")
        assert result.is_valid
        assert result.raw == "pi/4"
        assert not result.warnings

    def test_simple_symbolic_power_still_evaluated(self) -> None:
        engine = SymPyEngine()
        expr = engine.parse("x**p")
        result = engine.integrate(expr, "x", "0", "1")
        assert result.is_valid
        assert not result.sympy_expr.has(sp.Integral)
        assert not result.warnings


@pytest.mark.parametrize("expression", ["cos(theta)**(2*p-1)*sin(theta)"])
def test_adjacent_form_does_not_crash(expression: str) -> None:
    """A mixed integrand with one symbolic trig power still returns (guard is
    safe, not a wedge itself)."""
    payload = _run_in_subprocess(expression)
    assert payload["success"] is True, payload
