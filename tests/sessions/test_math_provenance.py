"""math() provenance for dimension, parse/cancel labels and evalf substitution.

r16 tasks 01/03/14/15/16:
* ``math("dimension", ..., session=True)`` must record a step (it used to record
  nothing, so ``step_count`` stayed 0 and the check was unreplayable).
* ``parse`` and ``cancel`` must not be archived under the coarse verification
  buckets ``load_formula`` / ``simplify``.
* an ``evalf`` call with a substitution must archive the substituted point.
"""

from __future__ import annotations

import json
from typing import Any

from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools import session as session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    return mcp.tools


def test_dimension_call_records_a_step(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("dimension-provenance")

    result = tools["math"](
        "dimension", "v*t", units={"v": "m/s", "t": "s"}, session=True
    )
    assert result["success"] is True
    assert result["step"] == 1

    step = tools["session_get_steps"]()["steps"][0]
    assert step["input_expressions"]["operation"] == "dimension"
    assert step["input_expressions"]["consistent"] == "True"
    assert "length" in step["input_expressions"]["dimensions"]


def test_parse_and_cancel_keep_their_own_labels(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("labels")

    tools["math"]("parse", "x**2 + 1", session=True)
    tools["math"]("cancel", "(x**2 - 1)/(x - 1)", session=True)

    steps = tools["session_get_steps"]()["steps"]
    assert steps[0]["operation"] == "parse"
    assert steps[0]["input_expressions"]["operation"] == "parse"
    assert steps[1]["operation"] == "cancel"
    assert steps[1]["input_expressions"]["operation"] == "cancel"


def test_evalf_substitution_is_archived(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("evalf-anchor")

    tools["math"]("evalf", "x**2", substitution={"x": "2"}, session=True)

    step = tools["session_get_steps"]()["steps"][0]
    assert json.loads(step["input_expressions"]["input_substitution"]) == {"x": "2"}
