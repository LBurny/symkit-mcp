"""SymPy implementation of the SymbolicEngine interface."""

from typing import Any

import sympy as sp
from sympy.core.function import AppliedUndef

from symkit.domain.assumption_binding import apply_assumptions, resolve_assumed_symbol
from symkit.domain.dsolve_ics import dsolve_with_ics
from symkit.domain.entities import Expression, ExpressionType
from symkit.domain.expression_parser import (
    TRANSFORMATIONS,
    parse_expression_string,
)
from symkit.domain.final_result import evaluate_pending
from symkit.domain.services import SymbolicEngine
from symkit.domain.value_objects import MathContext, SimplificationLevel
from symkit.infrastructure.solution_guards import dsolve_artifact_reason, laplace_condition_warnings
from symkit.infrastructure.vector_input import build_vector_field


def _failed(error: str) -> Expression:
    """Invalid Expression carrying an engine failure (one shared error shape)."""
    return Expression(raw="", latex="", sympy_expr=None, expr_type=ExpressionType.UNKNOWN, error=error)


def coupled_undefined_functions(
    ode_expr: sp.Basic, dependent: str, extra: list[str]
) -> list[str]:
    """Undefined functions sharing an additive term with the dependent one.

    A forcing term alone stays solvable; one times the dependent variable
    couples in a second equation (r14 task-15).
    """
    extra_set = set(extra)
    lhs = ode_expr.lhs - ode_expr.rhs if isinstance(ode_expr, sp.Equality) else ode_expr
    coupled: set[str] = set()
    for term in sp.Add.make_args(sp.expand(lhs)):
        names = {a.func.__name__ for a in term.atoms(AppliedUndef)}
        if dependent in names:
            coupled |= names & extra_set
    return sorted(coupled)


def nonpolynomial_ode_reason(ode_expr: sp.Basic, dependent: str) -> str | None:
    """A reason when ``dsolve`` is likely to hang without bound.

    SymPy has no time limit and raises nothing on a non-terminating nonlinear
    ODE (a pendulum wedged the server); detected: a dependent function under a
    transcendental, e.g. ``sin(theta(t))``.
    """
    if not isinstance(ode_expr, sp.Equality):
        return None
    funcs = {a.func for a in ode_expr.atoms(AppliedUndef)}
    target = next((f for f in funcs if f.__name__ == dependent), None)
    if target is None:
        return None
    body = ode_expr.lhs - ode_expr.rhs
    transcendental = (sp.sin, sp.cos, sp.tan, sp.exp, sp.log, sp.sinh, sp.cosh, sp.tanh)
    for node in sp.preorder_traversal(body):
        if isinstance(node, transcendental):
            for arg in node.args:
                if any(a.func is target for a in arg.atoms(AppliedUndef)):
                    return (
                        f"the dependent function appears inside "
                        f"{node.func.__name__}(...), a class sympy.dsolve does not "
                        f"terminate on (it has no closed form). Solve it numerically, "
                        f"or linearize the nonlinearity first."
                    )
    return None


def restore_zero_root(
    eq: sp.Basic, v: sp.Symbol, solutions: list[Any]
) -> tuple[list[Any], list[str], bool]:
    """Re-add the trivial root 0 that symbol assumptions filtered out.

    ``solve`` drops the zero root of a factored equation (r14 task-15).
    Returns ``(solutions, filtered, restored)``.
    """
    plain_v = sp.Symbol(str(v))

    def _same(candidate: Any, other: Any) -> bool:
        try:
            return bool(sp.simplify(candidate.xreplace({plain_v: v}) - other) == 0)
        except Exception:
            return str(candidate) == str(other)

    filtered: list[str] = []
    if v.is_zero is False:
        try:
            neutral = list(sp.solve(eq.xreplace({v: plain_v}), plain_v))
        except Exception:
            neutral = []
        filtered = [str(s) for s in neutral if not any(_same(s, x) for x in solutions)]

    lhs = eq.lhs - eq.rhs if isinstance(eq, sp.Equality) else eq
    try:
        zero_root = bool(sp.simplify(lhs.subs(v, 0)) == 0)
    except Exception:
        zero_root = False
    restored = False
    if zero_root and not any(_same(sp.Integer(0), x) for x in solutions):
        solutions = [sp.Integer(0), *solutions]
        restored = True
    return solutions, filtered, restored


