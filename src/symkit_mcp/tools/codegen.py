"""
Code Generation Tools

Tools for generating executable Python code from derivation steps.

═══════════════════════════════════════════════════════════════════════════════
⚠️ CRITICAL WORKFLOW - READ BEFORE USING THESE TOOLS!
═══════════════════════════════════════════════════════════════════════════════

CORRECT order:
1. Use SymPy-MCP for symbolic calculations (solve, simplify, diff, etc.)
2. Use print_latex_expression() to show formulas to user
3. User confirms the results
4. THEN use these tools to generate code/reports

❌ NEVER use these tools to generate code for UNVERIFIED calculations!
❌ NEVER skip the SymPy-MCP verification step!

The generated code assembles VERIFIED expressions into executable form.
It does NOT perform new calculations.
═══════════════════════════════════════════════════════════════════════════════
"""

import re
from typing import Any


def _to_latex(expr_str: str) -> str:
    """Render a result expression as LaTeX, falling back to the raw string.

    Result values arrive as SymPy source text (``sqrt(2)*...``); rendering
    them verbatim inside ``$...$`` is not valid LaTeX (black-box finding).
    """
    try:
        import sympy as sp

        return str(sp.latex(sp.sympify(expr_str)))
    except Exception:
        return expr_str.replace("**", "^")


def _symbol_to_latex(sym: str) -> str:
    """Render a bare symbol key (Given/Results sections) as LaTeX.

    ``rho`` must become ``$\\rho$`` and ``C_d`` ``$C_{d}$``; keys that are
    not plain identifiers (units, prose) pass through unchanged.
    """
    import re as _re

    if not _re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", sym):
        return sym
    try:
        import sympy as sp

        return str(sp.latex(sp.Symbol(sym)))
    except Exception:
        return sym


