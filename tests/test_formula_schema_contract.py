"""Writer/reader schema contract between DerivationResult and FormulaEntry.

The derived-formula writer (``DerivationResult.to_dict``) and the library
reader (``FormulaEntry.from_dict``) must agree on key names: a formula saved
by ``session_complete(auto_save=True)`` must come back from
``formula_search``/``formula_get`` with its expression and latex intact.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from symkit.domain.formula_library import FormulaEntry, FormulaLibrary
from symkit.infrastructure.derivation_repository import DerivationResult
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def test_derivation_result_to_formula_entry_roundtrip():
    result = DerivationResult(
        id="abc123",
        name="terminal velocity",
        expression="Eq(v_t, sqrt(2)*sqrt(g)*sqrt(m)/(sqrt(A)*sqrt(C_d)*sqrt(rho)))",
        latex="v_{t} = \\sqrt{2}",
    )
    data = result.to_dict()
    entry = FormulaEntry.from_dict(data)
    assert entry.sympy_str == result.expression
    assert entry.latex == result.latex


def test_formula_entry_accepts_legacy_expression_only_yaml():
    # YAML written by 1.1.0: has "expression", no "sympy_str"/"latex" keys.
    data = yaml.safe_load("id: old1\nname: legacy\nexpression: v_t**2 - 1 == 0\n")
    entry = FormulaEntry.from_dict(data)
    assert entry.sympy_str == "v_t**2 - 1 == 0"


def test_derivation_result_from_dict_tolerates_extra_keys():
    data = DerivationResult(id="x1", name="n", expression="x + 1").to_dict()
    data["future_field"] = "ignored"
    restored = DerivationResult.from_dict(data)
    assert restored.expression == "x + 1"


def test_derivation_result_yaml_roundtrip_keeps_expression():
    result = DerivationResult(id="rt1", name="n", expression="a**2 + b**2")
    restored = DerivationResult.from_yaml(yaml.dump(result.to_dict(), allow_unicode=True))
    assert restored.expression == result.expression
    assert restored.id == result.id


def test_session_complete_autosave_is_readable_by_library(fresh_session_manager, tmp_path):
    _ = fresh_session_manager
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    mcp.tools["session_start"]("vt", goal="solve for v_t")
    res = mcp.tools["math"](
        operation="solve",
        expression="1/2*rho*C_d*A*v_t**2 == m*g",
        variable="v_t",
    )
    assert res["success"], res
    done = mcp.tools["session_complete"](auto_save=True)
    assert done["success"], done
    saved = Path(done["saved_to"])
    assert saved.exists()
    lib = FormulaLibrary(library_path=tmp_path / "lib", derived_path=saved.parent.parent)
    entry = lib.get(done["session_id"])
    assert entry is not None
    assert entry.sympy_str  # non-empty!
    assert "v_t" in entry.sympy_str
    assert entry.latex  # non-empty!