def _coord_sub_symbol(expr: Any, name: str, coord: Any) -> Any:
    """Substitute the coordinate symbol ``name`` into *expr* by NAME.

    A bare subs key misses an assumption-bearing ``Symbol`` (gradient was
    silently zero, run-017).
    """
    target = next(
        (s for s in getattr(expr, "free_symbols", ()) if str(s) == name), None
    )
    return expr.subs(target if target is not None else sp.Symbol(name), coord)


def _build_vector_field(expr: Any, coords: list[str], N: Any) -> Any:
    """Build a vector field via :mod:`vector_input` (scalar input raises)."""
    return build_vector_field(expr, coords, N)


class SymPyEngine(SymbolicEngine):
    """SymPy-based implementation of the symbolic computation engine."""

    # Parser transformations for flexible input (mirrors the shared parser)
    TRANSFORMATIONS = TRANSFORMATIONS

    def parse(self, expr_str: str, context: MathContext | None = None) -> Expression:
        """Parse a string into an Expression using SymPy.

        Parsing is pure syntax; assumptions are applied afterwards, onto the
        free symbols (invariant I1) — injecting them into the parser let
        implicit multiplication rewrite ``k(x)`` into ``k*x`` (run-024).
        """
        try:
            # The shared parser handles Unicode, Leibniz derivatives, equation
            # conversion and reserved-name protection for every entry point.
            sympy_expr, error = parse_expression_string(
                expr_str,
                convert_equation=True,
            )
            if sympy_expr is None:
                raise ValueError(error or "parse failed")

            sympy_expr = apply_assumptions(
                sympy_expr, context.assumptions if context else None
            )

            expr_type = self._classify_expression(sympy_expr)

            return Expression(
                raw=str(sympy_expr),
                latex=sp.latex(sympy_expr),
                sympy_expr=sympy_expr,
                expr_type=expr_type,
            )

        except Exception as e:
            # Return invalid expression on parse error, keeping the cause.
            return Expression(
                raw=expr_str,
                latex="",
                sympy_expr=None,
                expr_type=ExpressionType.UNKNOWN,
                error=str(e),
            )

    def simplify(self, expr: Expression, context: MathContext | None = None) -> Expression:
        """Simplify using SymPy; pending operation nodes are evaluated first.

        The parser keeps ``Derivative(Add(...), (x, 2))`` unevaluated and
        ``sp.simplify`` cannot flatten its undistributed ``doit()`` form, so an
        exactly-zero residual came back as ``X - X`` (task-05 G11).  A no-op
        for undefined functions.
        """
        if not expr.is_valid:
            return expr

        level = context.simplify_level if context else SimplificationLevel.BASIC
        sym = evaluate_pending(expr.sympy_expr)

        match level:
            case SimplificationLevel.NONE:
                result = expr.sympy_expr
            case SimplificationLevel.BASIC:
                result = sp.simplify(sym)
            case SimplificationLevel.FULL:
                result = sp.simplify(sp.expand(sym))
            case SimplificationLevel.TRIGONOMETRIC:
                result = sp.trigsimp(sym)
            case SimplificationLevel.RADICAL:
                result = sp.radsimp(sym)
            case _:
                result = sp.simplify(sym)

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

        var = resolve_assumed_symbol(variable, self._get_assumptions(variable, context))
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
        var = resolve_assumed_symbol(variable, self._get_assumptions(variable, context))
        sym = expr.sympy_expr
        if lower is not None and upper is not None:
            from symkit.infrastructure.solution_guards import guarded_definite_integral
            result, guard_warnings = guarded_definite_integral(
                sym, var, self._to_sympy(lower), self._to_sympy(upper))
        elif isinstance(sym, sp.Integral) and str(var) in {str(lim[0]) for lim in sym.limits}:
            # Evaluating is required: integrating again treated the integral
            # as a constant and fabricated a factor ``var`` (r15 task-07).
            result = sym.doit()
            if result.has(sp.Integral, sp.Derivative):
                return _failed(
                    "integrate: the nested definite integral did not evaluate in "
                    "closed form; pass the inner Integral with explicit lower/upper "
                    "for the outer variable, or add assumptions."
                )
        else:
            result = sp.integrate(sym, var)
        return Expression(
            raw=str(result),
            latex=sp.latex(result),
            sympy_expr=result,
            expr_type=ExpressionType.CALCULUS,
            warnings=guard_warnings if lower is not None and upper is not None else [],
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

        var = resolve_assumed_symbol(variable, self._get_assumptions(variable, context))

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

        subs_dict = {}
        for var_name, value in substitutions.items():
            var = resolve_assumed_symbol(var_name, self._get_assumptions(var_name, context))
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

        diff = sp.simplify(expr1.sympy_expr - expr2.sympy_expr)
        if diff == 0:
            return True

        # Expanding first catches equalities plain simplify misses.
        diff_expanded = sp.simplify(sp.expand(expr1.sympy_expr - expr2.sympy_expr))
        return bool(diff_expanded == 0)

    # Vector Calculus

    def gradient(self, expr: Expression, coords: list[str],
                 context: MathContext | None = None) -> Expression:
        """Gradient of a scalar field.

        The ``{x, y, z}`` coordinates keep the sympy.vector basis form (r13);
        other names give plain partials and a missing coordinate fails by name.
        """
        if not expr.is_valid:
            return expr
        try:
            named = {str(s): s for s in expr.sympy_expr.free_symbols}
            if not all(name in {"x", "y", "z"} for name in coords):
                if missing := [n for n in coords if n not in named]:
                    return _failed(
                        f"gradient: coordinate(s) {', '.join(missing)} are not "
                        f"in the expression; free symbols are {sorted(named)}."
                    )
                partials = [sp.diff(expr.sympy_expr, named[n]) for n in coords]
                result = partials[0] if len(partials) == 1 else sp.Tuple(*partials)
                return Expression(raw=str(result), latex=sp.latex(result),
                                sympy_expr=result, expr_type=ExpressionType.CALCULUS)
            from sympy.vector import CoordSys3D, gradient
            N = CoordSys3D("N")
            basis = [N.x, N.y, N.z]
            # Match by NAME: parsed symbols may carry assumptions (run-017).
            subs_map = {named[n]: basis[coords.index(n)]
                        for n in coords[:3] if n in named}
            result = gradient(expr.sympy_expr.xreplace(subs_map), N)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

    def divergence(self, expr: Expression, coords: list[str],
                   context: MathContext | None = None) -> Expression:
        """Compute divergence of a vector field.

        Comma-separated components like "x*y, z*x, y*z" build the field.
        """
        if not expr.is_valid:
            return expr
        try:
            from sympy.vector import CoordSys3D, divergence
            N = CoordSys3D("N")
            field = _build_vector_field(expr.sympy_expr, coords, N)
            result = divergence(field, N)
            # sympy.vector leaves the scalar result unsimplified (run-017).
            result = sp.simplify(result)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

    def curl(self, expr: Expression, coords: list[str],
             context: MathContext | None = None) -> Expression:
        """Compute curl of a vector field.

        Comma-separated components like "x*y, z*x, y*z" build the field.
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
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

    def laplacian(self, expr: Expression, coords: list[str],
                  context: MathContext | None = None) -> Expression:
        """Compute Laplacian as div(grad(f))."""
        if not expr.is_valid:
            return expr
        try:
            from sympy.vector import CoordSys3D, divergence, gradient
            N = CoordSys3D("N")
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
                # Match by name: ``Symbol('x', positive=True)`` != Symbol('x').
                s = _coord_sub_symbol(s, c, cv)
            grad_field = gradient(s, N)  # returns VectorAdd
            result = divergence(grad_field, N)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

    # Matrix Operations

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
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

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
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

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

    # ODE, Limits, Series

    def dsolve(self, ode: Expression, func: str, var: str,
               context: MathContext | None = None,
               ics: dict[Any, Any] | None = None) -> Expression:
        """Solve an ordinary differential equation.

        ``ics`` maps applied-function points to values, e.g.
        ``{V(0): V_0}``, applied through a bounded constant solve (r18 A1).
        """
        if not ode.is_valid:
            return ode
        try:
            f = sp.Function(func)
            # Match the assumed ``t`` inside the parsed ODE (not a bare Symbol).
            v = resolve_assumed_symbol(var, self._get_assumptions(var, context))
            equation = (
                ode.sympy_expr if isinstance(ode.sympy_expr, sp.Equality)
                else sp.Eq(ode.sympy_expr, 0)
            )
            result, refusal = dsolve_with_ics(equation, f, v, ics)
            if refusal:
                return _failed(f"dsolve: {refusal}")
            if (artifact := dsolve_artifact_reason(equation, result)) is not None:
                return _failed(f"dsolve: {artifact}")
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.EQUATION)
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

    def limit(self, expr: Expression, var: str, point: str,
              direction: str = "+-",
              context: MathContext | None = None) -> Expression:
        """Compute limit of an expression."""
        if not expr.is_valid:
            return expr
        try:
            v = resolve_assumed_symbol(var, self._get_assumptions(var, context))
            p, error = parse_expression_string(point, convert_equation=False)
            if p is None:
                raise ValueError(error or f"cannot parse point '{point}'")
            target = expr.sympy_expr
            if target.has(sp.Derivative, sp.Integral):
                # unevaluated derivatives are not constants (r15 task-01)
                target = target.doit()
                if target.has(sp.Derivative, sp.Integral):
                    return _failed(
                        "limit: expression contains unevaluated derivatives or "
                        "integrals; evaluate them first (e.g. diff/integrate)."
                    )
            if direction == "+":
                result = sp.limit(target, v, p, dir="+")
            elif direction == "-":
                result = sp.limit(target, v, p, dir="-")
            elif p in (sp.oo, -sp.oo):
                result = sp.limit(target, v, p)
            else:
                # "+-" must be a genuine bidirectional limit: SymPy's no-dir
                # default is silently right-handed (``1/x`` at 0 "succeeded"
                # with oo, run-020), so compute both sides.
                right = sp.limit(target, v, p, dir="+")
                left = sp.limit(target, v, p, dir="-")
                same = right == left
                if not same:
                    try:
                        same = bool(sp.simplify(right - left) == 0)
                    except Exception:
                        same = False
                if not same:
                    return _failed(
                        f"Bidirectional limit does not exist: right-hand "
                        f"limit is {right}, left-hand limit is {left}. "
                        "Pass direction='+' or '-' for a one-sided limit."
                    )
                result = right
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

    def series(self, expr: Expression, var: str, point: str,
               order: int | None = 6,
               context: MathContext | None = None) -> Expression:
        """Series expansion; an input already carrying ``O(...)`` is returned as is."""
        if not expr.is_valid:
            return expr
        try:
            v = resolve_assumed_symbol(var, self._get_assumptions(var, context))
            p, error = parse_expression_string(point, convert_equation=False)
            if p is None:
                raise ValueError(error or f"cannot parse point '{point}'")
            result = expr.sympy_expr if expr.sympy_expr.has(sp.Order) else (
                sp.series(expr.sympy_expr, v, p, order) if order is not None
                else sp.series(expr.sympy_expr, v, p))
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.ALGEBRAIC)
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

    # Integral Transforms

    def laplace_transform(self, expr: Expression, time_var: str, freq_var: str,
                          context: MathContext | None = None) -> Expression:
        """Compute Laplace transform."""
        if not expr.is_valid:
            return expr
        try:
            # The transform variable must be the *same* symbol object as in the
            # parsed expression (an assumption-bearing ``Symbol('t',
            # positive=True)`` does not match a plain ``Symbol('t')``), and it
            # must actually be the time-domain symbol.
            t = resolve_assumed_symbol(time_var, self._get_assumptions(time_var, context))
            s = resolve_assumed_symbol(freq_var, self._get_assumptions(freq_var, context))
            free = {str(v) for v in getattr(expr.sympy_expr, "free_symbols", ())}
            if free and time_var not in free:
                return _failed(
                    f"laplace: the expression does not contain '{time_var}'; "
                    "the variable is the time-domain symbol (typically t)"
                )
            # noconds=False keeps SymPy's convergence condition for r23 F8 disclosure.
            result, _abscissa, cond = sp.laplace_transform(expr.sympy_expr, t, s)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS,
                            warnings=laplace_condition_warnings(cond, t, s))
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

    def inverse_laplace_transform(self, expr: Expression, freq_var: str, time_var: str,
                                  context: MathContext | None = None) -> Expression:
        """Compute inverse Laplace transform."""
        if not expr.is_valid:
            return expr
        try:
            s = resolve_assumed_symbol(freq_var, self._get_assumptions(freq_var, context))
            t = resolve_assumed_symbol(time_var, self._get_assumptions(time_var, context))
            free = {str(v) for v in getattr(expr.sympy_expr, "free_symbols", ())}
            if free and freq_var not in free:
                # The wrong symbol made SymPy transform in it and return a
                # Dirac-delta garbage value under ``success: true`` (r20).
                return _failed(
                    f"ilaplace: the expression does not contain '{freq_var}'; "
                    "the variable is the frequency-domain symbol (typically s)"
                )
            result = sp.inverse_laplace_transform(expr.sympy_expr, s, t)
            if result.atoms(sp.nan, sp.zoo):
                # A singular transform must not come back as success carrying
                # nan (r14 task-10: zeta=1 in the underdamped closed form).
                return _failed(
                    "ilaplace: transform is undefined (nan/zoo) for this input; "
                    "the critical-damping case needs a separate limit or "
                    "reduced-denominator form."
                )
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

    def fourier_transform(self, expr: Expression, space_var: str, freq_var: str,
                          context: MathContext | None = None) -> Expression:
        """Compute Fourier transform."""
        if not expr.is_valid:
            return expr
        try:
            x = resolve_assumed_symbol(space_var, self._get_assumptions(space_var, context))
            k = resolve_assumed_symbol(freq_var, self._get_assumptions(freq_var, context))
            result = sp.fourier_transform(expr.sympy_expr, x, k)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

    def inverse_fourier_transform(self, expr: Expression, freq_var: str, space_var: str,
                                  context: MathContext | None = None) -> Expression:
        """Compute inverse Fourier transform."""
        if not expr.is_valid:
            return expr
        try:
            k = resolve_assumed_symbol(freq_var, self._get_assumptions(freq_var, context))
            # ``math()`` defaults ifourier's output variable to ``k``, which can
            # collide with the input variable; inverting in ``k`` and returning
            # ``k`` is degenerate and produced branch-cut constants (task-03).
            out_name = space_var if space_var != freq_var else (
                "k" if freq_var == "x" else "x"
            )
            x = resolve_assumed_symbol(out_name, self._get_assumptions(out_name, context))
            free = {str(s) for s in getattr(expr.sympy_expr, "free_symbols", ())}
            if free and freq_var not in free:
                return _failed(
                    f"ifourier: variable '{freq_var}' is not in the expression; "
                    f"free symbols are {sorted(free)}. Pass the frequency "
                    "variable actually present."
                )
            result = sp.inverse_fourier_transform(expr.sympy_expr, k, x)
            return Expression(raw=str(result), latex=sp.latex(result),
                            sympy_expr=result, expr_type=ExpressionType.CALCULUS)
        except Exception as e:
            return _failed(f"{type(e).__name__}: {e}")

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
