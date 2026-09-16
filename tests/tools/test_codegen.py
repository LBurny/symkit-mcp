"""Tests for the merged ``generate_output`` codegen tool.

Regression for black-box run-001/run-002 findings:
- ``verification`` counts (int) were rejected by a bool-only schema;
- ``steps[].latex`` was never rendered (empty step sections);
- the Results section rendered raw SymPy source text instead of LaTeX.
"""

from __future__ import annotations

import re

from symkit_mcp.tools import codegen

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py

class TestGenerateDerivationReport:
    def test_renders_step_latex_and_verification_counts(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_output"]
        result = tool(
            format="markdown_report",
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
        tool = mcp.tools["generate_output"]
        result = tool(format="markdown_report", problem="p", given={}, steps=[],
                      results={}, verification={"verified": True})
        assert result["success"] is True
        assert "verified: ✅" in result["report"]

class TestReportVerificationRendering:
    def test_renders_failed_and_inconclusive_counts_even_when_zero(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_output"]
        result = tool(
            format="markdown_report",
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
        tool = mcp.tools["generate_output"]
        result = tool(
            format="markdown_report",
            problem="p",
            given={"rho": "1.225 kg/m^3", "C_d": "0.47"},
            steps=[],
            results={},
        )
        assert result["success"]
        assert r"$\rho$" in result["report"]
        assert "$C_{d}$" in result["report"]

    def test_verified_count_renders_without_total(self, fresh_manager):
        # Field 26e9028b: a verification dict without ``total`` fell into the
        # legacy fallback, which iterated only failed/inconclusive and filtered
        # zero counts — verified: 7 and failed: 0 silently vanished while
        # inconclusive: 7 rendered, understating the verification in the report.
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_output"]
        result = tool(
            format="markdown_report",
            problem="p",
            given={},
            steps=[],
            results={},
            verification={"verified": 7, "failed": 0, "inconclusive": 7,
                          "note": "inconclusive steps are manual averages"},
        )
        assert result["success"]
        report = result["report"]
        assert "- verified: 7" in report
        assert "- failed: 0" in report
        assert "- inconclusive: 7" in report
        assert "inconclusive steps are manual averages" in report

    def test_non_ascii_keys_are_not_wrapped_in_math_mode(self, fresh_manager):
        # Field 26e9028b: Chinese keys became pseudo-LaTeX ($连续方程$).
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_output"]
        result = tool(
            format="markdown_report",
            problem="p",
            given={"连续方程": "rho_b 守恒"},
            steps=[],
            results={"动量方程": "-p_b*u_t_i"},
        )
        assert result["success"]
        report = result["report"]
        assert "$连续方程$" not in report
        assert "$动量方程$" not in report
        assert "连续方程 = rho_b 守恒" in report

    def test_step_block_honors_provided_step_numbers(self, fresh_manager):
        # Field 26e9028b: report steps renumbered 1..n while the session's real
        # numbers were 4..18; an explicit per-step number must be honored.
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_output"]
        result = tool(
            format="markdown_report",
            problem="p",
            given={},
            steps=[
                {"description": "continuity", "expression": "x", "number": 4},
                {"description": "momentum", "expression": "y"},
            ],
            results={},
        )
        assert result["success"]
        assert "### Step 4: continuity" in result["report"]
        assert "### Step 2: momentum" in result["report"]

class TestGenerateSympyScript:
    """Regression (run-018): the generated script declared only the symbols of
    `expressions`; symbols appearing solely in `operations` (e.g. solve inputs)
    were never declared, so the script died with NameError on first run."""

    def test_declares_symbols_from_operations(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        tool = mcp.tools["generate_output"]
        result = tool(
            format="sympy_script",
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
        tool = mcp.tools["generate_output"]
        result = tool(
            format="sympy_script",
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
        tool = mcp.tools["generate_output"]
        result = tool(
            format="sympy_script",
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


class TestGenerateOutputValidation:
    """The merged tool reports contract errors instead of raising."""

    def _tool(self):
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        return mcp.tools["generate_output"]

    def test_unknown_format_lists_valid_formats(self, fresh_manager):
        _ = fresh_manager
        result = self._tool()(format="pdf")
        assert result["success"] is False
        assert "pdf" in result["error"]
        for name in ("markdown_report", "latex", "python", "sympy_script"):
            assert name in result["error"]

    def test_missing_required_parameter_names_it(self, fresh_manager):
        _ = fresh_manager
        result = self._tool()(format="latex", title="T")
        assert result["success"] is False
        assert "steps" in result["error"]
        assert "final_result" in result["error"]

    def test_optional_parameter_accepted_for_other_format(self, fresh_manager):
        _ = fresh_manager
        result = self._tool()(format="latex", title="T", steps=[], final_result="x",
                              problem="ignored")
        assert result["success"] is True
        assert "\\section{T}" in result["latex"]


class TestNestedItemValidation:
    """A missing key inside a step/item must be a structured error, not a KeyError.

    Sandbox round 13: ``generate_output(format="python")`` with steps lacking
    ``result_var`` returned the raw exception text
    ``Error executing tool generate_output: 'result_var'`` — and the "requires:"
    error implied the documented parameters were sufficient.
    """

    def _tool(self):
        mcp = MockMCP()
        codegen.register_codegen_tools(mcp)
        return mcp.tools["generate_output"]

    def test_python_step_missing_result_var_is_structured(self):
        result = self._tool()(
            format="python", name="f", description="d",
            parameters=[{"name": "x", "type": "float", "description": "in"}],
            steps=[{"description": "d", "expression": "2*x"}],
            return_vars=["y"],
        )
        assert result["success"] is False
        assert "result_var" in result["error"]
        assert "steps item 1" in result["error"]

    def test_python_parameter_missing_name_is_structured(self):
        result = self._tool()(
            format="python", name="f", description="d",
            parameters=[{"type": "float"}],
            steps=[{"description": "d", "expression": "2*x", "result_var": "y"}],
            return_vars=["y"],
        )
        assert result["success"] is False
        assert "parameters item 1" in result["error"]

    def test_sympy_script_expression_missing_keys_is_structured(self):
        result = self._tool()(format="sympy_script", expressions=[{"name": "a"}], operations=[])
        assert result["success"] is False
        assert "expr" in result["error"]

    def test_well_formed_python_still_succeeds(self):
        result = self._tool()(
            format="python", name="f", description="d",
            parameters=[{"name": "x", "type": "float", "description": "in"}],
            steps=[{"description": "d", "expression": "2*x", "result_var": "y"}],
            return_vars=["y"],
        )
        assert result["success"] is True, result.get("error")
