"""r18 A4: a general 3x3 matrix exponential must not wedge the server.

``(Matrix([[2,1,0],[0,3,1],[1,0,2]])*t).exp()`` evaluates ``Matrix.exp()``
eagerly at parse time; SymPy expands it through the eigen-decomposition of
``x^3 - 7x^2 + 16x - 13`` (nested-radical roots) and never returns (>750 s live,
>45 s under the probe cap).  The call must return a correct numeric matrix (for
``evalf`` with numeric values) or a curated refusal, and the fast controls
(diagonal/rotation 2x2, scalar ``exp``) must be unchanged.
"""

from __future__ import annotations

import threading
from typing import Any

import mpmath as mp
import sympy as sp

from symkit.infrastructure.matrix_exp import matrix_exp_argument
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py

_TIMEOUT = 30.0
_TIMED_OUT = object()
A3 = "Matrix([[2,1,0],[0,3,1],[1,0,2]])"
A3_FLOAT = "Matrix([[2.0,1,0],[0,3,1],[1,0,2]])"


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _run_bounded(func: Any, timeout: float = _TIMEOUT) -> Any:
    """Run ``func`` in a daemon thread; return ``_TIMED_OUT`` if it never ends."""
    box: dict[str, Any] = {}

    def runner() -> None:
        try:
            box["value"] = func()
        except Exception as exc:  # surfaced to the caller
            box["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return _TIMED_OUT
    if "error" in box:
        raise box["error"]
    return box["value"]


def _expected() -> Any:
    mp.mp.dps = 30
    return mp.expm(mp.matrix([[2, 1, 0], [0, 3, 1], [1, 0, 2]]))


def _assert_close(expression: str, expected: Any) -> None:
    matrix = sp.sympify(expression)
    assert isinstance(matrix, sp.MatrixBase), matrix
    for i in range(matrix.rows):
        for j in range(matrix.cols):
            got = complex(matrix[i, j]).real
            assert abs(got - float(expected[i, j])) < 1e-9, (i, j, got)


def test_cubic_matrix_exp_with_substitution_returns_correctly() -> None:
    out = _run_bounded(
        lambda: _tools()["math"](
            operation="evalf",
            expression=f"({A3}*t).exp()",
            substitution={"t": "1"},
            session=False,
        )
    )
    assert out is not _TIMED_OUT, "matrix exponential wedged the server"
    assert out["success"], out
    _assert_close(out["expression"], _expected())


def test_cubic_matrix_exp_with_session_returns_correctly() -> None:
    tools = _tools()
    tools["session_start"]("a4")
    out = _run_bounded(
        lambda: tools["math"](
            operation="evalf",
            expression=f"({A3}*t).exp()",
            substitution={"t": "1"},
            session=True,
        )
    )
    assert out is not _TIMED_OUT, "matrix exponential wedged the server"
    assert out["success"], out
    _assert_close(out["expression"], _expected())


def test_float_entry_matrix_exp_returns_correctly() -> None:
    out = _run_bounded(
        lambda: _tools()["math"](
            operation="evalf",
            expression=f"({A3_FLOAT}*t).exp()",
            substitution={"t": "1.0"},
            session=False,
        )
    )
    assert out is not _TIMED_OUT, "matrix exponential wedged the server"
    assert out["success"], out
    _assert_close(out["expression"], _expected())


def test_symbolic_matrix_exp_is_refused_not_wedged() -> None:
    out = _run_bounded(
        lambda: _tools()["math"](
            operation="evalf",
            expression=f"({A3}*t).exp()",
            session=False,
        )
    )
    assert out is not _TIMED_OUT, "symbolic matrix exponential wedged the server"
    assert not out["success"], out
    assert "matrix exponential" in out["error"], out
    assert "symbolic" in out["error"], out


def test_diagonal_2x2_control_unchanged() -> None:
    out = _tools()["math"](
        operation="evalf",
        expression="(Matrix([[2,0],[0,3]])*t).exp()",
        substitution={"t": "1"},
        session=False,
    )
    assert out["success"], out
    assert out["expression"] == "Matrix([[7.38905609893065, 0], [0, 20.0855369231877]])"


def test_rotation_2x2_control_unchanged() -> None:
    out = _tools()["math"](
        operation="evalf",
        expression="(Matrix([[0,1],[-1,0]])*t).exp()",
        substitution={"t": "1"},
        session=False,
    )
    assert out["success"], out
    matrix = sp.sympify(out["expression"])
    assert abs(complex(matrix[0, 0]).real - float(sp.cos(1))) < 1e-12
    assert abs(complex(matrix[0, 1]).real - float(sp.sin(1))) < 1e-12


def test_scalar_exp_control_unchanged() -> None:
    out = _tools()["math"](
        operation="evalf",
        expression="exp(7*t)",
        substitution={"t": "1"},
        session=False,
    )
    assert out["success"], out
    assert out["expression"] == "1096.63315842846"


def test_detector_ignores_scalar_exp() -> None:
    assert matrix_exp_argument("exp(7*t)") is None
    assert matrix_exp_argument("Matrix([[2,0],[0,3]])") is None
    assert matrix_exp_argument("(Matrix([[2,0],[0,3]])*t).exp()") is not None
