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


def test_session_complete_autosave_skips_numeric_closing_steps(
    fresh_session_manager, tmp_path
):
    """Regression (run-008/run-009): the saver used session.current_expression,
    which numeric closing steps (evalf / residual substitute) move to a float
    or ``0``; the saved formula then contained a constant instead of the
    derived symbolic formula."""
    _ = fresh_session_manager
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    mcp.tools["session_start"]("vt", goal="solve for v_t")
    solved = mcp.tools["math"](
        operation="solve",
        expression="1/2*rho*C_d*A*v_t**2 == m*g",
        variable="v_t",
    )
    assert solved["success"], solved
    # Numeric closing step drifts the current expression to a plain float.
    numeric = mcp.tools["math"](operation="evalf", expression="pi")
    assert numeric["success"], numeric
    assert "free_symbols" not in numeric or not numeric.get("free_symbols")

    done = mcp.tools["session_complete"](auto_save=True)
    assert done["success"], done
    saved = Path(done["saved_to"])
    lib = FormulaLibrary(library_path=tmp_path / "lib", derived_path=saved.parent.parent)
    entry = lib.get(done["session_id"])
    assert entry is not None
    # The stored formula is the symbolic solution, not the trailing float.
    assert "v_t" in entry.sympy_str
    assert "3.14" not in entry.sympy_str
    assert entry.variables, "variables metadata must be backfilled"


def test_session_complete_autosave_prefers_goal_target_steps(
    fresh_session_manager, tmp_path
):
    """Regression (run-011): after the derivation reached its target, unrelated
    symbolic probes (here ``limit (1+x/n)**n -> exp(x)``) moved the "last
    symbolic output" away from the goal; auto_save stored ``exp(x)`` under the
    derivation's name. The saver must prefer step outputs that involve the
    goal's target variables."""
    _ = fresh_session_manager
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    mcp.tools["session_start"](
        "mb", goal="derive v_rms from Maxwell-Boltzmann", target_variables=["v_rms"]
    )
    solved = mcp.tools["math"](
        operation="solve",
        expression="v_rms**2 == 3*k_B*T/m",
        variable="v_rms",
    )
    assert solved["success"], solved
    probe = mcp.tools["math"](
        operation="limit", expression="(1 + x/n)**n", variable="n", point="oo"
    )
    assert probe["success"], probe

    done = mcp.tools["session_complete"](auto_save=True)
    assert done["success"], done
    saved = Path(done["saved_to"])
    lib = FormulaLibrary(library_path=tmp_path / "lib", derived_path=saved.parent.parent)
    entry = lib.get(done["session_id"])
    assert entry is not None
    assert "v_rms" in entry.sympy_str
    assert "exp(x)" not in entry.sympy_str


def test_session_complete_autosave_matches_function_targets(
    fresh_session_manager, tmp_path
):
    """Regression (run-012): target variable ``V`` is satisfied by a step output
    ``Eq(V(t), ...)`` — the function name counts as involving the target, so a
    later unrelated solve for ``omega`` must not displace the RC discharge law."""
    _ = fresh_session_manager
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    mcp.tools["session_start"](
        "rc",
        goal="derive the RC discharge law",
        target_variables=["V", "omega_0"],
    )
    ode = mcp.tools["math"](
        operation="dsolve",
        expression="diff(V,t) + V/(R*C)",
        variable="V",
        with_respect_to="t",
    )
    assert ode["success"], ode
    res = mcp.tools["math"](
        operation="solve", expression="omega*L - 1/(omega*C)", variable="omega"
    )
    assert res["success"], res

    done = mcp.tools["session_complete"](auto_save=True)
    assert done["success"], done
    saved = Path(done["saved_to"])
    lib = FormulaLibrary(library_path=tmp_path / "lib", derived_path=saved.parent.parent)
    entry = lib.get(done["session_id"])
    assert entry is not None
    assert "V(t)" in entry.sympy_str
    assert "omega" not in entry.sympy_str


def test_session_complete_autosave_skips_tangential_probes(
    fresh_session_manager, tmp_path
):
    """Regression (run-013): when NO step output mentions the target variable
    (the agent derived ``sqrt(3*k_B*T/m)`` without ever binding it to the name
    ``v_rms``), goal-target matching cannot fire.  Tangential probes (series of
    ``exp(-x)``, limit of ``(1+x/n)**n``) introduce symbols unrelated to the
    derivation's lineage and must not displace it in the saved formula."""
    _ = fresh_session_manager
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    mcp.tools["session_start"](
        "mb2", goal="derive v_rms", target_variables=["v_rms"]
    )
    integ = mcp.tools["math"](
        operation="integrate",
        expression="v**2 * 4*pi*(m/(2*pi*k_B*T))**(3/2) * v**2 * exp(-m*v**2/(2*k_B*T))",
        variable="v",
        lower="0",
        upper="oo",
        assumptions=["k_B positive", "T positive", "m positive", "v positive"],
    )
    assert integ["success"], integ
    root = mcp.tools["math"](operation="powsimp", expression="sqrt(3*k_B*T/m)")
    assert root["success"], root
    # Two tangential probes: symbols x and n never join the derivation lineage.
    ser = mcp.tools["math"](
        operation="series", expression="exp(-x)", variable="x", point="0", order=4
    )
    assert ser["success"], ser
    lim = mcp.tools["math"](
        operation="limit", expression="(1 + x/n)**n", variable="n", point="oo"
    )
    assert lim["success"], lim

    done = mcp.tools["session_complete"](auto_save=True)
    assert done["success"], done
    saved = Path(done["saved_to"])
    lib = FormulaLibrary(library_path=tmp_path / "lib", derived_path=saved.parent.parent)
    entry = lib.get(done["session_id"])
    assert entry is not None
    assert "k_B" in entry.sympy_str


def test_session_complete_accepts_scalar_string_for_list_params(
    fresh_session_manager,
):
    """Regression (run-011): ``limitations="a string"`` (not a list) failed
    FastMCP schema validation outright, and inside the function a bare string
    would flow into the stored record. Scalar strings are coerced to
    single-element lists at the tool boundary, so the archive stays list-typed."""
    _ = fresh_session_manager
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    mcp.tools["session_start"]("coerce", goal="solve for x")
    res = mcp.tools["math"](operation="solve", expression="x - 1 == 0", variable="x")
    assert res["success"], res
    done = mcp.tools["session_complete"](
        auto_save=True,
        limitations="single string",
        tags="one-tag",
        assumptions="x real",
    )
    assert done["success"], done
    assert "saved_to" in done, done.get("warnings")
    data = yaml.safe_load(Path(done["saved_to"]).read_text(encoding="utf-8"))
    assert data["limitations"] == ["single string"]
    assert data["tags"] == ["one-tag"]
    assert data["assumptions"] == ["x real"]
