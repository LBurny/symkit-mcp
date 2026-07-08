"""Test Phase 2 integral transforms via the unified math() tool."""

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


def test_phase2_unified_integral_transforms() -> None:
    """Exercise all 4 Phase 2 integral transforms via math()."""
# ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    _register_math_tools(mcp)

    # Laplace transform: exp(-k*t) -> 1/(k + s)
    result = mcp.tools["math"](
        "laplace", "exp(-k*t)", variable="t", with_respect_to="s", session=False
    )
    assert result["success"], result.get("error")
    result_str = result["expression"]
    assert "1/" in result_str and ("s" in result_str or "k" in result_str)

    # Laplace transform: Heaviside step
    result = mcp.tools["math"](
        "laplace", "Heaviside(t)", variable="t", with_respect_to="s", session=False
    )
    assert result["success"], result.get("error")
    assert "1/s" in result["expression"]

    # Laplace transform: PK elimination
    result = mcp.tools["math"](
        "laplace", "C0*exp(-k*t)", variable="t", with_respect_to="s", session=False
    )
    assert result["success"], result.get("error")

    # Inverse Laplace transform: 1/(s + k)
    result = mcp.tools["math"](
        "ilaplace", "1/(s + k)", variable="s", with_respect_to="t", session=False
    )
    assert result["success"], result.get("error")
    assert any(
        p in result["expression"]
        for p in ("exp(-k*t)", "exp(-t*k)", "exp(-t*re(k)")
    )

    # Inverse Laplace transform: 1/s
    result = mcp.tools["math"](
        "ilaplace", "1/s", variable="s", with_respect_to="t", session=False
    )
    assert result["success"], result.get("error")

    # Inverse Laplace transform: two poles
    result = mcp.tools["math"](
        "ilaplace",
        "A/(s + lambda1) + B/(s + lambda2)",
        variable="s",
        with_respect_to="t",
        session=False,
    )
    assert result["success"], result.get("error")

    # Fourier transform: Gaussian
    result = mcp.tools["math"](
        "fourier", "exp(-x**2)", variable="x", with_respect_to="k", session=False
    )
    assert result["success"], result.get("error")

    # Fourier transform: constant
    result = mcp.tools["math"](
        "fourier", "1", variable="x", with_respect_to="k", session=False
    )
    assert result["success"], result.get("error")

    # Inverse Fourier transform: Lorentzian
    result = mcp.tools["math"](
        "ifourier", "1/(1 + k**2)", variable="k", with_respect_to="x", session=False
    )
    assert result["success"], result.get("error")

    # Inverse Fourier transform: constant
    result = mcp.tools["math"](
        "ifourier", "1", variable="k", with_respect_to="x", session=False
    )
    assert result["success"], result.get("error")


if __name__ == "__main__":
    test_phase2_unified_integral_transforms()
    print("✅ Phase 2 unified integral transforms passed")
