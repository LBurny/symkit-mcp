"""Comprehensive coverage of the unified math() tool operations."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit_mcp.tools import math as math_tools  # noqa: E402

# MockMCP is provided by conftest.py


def _register_math_tools(mcp: Any) -> None:
    math_tools.register_math_tools(mcp)


def test_unified_math_all_operations() -> None:
    """Exercise every operation exposed by math() at least once."""
# ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    _register_math_tools(mcp)

    cases: list[tuple[str, str, dict[str, Any]]] = [
        # syntactic
        ("parse", "x**2 + 2*x + 1", {}),
        ("simplify", "x**2 + 2*x + 1", {}),
        ("expand", "(x + 1)**2", {}),
        ("factor", "x**2 - 1", {}),
        ("collect", "x*y + x - 3 + 2*x**2", {"variable": "x"}),
        ("cancel", "(x**2 - 1)/(x - 1)", {}),
        ("apart", "(x**2 + 3*x + 2)/(x**2 + 5*x + 6)", {"variable": "x"}),
        ("together", "1/x + 1/y", {}),
        ("trigsimp", "sin(x)**2 + cos(x)**2", {}),
        ("powsimp", "x**2 * x**3", {}),
        ("radsimp", "1/(sqrt(3) + sqrt(2))", {}),
        ("combsimp", "factorial(n)/factorial(n - 2)", {}),
        # solve / substitute
        ("solve", "a*x**2 + b*x + c = 0", {"variable": "x"}),
        ("substitute", "x**2 + y", {"substitution": {"x": "a + b", "y": "c"}}),
        # calculus
        ("diff", "x**3 + 2*x", {"variable": "x"}),
        ("integrate", "3*x**2 + 2", {"variable": "x"}),
        ("limit", "sin(x)/x", {"variable": "x", "point": "0"}),
        ("series", "exp(x)", {"variable": "x", "point": "0", "order": 4}),
        # ODE
        ("dsolve", "diff(y, t) - k*y", {"variable": "y", "with_respect_to": "t"}),
        # vector
        ("gradient", "x**2 + y**2", {"variable": "x,y,z"}),
        ("divergence", "x*y, y*z, z*x", {"variable": "x,y,z"}),
        ("curl", "y, z, x", {"variable": "x,y,z"}),
        ("laplacian", "x**2 + y**2", {"variable": "x,y,z"}),
        # matrix
        ("det", "Matrix([[1, 2], [3, 4]])", {}),
        ("inv", "Matrix([[1, 2], [3, 4]])", {}),
        ("eigenvals", "Matrix([[1, 2], [2, 1]])", {}),
        ("eigenvects", "Matrix([[1, 2], [2, 1]])", {}),
        # transforms
        ("laplace", "exp(-k*t)", {"variable": "t", "with_respect_to": "s"}),
        ("ilaplace", "1/(s + k)", {"variable": "s", "with_respect_to": "t"}),
        ("fourier", "exp(-x**2)", {"variable": "x", "with_respect_to": "k"}),
        ("ifourier", "1/(1 + k**2)", {"variable": "k", "with_respect_to": "x"}),
    ]

    for operation, expression, kwargs in cases:
        result = mcp.tools["math"](operation, expression, session=False, **kwargs)
        assert result["success"], (
            f"math('{operation}', '{expression}') failed: {result.get('error')}"
        )

    # Specific result checks for operations that return structured data
    result = mcp.tools["math"]("solve", "a*x**2 + b*x + c = 0", variable="x", session=False)
    assert len(result["all_solutions"]) == 2

    result = mcp.tools["math"]("eigenvals", "Matrix([[1, 2], [2, 1]])", session=False)
    assert result.get("eigenvalues") is not None
    assert len(result["eigenvalues"]) == 2

    result = mcp.tools["math"]("eigenvects", "Matrix([[1, 2], [2, 1]])", session=False)
    assert result.get("eigenvectors") is not None
    assert len(result["eigenvectors"]) == 2

    # After the ifourier fix, this should not collapse to 0
    result = mcp.tools["math"](
        "ifourier", "1/(1 + k**2)", variable="k", with_respect_to="x", session=False
    )
    assert result["expression"] != "0"

    # Assumptions must not break solve: the variable symbol should match the
    # assumption-bearing symbols in the expression.
    result = mcp.tools["math"](
        "solve",
        "(-G)*M*m/R + m*v**2/2 = 0",
        variable="v",
        assumptions=[
            "G is positive",
            "M is positive",
            "R is positive",
            "m is positive",
            "v is positive",
        ],
        session=False,
    )
    assert result["success"], result.get("error")
    assert "sqrt" in result["expression"]


if __name__ == "__main__":
    test_unified_math_all_operations()
    print("✅ Unified math operation coverage passed")
