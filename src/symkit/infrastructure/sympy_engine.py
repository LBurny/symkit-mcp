"""
SymPy Engine Implementation

Concrete implementation of the SymbolicEngine interface using SymPy.
"""

from typing import Any

import sympy as sp

from symkit.domain.entities import Expression, ExpressionType
from symkit.domain.expression_parser import (
    TRANSFORMATIONS,
    parse_expression_string,
)
from symkit.domain.services import SymbolicEngine
from symkit.domain.value_objects import MathContext, SimplificationLevel


def _build_vector_field(expr: Any, coords: list[str], N: Any) -> Any:
    """Build a sympy.vector vector field from components or expression.

    If expr contains multiple comma-separated components (parsed as
    a tuple), treat them as [F_x, F_y, F_z] and build F_x*N.i + ...
    Otherwise treat expr as a scalar and build expr*N.i (for 1D) etc.
    """

    # Check if expr is a tuple (comma-separated in input like "x*y, z*x, y*z")
    # Python's parse_expr returns a plain tuple (x*y, z*x, y*z)
    if isinstance(expr, tuple):
        components = list(expr)
        basis = [N.i, N.j, N.k]
        field = None
        for i, comp in enumerate(components):
            if i >= len(basis):
                break
            coord_expr = comp
            # Substitute coordinate symbols into component expression
            for j, c in enumerate(coords):
                coord_var = {0: N.x, 1: N.y, 2: N.z}.get(j)
                if coord_var:
                    coord_expr = coord_expr.subs(sp.Symbol(c), coord_var)
            term = coord_expr * basis[i]
            field = term if field is None else field + term
        return field if field is not None else 0 * N.i

    # Single expression — treat as scalar*x.i for 1D, or build from coords
    if len(coords) == 1:
        return expr.subs(sp.Symbol(coords[0]), N.x) * N.i
    elif len(coords) == 2:
        x_comp = expr.subs(sp.Symbol(coords[0]), N.x)
        y_comp = expr.subs(sp.Symbol(coords[1]), N.y)
        return x_comp * N.i + y_comp * N.j
    else:
        x_comp = expr.subs(sp.Symbol(coords[0]), N.x)
        y_comp = expr.subs(sp.Symbol(coords[1]), N.y)
        z_comp = expr.subs(sp.Symbol(coords[2]), N.z)
        return x_comp * N.i + y_comp * N.j + z_comp * N.k


