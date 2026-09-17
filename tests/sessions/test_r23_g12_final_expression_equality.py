"""r23 G12: an equality ``final_expression`` must not collapse to "True".

``session_complete(final_expression="Matrix([[1,0],[0,1]]) = Matrix([[1,0],[0,1]])")``
parsed the equality with the ordinary parser, where ``Eq`` folds to a boolean at
construction because both sides are equal — the deliverable came back as
``"final_expression": "True"`` / ``"final_latex": "\\text{True}"``, silently
dropping both sides (operator transcript: a spectral-theorem deliverable
``A = Q*Lambda*Q.T`` became "True").  The ``final_expression`` path now reuses
``unevaluated_equality`` whenever the ordinary parse collapses to a boolean, so
the two sides survive; a bare constant ("3/8") is untouched.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP / fresh_session_manager are provided by conftest.py
# ruff: noqa: F821

_MATRIX_IDENTITY = "Matrix([[1,0],[0,1]]) = Matrix([[1,0],[0,1]])"


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _session_with_step(tools: dict[str, Any], name: str) -> None:
    tools["session_start"](name=name)
    tools["math"]("simplify", "x + x", session=True)


class TestG12EqualityDeliverableSurvives:
    def test_matrix_identity_keeps_both_sides(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = _tools()
        _session_with_step(tools, "g12-matrix-identity")
        done = tools["session_complete"](
            final_expression=_MATRIX_IDENTITY, auto_save=False
        )
        assert done["success"], done
        assert done["final_expression"] != "True", done["final_expression"]
        assert "Matrix" in done["final_expression"], done["final_expression"]
        assert "True" not in done["final_latex"], done["final_latex"]
        assert "begin{matrix}" in done["final_latex"], done["final_latex"]
        assert "=" in done["final_latex"], done["final_latex"]

    def test_equality_override_is_rebuilt_as_unevaluated_eq(
        self, fresh_session_manager
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        _session_with_step(tools, "g12-eq-shape")
        done = tools["session_complete"](
            final_expression=_MATRIX_IDENTITY, auto_save=False
        )
        assert done["success"], done
        expected = sp.Eq(
            sp.Matrix([[1, 0], [0, 1]]), sp.Matrix([[1, 0], [0, 1]]), evaluate=False
        )
        assert done["final_expression"] == str(expected), done["final_expression"]


class TestG12ConstantBehaviourUnchanged:
    def test_bare_constant_override_unchanged(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = _tools()
        _session_with_step(tools, "g12-constant")
        done = tools["session_complete"](final_expression="3/8", auto_save=False)
        assert done["success"], done
        assert done["final_expression"] == "3/8", done["final_expression"]
        assert done["final_latex"] == sp.latex(sp.Rational(3, 8)), done["final_latex"]

    def test_symbolic_override_unchanged(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = _tools()
        _session_with_step(tools, "g12-symbolic")
        done = tools["session_complete"](final_expression="2*x", auto_save=False)
        assert done["success"], done
        assert done["final_expression"] == "2*x", done["final_expression"]


class TestG12AutoSaveWordingIsHonest:
    def test_equality_outcome_is_not_called_a_bare_constant(
        self, fresh_session_manager
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        _session_with_step(tools, "g12-warning")
        done = tools["session_complete"](
            final_expression=_MATRIX_IDENTITY, auto_save=True
        )
        assert done["success"], done
        warnings = done.get("warnings", [])
        skipped = [w for w in warnings if "auto_save skipped" in w]
        assert skipped, warnings
        assert "bare constant" not in skipped[0], skipped[0]
