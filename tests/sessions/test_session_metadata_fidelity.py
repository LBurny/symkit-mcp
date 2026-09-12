"""Session provenance: concrete operation names, and silently-dropped metadata.

From the 2026-09-12 complex-derivation black-box round
(`symkit-mcp-test-complex`):

* Recording buckets four distinct matrix calls onto ``matrix_op``, so the step
  no longer says which call it was.
* ``session_load_formula(source=...)`` coerced an unknown label to
  ``user_input`` with no warning, so the caller's provenance label vanished.
* ``session_start(pattern=...)`` swapped an unrecognized pattern for
  ``direct-manipulation`` with no warning.
"""

from __future__ import annotations

from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools import session as session_tools

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py


def _tools() -> dict:
    mcp = MockMCP()
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    return mcp.tools


class TestOperationProvenance:
    def test_matrix_call_keeps_its_own_name(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](name="provenance")
        tools["math"](
            operation="eigenvals",
            expression="Matrix([[0, -1], [1, 0]])",
            session=True,
        )

        step = tools["session_get_steps"]()["steps"][0]

        assert step["operation"] == "matrix_op"  # coarse bucket is unchanged
        assert step["input_expressions"]["operation"] == "eigenvals"


class TestUnknownSourceLabel:
    def test_unknown_label_is_reported_not_dropped(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](name="source-label")

        result = tools["session_load_formula"](
            expression="F = m*a", source="newtonian_mechanics"
        )

        assert result["success"] is True
        assert result["source"] == "user_input"
        assert result["source_detail"] == "newtonian_mechanics"
        assert any(
            "newtonian_mechanics" in w for w in result.get("warnings", [])
        ), result

    def test_known_label_needs_no_warning(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](name="source-label-known")

        result = tools["session_load_formula"](expression="F = m*a", source="textbook")

        assert result["source"] == "textbook"
        assert not result.get("warnings")


class TestUnrecognizedPattern:
    def test_replacement_is_reported(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()

        result = tools["session_start"](name="pattern", pattern="stability_analysis")

        assert result["pattern"] == "direct-manipulation"
        assert any("stability_analysis" in w for w in result.get("warnings", [])), result

    def test_known_pattern_needs_no_warning(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()

        result = tools["session_start"](name="pattern-ok", pattern="variational")

        assert result["pattern"] == "variational"
        assert not result.get("warnings")
