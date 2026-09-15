"""The math() tool's error and provenance contract (r17 round).

Black-box findings from the 2026-09-14 complex-theorem round:

* ``math("evalf", "isprime(1681)")`` and ``math("simplify", "factorint(1681)")``
  raised inside the handler, so the client saw a protocol error
  (``'bool' object has no attribute 'evalf'`` / ``'success'``) instead of a
  structured ``success: false``.  An internal failure is still a tool result.
* An unknown operation that arrived with parameters was rejected with
  "Parameter 'variable' is not used by operation 'sum'", which describes an
  operation that does not exist.
* A recorded step stored ``str(parsed_input)`` as ``input_expressions.original``,
  so ``hermite(3, 0.7)`` was archived as ``-5.656`` and ``(x+1)*(x-1)`` as
  ``(x + 1)*(x - 1*1)`` — the provenance no longer reproduced the submission.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit_mcp.tools import math as math_tools


def _tool() -> Any:
    mcp = MockMCP()  # noqa: F821 - provided by conftest.py
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def test_evalf_on_boolean_is_a_structured_failure() -> None:
    result = _tool()("evalf", "isprime(1681)", session=False)
    assert result["success"] is False
    assert "failed" in result["error"] or "boolean" in result["error"]


def test_simplify_on_dict_is_a_structured_failure() -> None:
    result = _tool()("simplify", "factorint(1681)", session=False)
    assert result["success"] is False
    assert result["error"]


def test_unknown_operation_is_named_before_its_parameters() -> None:
    result = _tool()("sum", "k**2", variable="k", lower="1", upper="10", session=False)
    assert result["success"] is False
    assert "Unknown operation 'sum'" in result["error"]


def test_recorded_input_is_the_submitted_string() -> None:
    recorded = math_tools._step_input_expressions(
        "expand", "(x+1)*(x-1)", None, None, None, "+-"
    )
    assert recorded["original"] == "(x+1)*(x-1)"


def test_recorded_input_keeps_a_function_call() -> None:
    recorded = math_tools._step_input_expressions(
        "evalf", "hermite(3, 0.7)", None, None, None, "+-"
    )
    assert recorded["original"] == "hermite(3, 0.7)"


def test_recorded_input_survives_a_falsy_parsed_object() -> None:
    # Non-string submissions archive the parsed object; sympy's 0/false are
    # falsy, so ``input_obj or ""`` blanked them instead of recording them.
    recorded = math_tools._step_input_expressions(
        "expand", 0, sp.Integer(0), None, None, "+-"
    )
    assert recorded["original"] == "0"
