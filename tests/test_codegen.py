"""Tests for codegen tools: generate_derivation_report.

Regression for black-box run-001/run-002 findings:
- ``verification`` counts (int) were rejected by a bool-only schema;
- ``steps[].latex`` was never rendered (empty step sections);
- the Results section rendered raw SymPy source text instead of LaTeX.
"""

from __future__ import annotations

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
