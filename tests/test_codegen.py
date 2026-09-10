"""Tests for codegen tools: generate_derivation_report.

Regression for black-box run-001/run-002 findings:
- ``verification`` counts (int) were rejected by a bool-only schema;
- ``steps[].latex`` was never rendered (empty step sections);
- the Results section rendered raw SymPy source text instead of LaTeX.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Ensure src is on path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit_mcp.tools import codegen  # noqa: E402

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


class TestGenerateDerivationReport:
    def test_renders_step_latex_and_verification_counts(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_derivation_report"]
        result = tool(
            problem="terminal velocity",
            given={"m": "mass (kg)"},
            steps=[{
                "description": "solve the balance equation",
                "latex": "v = \\sqrt{\\frac{2mg}{\\rho C_d A}}",
            }],
            results={"v_t": "sqrt(2*m*g/(rho*C_d*A))"},
            verification={"total": 4, "verified": 4, "failed": 0,
                          "inconclusive": 0, "note": "all steps verified"},
        )
        assert result["success"] is True, result.get("error")
        report = result["report"]
        assert "\\sqrt{\\frac{2mg}" in report          # step latex rendered verbatim
        assert "4/4 steps verified" in report          # counts rendered
        assert "all steps verified" in report
        results_section = report.split("## Results")[1].split("##")[0]
        assert "\\sqrt" in results_section             # real LaTeX, not sympy source
        assert "**" not in results_section             # no raw sympy source text

    def test_legacy_bool_verification_still_renders(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_derivation_report"]
        result = tool(problem="p", given={}, steps=[],
                      results={}, verification={"verified": True})
        assert result["success"] is True
        assert "verified: ✅" in result["report"]


class TestReportVerificationRendering:
    def test_renders_failed_and_inconclusive_counts_even_when_zero(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_derivation_report"]
        result = tool(
            problem="p",
            given={},
            steps=[],
            results={"x": "1"},
            verification={"total": 4, "verified": 4, "failed": 0, "inconclusive": 0},
        )
        assert result["success"]
        assert "- failed: 0" in result["report"]
        assert "- inconclusive: 0" in result["report"]

    def test_given_section_latexifies_symbol_keys(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_derivation_report"]
        result = tool(
            problem="p",
            given={"rho": "1.225 kg/m^3", "C_d": "0.47"},
            steps=[],
            results={},
        )
        assert result["success"]
        assert r"$\rho$" in result["report"]
        assert "$C_{d}$" in result["report"]


class TestGenerateSympyScript:
    """Regression (run-018): the generated script declared only the symbols of
    `expressions`; symbols appearing solely in `operations` (e.g. solve inputs)
    were never declared, so the script died with NameError on first run."""

    def test_declares_symbols_from_operations(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_sympy_script"]
        result = tool(
            expressions=[
                {"name": "omega", "expr": "sqrt(k/m)", "description": "angular frequency"},
                {"name": "T", "expr": "2*pi*sqrt(m/k)", "description": "period"},
            ],
            operations=[{"op": "solve", "input": "m*x**2 - k", "for": "x"}],
        )
        assert result["success"], result
        script = result["script"]
        # x (and m, k) must be declared as sympy symbols.
        assert "x" in _declared_symbols(script), script

    def test_generated_script_runs_without_name_error(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_sympy_script"]
        result = tool(
            expressions=[
                {"name": "omega", "expr": "sqrt(k/m)", "description": "angular frequency"},
            ],
            operations=[{"op": "solve", "input": "m*x**2 - k", "for": "x"}],
        )
        assert result["success"], result
        namespace: dict = {}
        exec(result["script"], namespace)  # must not raise NameError
        assert len(namespace["result_1"]) == 2  # [-sqrt(k/m), sqrt(k/m)]

    def test_solve_operation_without_equals_avoids_eq_warning(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_sympy_script"]
        result = tool(
            expressions=[],
            operations=[{"op": "solve", "input": "m*x**2 - k", "for": "x"}],
        )
        assert result["success"], result
        assert "Eq(" not in result["script"], result["script"]


def _declared_symbols(script: str) -> set[str]:
    """Names on the script's ``symbols('...')`` declaration line."""
    match = re.search(r"=\s*symbols\('([^']+)'\)", script)
    if match is None:
        return set()
    return set(match.group(1).split())
