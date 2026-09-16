"""Expression-level dimensional consistency checking.

Given a mapping of symbol name to display unit string (for example
``{"rho": "kg/m^3", "v": "m/s"}``), :func:`check_expression_dimensions`
resolves each symbol's base-quantity dimension vector and reports whether the
expression is dimensionally coherent.

The report is deliberately conservative: a symbol without usable unit
information makes the verdict ``None`` (unknown) instead of falsely flagging
the expression as inconsistent.  Only a definite mismatch (for example
``rho + v`` with density and velocity) yields ``consistent=False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sympy as sp

from symkit.domain.units import (
    dimension_dependencies,
    is_dimensionless_marker,
    parse_unit,
)
from symkit.domain.value_objects import VerificationResult, VerificationStatus

# Functions whose arguments must be dimensionless.
_TRANSCENDENTAL: frozenset[str] = frozenset(
    {
        "sin", "cos", "tan", "cot", "sec", "csc",
        "asin", "acos", "atan", "acot", "asec", "acsc",
        "sinh", "cosh", "tanh", "coth", "sech", "csch",
        "asinh", "acosh", "atanh", "acoth",
        "exp", "log", "LambertW", "erf", "erfc", "gamma",
        "digamma", "zeta",
    }
)


@dataclass(frozen=True)
class DimensionReport:
    """Outcome of checking one expression for dimensional consistency."""

    consistent: bool | None
    issues: list[str] = field(default_factory=list)
    unknown_symbols: list[str] = field(default_factory=list)
    dimensions: dict[str, dict[str, int]] = field(default_factory=dict)
    indeterminate_reasons: list[str] = field(default_factory=list)


def check_expression_dimensions(
    expr: sp.Basic,
    unit_map: dict[str, str],
) -> DimensionReport:
    """Check ``expr`` against ``unit_map`` (symbol name -> unit string)."""
    if expr is None:
        return DimensionReport(consistent=None)
    if not unit_map:
        # Nothing to check against, so still no verdict — but name the symbols
        # that would need a declaration. "Which ones do I declare?" is what this
        # response is read for, and an empty list answered nothing.
        bare = _DimensionChecker(unit_map)
        bare.dimension_of(expr)
        return DimensionReport(consistent=None, unknown_symbols=list(bare.unknown_symbols))
    checker = _DimensionChecker(unit_map)
    net = checker.dimension_of(expr)
    if checker.issues:
        consistent: bool | None = False
    elif checker.unknown_symbols or checker.indeterminate:
        consistent = None
    else:
        # A dimensionless *ratio* of two distinct quantities written with
        # different unit strings is the signature of a mis-declared unit, not a
        # coherent cancellation (r15 task-15: L in henry/second, R in ohm).
        conflicts = (
            _cancelling_pairs(expr, checker.dimensions, unit_map) if not net else []
        )
        for symbol_a, symbol_b, unit_a, unit_b in conflicts:
            checker._add_issue(
                "division of distinct quantities with equal dimensions: "
                f"{symbol_a} ({unit_a}) and {symbol_b} ({unit_b}) cancel to "
                "dimensionless; the declared units may be inconsistent"
            )
        consistent = not conflicts
    return DimensionReport(
        consistent=consistent,
        issues=list(checker.issues),
        unknown_symbols=list(checker.unknown_symbols),
        dimensions=dict(checker.dimensions),
        indeterminate_reasons=list(checker.indeterminate_reasons),
    )


def expression_dimension(
    expr: sp.Basic,
    unit_map: dict[str, str],
) -> dict[str, int] | None:
    """Whole-expression dimension vector; ``None`` when undetermined.

    Public wrapper so callers do not reach into ``_DimensionChecker``: ``{}``
    means dimensionless, ``None`` means unknown/undetermined.
    """
    if not unit_map:
        return None
    checker = _DimensionChecker(unit_map)
    try:
        return checker.dimension_of(expr)
    except Exception:
        return None


class _DimensionChecker:
    """Recursive dimension resolver accumulating issues and unknowns."""

    def __init__(self, unit_map: dict[str, str]) -> None:
        self.unit_map = unit_map
        self.issues: list[str] = []
        self.unknown_symbols: list[str] = []
        self.dimensions: dict[str, dict[str, int]] = {}
        self.indeterminate = False
        self.indeterminate_reasons: list[str] = []
        self._symbol_cache: dict[sp.Symbol, dict[str, int] | None] = {}

    # -- dispatch ---------------------------------------------------------

    def dimension_of(self, expr: sp.Basic) -> dict[str, int] | None:
        """Base-quantity dimensions of ``expr``; ``None`` when unknown."""
        if isinstance(expr, sp.MatrixBase):
            # A matrix carries no single dimension vector. A constant matrix is
            # dimensionless; a symbolic one is indeterminate — and neither may
            # crash the caller (``MutableDenseMatrix`` has no ``is_number``).
            if not expr.free_symbols:
                return {}
            self.indeterminate = True
            return None
        if isinstance(expr, sp.Equality):
            return self._dimension_of_equation(expr)
        if isinstance(expr, sp.Derivative):
            return self._dimension_of_derivative(expr)
        if isinstance(expr, sp.Add):
            return self._dimension_of_sum(expr)
        if isinstance(expr, sp.Mul):
            return self._dimension_of_product(expr)
        if isinstance(expr, sp.Pow):
            return self._dimension_of_power(expr)
        if isinstance(expr, sp.Symbol):
            return self._symbol_dimension(expr)
        if isinstance(expr, sp.Function):
            return self._dimension_of_function(expr)
        if isinstance(expr, sp.Number) or getattr(expr, "is_number", False):
            return {}
        if not expr.free_symbols:
            return {}
        self.indeterminate = True
        self._note_reason("unsupported")
        return None

    # -- leaves -----------------------------------------------------------

    def _symbol_dimension(self, symbol: sp.Symbol) -> dict[str, int] | None:
        if symbol in self._symbol_cache:
            return self._symbol_cache[symbol]
        dim = self._resolve_symbol(str(symbol))
        self._symbol_cache[symbol] = dim
        if dim is None:
            self._mark_unknown(str(symbol))
        else:
            self.dimensions[str(symbol)] = dim
        return dim

    def _resolve_symbol(self, name: str) -> dict[str, int] | None:
        raw = self.unit_map.get(name)
        if raw is None:
            return None
        if is_dimensionless_marker(raw):
            return {}
        unit = parse_unit(raw)
        if unit is None:
            return None
        return dimension_dependencies(unit)

    # -- compound nodes ---------------------------------------------------

    def _dimension_of_equation(self, expr: sp.Equality) -> dict[str, int] | None:
        lhs = self.dimension_of(expr.lhs)
        rhs = self.dimension_of(expr.rhs)
        # A literal zero is dimensionally polymorphic: "0" is a valid value for
        # any unit, so an equation normalised to ``Eq(..., 0)`` (e.g. a dsolve
        # step) must not be failed for the zero side's empty vector.
        if _is_literal_zero(expr.lhs) or _is_literal_zero(expr.rhs):
            return lhs if lhs is not None else rhs
        if lhs is not None and rhs is not None and lhs != rhs:
            self._add_issue(
                "equation sides have different dimensions: "
                f"{expr.lhs} ({_describe(lhs)}) vs {expr.rhs} ({_describe(rhs)})"
            )
        return lhs if lhs is not None else rhs

    def _dimension_of_derivative(self, expr: sp.Derivative) -> dict[str, int] | None:
        """dim(dF/dt) = dim(F) / dim(t) for each differentiation variable."""
        base = self.dimension_of(expr.expr)
        if base is None:
            self._note_reason("derivative")
            return None
        total = dict(base)
        for variable in expr.variables:
            var_dim = self.dimension_of(variable)
            if var_dim is None:
                self._note_reason("derivative")
                return None
            _accumulate(total, {name: -power for name, power in var_dim.items()})
        return _drop_zeros(total)

    def _dimension_of_sum(self, expr: sp.Add) -> dict[str, int] | None:
        combined: dict[str, int] | None = None
        first_term: sp.Basic | None = None
        undetermined = False
        for term in expr.args:
            dim = self.dimension_of(term)
            if dim is None:
                # Keep checking the remaining terms (a mismatch between *known*
                # terms is still a definite finding), but the dimension of the
                # whole sum is not determined: reporting a vector built from a
                # subset dropped the un-reducible term, so ``sqrt(m) + s`` came
                # back as ``{time: 1}`` — a determined-looking answer to a
                # question the checker had not answered.
                undetermined = True
                continue
            if combined is None:
                combined, first_term = dim, term
            elif combined != dim:
                self._add_issue(
                    "addition of incompatible dimensions: "
                    f"{first_term} ({_describe(combined)}) vs "
                    f"{term} ({_describe(dim)})"
                )
        if undetermined and not self.issues:
            return None
        return combined

    def _dimension_of_product(self, expr: sp.Mul) -> dict[str, int] | None:
        total: dict[str, int] = {}
        unknown = False
        for factor in expr.args:
            dim = self.dimension_of(factor)
            if dim is None:
                # Keep walking: a later factor can still carry a *definite*
                # inconsistency, and every unresolved symbol must be named.
                # Returning early here made the verdict depend on factor order
                # (``u*(p + v)`` was accepted while ``(p + v)*u`` was failed)
                # and reported one unknown symbol per round trip.
                unknown = True
                continue
            _accumulate(total, dim)
        return None if unknown else _drop_zeros(total)

    def _dimension_of_power(self, expr: sp.Pow) -> dict[str, int] | None:
        base, exponent = expr.args
        base_dim = self.dimension_of(base)
        if base_dim is None:
            return None
        exp_dim = self.dimension_of(exponent)
        if exp_dim is None:
            return None
        if exp_dim:
            self._add_issue(f"exponent of {base} carries dimensions")
            return None
        if not base_dim:
            # A dimensionless base raised to any power stays dimensionless.
            # Engineering correlations rely on this (``Re**0.8``, ``Pr**(1/3)``);
            # demanding a rational exponent here made them all unverifiable.
            return {}
        if not exponent.is_rational:
            self.indeterminate = True
            self._note_reason("non_integer_exponent")
            return None
        scaled = {name: power * sp.Rational(exponent) for name, power in base_dim.items()}
        if any(value.q != 1 for value in scaled.values()):
            self.indeterminate = True
            self._note_reason("non_integer_exponent")
            return None
        return {name: int(value) for name, value in scaled.items() if value != 0}

    def _dimension_of_function(self, expr: sp.Function) -> dict[str, int] | None:
        name = type(expr).__name__
        if name in _TRANSCENDENTAL:
            self._check_dimensionless_args(expr, name)
            return {}
        if name == "Abs" and expr.args:
            return self.dimension_of(expr.args[0])
        # An applied undefined function such as ``x(t)`` carries the dimension
        # of the symbol it is named after (``x``); resolving it is what lets a
        # derivative be reduced from the dependent variable's own unit.
        resolved = self._resolve_symbol(name)
        if resolved is not None:
            return resolved
        self._mark_unknown(name)
        return None

    def _check_dimensionless_args(self, expr: sp.Function, name: str) -> None:
        for arg in expr.args:
            dim = self.dimension_of(arg)
            if dim:  # known and dimensioned
                self._add_issue(
                    f"transcendental function {name} has a dimensioned "
                    f"argument: {arg} ({_describe(dim)})"
                )

    # -- bookkeeping ------------------------------------------------------

    def _mark_unknown(self, name: str) -> None:
        if name not in self.unknown_symbols:
            self.unknown_symbols.append(name)

    def _add_issue(self, issue: str) -> None:
        if issue not in self.issues:
            self.issues.append(issue)

    def _note_reason(self, reason: str) -> None:
        if reason not in self.indeterminate_reasons:
            self.indeterminate_reasons.append(reason)


def _accumulate(total: dict[str, int], dim: dict[str, int]) -> None:
    """Add ``dim`` into ``total`` in place."""
    for name, power in dim.items():
        total[name] = total.get(name, 0) + power


def _drop_zeros(total: dict[str, int]) -> dict[str, int]:
    """Remove base quantities that cancelled out."""
    return {name: power for name, power in total.items() if power != 0}


def _is_literal_zero(expr: sp.Basic) -> bool:
    """True when ``expr`` is known to be exactly zero.

    A zero on one side of an equation is dimensionally polymorphic — ``0``
    volts is as valid as ``0`` metres — so its empty vector must not be
    compared against a dimensioned counterpart.
    """
    if expr.is_zero is True:
        return True
    return isinstance(expr, sp.Number) and expr == 0


def _cancelling_pairs(
    expr: sp.Basic,
    dimensions: dict[str, dict[str, int]],
    unit_map: dict[str, str],
) -> list[tuple[str, str, str, str]]:
    """Distinct symbols whose declared units cancel in a dimensionless ratio.

    ``L`` declared ``henry/second`` and ``R`` declared ``ohm`` share a dimension
    vector, so ``L/R`` collapses to dimensionless — but they are two different
    quantities written with different unit strings. That is the signature of a
    mis-declared unit, not a coherent dimensionless expression (r15 task-15:
    ``henry/second`` is dimensionally ``ohm``). Returns the conflicting
    ``(name_a, name_b, unit_a, unit_b)`` pairs.
    """
    names = sorted(dimensions)
    conflicts: list[tuple[str, str, str, str]] = []
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            dim = dimensions[first]
            if not dim or dim != dimensions[second]:
                continue
            unit_a, unit_b = unit_map.get(first), unit_map.get(second)
            if not unit_a or not unit_b or unit_a == unit_b:
                continue
            # Only a genuine numerator/denominator split, not a symmetric
            # cancellation such as ``L*R/(R*L)``.
            if _net_power(expr, first) * _net_power(expr, second) < 0:
                conflicts.append((first, second, unit_a, unit_b))
    return conflicts


def _net_power(expr: sp.Basic, name: str) -> int:
    """Net integer power of symbol ``name`` in ``expr`` (0 when it cancels)."""
    if isinstance(expr, sp.Symbol):
        return 1 if str(expr) == name else 0
    if isinstance(expr, sp.Pow) and isinstance(expr.exp, sp.Integer):
        return int(expr.exp) * _net_power(expr.base, name)
    if isinstance(expr, sp.Mul):
        return sum(_net_power(arg, name) for arg in expr.args)
    return 0


def describe_dimension(dim: dict[str, int]) -> str:
    """Human-readable rendering of a dimension vector.

    ``{"time": 1}`` becomes ``"time"``; a compound vector becomes
    ``"length*time**-1"``; the empty vector becomes ``"dimensionless"``.
    """
    if not dim:
        return "dimensionless"
    return "*".join(
        name if power == 1 else f"{name}**{power}" for name, power in sorted(dim.items())
    )


def _describe(dim: dict[str, int]) -> str:
    """Human-readable rendering of a dimension vector."""
    if not dim:
        return "dimensionless"
    return "*".join(f"{name}**{power}" for name, power in sorted(dim.items()))


def combine_dimension_reports(reports: list[DimensionReport]) -> DimensionReport:
    """Merge per-expression reports; a definite failure dominates unknowns."""
    issues: list[str] = []
    unknown: list[str] = []
    dimensions: dict[str, dict[str, int]] = {}
    reasons: list[str] = []
    for report in reports:
        issues.extend(issue for issue in report.issues if issue not in issues)
        unknown.extend(
            symbol for symbol in report.unknown_symbols if symbol not in unknown
        )
        dimensions.update(report.dimensions)
        reasons.extend(
            reason
            for reason in report.indeterminate_reasons
            if reason not in reasons
        )
    if any(report.consistent is False for report in reports):
        consistent: bool | None = False
    elif any(report.consistent is None for report in reports):
        consistent = None
    else:
        consistent = True
    return DimensionReport(
        consistent=consistent,
        issues=issues,
        unknown_symbols=unknown,
        dimensions=dimensions,
        indeterminate_reasons=reasons,
    )


def apply_dimension_check(
    result: VerificationResult,
    input_expr: sp.Basic | None,
    output_expr: sp.Basic | None,
    unit_map: dict[str, str],
) -> VerificationResult:
    """Fold dimensional analysis into an algebraic verification result.

    Post-processor kept out of ``step_verifier.py`` (modularity ratchet):
    callers run ``StepVerifier.verify_step`` first, then this when a unit
    map is available. A definite inconsistency fails the step.

    Pass ``None`` for an expression that carries no meaning for this step —
    a manually recorded step asserts a single result, and its archived input
    is the *previous* step's expression, so checking it would judge the wrong
    formula.
    """
    expressions = [
        expr for expr in (input_expr, output_expr) if expr is not None
    ]
    if not expressions:
        return result
    report = combine_dimension_reports(
        [check_expression_dimensions(expr, unit_map) for expr in expressions]
    )
    details = dict(result.details)
    if report.issues:
        details["dimension_issues"] = report.issues
    if report.unknown_symbols:
        details["dimension_unknown_symbols"] = report.unknown_symbols
    if report.dimensions:
        details["dimensions"] = report.dimensions
    if report.consistent is None and report.indeterminate_reasons:
        # Why the check reached no conclusion: "non_integer_exponent" (a
        # fractional-power dimension is not representable) is a different
        # finding from "some symbol has no unit" and must not be reported as
        # the latter (r19 F25).
        details["dimension_indeterminate_reasons"] = list(report.indeterminate_reasons)
    status = result.status
    message = result.message
    if report.consistent is False:
        status = VerificationStatus.FAILED
        message = "Step is dimensionally inconsistent"
    return VerificationResult(
        status=status,
        message=message,
        details=details,
        dimension_check=report.consistent,
        reverse_check=result.reverse_check,
        boundary_check=result.boundary_check,
    )
