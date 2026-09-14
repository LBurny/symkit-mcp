"""The math tool must answer list literals instead of leaking internal errors.

2026-09-14 defect: ``evalf("[1/1.168, 2+2]")`` died with
``'list' object has no attribute 'evalf'`` and ``simplify`` with
``'list' object has no attribute 'replace'`` — the parser accepted the
bracket syntax but the execution layer received a bare Python list.
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools import math as math_tools

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py


def _math() -> Any:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


class TestListLiteralToolSurface:
    def test_evalf_flat_list(self) -> None:
        result = _math()("evalf", "[1/1.168, 2+2]", session=False)
        assert result["success"] is True, result

    def test_simplify_flat_list(self) -> None:
        result = _math()("simplify", "[1/1.168, 2+2]", session=False)
        assert result["success"] is True, result

    def test_evalf_matrix_grid(self) -> None:
        result = _math()("evalf", "[[1, 2], [3, 4]]", session=False)
        assert result["success"] is True, result
