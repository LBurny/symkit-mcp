"""Shared expression parsing utilities for SymKit MCP tools.

This module provides a single, robust entry point for turning user-facing
mathematical strings into SymPy expressions. It centralizes several concerns
that were previously duplicated across ``math.py``, ``derivation.py``,
``expression.py`` and ``simplify.py``:

1. Unicode/Greek/ASCII math preprocessing (e.g. ``β → beta``).
2. Converting a single ``=`` into ``Eq(...)`` so users can write equations
   naturally.
3. Protecting SymPy reserved names when they are used as *variables* (e.g.
   ``beta * x``) while still allowing their native function semantics when
   called as functions (e.g. ``beta(x, y)``).
4. Converting Leibniz derivative notation (e.g. ``dX/dY``) into ``Derivative(...)``.
5. Protecting vector-calculus notation (``div``, ``grad``, ``curl``, ``Del``,
   ``laplacian``) as user-defined symbolic functions so they parse correctly
   inside equations.
6. Auto-detecting LaTeX input and routing it through ``FormulaParser``.

"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_application,
    implicit_multiplication,
    parse_expr,
    standard_transformations,
)

TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication,
    implicit_application,
    convert_xor,
)

# Unicode → ASCII replacements for Greek letters and common math symbols.
# These were previously duplicated in math.py, derivation.py and expression.py.
_UNICODE_REPLACEMENTS: dict[str, str] = {
    # Greek lowercase
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "epsilon",
    "ζ": "zeta",
    "η": "eta",
    "θ": "theta",
    "ι": "iota",
    "κ": "kappa",
    "λ": "lambda",
    "μ": "mu",
    "ν": "nu",
    "ξ": "xi",
    "ο": "omicron",
    "π": "pi",
    "ρ": "rho",
    "σ": "sigma",
    "τ": "tau",
    "υ": "upsilon",
    "φ": "phi",
    "χ": "chi",
    "ψ": "psi",
    "ω": "omega",
    # Greek uppercase
    "Α": "Alpha",
    "Β": "Beta",
    "Γ": "Gamma",
    "Δ": "Delta",
    "Ε": "Epsilon",
    "Ζ": "Zeta",
    "Η": "Eta",
    "Θ": "Theta",
    "Ι": "Iota",
    "Κ": "Kappa",
    "Λ": "Lambda",
    "Μ": "Mu",
    "Ν": "Nu",
    "Ξ": "Xi",
    "Ο": "Omicron",
    "Π": "Pi",
    "Ρ": "Rho",
    "Σ": "Sigma",
    "Τ": "Tau",
    "Υ": "Upsilon",
    "Φ": "Phi",
    "Χ": "Chi",
    "Ψ": "Psi",
    "Ω": "Omega",
    # Common math symbols
    "∞": "oo",
    "∂": "d",
    "∇": "nabla",
    "±": "+-",
    "∓": "-+",
    "×": "*",
    "÷": "/",
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
    "≈": "~",
    "≡": "==",
    "√": "sqrt",
    "'": "_prime",
    "^": "**",
}

_SUPERSCRIPTS: dict[str, str] = {
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
}

_SUBSCRIPTS: dict[str, str] = {
    "₀": "0",
    "₁": "1",
    "₂": "2",
    "₃": "3",
    "₄": "4",
    "₅": "5",
    "₆": "6",
    "₇": "7",
    "₈": "8",
    "₉": "9",
}

# Names that SymPy exposes as functions/classes in the default namespace.
# When a user writes these as bare variables (e.g. ``beta * x``), we force
# SymPy to treat them as Symbols via ``local_dict``. When they are called as
# functions (e.g. ``beta(x, y)``), we leave them alone so SymPy's native
# semantics apply.
_RESERVED_NAMES: frozenset[str] = frozenset({
    "beta",
    "gamma",
    "S",
    "N",
    "loggamma",
    "digamma",
    "polygamma",
    "zeta",
    "dirichlet_eta",
    "lerchphi",
    "polylog",
    "dilog",
    "sin",
    "cos",
    "tan",
    "cot",
    "sec",
    "csc",
    "asin",
    "acos",
    "atan",
    "atan2",
    "sinh",
    "cosh",
    "tanh",
    "asinh",
    "acosh",
    "atanh",
    "exp",
    "log",
    "ln",
    "sqrt",
    "erf",
    "erfc",
    "erfi",
    "besselj",
    "bessely",
    "besselk",
    "besseli",
    "hankel1",
    "hankel2",
    "jn",
    "yn",
    "hyper",
    "meijerg",
    "factorial",
    "binomial",
    "harmonic",
    "bernoulli",
    "euler",
    "catalan",
    "tribonacci",
    "fibonacci",
    "lucas",
    "airyai",
    "airybi",
    "jacobi",
    "legendre",
    "laguerre",
    "hermite",
    "gegenbauer",
    "chebyshevt",
    "chebyshevu",
    "elliptic_k",
    "elliptic_e",
    "elliptic_f",
    "elliptic_pi",
    "bell",
    "stirling2",
    "partition",
    "subfactorial",
    "factorial2",
    "doublefactorial",
    "rising_factorial",
    "falling_factorial",
    "genocchi",
    "spherical_harmonic",
    "diff",
    # Upper-case special functions/classes that are also common physics symbols
    "Beta",
    "Gamma",
    "Lambda",
})

# Constants that should keep their native SymPy meaning. We intentionally do NOT
# protect these as Symbols.
_CONSTANT_NAMES: frozenset[str] = frozenset({
    "pi",
    "E",
    "I",
    "oo",
    "zoo",
    "nan",
    "GoldenRatio",
    "Catalan",
    "TribonacciConstant",
})

# Vector calculus operators that should be treated as user-defined symbolic
# functions rather than native SymPy names. For example, ``div`` is polynomial
# division in SymPy, and ``curl`` / ``laplacian`` only exist in ``sympy.vector``.
# By protecting them as ``Function`` objects, expressions such as
# ``div(rho*u)`` or ``Del(p)`` can be recorded and manipulated symbolically.
_VECTOR_CALCULUS_NAMES: tuple[str, ...] = (
    "div",
    "grad",
    "curl",
    "laplace",
    "laplacian",
    "Del",
    "nabla",
    "convective",
    "dot",          # lowercase dot product
    "Div",          # uppercase aliases for natural math notation
    "Grad",
    "Dot",
    "Curl",
    "Laplacian",
)

# Regex for Laplacian shorthand ``Del^2(u)`` / ``Del**2(u)`` / ``nabla^2(u)``.
# The argument is matched as a simple identifier or expression without nested
# parentheses; complex arguments fall back to the standard parser.
_LAPLACIAN_RE: re.Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9_])(Del|nabla)\s*(?:\*\*|\^)\s*2\s*\(\s*([^)]+)\s*\)",
)

# Regex for convective derivative shorthand ``(u*Del)*v`` or ``(u*nabla)*v``.
_CONVECTIVE_DERIVATIVE_RE: re.Pattern[str] = re.compile(
    r"\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\*\s*(Del|nabla)\s*\)\s*\*\s*([A-Za-z_][A-Za-z0-9_]*)",
)

# Regex for uppercase material derivative ``D(u)/Dt``.
_MATERIAL_DERIVATIVE_RE: re.Pattern[str] = re.compile(
    r"\bD\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*/\s*\bDt\b",
)

# Regex for uppercase material derivative function form ``D/Dt(u)``.
_MATERIAL_DERIVATIVE_FUNC_RE: re.Pattern[str] = re.compile(
    r"\bD/Dt\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
)

# Regex for higher-order material derivative ``D^2 u / Dt^2``.
_MATERIAL_DERIVATIVE_HO_RE: re.Pattern[str] = re.compile(
    r"\bD\^(\d+)\s*([A-Za-z_][A-Za-z0-9_]*)\s*/\s*\bDt\b\^(\d+)",
)

# Compile-once regex caches.
_WORD_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}
_FUNC_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def preprocess_unicode(expr_str: str) -> str:
    """Convert Unicode math characters to SymPy-compatible ASCII.

    Handles Greek letters, superscripts/subscripts, and common math symbols.
    """
    result = expr_str
    for src, dst in _SUPERSCRIPTS.items():
        result = result.replace(src, dst)
    for src, dst in _SUBSCRIPTS.items():
        result = result.replace(src, dst)
    for src, dst in _UNICODE_REPLACEMENTS.items():
        result = result.replace(src, dst)
    return result


def preprocess_vector_calculus(expr_str: str) -> str:
    """Convert common vector-calculus shorthand into symbolic function calls.

    Handles:

    - ``Del^2(u)`` / ``Del**2(u)`` / ``nabla^2(u)`` → ``laplacian(u)``
    - ``(u*Del)*v`` / ``(u*nabla)*v`` → ``convective(u, v)``

    ``div(...)``, ``grad(...)`` and ``curl(...)`` are left as-is; the parser
    protects them as user-defined functions via ``_build_vector_calculus_local_dict``.
    """
    result = _LAPLACIAN_RE.sub(
        lambda m: f"laplacian({m.group(2)})", result := expr_str
    )
    result = _CONVECTIVE_DERIVATIVE_RE.sub(
        lambda m: f"convective({m.group(1)}, {m.group(3)})", result
    )
    return result


def preprocess_diff_to_derivative(expr_str: str) -> str:
    """Convert ``diff(X, Y)`` calls into ``Derivative(X, Y)``.

    SymPy's ``diff(Symbol, t)`` returns ``0``, which is surprising when users
    write PDEs such as ``diff(u, t) + div(rho*u) = 0``. By rewriting to the
    unevaluated ``Derivative`` form, the differential term is preserved for
    symbolic derivation and display.
    """
    return re.sub(r"\bdiff\s*\(", "Derivative(", expr_str)


def preprocess_leibniz_derivatives(expr_str: str) -> str:
    """Convert Leibniz derivative notation (e.g. ``dX/dY``) into SymPy ``Derivative(...)``.

    Supports first-order forms like ``dX/dY`` and higher-order forms like
    ``d^2X/dY^2``. Also supports uppercase material derivative ``D(X)/Dt``.
    Non-matching ``d`` or ``D`` tokens are left untouched.
    """
    result = _LEIBNIZ_HIGHER_ORDER_RE.sub(_leibniz_higher_repl, expr_str)
    result = _LEIBNIZ_FIRST_ORDER_RE.sub(_leibniz_first_repl, result)
    result = _MATERIAL_DERIVATIVE_HO_RE.sub(_material_derivative_ho_repl, result)
    result = _MATERIAL_DERIVATIVE_RE.sub(_material_derivative_repl, result)
    result = _MATERIAL_DERIVATIVE_FUNC_RE.sub(_material_derivative_func_repl, result)
    return result


_LEIBNIZ_FIRST_ORDER_RE: re.Pattern[str] = re.compile(
    r"\bd([A-Za-z_][A-Za-z0-9_]*)\b\s*/\s*\bd([A-Za-z_][A-Za-z0-9_]*)\b",
)
_LEIBNIZ_HIGHER_ORDER_RE: re.Pattern[str] = re.compile(
    r"\bd\^(\d+)\s*([A-Za-z_][A-Za-z0-9_]*)\b\s*/\s*\bd([A-Za-z_][A-Za-z0-9_]*)\b\^(\d+)",
)


def _leibniz_first_repl(match: re.Match[str]) -> str:
    """Convert a first-order Leibniz derivative match to ``Derivative``.
    """
    return f"Derivative({match.group(1)}, {match.group(2)})"


def _leibniz_higher_repl(match: re.Match[str]) -> str:
    """Convert a higher-order Leibniz derivative match to ``Derivative``.
    """
    numerator_order = int(match.group(1))
    variable = match.group(2)
    wrt = match.group(3)
    denominator_order = int(match.group(4))
    if numerator_order != denominator_order:
        # Mismatched orders: leave the original text so the parser fails
        # clearly instead of silently guessing.
        return match.group(0)
    return f"Derivative({variable}, ({wrt}, {numerator_order}))"


def _material_derivative_repl(match: re.Match[str]) -> str:
    """Convert ``D(u)/Dt`` to ``Derivative(u, t)``.
    """
    return f"Derivative({match.group(1)}, t)"


def _material_derivative_func_repl(match: re.Match[str]) -> str:
    """Convert ``D/Dt(u)`` to ``Derivative(u, t)``.
    """
    return f"Derivative({match.group(1)}, t)"


def _material_derivative_ho_repl(match: re.Match[str]) -> str:
    """Convert ``D^2 u / Dt^2`` to ``Derivative(u, (t, 2))``.
    """
    numerator_order = int(match.group(1))
    variable = match.group(2)
    denominator_order = int(match.group(3))
    if numerator_order != denominator_order:
        return match.group(0)
    return f"Derivative({variable}, (t, {numerator_order}))"


def _word_pattern(name: str) -> re.Pattern[str]:
    """Return a regex that matches ``name`` as a whole identifier token.

    Excludes attribute access (``name.attr``) and function calls (``name(...)``).
    """
    if name not in _WORD_PATTERN_CACHE:
        _WORD_PATTERN_CACHE[name] = re.compile(
            r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_\.])",
        )
    return _WORD_PATTERN_CACHE[name]


def _func_pattern(name: str) -> re.Pattern[str]:
    """Return a regex that matches ``name(...)`` as a function call."""
    if name not in _FUNC_PATTERN_CACHE:
        _FUNC_PATTERN_CACHE[name] = re.compile(
            r"(?<![A-Za-z0-9_])" + re.escape(name) + r"\s*\(",
        )
    return _FUNC_PATTERN_CACHE[name]


def _name_used_as_variable(expr: str, name: str) -> bool:
    """True if ``name`` appears in ``expr`` but not as a function call."""
    return bool(_word_pattern(name).search(expr)) and not bool(
        _func_pattern(name).search(expr)
    )


def _build_local_dict(expr: str) -> dict[str, Any]:
    """Build a ``local_dict`` that protects reserved names used as variables."""
    local_dict: dict[str, Any] = {}
    for name in _RESERVED_NAMES:
        if _name_used_as_variable(expr, name):
            local_dict[name] = sp.Symbol(name)
    return local_dict


def build_reserved_local_dict(expr: str) -> dict[str, Any]:
    """Public alias for building a reserved-name ``local_dict``.

    Exposed so other parsers (e.g. ``FormulaParser``) can reuse the same
    reserved-name protection list without duplicating it.
    """
    return _build_local_dict(expr)


def _build_vector_calculus_local_dict(expr: str) -> dict[str, Any]:
    """Build a ``local_dict`` that protects vector-calculus names.

    Names used as function calls (e.g. ``div(rho*u)``) become SymPy
    ``Function`` objects so they are not hijacked by native SymPy semantics
    such as polynomial division. Bare names (e.g. ``nabla`` used as a scalar
    multiplier) become Symbols.
    """
    local_dict: dict[str, Any] = {}
    for name in _VECTOR_CALCULUS_NAMES:
        if _func_pattern(name).search(expr):
            local_dict[name] = sp.Function(name)
        elif _word_pattern(name).search(expr):
            local_dict[name] = sp.Symbol(name)
    return local_dict


def _convert_equals_to_eq(expr_str: str) -> str:
    """Convert a single ``A = B`` into ``Eq(A, B)``.

    Leaves alone:
    - ``==``, ``<=``, ``>=``, ``!=``
    - Already wrapped calls like ``Eq(...)``, ``Ne(...)``, etc.
    - Multiple ``=`` signs (let the parser surface the error)
    """
    stripped = expr_str.strip()
    if stripped.startswith((
        "Eq(", "Ne(", "Lt(", "Le(", "Gt(", "Ge(", "Equality(", "Rel(",
    )):
        return expr_str

    # Match a lone '=' that is not part of '==', '<=', '>=', or '!='.
    eq_pattern = re.compile(r"(?<![=<>!])=(?!=)")
    matches = list(eq_pattern.finditer(expr_str))
    if len(matches) == 0:
        return expr_str
    if len(matches) > 1:
        # Multiple bare '=' signs; do not guess, let the parser fail.
        return expr_str

    pos = matches[0].start()
    lhs = expr_str[:pos].strip()
    rhs = expr_str[pos + 1 :].strip()
    return f"Eq({lhs}, {rhs})"


def _split_eq_args(expr_str: str) -> tuple[str, str] | None:
    """Split a top-level ``Eq(lhs, rhs)`` string into ``(lhs, rhs)``.

    Handles nested parentheses so that ``Eq(f(x, y), z)`` is split correctly.
    Returns ``None`` if the input is not a well-formed ``Eq(...)`` call.
    """
    if not (expr_str.startswith("Eq(") and expr_str.endswith(")")):
        return None
    inner = expr_str[3:-1]
    depth = 0
    for i, ch in enumerate(inner):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            return inner[:i].strip(), inner[i + 1 :].strip()
    return None


def parse_expression_string(
    expr_str: str,
    *,
    convert_equation: bool = True,
    preprocess: bool = True,
    local_dict: dict[str, Any] | None = None,
) -> tuple[sp.Expr | None, str | None]:
    """Parse a user-facing expression string into a SymPy expression.

    Args:
        expr_str: The mathematical expression as a string.
        convert_equation: If ``True`` (default), convert a single ``=`` into
            ``Eq(...)``. Disable this if you already know the input is an
            expression rather than an equation.
        preprocess: If ``True`` (default), run Unicode/Greek, Leibniz
            derivative (``dX/dY``), and vector-calculus preprocessing.
        local_dict: Optional mapping of symbol names to SymPy objects. When
            provided, it is merged with the reserved-name protection built by
            this parser; caller-provided entries take precedence.

    Returns:
        A tuple ``(sympy_expr, error)``. On success, ``error`` is ``None``; on
        failure, ``sympy_expr`` is ``None`` and ``error`` is a message string.
    """
    if not isinstance(expr_str, str) or not expr_str.strip():
        return None, "Empty or non-string expression"

    processed = preprocess_unicode(expr_str) if preprocess else expr_str
    processed = preprocess_vector_calculus(processed) if preprocess else processed
    processed = preprocess_diff_to_derivative(processed) if preprocess else processed
    processed = preprocess_leibniz_derivatives(processed) if preprocess else processed

    if convert_equation:
        processed = _convert_equals_to_eq(processed)

    merged_local_dict = _build_local_dict(processed)
    merged_local_dict.update(_build_vector_calculus_local_dict(processed))
    if local_dict:
        merged_local_dict.update(local_dict)

    # SymPy's ``parse_expr(..., evaluate=False)`` fails for ``Eq`` when the RHS
    # contains an expression that simplifies to zero (e.g. ``1*(0+0)/2``),
    # raising "integer division or modulo by zero". We work around this by
    # parsing the LHS and RHS separately and building the Equality ourselves.
    eq_args = _split_eq_args(processed)
    if eq_args is not None:
        lhs_str, rhs_str = eq_args
        try:
            # We use evaluate=True for the arguments of Eq.  SymPy's Eq
            # constructor has a known bug when passed an unevaluated Mul that
            # contains a zero sub-expression (e.g. ``1*(0+0)/2``), so we let
            # SymPy simplify the operands before building the relation.
            lhs = parse_expr(
                lhs_str,
                local_dict=merged_local_dict,
                transformations=TRANSFORMATIONS,
            )
            rhs = parse_expr(
                rhs_str,
                local_dict=merged_local_dict,
                transformations=TRANSFORMATIONS,
            )
            return sp.Eq(lhs, rhs), None
        except Exception as exc:  # pragma: no cover
            return None, str(exc)

    try:
        expr = parse_expr(
            processed,
            local_dict=merged_local_dict,
            transformations=TRANSFORMATIONS,
            evaluate=False,
        )
        return expr, None
    except Exception as exc:  # pragma: no cover - parser raises many types
        return None, str(exc)


def parse_expression_string_to_str(
    expr_str: str,
    *,
    convert_equation: bool = True,
    preprocess: bool = True,
) -> tuple[str | None, str | None]:
    """Convenience wrapper that returns the SymPy expression as a string."""
    expr, error = parse_expression_string(
        expr_str,
        convert_equation=convert_equation,
        preprocess=preprocess,
    )
    if expr is None:
        return None, error
    return str(expr), None


def parse_user_expression(
    expr_str: str,
    *,
    convert_equation: bool = True,
) -> tuple[sp.Expr | None, str | None]:
    """Parse a user-facing expression that may be LaTeX or a SymPy-style string.

    This is the recommended entry point for MCP tools that accept arbitrary
    mathematical input.  It automatically detects LaTeX and routes it through
    ``FormulaParser``; otherwise it uses the shared parser with Unicode,
    reserved-name, equation and Leibniz-derivative support.

    Args:
        expr_str: The mathematical expression as a string.
        convert_equation: If ``True`` (default), convert a single ``=`` into
            ``Eq(...)`` for SymPy-style inputs.

    Returns:
        A tuple ``(sympy_expr, error)``. On success, ``error`` is ``None``; on
        failure, ``sympy_expr`` is ``None`` and ``error`` is a message string.
    """
    if not isinstance(expr_str, str) or not expr_str.strip():
        return None, "Empty or non-string expression"

    # Lazy import to avoid a circular module dependency: ``symkit.domain.formula``
    # is used here only when LaTeX is detected, while ``formula.py`` may reuse
    # helpers from this module for SymPy-string parsing.
    from symkit.domain.formula import FormulaParser, FormulaSource, ParseError

    if FormulaParser._is_latex(expr_str):
        result = FormulaParser.parse(
            expr_str,
            formula_id="user_expression",
            source=FormulaSource.USER_INPUT,
        )
        if isinstance(result, ParseError):
            return None, result.message
        return result.expression, None

    return parse_expression_string(expr_str, convert_equation=convert_equation)
