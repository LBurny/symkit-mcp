"""``session_verify_session`` must surface the Lean kernel lane's verdicts.

The Lean certification attaches a ``details.lean`` sub-record to a step's
verification result without touching the SymPy verdict, so the summary only
reported the SymPy counts and an operator could not see from it how many steps
the kernel actually proved (operator feedback, 2026-09-16: 23 SymPy-verified
steps of which only 12 carried a kernel proof).  The summary now counts the
attached kernel verdicts under ``lean`` whenever any step was certified.
"""

from __future__ import annotations

import json
from typing import Any

from symkit_mcp.tools import _state
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP / fresh_session_manager are provided by conftest.py
# ruff: noqa: F821


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _attach_lean(step: Any, status: str) -> None:
    """Shape a ``details.lean`` record the way ``certify_session`` leaves it."""
    record = json.loads(step.verification_result)
    record.setdefault("details", {})["lean"] = {
        "method": "lean_kernel",
        "status": status,
        "lane": "ring",
    }
    step.verification_result = json.dumps(record)


def test_summary_reports_kernel_counts(fresh_session_manager) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("lean-summary")
    tools["math"]("simplify", "x + x", session=True)
    tools["math"]("expand", "(x + 1)*(x - 1)", session=True)
    session = _state.get_session()
    _attach_lean(session.steps[0], "proven")
    _attach_lean(session.steps[1], "unproven")

    res = tools["session_verify_session"]()

    assert res["success"], res
    assert res["lean"] == {"proven": 1, "unproven": 1}
    assert "Lean kernel: proven 1, unproven 1" in res["display_text"]


def test_summary_omits_kernel_counts_without_certification(fresh_session_manager) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("lean-summary-none")
    tools["math"]("simplify", "x + x", session=True)

    res = tools["session_verify_session"]()

    assert res["success"], res
    assert "lean" not in res