class SymPyEngine(SymbolicEngine):
    """
    SymPy-based implementation of the symbolic computation engine.

    This is the primary symbolic engine used by SymKit.
    """

    # Parser transformations for flexible input (mirrors the shared parser)
    TRANSFORMATIONS = TRANSFORMATIONS

    def parse(self, expr_str: str, context: MathContext | None = None) -> Expression:
        """Parse a string into an Expression using SymPy."""
        try:
            # Get symbols with assumptions if provided
            local_dict = self._get_local_dict(context)

            # Parse through the shared parser: Unicode, Leibniz derivatives,
            # equation conversion and reserved-name protection are handled
            # consistently across all MCP entry points.
            sympy_expr, error = parse_expression_string(
                expr_str,
                convert_equation=True,
                local_dict=local_dict,
            )
            if sympy_expr is None:
                raise ValueError(error or "parse failed")

            # Determine expression type
            expr_type = self._classify_expression(sympy_expr)

            return Expression(
                raw=str(sympy_expr),
                latex=sp.latex(sympy_expr),
                sympy_expr=sympy_expr,
                expr_type=expr_type,
            )

        except Exception:
            # Return invalid expression on parse error
            return Expression(
                raw=expr_str,
                latex="",
                sympy_expr=None,
                expr_type=ExpressionType.UNKNOWN,
            )

    def simplify(self, expr: Expression, context: MathContext | None = None) -> Expression:
        """Simplify an expression using SymPy."""
        if not expr.is_valid:
            return expr

        level = context.simplify_level if context else SimplificationLevel.BASIC

        match level:
            case SimplificationLevel.NONE:
                result = expr.sympy_expr
            case SimplificationLevel.BASIC:
                result = sp.simplify(expr.sympy_expr)
            case SimplificationLevel.FULL:
                result = sp.simplify(sp.expand(expr.sympy_expr))
            case SimplificationLevel.TRIGONOMETRIC:
                result = sp.trigsimp(expr.sympy_expr)
            case SimplificationLevel.RADICAL:
                result = sp.radsimp(expr.sympy_expr)
            case _:
                result = sp.simplify(expr.sympy_expr)

        return Expression(
            raw=str(result),
            latex=sp.latex(result),
            sympy_expr=result,
            expr_type=expr.expr_type,
        )

    def differentiate(
        self,
        expr: Expression,
        variable: str,
        order: int = 1,
        context: MathContext | None = None,
    ) -> Expression:
        """Differentiate an expression using SymPy."""
        if not expr.is_valid:
            return expr

        var = sp.Symbol(variable, **self._get_assumptions(variable, context))
        result = sp.diff(expr.sympy_expr, var, order)

        return Expression(
            raw=str(result),
            latex=sp.latex(result),
            sympy_expr=result,
            expr_type=ExpressionType.CALCULUS,
        )

    def integrate(
        self,
        expr: Expression,
        variable: str,
        lower: Any = None,
        upper: Any = None,
        context: MathContext | None = None,
    ) -> Expression:
        """Integrate an expression using SymPy."""
        if not expr.is_valid:
            return expr

        var = sp.Symbol(variable, **self._get_assumptions(variable, context))

        if lower is not None and upper is not None:
            # Definite integral
            lower_val = self._to_sympy(lower)
            upper_val = self._to_sympy(upper)
            result = sp.integrate(expr.sympy_expr, (var, lower_val, upper_val))
        else:
            # Indefinite integral
            result = sp.integrate(expr.sympy_expr, var)

        return Expression(
            raw=str(result),
            latex=sp.latex(result),
            sympy_expr=result,
            expr_type=ExpressionType.CALCULUS,
        )

    def solve(
        self,
        equation: Expression,
        variable: str,
        context: MathContext | None = None,
    ) -> list[Expression]:
        """Solve an equation for a variable using SymPy."""
        if not equation.is_valid:
            return []

        var = sp.Symbol(variable, **self._get_assumptions(variable, context))

        # Handle both equations and expressions (expr = 0)
        if isinstance(equation.sympy_expr, sp.Equality):
            solutions = sp.solve(equation.sympy_expr, var)
        else:
            solutions = sp.solve(equation.sympy_expr, var)

        return [
            Expression(
                raw=str(sol),
                latex=sp.latex(sol),
                sympy_expr=sol,
                expr_type=ExpressionType.ALGEBRAIC,
            )
            for sol in solutions
        ]

    def substitute(
        self,
        expr: Expression,
        substitutions: dict[str, Any],
        context: MathContext | None = None,
    ) -> Expression:
        """Substitute values into an expression using SymPy."""
        if not expr.is_valid:
            return expr

        # Convert substitutions to SymPy format
        subs_dict = {}
        for var_name, value in substitutions.items():
            var = sp.Symbol(var_name, **self._get_assumptions(var_name, context))
            subs_dict[var] = self._to_sympy(value)

        result = expr.sympy_expr.subs(subs_dict)

        return Expression(
            raw=str(result),
            latex=sp.latex(result),
            sympy_expr=result,
            expr_type=expr.expr_type,
        )

    def equals(
        self,
        expr1: Expression,
        expr2: Expression,
        context: MathContext | None = None,  # noqa: ARG002 - reserved for future use
    ) -> bool:
        """Check if two expressions are mathematically equal."""
        if not expr1.is_valid or not expr2.is_valid:
            return False

        # Try simplifying the difference
        diff = sp.simplify(expr1.sympy_expr - expr2.sympy_expr)
        if diff == 0:
            return True

        # Try expanding and simplifying
        diff_expanded = sp.simplify(sp.expand(expr1.sympy_expr - expr2.sympy_expr))
        return bool(diff_expanded == 0)

    # ═══════════════════════════════════════════════════════════════
    # Vector Calculus
    # ═══════════════════════════════════════════════════════════════

    def gradient(self, expr: Expression, coords: list[str],
                 context: MathContext | None = None) -> Expression:
        """Compute gradient of a scalar field using sympy.vector."""
        if not expr.is_valid:
            return expr
        try:
            from sympy.vector import CoordSys3D, gradient
            N = CoordSys3D("N")
            # Map coordinate symbols to vector components
            coord_map: dict[str, Any] = {}
            if len(coords) >= 3:
                coord_map = {coords[0]: N.x, coords[1]: N.y, coords[2]: N.z}
            elif len(coords) == 2:
                coord_map = {coords[0]: N.x, coords[1]: N.y}
            else:
                coord_map = {coords[0]: N.x}
            scalar = expr.sympy_expr.subs({sp.Symbol(k): v for k, v in coord_map.items()})
            result = gradient(scalar, N)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    def divergence(self, expr: Expression, coords: list[str],
                   context: MathContext | None = None) -> Expression:
        """Compute divergence of a vector field.

        For comma-separated vector components like "x*y, z*x, y*z",
        builds the vector field automatically.
        """
        if not expr.is_valid:
            return expr
        try:
            from sympy.vector import CoordSys3D, divergence
            N = CoordSys3D("N")
            field = _build_vector_field(expr.sympy_expr, coords, N)
            result = divergence(field, N)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    def curl(self, expr: Expression, coords: list[str],
             context: MathContext | None = None) -> Expression:
        """Compute curl of a vector field.

        For comma-separated vector components like "x*y, z*x, y*z",
        builds the vector field automatically.
        """
        if not expr.is_valid:
            return expr
        try:
            from sympy.vector import CoordSys3D, curl
            N = CoordSys3D("N")
            field = _build_vector_field(expr.sympy_expr, coords, N)
            result = curl(field, N)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    def laplacian(self, expr: Expression, coords: list[str],
                  context: MathContext | None = None) -> Expression:
        """Compute Laplacian as div(grad(f))."""
        if not expr.is_valid:
            return expr
        try:
            from sympy.vector import CoordSys3D, divergence, gradient
            N = CoordSys3D("N")
            # Compute gradient on scalar expression
            scalar = expr.sympy_expr
            if isinstance(scalar, tuple):
                return Expression(raw="", latex="", sympy_expr=None,
                                expr_type=ExpressionType.UNKNOWN)
            coord_map = {}
            for i, c in enumerate(coords):
                coord_var = {0: N.x, 1: N.y, 2: N.z}.get(i)
                if coord_var:
                    coord_map[c] = coord_var
            s = scalar
            for c, cv in coord_map.items():
                s = s.subs(sp.Symbol(c), cv)
            grad_field = gradient(s, N)  # returns VectorAdd
            result = divergence(grad_field, N)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    # ═══════════════════════════════════════════════════════════════
    # Matrix Operations
    # ═══════════════════════════════════════════════════════════════

    def matrix_det(self, expr: Expression,
                   context: MathContext | None = None) -> Expression:
        """Compute determinant of a matrix."""
        if not expr.is_valid:
            return expr
        try:
            if isinstance(expr.sympy_expr, sp.MatrixBase):
                result = expr.sympy_expr.det()
            else:
                result = sp.Matrix(expr.sympy_expr).det()
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.ALGEBRAIC)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    def matrix_inv(self, expr: Expression,
                   context: MathContext | None = None) -> Expression:
        """Compute inverse of a matrix."""
        if not expr.is_valid:
            return expr
        try:
            if isinstance(expr.sympy_expr, sp.MatrixBase):
                result = expr.sympy_expr.inv()
            else:
                result = sp.Matrix(expr.sympy_expr).inv()
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.MATRIX)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    def matrix_eigenvals(self, expr: Expression,
                         context: MathContext | None = None) -> list[Expression]:
        """Compute eigenvalues of a matrix."""
        if not expr.is_valid:
            return []
        try:
            if isinstance(expr.sympy_expr, sp.MatrixBase):
                eigenvals = expr.sympy_expr.eigenvals()
            else:
                eigenvals = sp.Matrix(expr.sympy_expr).eigenvals()
            return [
                Expression(raw=str(v), latex=sp.latex(v),
                          sympy_expr=v, expr_type=ExpressionType.ALGEBRAIC)
                for v in eigenvals
            ]
        except Exception:
            return []

    def matrix_eigenvects(self, expr: Expression,
                          context: MathContext | None = None) -> list[dict[str, Any]]:
        """Compute eigenvectors of a matrix."""
        if not expr.is_valid:
            return []
        try:
            if isinstance(expr.sympy_expr, sp.MatrixBase):
                eigens = expr.sympy_expr.eigenvects()
            else:
                eigens = sp.Matrix(expr.sympy_expr).eigenvects()
            results: list[dict[str, Any]] = []
            for ev in eigens:
                results.append({
                    "eigenvalue": str(ev[0]),
                    "multiplicity": ev[1],
                    "vectors": [str(v) for v in ev[2]],
                })
            return results
        except Exception:
            return []

    # ═══════════════════════════════════════════════════════════════
    # ODE, Limits, Series
    # ═══════════════════════════════════════════════════════════════

    def dsolve(self, ode: Expression, func: str, var: str,
               context: MathContext | None = None) -> Expression:
        """Solve an ordinary differential equation."""
        if not ode.is_valid:
            return ode
        try:
            f = sp.Function(func)
            v = sp.Symbol(var)
            if isinstance(ode.sympy_expr, sp.Equality):
                result = sp.dsolve(ode.sympy_expr, f(v))
            else:
                result = sp.dsolve(sp.Eq(ode.sympy_expr, 0), f(v))
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.EQUATION)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    def limit(self, expr: Expression, var: str, point: str,
              direction: str = "+-",
              context: MathContext | None = None) -> Expression:
        """Compute limit of an expression."""
        if not expr.is_valid:
            return expr
        try:
            v = sp.Symbol(var, **self._get_assumptions(var, context))
            p, error = parse_expression_string(point, convert_equation=False)
            if p is None:
                raise ValueError(error or f"cannot parse point '{point}'")
            if direction == "+":
                result = sp.limit(expr.sympy_expr, v, p, dir="+")
            elif direction == "-":
                result = sp.limit(expr.sympy_expr, v, p, dir="-")
            else:
                result = sp.limit(expr.sympy_expr, v, p)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    def series(self, expr: Expression, var: str, point: str,
               order: int = 6,
               context: MathContext | None = None) -> Expression:
        """Compute series expansion of an expression."""
        if not expr.is_valid:
            return expr
        try:
            v = sp.Symbol(var, **self._get_assumptions(var, context))
            p, error = parse_expression_string(point, convert_equation=False)
            if p is None:
                raise ValueError(error or f"cannot parse point '{point}'")
            result = sp.series(expr.sympy_expr, v, p, order).removeO()
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.ALGEBRAIC)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    # ═══════════════════════════════════════════════════════════════
    # Integral Transforms
    # ═══════════════════════════════════════════════════════════════

    def laplace_transform(self, expr: Expression, time_var: str, freq_var: str,
                          context: MathContext | None = None) -> Expression:
        """Compute Laplace transform."""
        if not expr.is_valid:
            return expr
        try:
            t = sp.Symbol(time_var)
            s = sp.Symbol(freq_var)
            result = sp.laplace_transform(expr.sympy_expr, t, s, noconds=True)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    def inverse_laplace_transform(self, expr: Expression, freq_var: str, time_var: str,
                                  context: MathContext | None = None) -> Expression:
        """Compute inverse Laplace transform."""
        if not expr.is_valid:
            return expr
        try:
            s = sp.Symbol(freq_var)
            t = sp.Symbol(time_var)
            result = sp.inverse_laplace_transform(expr.sympy_expr, s, t)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    def fourier_transform(self, expr: Expression, space_var: str, freq_var: str,
                          context: MathContext | None = None) -> Expression:
        """Compute Fourier transform."""
        if not expr.is_valid:
            return expr
        try:
            x = sp.Symbol(space_var)
            k = sp.Symbol(freq_var)
            result = sp.fourier_transform(expr.sympy_expr, x, k)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    def inverse_fourier_transform(self, expr: Expression, freq_var: str, space_var: str,
                                  context: MathContext | None = None) -> Expression:
        """Compute inverse Fourier transform."""
        if not expr.is_valid:
            return expr
        try:
            k = sp.Symbol(freq_var)
            x = sp.Symbol(space_var)
            result = sp.inverse_fourier_transform(expr.sympy_expr, k, x)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception:
            return Expression(raw="", latex="", sympy_expr=None,
                            expr_type=ExpressionType.UNKNOWN)

    def _get_local_dict(self, context: MathContext | None) -> dict[str, Any]:
        """Get local dictionary for parsing with symbol assumptions."""
        local_dict: dict[str, Any] = {}

        if context and context.assumptions:
            for var_name, assumptions in context.assumptions.items():
                local_dict[var_name] = sp.Symbol(var_name, **assumptions)

        return local_dict

    def _get_assumptions(self, variable: str, context: MathContext | None) -> dict[str, bool]:
        """Get assumptions for a specific variable."""
        if context and variable in context.assumptions:
            return context.assumptions[variable]
        return {}

    def _to_sympy(self, value: Any) -> Any:
        """Convert a value to SymPy format."""
        if isinstance(value, str):
            expr, error = parse_expression_string(value, convert_equation=False)
            if expr is None:
                raise ValueError(error or f"cannot parse '{value}'")
            return expr
        return sp.sympify(value)

    def _classify_expression(self, expr: Any) -> ExpressionType:
        """Classify the type of a SymPy expression."""
        if isinstance(expr, (sp.Derivative, sp.Integral)):
            return ExpressionType.CALCULUS
        if isinstance(expr, (sp.Equality, sp.Rel)):
            return ExpressionType.EQUATION
        if isinstance(expr, sp.MatrixBase):
            return ExpressionType.MATRIX
        return ExpressionType.ALGEBRAIC
