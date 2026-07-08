"""Formula - Standard formula interface

Supports multiple input formats and converts them into a unified internal representation.
Returns detailed error information on failure.

The "Forge" in SymKit means we CREATE new formulas through derivation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import sympy as sp
from sympy.parsing.latex import parse_latex

from symkit.domain.expression_parser import parse_expression_string

# Regex for a bare '=' that is not part of '==', '<=', '>=', or '!='.
_BARE_EQ_PATTERN = re.compile(r"(?<![=<>!])=(?!=)")

# Common LaTeX separators used to join multiple equations in one string
# (e.g. "\omega = ..., \quad \beta^* = 0.09" or aligned environments
# separated by \\ line breaks). Commas and semicolons are intentionally
# excluded here because they also appear inside function calls such as
# ``diff(u, t)``; they are handled by stripping trailing punctuation from
# each part after splitting.
_LATEX_SEPARATORS_RE = re.compile(
    r"(?:\\quad|\\qquad|\\\\)\s*"
)

# Regex to detect whether a preprocessed string has been converted to a
# SymPy-style expression (contains vector-calculus function calls).
_VECTOR_CALCULUS_FUNC_RE = re.compile(
    r"\b(diff|convective|laplacian|grad|div|curl|Del|nabla)\s*\("
)

# Regex to strip common display-math environment wrappers.
_LATEX_ENVIRONMENT_RE = re.compile(
    r"\\begin\{(?:aligned|align|equation|gather|multline|eqnarray)\*?\}"
    r"|\\end\{(?:aligned|align|equation|gather|multline|eqnarray)\*?\}"
)


def _strip_latex_environments(s: str) -> str:
    """Remove common display-math environment delimiters from a LaTeX string."""
    s = _LATEX_ENVIRONMENT_RE.sub("", s)
    # Remove alignment characters used in aligned/align environments.
    s = s.replace("&", "")
    # Also strip surrounding $$ and $ delimiters.
    s = s.strip()
    if s.startswith("$$") and s.endswith("$$"):
        s = s[2:-2].strip()
    elif s.startswith("$") and s.endswith("$"):
        s = s[1:-1].strip()
    return s


def _preprocess_latex_vector_calculus(s: str) -> str:
    r"""Convert common vector-calculus LaTeX notation into SymPy-compatible strings.

    This is a heuristic preprocessor that lets us load PDE-heavy formulas from
    Wikidata (e.g. the Navier-Stokes equations) into a SymKit derivation session
    even though SymPy's ``parse_latex`` does not understand ``\nabla``,
    ``\vec`` or ``\partial`` in vector form.

    Supported conversions:

    - ``\vec{u}`` / ``\vec u`` -> ``u``
    - ``\nabla \cdot \vec{u}`` -> ``div(u)``
    - ``\nabla \times \vec{u}`` -> ``curl(u)``
    - ``\nabla^2 \vec{u}`` -> ``laplacian(u)``
    - ``\nabla h`` -> ``grad(h)``
    - ``\vec{u} \cdot \nabla \vec{u}`` -> ``convective(u, u)``
    - ``\frac{\partial u}{\partial t}`` -> ``diff(u, t)``
    - ``\partial_t u`` -> ``diff(u, t)``
    - ``\frac{D u}{D t}`` -> ``diff(u, t)``
    - ``\frac{D}{Dt} u`` / ``\frac{D}{Dt}(u)`` -> ``diff(u, t)``
    """
    # Helper: match an identifier optionally wrapped in braces.
    ident = r"(?:\{([A-Za-z][A-Za-z0-9]*)\}|([A-Za-z][A-Za-z0-9]*))"

    # 1. Vector arrow: \vec{u} or \vec u -> u (must run before other steps)
    s = re.sub(r"\\vec\s*" + ident, r"\1\2", s)

    # 2. Partial derivative shorthand: \partial_t u -> diff(u, t)
    s = re.sub(r"\\partial_\{?([A-Za-z])\}?\s*" + ident, r"diff(\2\3, \1)", s)

    # 3. Fractional partial derivative: \frac{\partial u}{\partial t} -> diff(u, t)
    s = re.sub(
        r"\\frac\{\\partial\s+" + ident + r"\}\{\\partial\s+([A-Za-z])\}",
        r"diff(\1\2, \3)",
        s,
    )

    # 4. Convective derivative:
    #    Parenthesized form: (u \cdot \nabla) v -> convective(u, v)
    #    Bare form:          u \cdot \nabla v   -> convective(u, v)
    #    Must run before gradient/divergence conversion so \nabla stays intact.
    #    The parenthesized form is matched first so the longer match wins; the
    #    bare form requires an identifier immediately after \nabla, which the
    #    closing paren in "(u \cdot \nabla) v" would otherwise break.
    s = re.sub(
        r"\(\s*" + ident + r"\s*\\cdot\s*\\nabla\s*\)\s*" + ident,
        r"convective(\1\2, \3\4)",
        s,
    )
    s = re.sub(
        ident + r"\s*\\cdot\s*\\nabla\s*" + ident,
        r"convective(\1\2, \3\4)",
        s,
    )

    # 5. Divergence: \nabla \cdot u -> div(u)
    s = re.sub(r"\\nabla\s*\\cdot\s*" + ident, r"div(\1\2)", s)

    # 6. Curl: \nabla \times u -> curl(u)
    s = re.sub(r"\\nabla\s*\\times\s*" + ident, r"curl(\1\2)", s)

    # 7. Laplacian: \nabla^2 u -> laplacian(u)
    s = re.sub(r"\\nabla\^2\s*" + ident, r"laplacian(\1\2)", s)

    # 8. Material derivative: \frac{D u}{D t} -> diff(u, t)
    #    Must run before gradient conversion so \nabla in the same expression stays intact.
    s = re.sub(
        r"\\frac\{D\s+" + ident + r"\}\{D\s+([A-Za-z])\}",
        r"diff(\1\2, \3)",
        s,
    )
    s = re.sub(
        r"\\frac\{D\}\{Dt\}\s*" + ident,
        r"diff(\1\2, t)",
        s,
    )
    s = re.sub(
        r"\\frac\{D\}\{Dt\}\s*\(\s*" + ident + r"\s*\)",
        r"diff(\1\2, t)",
        s,
    )

    # 9. Gradient: \nabla h -> grad(h) (last, so it doesn't catch div/curl/lap)
    s = re.sub(r"\\nabla\s+" + ident, r"grad(\1\2)", s)

    return s

def _preprocess_latex_greek(s: str) -> str:
    """Convert common LaTeX Greek-letter commands to ASCII names.

    Also inserts explicit ``*`` between a converted Greek-letter coefficient and
    a following function call so that ``\nu\nabla^2 u`` becomes ``nu * laplacian(u)``
    rather than the invalid token ``nulaplacian``.
    """
    greek_map = {
        r"\alpha": "alpha",
        r"\beta": "beta",
        r"\gamma": "gamma",
        r"\delta": "delta",
        r"\epsilon": "epsilon",
        r"\zeta": "zeta",
        r"\eta": "eta",
        r"\theta": "theta",
        r"\iota": "iota",
        r"\kappa": "kappa",
        r"\lambda": "lambda_",
        r"\mu": "mu",
        r"\nu": "nu",
        r"\xi": "xi",
        r"\pi": "pi",
        r"\rho": "rho",
        r"\sigma": "sigma",
        r"\tau": "tau",
        r"\upsilon": "upsilon",
        r"\phi": "phi",
        r"\chi": "chi",
        r"\psi": "psi",
        r"\omega": "omega",
        r"\Gamma": "Gamma",
        r"\Delta": "Delta",
        r"\Theta": "Theta",
        r"\Lambda": "Lambda",
        r"\Xi": "Xi",
        r"\Pi": "Pi",
        r"\Sigma": "Sigma",
        r"\Upsilon": "Upsilon",
        r"\Phi": "Phi",
        r"\Psi": "Psi",
        r"\Omega": "Omega",
    }
    for latex_cmd, ascii_name in greek_map.items():
        s = s.replace(latex_cmd, ascii_name)

    # Insert explicit multiplication between a Greek-letter name and a
    # following function call, e.g. ``nu laplacian(u)`` -> ``nu*laplacian(u)``.
    greek_names = set(greek_map.values())
    greek_names_pattern = "|".join(re.escape(name) for name in greek_names)
    s = re.sub(
        rf"(?P<greek>{greek_names_pattern})(?P<func>[A-Za-z_][A-Za-z0-9_]*\()",
        r"\g<greek>*\g<func>",
        s,
    )
    return s


def _preprocess_latex_trig_powers(s: str) -> str:
    r"""Protect trig-function powers from being swallowed by adjacent symbols.

    SymPy's ``parse_latex`` sometimes treats ``\sin^2\theta d\phi^2`` as
    ``sin(dphi**2 * theta)**2``. Rewriting powers to an explicit form
    ``(\sin(\theta))^2`` keeps the function argument separate from other
    factors.
    """
    # Match: \sin^2\theta, \cos^{2}{x}, \tan^2(x), etc.
    pattern = re.compile(
        r"\\(sin|cos|tan|cot|sec|csc)\^(\{[^}]*\}|\d+)\s*"
        r"(\{[^}]*\}|\([^\)]*\)|\\[A-Za-z]+|[A-Za-z])"
    )

    def _repl(m: re.Match[str]) -> str:
        func = m.group(1)
        power = m.group(2)
        arg = m.group(3)
        # Strip surrounding braces from power and argument if present.
        if power.startswith("{") and power.endswith("}"):
            power = power[1:-1]
        if arg.startswith("{") and arg.endswith("}"):
            arg = arg[1:-1]
        return rf"(\{func}({arg}))^{power}"

    return pattern.sub(_repl, s)


def _preprocess_latex_differentials(s: str) -> str:
    r"""Normalize bare differential forms like ``d\theta`` to single symbols.

    ``parse_latex`` already treats ``d\theta`` as a single symbol ``dtheta``,
    but ``d\theta^2`` can be mis-parsed when adjacent to other symbols. We
    rewrite it as ``(dtheta)^2`` so it stays grouped.
    """
    # Pattern: d followed by a Greek command or identifier, optionally raised
    # to a power, and not already part of a fraction like \frac{dX}{dY}.
    greek_or_ident = r"(?:\\[A-Za-z]+|[A-Za-z][A-Za-z0-9]*)"
    pattern = re.compile(
        r"(?<![A-Za-z0-9_\\])d" + greek_or_ident + r"(?:\^(\{[^}]*\}|\d+))?"
    )

    def _repl(m: re.Match[str]) -> str:
        full = m.group(0)
        power = m.group(1)
        if power:
            if power.startswith("{") and power.endswith("}"):
                power = power[1:-1]
            base = full[: full.rfind("^")]
            return rf"({base})^{power}"
        return full

    return pattern.sub(_repl, s)


def _fix_latex_multiindex_symbols(expr: sp.Basic) -> sp.Basic:
    r"""Post-process symbols created by ``parse_latex`` for multi-index subscripts.

    ``parse_latex`` turns ``G_{\mu\nu}`` into ``Symbol('G_{mu*nu}')`` because
    it interprets the subscript as an implicit product. Replace those
    multiplication markers with commas so the symbol represents a single
    tensor component.
    """
    mapping: dict[sp.Basic, sp.Basic] = {}
    for sym in expr.free_symbols:
        if not isinstance(sym, sp.Symbol):
            continue
        name = sym.name
        match = re.match(r"([A-Za-z][A-Za-z0-9_]*)_\{(.+)\}$", name)
        if match and "*" in match.group(2):
            base = match.group(1)
            sub = match.group(2).replace("*", ",")
            mapping[sym] = sp.Symbol(f"{base}_{{{sub}}}")
    if mapping:
        return expr.xreplace(mapping)
    return expr


class FormulaSource(Enum):
    """Formula source tag - key to academic provenance."""

    USER_INPUT = "user_input"  # Direct user input
    TEXTBOOK = "textbook"  # Textbook formula
    LOCAL = "local"  # Local YAML library (editable by user)
    SYMPY_BUILTIN = "sympy_builtin"  # SymPy built-in
    DERIVED = "derived"  # Generated by SymKit derivation
    EXTERNAL_MCP = "external_mcp"  # From another MCP (e.g., sympy-mcp)


class FormulaFormat(Enum):
    """Supported input formats."""

    SYMPY = "sympy"  # SymPy string: "C_0 * exp(-k*t)"
    LATEX = "latex"  # LaTeX: "C_0 e^{-kt}"
    PYTHON = "python"  # Python expression: "C_0 * math.exp(-k*t)"
    NATURAL = "natural"  # Natural language (future support)
    DICT = "dict"  # Dictionary format


@dataclass
class ParseError:
    """Detailed parse error information."""

    error_type: str  # "syntax", "latex", "variable", "dimension"
    message: str
    position: int | None = None
    suggestion: str | None = None
    original_input: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": False,
            "error_type": self.error_type,
            "message": self.message,
            "position": self.position,
            "suggestion": self.suggestion,
            "original_input": self.original_input,
        }


@dataclass
class Variable:
    """Variable in a formula."""

    name: str
    description: str = ""
    unit: str | None = None
    constraints: str | None = None  # "positive", "real", "integer"
    value: Any = None  # Numerical value if known

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "unit": self.unit,
            "constraints": self.constraints,
            "value": self.value,
        }


@dataclass
class Formula:
    """
    Standard formula interface.

    Unified representation for formulas from any format, with complete metadata.
    """

    # Core content
    id: str
    expression: sp.Expr | sp.Equality  # SymPy expression
    variables: dict[str, Variable] = field(default_factory=dict)

    # Source tracking (academic value)
    source: FormulaSource = FormulaSource.USER_INPUT
    source_detail: str = ""  # Detailed source (e.g., "sympy-mcp.arrhenius")
    original_input: str = ""  # Original input string
    input_format: FormulaFormat = FormulaFormat.SYMPY

    # Metadata
    name: str = ""
    description: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)

    # Timestamp
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def sympy_str(self) -> str:
        """SymPy string representation."""
        return str(self.expression)

    @property
    def latex(self) -> str:
        """LaTeX representation."""
        result = sp.latex(self.expression)
        return str(result) if result else ""

    @property
    def symbol_names(self) -> set[str]:
        """All symbol names."""
        return {str(s) for s in self.expression.free_symbols}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "expression": self.sympy_str,
            "latex": self.latex,
            "variables": {k: v.to_dict() for k, v in self.variables.items()},
            "source": self.source.value,
            "source_detail": self.source_detail,
            "original_input": self.original_input,
            "input_format": self.input_format.value,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "references": self.references,
            "parse_warnings": self.parse_warnings,
            "created_at": self.created_at,
        }


def _split_latex_compound_equations(input_str: str) -> list[str]:
    """Split a LaTeX string that may contain multiple equations into parts.

    Handles common separators such as ``\\quad``, ``\\qquad`` and ``\\`` line
    breaks. Trailing commas/semicolons that were used to introduce a separator
    are stripped so that equations like ``A = B, \\quad C = D`` still parse.
    Empty or whitespace-only parts are discarded.
    """
    parts = _LATEX_SEPARATORS_RE.split(input_str)
    cleaned = []
    for part in parts:
        part = part.strip()
        # Strip a single trailing comma/semicolon that was used as punctuation
        # before the next equation separator.
        if part.endswith(",") or part.endswith(";"):
            part = part[:-1].strip()
        if part:
            cleaned.append(part)
    return cleaned


def _replace_latex_max_min(expr: sp.Basic) -> sp.Basic:
    r"""Replace undefined ``Function('max')`` / ``Function('min')`` from LaTeX
    ``\max`` / ``\min`` with SymPy's symbolic ``Max`` / ``Min``.

    SymPy's ``parse_latex`` does not always map ``\max`` to ``Max``, so this helper
    fixes that after parsing.
    """
    mapping = {
        "max": sp.Max,
        "min": sp.Min,
    }

    def _match(e: sp.Basic) -> bool:
        return (
            isinstance(e, sp.Function)
            and str(e.func) in mapping
        )

    def _replacement(e: sp.Function) -> sp.Basic:
        cls = mapping[str(e.func)]
        return cls(*e.args)

    return expr.replace(_match, _replacement)


def _rename_star_symbols(expr: sp.Basic) -> sp.Basic:
    r"""Rename LaTeX ``^*`` symbols from ``X_{star}`` to ``X_star``.

    We first map ``\beta^*`` -> ``\beta_{\star}`` so that SymPy's LaTeX parser
    treats it as a single-character subscript keeping it as a single symbol,
    then this helper renames ``X_{star}`` to ``X_star``.
    """

    def _match(e: sp.Basic) -> bool:
        return isinstance(e, sp.Indexed) or (
            isinstance(e, sp.Symbol)
            and str(e).endswith("_star")
        )

    def _replacement(e: sp.Basic) -> sp.Basic:
        if isinstance(e, sp.Symbol):
            return sp.Symbol(str(e))
        return e

    return expr.replace(_match, _replacement)


class FormulaParser:
    """
    Formula parser.

    Supports multiple input formats and converts them into Formula objects.
    Returns detailed ParseError on failure.
    """

    # Common replacements
    SYMBOL_REPLACEMENTS = {
        "θ": "theta",
        "Θ": "Theta",
        "α": "alpha",
        "β": "beta",
        "γ": "gamma",
        "δ": "delta",
        "Δ": "Delta",
        "ε": "epsilon",
        "λ": "lambda_",
        "μ": "mu",
        "π": "pi",
        "σ": "sigma",
        "τ": "tau",
        "ω": "omega",
        "Ω": "Omega",
        "∞": "oo",
        "√": "sqrt",
        "²": "**2",
        "³": "**3",
        "₀": "_0",
        "₁": "_1",
        "₂": "_2",
        "₃": "_3",
        "ₐ": "_a",
        "ₑ": "_e",
        "ᵣ": "_r",
    }

    @classmethod
    def parse(
        cls,
        input_data: str | dict[str, Any],
        formula_id: str,
        source: FormulaSource = FormulaSource.USER_INPUT,
        source_detail: str = "",
        **metadata: Any,
    ) -> Formula | ParseError:
        """
        Parse formula input.

        Args:
            input_data: Formula input (string or dictionary)
            formula_id: Formula ID
            source: Source tag
            source_detail: Detailed source information
            **metadata: Extra metadata (name, description, category, tags)

        Returns:
            Formula or ParseError
        """
        # Determine input format
        if isinstance(input_data, dict):
            return cls._parse_dict(input_data, formula_id, source, source_detail, **metadata)

        # String input - auto-detect format
        input_str = str(input_data).strip()

        # Detect whether it is LaTeX
        if cls._is_latex(input_str):
            return cls._parse_latex(input_str, formula_id, source, source_detail, **metadata)

        # Default to SymPy format
        return cls._parse_sympy(input_str, formula_id, source, source_detail, **metadata)

    @classmethod
    def _is_latex(cls, s: str) -> bool:
        """Detect whether a string looks like LaTeX."""
        latex_indicators = [
            "\\frac",
            "\\cdot",
            "\\times",
            "\\sqrt",
            "^{",
            "_{",
            "\\exp",
            "\\ln",
            "\\log",
            # Common PDE/RANS commands that are not in the list above
            "\\partial",
            "\\bar",
            "\\overline",
            "\\underline",
            "\\left",
            "\\right",
            "\\sum",
            "\\int",
            "\\prod",
            "\\alpha",
            "\\beta",
            "\\gamma",
            "\\delta",
            "\\epsilon",
            "\\omega",
            "\\sigma",
            "\\nu",
            "\\rho",
            "\\mu",
            "\\tau",
            "\\theta",
            "\\infty",
            "\\pm",
            "\\mp",
            "\\leq",
            "\\geq",
            "\\neq",
        ]
        if any(ind in s for ind in latex_indicators):
            return True
        # Any backslash followed by a letter is a strong LaTeX signal.
        return bool(re.search(r"\\[A-Za-z]+", s))

    @classmethod
    def _parse_sympy(
        cls,
        input_str: str,
        formula_id: str,
        source: FormulaSource,
        source_detail: str,
        **metadata: Any,
    ) -> Formula | ParseError:
        """Parse SymPy format."""
        original = input_str

        # Apply symbol replacements (keep FormulaParser's special mappings, e.g., λ → lambda_)
        for old, new in cls.SYMBOL_REPLACEMENTS.items():
            input_str = input_str.replace(old, new)

        # Use the unified shared parser to auto-convert equations, protect reserved names,
        # handle Leibniz derivative notation, and pre-process Unicode/Greek characters,
        # avoiding mis-parsing of multi-letter reserved names such as beta/S/N.
        expr, error = parse_expression_string(
            input_str,
            convert_equation=True,
        )

        if error is not None:
            suggestion = "Verify expression syntax. Example: 'C_0 * exp(-k*t)'"
            if "Lambda" in original or "Gamma" in original or "Beta" in original:
                suggestion += "; capital Greek letters used as symbols must be bare identifiers, e.g. 'Lambda * x'"
            if any(sub in original for sub in ("_{", "^}")):
                suggestion += "; for LaTeX input use the latex argument or wrap the expression in $...$"
            return ParseError(
                error_type="parse",
                message=f"Parse error: {error}",
                suggestion=suggestion,
                original_input=original,
            )

        # Extract variables
        variables = cls._extract_variables(expr)

        return Formula(
            id=formula_id,
            expression=expr,
            variables=variables,
            source=source,
            source_detail=source_detail,
            original_input=original,
            input_format=FormulaFormat.SYMPY,
            **metadata,
        )

    @classmethod
    def _parse_latex(
        cls,
        input_str: str,
        formula_id: str,
        source: FormulaSource,
        source_detail: str,
        **metadata: Any,
    ) -> Formula | ParseError:
        """Parse LaTeX format."""
        original = input_str

        # Strip display-math environment wrappers (aligned, align, equation, etc.)
        # so that multiple equations separated by \ can be handled consistently.
        input_str = _strip_latex_environments(input_str)

        # Convert common vector-calculus LaTeX notation to SymPy function calls
        # (e.g. \nabla \cdot \vec u -> div(u), \nabla h -> grad(h)).
        input_str = _preprocess_latex_vector_calculus(input_str)

        # Split compound/aligned equations and take the first one as the primary
        # expression. Additional equations are recorded as parse warnings.
        parts = _split_latex_compound_equations(input_str)
        parse_warnings: list[str] = []
        if not parts:
            return ParseError(
                error_type="latex",
                message="Empty equation after LaTeX preprocessing",
                suggestion="Check that the formula contains at least one equation",
                original_input=original,
            )

        first = parts[0]
        if len(parts) > 1:
            skipped = parts[1:]
            parse_warnings.append(
                f"Only the first equation was recorded; "
                f"{len(skipped)} additional equation(s) skipped: "
                f"{'; '.join(skipped)}. Record them separately."
            )

        # If the vector-calculus preprocessor produced SymPy-style function calls
        # (diff, grad, div, curl, ...), convert any remaining Greek-letter
        # commands to ASCII and route through the SymPy parser so those operators
        # are protected as user-defined symbolic functions.
        if _VECTOR_CALCULUS_FUNC_RE.search(first):
            sympy_str = _preprocess_latex_greek(first)
            result = cls._parse_sympy(sympy_str, formula_id, source, source_detail, **metadata)
            if isinstance(result, Formula):
                result.parse_warnings.extend(parse_warnings)
            return result

        # Otherwise fall back to the native LaTeX parser. Preprocess the
        # expression in an order that preserves LaTeX commands until the last
        # moment:
        # 1. Convert "^*" superscripts (\beta^*) to \star subscripts.
        # 2. Protect trig-function powers from being swallowed by adjacent
        #    factors (\sin^2\theta -> (\sin(\theta))^2).
        # 3. Keep differential forms grouped (d\theta^2 -> (dtheta)^2).
        # After parsing, multi-index subscripts like G_{\mu\nu} are repaired
        # because SymPy's parse_latex treats them as implicit products.
        input_str = first

        # Convert common "^*" superscript symbols in physics/turbulence to single _star symbols.
        # First use the \star command as a placeholder; parse_latex will treat it as a single-character
        # subscript keeping it as a single symbol, then _rename_star_symbols renames X_{star} to X_star.
        def _repl_star(m: re.Match[str]) -> str:
            return "\\" + m.group(1) + r"_{\star}"

        input_str = re.sub(r"\\([A-Za-z]+)\^(\*|\{\*\})", _repl_star, input_str)

        input_str = _preprocess_latex_trig_powers(input_str)
        input_str = _preprocess_latex_differentials(input_str)

        # Check brace balance
        if input_str.count("{") != input_str.count("}"):
            return ParseError(
                error_type="latex",
                message="Unmatched braces in LaTeX",
                suggestion="Check if all { have matching }",
                original_input=original,
            )

        # Handle a single equation
        bare_equals = list(_BARE_EQ_PATTERN.finditer(input_str))
        is_equation = len(bare_equals) == 1

        try:
            if is_equation:
                pos = bare_equals[0].start()
                lhs = input_str[:pos].strip()
                rhs = input_str[pos + 1 :].strip()
                lhs_expr = parse_latex(lhs)
                rhs_expr = parse_latex(rhs)
                expr = sp.Eq(lhs_expr, rhs_expr)
            else:
                expr = parse_latex(input_str)

            # Map LaTeX \max / \min to SymPy Max / Min
            expr = _replace_latex_max_min(expr)

            # Rename ^* placeholder to X_star
            expr = _rename_star_symbols(expr)

            # Repair multi-index subscripts turned into products by parse_latex
            expr = _fix_latex_multiindex_symbols(expr)

            # Extract variables
            variables = cls._extract_variables(expr)

            return Formula(
                id=formula_id,
                expression=expr,
                variables=variables,
                source=source,
                source_detail=source_detail,
                original_input=original,
                input_format=FormulaFormat.LATEX,
                parse_warnings=parse_warnings,
                **metadata,
            )

        except Exception as e:
            return ParseError(
                error_type="latex",
                message=f"LaTeX parse error: {e}",
                suggestion=r"Check LaTeX syntax. Use \frac{a}{b}, e^{x}, etc.",
                original_input=original,
            )

    @classmethod
    def _parse_dict(
        cls,
        data: dict[str, Any],
        formula_id: str,
        source: FormulaSource,
        source_detail: str,
        **metadata: Any,
    ) -> Formula | ParseError:
        """Parse dictionary format."""
        # Must contain expression
        if "expression" not in data and "latex" not in data and "sympy" not in data:
            return ParseError(
                error_type="format",
                message="Missing expression in dict",
                suggestion="Provide 'expression', 'latex', or 'sympy' key",
                original_input=str(data),
            )

        # Get expression string
        expr_str = data.get("expression") or data.get("sympy") or data.get("latex")

        # Ensure expr_str is a str
        if not isinstance(expr_str, str):
            return ParseError(
                error_type="syntax",
                message="Expression must be a string",
                suggestion="Dict format requires 'expression', 'sympy', or 'latex' key with string value",
                original_input=str(data),
            )

        # Parse expression
        if data.get("latex") or cls._is_latex(expr_str):
            result = cls._parse_latex(expr_str, formula_id, source, source_detail)
        else:
            result = cls._parse_sympy(expr_str, formula_id, source, source_detail)

        if isinstance(result, ParseError):
            return result

        # Supplement metadata from dict
        if "name" in data:
            result.name = data["name"]
        if "description" in data:
            result.description = data["description"]
        if "category" in data:
            result.category = data["category"]
        if "tags" in data:
            result.tags = data["tags"]
        if "references" in data:
            result.references = data["references"]

        # Supplement variable information
        if "variables" in data:
            for var_name, var_info in data["variables"].items():
                if var_name in result.variables and isinstance(var_info, dict):
                    result.variables[var_name].description = var_info.get("description", "")
                    result.variables[var_name].unit = var_info.get("unit")
                    result.variables[var_name].constraints = var_info.get("constraints")

        # Apply extra metadata
        for key, value in metadata.items():
            if hasattr(result, key):
                setattr(result, key, value)

        return result

    @classmethod
    def _extract_variables(cls, expr: sp.Expr | sp.Equality) -> dict[str, Variable]:
        """Extract variables from the expression."""
        symbols = expr.free_symbols
        variables = {}

        for sym in symbols:
            name = str(sym)
            variables[name] = Variable(
                name=name,
                description="",  # To be filled by user
                unit=None,
                constraints=cls._infer_constraints(name),
            )

        return variables

    @classmethod
    def _infer_constraints(cls, name: str) -> str | None:
        """Infer mathematical constraints based on naming conventions (general mathematics oriented)."""
        # Time, temperature, mass, etc. are usually positive
        positive_single = {"t", "T", "m", "M", "V", "k", "K", "R", "g"}
        if name in positive_single:
            return "positive"

        # Multi-character naming patterns
        positive_prefixes = ["rho_", "mu_", "nu_", "epsilon_", "lambda_", "sigma_", "omega_"]
        if any(name.startswith(p) for p in positive_prefixes):
            return "positive"

        # Angles
        angle_names = {"theta", "phi", "psi", "alpha", "beta", "gamma",
                       "delta", "epsilon", "zeta", "eta"}
        if name in angle_names:
            return "real"

        # Natural numbers (indices)
        integer_names = {"i", "j", "n", "m", "k", "l"}
        if name in integer_names:
            return "integer"

        return "real"