def register_codegen_tools(mcp: Any) -> None:
    """Register code generation tools with MCP server.

    ⚠️ These tools generate code from VERIFIED derivation steps.
    Always use SymPy-MCP first to verify calculations!
    """

    @mcp.tool()
    def generate_python_function(
        name: str,
        description: str,
        parameters: list[dict[str, str]],
        steps: list[dict[str, str]],
        return_vars: list[str],
    ) -> dict[str, Any]:
        """
        Generate a Python function from VERIFIED derivation steps.

        ═══════════════════════════════════════════════════════════════════════
        ⚠️ PREREQUISITE: All expressions must be verified with SymPy-MCP first!
        ═══════════════════════════════════════════════════════════════════════

        Correct workflow:
        1. Use SymPy-MCP to derive and verify each expression
        2. Use print_latex_expression() to show results to user
        3. User confirms the derivation is correct
        4. Call this tool with the verified expressions

        The generated code assembles the provided expressions into a Python
        function; it does not perform new symbolic calculations. The expressions
        must already be verified before calling this tool.

        Args:
            name: Function name (e.g., "calculate_seatbelt_tension")
            description: Function docstring description
            parameters: List of {"name": str, "type": str, "description": str}
            steps: List of {"description": str, "expression": str, "result_var": str}
            return_vars: Variables to return

        Returns:
            dict with keys ``success``, ``code`` (the generated Python function),
            ``function_name``, ``parameters``, and ``returns``.

        Example:
            generate_python_function(
                name="calculate_tension",
                description="Calculate seatbelt tension from collision",
                parameters=[
                    {"name": "M1", "type": "float", "description": "Vehicle 1 mass (kg)"},
                    {"name": "M2", "type": "float", "description": "Vehicle 2 mass (kg)"},
                    {"name": "v", "type": "float", "description": "Initial velocity (m/s)"},
                    {"name": "m", "type": "float", "description": "Person mass (kg)"},
                    {"name": "k", "type": "float", "description": "Seatbelt constant (N/m)"},
                ],
                steps=[
                    {"description": "Final velocity after collision",
                     "expression": "M1 * v / (M1 + M2)",
                     "result_var": "v_f"},
                    {"description": "Velocity change",
                     "expression": "v - v_f",
                     "result_var": "delta_v"},
                    {"description": "Maximum tension",
                     "expression": "delta_v * sqrt(m * k)",
                     "result_var": "T_max"},
                ],
                return_vars=["v_f", "delta_v", "T_max"]
            )
        """
        # Build function signature
        param_str = ", ".join(f"{p['name']}: {p.get('type', 'float')}" for p in parameters)

        # Build docstring
        doc_lines = [f'    """{description}', "", "    Args:"]
        for p in parameters:
            doc_lines.append(f"        {p['name']}: {p.get('description', '')}")
        doc_lines.append("")
        doc_lines.append("    Returns:")
        doc_lines.append(f"        dict with keys: {return_vars}")
        doc_lines.append("")
        doc_lines.append("    Note:")
        doc_lines.append("        Generated by SymKit - computations use SymPy for correctness.")
        doc_lines.append('    """')
        docstring = "\n".join(doc_lines)

        # Build computation steps
        step_lines = [
            "    import sympy as sp",
            "    from sympy import sqrt, sin, cos, tan, pi, exp, log",
            "",
        ]
        for i, step in enumerate(steps, 1):
            step_lines.append(f"    # Step {i}: {step['description']}")
            step_lines.append(f"    {step['result_var']} = {step['expression']}")
            step_lines.append("")

        # Build return statement
        return_dict = ", ".join(f'"{v}": {v}' for v in return_vars)
        step_lines.append(f"    return {{{return_dict}}}")

        # Combine all
        code = f"""def {name}({param_str}):
{docstring}
{chr(10).join(step_lines)}
"""

        return {
            "success": True,
            "code": code,
            "function_name": name,
            "parameters": [p["name"] for p in parameters],
            "returns": return_vars,
        }

    @mcp.tool()
    def generate_latex_derivation(
        title: str,
        steps: list[dict[str, str]],
        final_result: str,
    ) -> dict[str, Any]:
        """
        Generate LaTeX documentation for a derivation.

        Args:
            title: Derivation title
            steps: List of {"description": str, "latex": str}
            final_result: Final result in LaTeX

        Returns:
            LaTeX document string
        """
        lines = [
            f"\\section{{{title}}}",
            "",
            "\\begin{align}",
        ]

        for i, step in enumerate(steps, 1):
            desc = step.get("description", f"Step {i}")
            latex = step.get("latex", step.get("expression", ""))
            lines.append(f"    &\\text{{{desc}}} \\nonumber \\\\")
            lines.append(f"    &{latex} \\\\")

        lines.append("\\end{align}")
        lines.append("")
        lines.append(f"\\textbf{{Final Result:}} ${final_result}$")

        latex_doc = "\n".join(lines)

        return {
            "success": True,
            "latex": latex_doc,
            "title": title,
            "steps_count": len(steps),
        }

    @mcp.tool()
    def generate_derivation_report(
        problem: str,
        given: dict[str, str],
        steps: list[dict[str, str]],
        results: dict[str, str],
        verification: dict[str, int | str | bool] | None = None,
    ) -> dict[str, Any]:
        """
        Generate a complete derivation report in Markdown.

        Args:
            problem: Problem description
            given: Given parameters {"symbol": "value with unit"}
            steps: Derivation steps [{"description": str, "latex": str}];
                a legacy "expression" key is rendered when "latex" is absent
            results: Final results {"symbol": "expression"}
            verification: Optional verification summary — counts as ints
                (total/verified/failed/inconclusive), an optional "note" str,
                and legacy bool fields rendered as ✅/❌

        Returns:
            Markdown report
        """
        lines = [
            "# Derivation Report",
            "",
            "## Problem",
            problem,
            "",
            "## Given",
            "",
        ]

        for sym, val in given.items():
            lines.append(f"- ${_symbol_to_latex(sym)}$ = {val}")

        lines.extend(
            [
                "",
                "## Derivation Steps",
                "",
            ]
        )

        for i, step in enumerate(steps, 1):
            lines.append(f"### Step {i}: {step.get('description', '')}")
            if "latex" in step:
                lines.append(f"$${step['latex']}$$")
            elif "expression" in step:
                lines.append(f"$${step['expression']}$$")
            if "result" in step:
                lines.append(f"**Result:** ${step.get('result_var', '')} = {step['result']}$")
            lines.append("")

        lines.extend(
            [
                "## Results",
                "",
            ]
        )

        for sym, expr in results.items():
            lines.append(f"- ${sym} = {_to_latex(expr)}$")

        if verification:
            lines.extend(
                [
                    "",
                    "## Verification",
                    "",
                ]
            )
            total = verification.get("total")
            verified = verification.get("verified")
            if (isinstance(total, int) and not isinstance(total, bool)
                    and isinstance(verified, int) and not isinstance(verified, bool)):
                lines.append(f"- {verified}/{total} steps verified")
                # Render the full count triple (including zeros) so readers
                # never have to infer a missing count as "zero".
                for key in ("failed", "inconclusive"):
                    count_val = verification.get(key)
                    if isinstance(count_val, int) and not isinstance(count_val, bool):
                        lines.append(f"- {key}: {count_val}")
            else:
                for key in ("failed", "inconclusive"):
                    count_val = verification.get(key)
                    if (isinstance(count_val, int)
                            and not isinstance(count_val, bool) and count_val):
                        lines.append(f"- {key}: {count_val}")
            for key, flag_val in verification.items():
                if isinstance(flag_val, bool):
                    lines.append(f"- {key}: {'✅' if flag_val else '❌'}")
            note_val = verification.get("note")
            if isinstance(note_val, str) and note_val:
                lines.append(f"- {note_val}")

        lines.extend(
            [
                "",
                "---",
                "*Generated by SymKit - Where Neural Meets Symbolic*",
            ]
        )

        report = "\n".join(lines)

        return {
            "success": True,
            "report": report,
            "format": "markdown",
        }

    @mcp.tool()
    def generate_sympy_script(
        expressions: list[dict[str, str]],
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Generate a standalone SymPy script for a computation.

        This generates a complete, runnable Python script that can be
        executed independently to reproduce the derivation.

        Args:
            expressions: List of {"name": str, "expr": str, "description": str}
            operations: List of operations to perform
                {"op": "simplify|solve|diff|integrate", "input": str, ...}

        Returns:
            Complete Python script

        Example:
            generate_sympy_script(
                expressions=[
                    {"name": "momentum", "expr": "m1*v1 + m2*v2", "description": "Total momentum"},
                ],
                operations=[
                    {"op": "solve", "input": "momentum = (m1+m2)*v_f", "for": "v_f"},
                ]
            )
        """
        lines = [
            '"""',
            "Auto-generated SymPy script by SymKit",
            "Run with: python script.py",
            '"""',
            "",
            "import sympy as sp",
            "from sympy import symbols, sqrt, sin, cos, tan, pi, exp, log, Eq, solve, diff, integrate, simplify",
            "",
            "# Define symbols",
        ]

        # Collect all symbols — from expressions AND operations. Operations
        # routinely introduce symbols absent from the expressions (e.g. a
        # solve input); declaring only the expression symbols made the
        # generated script die with NameError on its first run (run-018).
        _reserved = (
            "sin", "cos", "tan", "sqrt", "exp", "log", "pi",
            "Derivative", "Integral", "oo", "E", "I",
        )
        all_symbols: set[str] = set()
        for expr in expressions:
            syms = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", str(expr.get("expr", "")))
            all_symbols.update(s for s in syms if s not in _reserved)
        for op in operations:
            for field in ("input", "for", "var"):
                value = op.get(field)
                if isinstance(value, str):
                    syms = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", value)
                    all_symbols.update(s for s in syms if s not in _reserved)

        if all_symbols:
            lines.append(
                f"{', '.join(sorted(all_symbols))} = symbols('{' '.join(sorted(all_symbols))}')"
            )

        lines.append("")
        lines.append("# Define expressions")

        for expr in expressions:
            lines.append(f"# {expr.get('description', '')}")
            lines.append(f"{expr['name']} = {expr['expr']}")
            lines.append("")

        lines.append("# Operations")
        for i, op in enumerate(operations, 1):
            lines.append(f"# Operation {i}: {op['op']}")
            if op["op"] == "solve":
                # Wrap in Eq only when the input actually contains '='; a
                # single-argument Eq() is deprecated (run-018).
                if "=" in str(op["input"]):
                    lhs, _, rhs = str(op["input"]).partition("=")
                    lines.append(f"result_{i} = solve(Eq({lhs.strip()}, {rhs.strip()}), {op['for']})")
                else:
                    lines.append(f"result_{i} = solve({op['input']}, {op['for']})")
            elif op["op"] == "simplify":
                lines.append(f"result_{i} = simplify({op['input']})")
            elif op["op"] == "diff":
                lines.append(f"result_{i} = diff({op['input']}, {op.get('var', 'x')})")
            elif op["op"] == "integrate":
                lines.append(f"result_{i} = integrate({op['input']}, {op.get('var', 'x')})")
            lines.append(f"print(f'Result {i}: {{result_{i}}}')")
            lines.append("")

        script = "\n".join(lines)

        return {
            "success": True,
            "script": script,
            "language": "python",
            "requires": ["sympy"],
        }
