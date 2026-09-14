"""Regression: a system ``solve`` step must not brick session explain/complete.

r16 task-20: a comma-separated system solve records a Python tuple as the
step output / current expression.  ``compute_progress`` then called
``.free_symbols`` on that tuple, so ``session_explain`` and
``session_complete`` raised ``'tuple' object has no attribute 'free_symbols'``
and the session could neither be explained nor finalized.
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools import session as session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _register_all_tools(mcp: Any) -> None:
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)


_SYSTEM = "x+y+z-12, -lam+y*z, -lam+x*z, -lam+x*y"


class TestTupleSolveStep:
    def test_system_solve_then_explain_verify_complete(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

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
