"""StepVerifier — Assumption-aware step-level verification engine.

Combines SymPy symbolic verification, reverse-operation verification, and
AssumptionEngine assumption management to provide explainable verification
conclusions for each derivation step in DerivationSession.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import sympy as sp
from sympy.logic.boolalg import BooleanFalse, BooleanTrue

from symkit.domain.assumption_binding import (
    apply_assumptions,
    resolve_assumed_symbol,
)
from symkit.domain.assumption_engine import AssumptionEngine
from symkit.domain.expr_io import evaluated_form, substitution_pairs
from symkit.domain.expression_parser import (
    parse_expression_string,
)
from symkit.domain.symbol_registry import SymbolRegistry
from symkit.domain.value_objects import VerificationResult, VerificationStatus

if TYPE_CHECKING:
    from symkit.domain.derivation_session import DerivationStep


# Numeric residual tolerance for symbolic verification. Symbolic derivation
# diffs are dimensionless algebraic residuals; machine-precision noise from
# float inputs must not flip a correct step to FAILED.
_NUM_ZERO_TOL = 1e-9


def _evaluate_pending(expr: sp.Basic) -> sp.Basic:
    """Evaluate unevaluated operations (``Derivative``/``Integral``/``Sum``).

    A ``simplify`` step whose input is an unevaluated derivative is correct when
    the output is that derivative's value, but ``simplify`` does not reduce the
    difference to zero: SymPy evaluates the ``Derivative`` and then fails to
    apply the trig identity to what is left, so an identically zero residual was
    reported as a changed value and the whole chain became ``failed``
    (task-15 step 12).  ``doit()`` first, and the difference collapses to 0.
    """
    try:
        return expr.doit()
    except Exception:  # pragma: no cover - doit may fail on exotic objects
        return expr


def is_numerically_zero(diff: sp.Basic) -> bool:
    """True if ``diff`` is exactly zero, or numerically zero within tolerance.

    Symbolic differences must simplify to exact zero; purely numeric ones are
    compared in floating point with an absolute tolerance of 1e-9.  Matrix-valued
    differences are checked entrywise: ``Matrix == 0`` is not a Python truth
    value and ``complex(matrix.evalf())`` raises, so a zero-matrix difference was
    reported as changing the expression (2026-09-12 black-box round).  Symbolic
    matrix expressions are expanded first, which also absorbs a stray
    ``Identity`` term.
    """
    if isinstance(diff, sp.MatrixExpr) and not isinstance(diff, sp.MatrixBase):
        diff = diff.as_explicit()
    if isinstance(diff, sp.MatrixBase):
        return all(is_numerically_zero(entry) for entry in diff)
    if diff == 0:
        return True
    if diff.free_symbols:
        return False
    try:
        return abs(complex(diff.evalf())) < _NUM_ZERO_TOL
    except (TypeError, ValueError):
        return False


class StepVerifier:
    """Verify correctness of a single derivation step or the entire derivation chain."""

    def __init__(self, symbol_registry: SymbolRegistry | None = None) -> None:
        self.symbol_registry = symbol_registry

    # ═══════════════════════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════════════════════

    def verify_step(
        self,
        step: DerivationStep,
        prior_expr: sp.Basic | None = None,
        assumption_engine: AssumptionEngine | None = None,
    ) -> VerificationResult:
        """Verify a single derivation step.

        Args:
            step: The step to verify.
            prior_expr: The step's input expression (preferred). If not provided, will try to parse from step.input_expressions.
            assumption_engine: The current session's assumption engine, used for assumption-awareness and conflict detection.

        Returns:
            VerificationResult containing status, message, and details.
        """
        from symkit.domain.derivation_session import OperationType

        assumptions = (
            assumption_engine.get_assumptions() if assumption_engine else {}
        )
        conflicts = (
            assumption_engine.detect_conflicts() if assumption_engine else []
        )

        op = step.operation
        if op == OperationType.CUSTOM:
            return self._inconclusive_with_conflicts(
                "Custom step: no automatic verification available", conflicts
            )

        parsed_input = self._parse_step_input(step, assumptions)
        input_expr = parsed_input if parsed_input is not None else prior_expr
        output_expr = self._parse_archived(
            step.output_expression, step.output_srepr, assumptions
        )

        if input_expr is None or output_expr is None:
            # When input cannot be reconstructed, give INCONCLUSIVE rather than FAILED
            return self._inconclusive_with_conflicts(
                "Cannot parse expressions for verification", conflicts
            )

        warnings = self._collect_warnings(input_expr, output_expr, assumptions)

        if op == OperationType.LOAD_FORMULA:
            result = VerificationResult.success("Formula loaded successfully")
        elif op in (OperationType.SIMPLIFY, OperationType.EXPAND, OperationType.FACTOR):
            result = self._verify_equality(input_expr, output_expr, op.value)
        elif op == OperationType.DIFFERENTIATE:
            result = self._verify_differentiation(step, input_expr, output_expr, assumptions)
        elif op == OperationType.INTEGRATE:
            result = self._verify_integration(step, input_expr, output_expr, assumptions)
        elif op == OperationType.SUBSTITUTE:
            result = self._verify_substitution(step, input_expr, output_expr, assumptions)
        elif op == OperationType.SOLVE:
            result = self._verify_solution(step, input_expr, output_expr, assumptions)
        elif op == OperationType.DSOLVE:
            result = self._verify_dsolve(input_expr, output_expr)
        elif op == OperationType.LIMIT:
            result = self._verify_limit(step, input_expr, output_expr, assumptions)
        elif op == OperationType.EVALF:
            result = self._verify_evalf(input_expr, output_expr)
        else:
            result = VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message=f"Operation '{op.value}' is not yet automatically verifiable",
            )

        # Assumption conflicts weaken the credibility of any verification conclusion
        if conflicts and result.is_verified:
            result = VerificationResult.failure(
                "Step is mathematically consistent but assumptions are contradictory",
                assumption_conflicts=conflicts,
                original_message=result.message,
            )

        details: dict[str, Any] = {}
        if warnings:
            details["warnings"] = warnings
        if conflicts:
            details["assumption_conflicts"] = conflicts
        if details:
            result = VerificationResult(
                status=result.status,
                message=result.message,
                details={**result.details, **details},
                dimension_check=result.dimension_check,
                reverse_check=result.reverse_check,
                boundary_check=result.boundary_check,
            )

        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # Parsing and assumption-awareness
    # ═══════════════════════════════════════════════════════════════════════════

    def _parse(
        self,
        expression: str,
        assumptions: dict[str, dict[str, bool]] | None = None,
    ) -> sp.Basic | None:
        """Parse expression with an assumption-aware symbol table."""
        try:
            local_dict = self._build_symbol_dict(expression, assumptions or {})
            expr, _ = parse_expression_string(
                expression,
                convert_equation=True,
                local_dict=local_dict,
            )
            return expr
        except Exception:
            return None

    def _parse_archived(
        self,
        expression: str,
        srepr_str: str,
        assumptions: dict[str, dict[str, bool]] | None = None,
    ) -> sp.Basic | None:
        """Rebuild an archived expression, preferring the machine-readable srepr.

        The display string does not always round-trip: ``str(E)``/``str(I)``
        re-parse to plain Symbols because the parser protects those names as
        user variables (run-020), and ``str(Symbol('mu_{t}'))`` is not valid
        Python. Re-parsing the display string therefore produced false FAILED
        verdicts (invariant I2). Records written before srepr archiving existed
        have no ``srepr_str`` and fall back to the assumption-aware string
        parse.
        """
        if srepr_str:
            from symkit.domain.expr_io import safe_load_expression

            loaded = safe_load_expression("", srepr_str)
            if loaded is not None:
                return self._apply_assumptions_to_loaded(loaded, assumptions or {})
        return self._parse(expression, assumptions)

    def _apply_assumptions_to_loaded(
        self,
        expr: sp.Basic,
        assumptions: dict[str, dict[str, bool]],
    ) -> sp.Basic:
        """Bind assumptions onto the free symbols of an srepr-loaded object.

        Symbols archived in a step may predate (or omit) the session's current
        assumptions; without this the verifier would compare
        ``Symbol('k', positive=True)`` against a plain ``Symbol('k')`` and
        report a spurious mismatch. Only free symbols are touched, so constants
        such as ``I``/``E`` are never rebound.
        """
        return apply_assumptions(expr, assumptions)

    def _parse_step_input(
        self,
        step: DerivationStep,
        assumptions: dict[str, dict[str, bool]],
    ) -> sp.Basic | None:
        """Reconstruct the input SymPy object from the step's input expressions.

        The archived ``input_srepr`` is authoritative when present (it is the
        live object the operation actually ran on); the string keys below are
        the fallback for legacy records.
        """
        if step.input_srepr:
            loaded = self._parse_archived(
                self._representative_input_string(step),
                step.input_srepr,
                assumptions,
            )
            if loaded is not None:
                return loaded
        # Prefer the "original" key (used by simplify/differentiate/integrate etc.)
        if "original" in step.input_expressions:
            return self._parse(step.input_expressions["original"], assumptions)
        # Use the "equation" key for solve
        if "equation" in step.input_expressions:
            return self._parse(step.input_expressions["equation"], assumptions)
        # For load_formula, take the original input corresponding to the formula_id
        if step.operation.value == "load_formula" and step.input_expressions:
            key = next(iter(step.input_expressions))
            return self._parse(step.input_expressions[key], assumptions)
        # Return None when cannot be reconstructed; caller marks INCONCLUSIVE
        return None

    @staticmethod
    def _representative_input_string(step: DerivationStep) -> str:
        """Display string matching :attr:`DerivationStep.input_srepr`."""
        for key in ("original", "equation"):
            if key in step.input_expressions:
                return step.input_expressions[key]
        if step.input_expressions:
            return next(iter(step.input_expressions.values()))
        return ""

    def _build_symbol_dict(
        self,
        expression: str,
        assumptions: dict[str, dict[str, bool]],
    ) -> dict[str, sp.Symbol]:
        """Symbol table for parsing ``expression`` under ``assumptions``.

        Only names that are free symbols of the expression are bound, and each
        binding goes through :func:`resolve_assumed_symbol` — the single
        constructor shared with the engine and the math dispatcher (invariant
        I3).  Conflicting assumption sets yield a plain Symbol rather than a
        SymPy error.
        """
        # First pass: parse without assumptions, only to collect symbol names
        try:
            first_pass, _ = parse_expression_string(
                expression,
                convert_equation=True,
            )
            names = {str(s) for s in first_pass.free_symbols} if first_pass is not None else set()
        except Exception:
            names = set()

        return {
            name: resolve_assumed_symbol(name, assumptions.get(name, {}))
            for name in names
        }

    def _assumed_symbol(
        self, name: str, assumptions: dict[str, dict[str, bool]]
    ) -> sp.Symbol:
        """Build ``name`` as a Symbol carrying the same assumptions used to
        parse the step input, so ``subs`` actually matches the input symbols
        (a bare ``sp.Symbol(name)`` is a different object when assumptions
        apply and the substitution silently becomes a no-op)."""
        return resolve_assumed_symbol(name, assumptions.get(name, {}))

    # ═══════════════════════════════════════════════════════════════════════════
    # Operation-level verification
    # ═══════════════════════════════════════════════════════════════════════════

    def _verify_equality(
        self,
        input_expr: sp.Basic,
        output_expr: sp.Basic,
        operation: str,
    ) -> VerificationResult:
        """Verify that simplify/expand/factor preserves the expression value."""
        out_bool = self._boolean_value(output_expr)
        if out_bool is not None:
            # simplify may resolve an input equation to a plain True/False
            # (Python bool, not BooleanTrue) when the caller's assumptions make
            # it decidable.  The verifier often cannot see those per-call
            # assumptions, so treat an unconfirmable boolean claim as
            # INCONCLUSIVE rather than crashing or false-failing (run-008).
            if isinstance(input_expr, sp.Equality):
                diff = sp.simplify(input_expr.lhs - input_expr.rhs)
                if is_numerically_zero(diff):
                    return VerificationResult.success(
                        f"{operation.capitalize()} verified: expression is an identity"
                    )
                return VerificationResult(
                    status=VerificationStatus.INCONCLUSIVE,
                    message=(
                        f"{operation} returned True; the identity holds under "
                        "assumptions the verifier cannot confirm"
                    ),
                )
            in_bool = self._boolean_value(input_expr)
            if in_bool is not None:
                # Under session assumptions the parser itself may collapse an
                # Eq to a boolean before recording (run-016): input True →
                # output True is trivially value-preserving; a flip is a bug.
                if in_bool == out_bool:
                    return VerificationResult.success(
                        f"{operation.capitalize()} verified: boolean value preserved"
                    )
                return VerificationResult.failure(
                    f"{operation.capitalize()} changed the boolean value",
                    input=str(input_expr),
                    output=str(output_expr),
                )
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message=f"{operation} returned boolean output; no automatic check",
            )

        diff = sp.simplify(
            self._difference(
                _evaluate_pending(input_expr), _evaluate_pending(output_expr)
            )
        )
        if is_numerically_zero(diff):
            return VerificationResult.success(
                f"{operation.capitalize()} verified: expressions are equal"
            )

        # Try comparing after expansion
        diff_expanded = sp.simplify(
            sp.expand(self._difference(input_expr, output_expr))
        )
        if is_numerically_zero(diff_expanded):
            return VerificationResult.success(
                f"{operation.capitalize()} verified after expansion"
            )

        return VerificationResult.failure(
            f"{operation.capitalize()} changes expression value",
            difference=str(diff),
        )

    def _verify_differentiation(
        self,
        step: DerivationStep,
        input_expr: sp.Basic,
        output_expr: sp.Basic,
        _assumptions: dict[str, dict[str, bool]],
    ) -> VerificationResult:
        """Verify differentiation by reverse integration."""
        var = self._extract_variable_from_command(step.sympy_command, "differentiate")
        if var is None:
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Could not determine differentiation variable",
            )

        var_sym = sp.Symbol(var)
        # No free-symbol shortcut here: `diff(2*x, x) = 2` has a constant
        # output and is correct. Reverse integration below handles both that
        # and `diff(5, x) = 0` — integrating 2 gives 2*x, integrating 0 gives a
        # constant — so deciding from "output has no free symbols" was simply
        # wrong and rejected correct steps (2026-09-12 black-box round).

        # Reverse integration, repeated for each differentiation order:
        # integrating `2` once recovers `2*x`, twice recovers `x**2`.
        integral = output_expr
        for _ in range(self._extract_order_from_command(step.sympy_command)):
            integral = sp.integrate(integral, var_sym)
        diff = sp.simplify(integral - input_expr)
        if diff.free_symbols <= {var_sym} and is_numerically_zero(
            sp.diff(diff, var_sym)
        ):
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                message="Differentiation verified by reverse integration",
                reverse_check=True,
            )

        return VerificationResult(
            status=VerificationStatus.INCONCLUSIVE,
            message="Could not verify differentiation by reverse integration",
            reverse_check=False,
        )

    def _verify_integration(
        self,
        step: DerivationStep,
        input_expr: sp.Basic,
        output_expr: sp.Basic,
        assumptions: dict[str, dict[str, bool]],
    ) -> VerificationResult:
        """Verify integration: reverse differentiation for indefinite integrals,
        numeric quadrature for definite ones."""
        definite = re.search(
            r"integrate\(expr,\s*\(\s*(\w+)\s*,\s*([^,]+),\s*([^)]+)\)",
            step.sympy_command,
        )
        if definite:
            return self._verify_definite_integration(
                definite, input_expr, output_expr, assumptions
            )

        var = self._extract_variable_from_command(step.sympy_command, "integrate")
        if var is None:
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Could not determine integration variable",
            )

        var_sym = sp.Symbol(var)
        derivative = sp.diff(output_expr, var_sym)
        diff = sp.simplify(derivative - input_expr)
        if is_numerically_zero(diff):
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                message="Integration verified by differentiation",
                reverse_check=True,
            )

        return VerificationResult.failure(
            "Differentiation of integral does not match original",
            derivative=str(derivative),
            expected=str(input_expr),
            reverse_check=False,
        )

    def _verify_definite_integration(
        self,
        match: re.Match[str],
        input_expr: sp.Basic,
        output_expr: sp.Basic,
        assumptions: dict[str, dict[str, bool]],
    ) -> VerificationResult:
        """Verify a definite integral by numeric quadrature with valued parameters.

        Reverse differentiation is meaningless here: the result no longer
        depends on the integration variable, so d/dx of a correct constant
        result is 0 and the indefinite check false-FAILED correct work
        (run-011's Maxwell-Boltzmann moment).  Parameters are valued with
        small primes (same policy as limit verification); disagreement yields
        INCONCLUSIVE, never FAILED — quadrature of improper or oscillatory
        integrals can legitimately mislead, and FAILED is reserved for
        symbolic proof of error.
        """
        var = self._assumed_symbol(match.group(1), assumptions)
        lo = self._parse(match.group(2).strip(), assumptions)
        hi = self._parse(match.group(3).strip(), assumptions)
        if lo is None or hi is None:
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Could not parse integration bounds",
            )
        others = [
            s
            for s in (input_expr.free_symbols | output_expr.free_symbols)
            if str(s) != str(var)
        ]
        primes = [2, 3, 5, 7, 11, 13]
        valuation = {s: sp.Integer(primes[i % len(primes)]) for i, s in enumerate(others)}
        try:
            quadrature = sp.Integral(input_expr, (var, lo, hi)).subs(valuation)
            expected = complex(sp.N(quadrature, 20))
            actual = complex(sp.N(output_expr.subs(valuation), 20))
        except (TypeError, ValueError):
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Numeric quadrature not possible for definite integral",
            )
        tol = 1e-6 * max(1.0, abs(expected))
        if abs(expected - actual) < tol:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                message="Definite integral verified by numeric quadrature",
                reverse_check=True,
            )
        return VerificationResult(
            status=VerificationStatus.INCONCLUSIVE,
            message="Numeric quadrature disagrees with the stated "
            "definite-integral result",
        )

    def _verify_substitution(
        self,
        step: DerivationStep,
        input_expr: sp.Basic,
        output_expr: sp.Basic,
        assumptions: dict[str, dict[str, bool]],
    ) -> VerificationResult:
        """Verify substitution operation."""
        pairs = substitution_pairs(step.input_expressions)
        if pairs is None:
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Could not parse substitution mapping",
            )

        expected = input_expr
        applied = False
        for key_str, value_str in pairs:
            if re.fullmatch(r"\w+", key_str):
                target_sym: sp.Basic = self._assumed_symbol(key_str, assumptions)
            else:
                # Non-identifier keys (e.g. ``x**2`` or ``Derivative(f(x), x)``)
                parsed_key = self._parse(key_str, assumptions)
                if parsed_key is None:
                    return VerificationResult(
                        status=VerificationStatus.INCONCLUSIVE,
                        message="Could not parse substitution key",
                    )
                target_sym = evaluated_form(parsed_key)
            replacement_expr = self._parse(value_str, assumptions)
            if replacement_expr is None:
                return VerificationResult(
                    status=VerificationStatus.INCONCLUSIVE,
                    message="Could not parse replacement expression",
                )
            before = expected
            expected = expected.subs(target_sym, replacement_expr)
            applied = applied or expected != before

        if not applied:
            # Every key is absent from the input, so nothing was substituted and
            # there is nothing to compare. Saying "verified" here inflated the
            # verified count with steps that did no work.
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Substitution keys do not occur in the input expression",
            )

        diff = sp.simplify(self._difference(expected, output_expr))
        if is_numerically_zero(diff):
            return VerificationResult.success("Substitution verified")

        return VerificationResult.failure(
            "Substitution result does not match expected expression",
            expected=str(expected),
            actual=str(output_expr),
        )

    def _verify_solution(
        self,
        _step: DerivationStep,
        input_expr: sp.Basic,
        output_expr: sp.Basic,
        _assumptions: dict[str, dict[str, bool]],
    ) -> VerificationResult:
        """Verify that the solution satisfies the original equation."""
        if not isinstance(output_expr, sp.Equality):
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Solver output is not an equality",
            )

        var_sym = output_expr.lhs
        solution = output_expr.rhs
        expected = input_expr.subs(var_sym, solution)
        # Substituting a valid solution into the equation may reduce to a
        # SymPy or Python boolean.  A tautology means the solution is verified.
        if expected is True or isinstance(expected, BooleanTrue):
            return VerificationResult.success(
                "Solution verified by substitution back into original equation"
            )
        if expected is False or isinstance(expected, BooleanFalse):
            return VerificationResult.failure(
                "Solution does not satisfy the original equation",
                residual=str(expected),
            )
        diff = sp.simplify(self._difference(expected, sp.Integer(0)))
        if is_numerically_zero(diff):
            return VerificationResult.success(
                "Solution verified by substitution back into original equation"
            )

        return VerificationResult.failure(
            "Solution does not satisfy the original equation",
            residual=str(diff),
        )

    def _verify_dsolve(
        self, input_expr: sp.Basic, output_expr: sp.Basic
    ) -> VerificationResult:
        """Verify an ODE solution by substituting it back into the equation."""
        if not isinstance(input_expr, sp.Equality) or not isinstance(
            output_expr, sp.Equality
        ):
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="dsolve input/output are not both equations",
            )
        try:
            ok, residual = sp.checkodesol(input_expr, output_expr)
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message=f"checkodesol could not run: {type(e).__name__}",
            )
        if ok:
            return VerificationResult.success(
                "ODE solution verified by substitution (checkodesol)",
            )
        return VerificationResult.failure(
            "ODE solution does not satisfy the equation",
            residual=str(residual),
        )

    def _verify_evalf(
        self, input_expr: sp.Basic, output_expr: sp.Basic
    ) -> VerificationResult:
        """Verify numeric evaluation by independent re-evaluation."""
        try:
            expected = complex(sp.N(input_expr, 20))
            actual = complex(sp.N(output_expr, 20))
        except (TypeError, ValueError):
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="evalf input/output is not purely numeric",
            )
        tol = 1e-12 * max(1.0, abs(expected))
        if abs(expected - actual) < tol:
            return VerificationResult.success("Numeric evaluation verified")
        return VerificationResult.failure(
            "Numeric evaluation mismatch",
            expected=str(expected),
            actual=str(actual),
        )

    def _verify_limit(
        self,
        step: DerivationStep,
        input_expr: sp.Basic,
        output_expr: sp.Basic,
        assumptions: dict[str, dict[str, bool]],
    ) -> VerificationResult:
        """Verify a limit by numeric spot-checks near the point.

        A disagreeing probe yields INCONCLUSIVE rather than FAILED: numeric
        probing can legitimately disagree for slowly-converging limits, and
        FAILED is reserved for symbolic proof of error.
        """
        match = re.search(r"limit\(expr,\s*(\w+),\s*([^)]+)\)", step.sympy_command)
        if not match:
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Could not determine limit variable/point",
            )
        var = self._assumed_symbol(match.group(1), assumptions)
        point_expr = self._parse(match.group(2).strip(), assumptions)
        if point_expr is None:
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Could not parse limit point",
            )
        others = [s for s in input_expr.free_symbols if s != var]
        # Deterministic small-prime valuation for unrelated symbols.
        primes = [2, 3, 5, 7, 11, 13]
        valuation = {s: sp.Integer(primes[i % len(primes)]) for i, s in enumerate(others)}
        # Probe only the side the user asked for. Probing both sides of a
        # correct one-sided limit always disagrees on the other side, which
        # reported INCONCLUSIVE with no hint that the answer was right (P5).
        direction = step.input_expressions.get("limit_direction", "+-")

        def _disagree() -> VerificationResult:
            if direction in ("+", "-"):
                side = "right" if direction == "+" else "left"
                return VerificationResult(
                    status=VerificationStatus.INCONCLUSIVE,
                    message=(
                        f"Numeric spot-check disagrees with the {side}-sided "
                        "limit (or it converges too slowly to probe)"
                    ),
                )
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message=(
                    "Numeric spot-check disagrees with the two-sided limit (or "
                    "it converges too slowly to probe). If you meant a "
                    "one-sided limit, pass direction='+' or '-'."
                ),
            )

        try:
            if point_expr == sp.oo:
                probes = [sp.Integer(10**4), sp.Integer(10**5)]
            elif point_expr == -sp.oo:
                probes = [sp.Integer(-10**4), sp.Integer(-10**5)]
            else:
                eps = sp.Rational(1, 10**4)
                if direction == "+":
                    probes = [point_expr + eps]
                elif direction == "-":
                    probes = [point_expr - eps]
                else:
                    probes = [point_expr + eps, point_expr - eps]

            expected_expr = output_expr.subs(valuation)
            # An infinite limit is checked by magnitude growth and sign: the
            # tolerance comparison degenerates for infinities (``inf < inf`` is
            # False), so every correct infinite limit used to look wrong.
            infinite = bool(getattr(expected_expr, "is_infinite", False))
            expected: complex = complex(0) if infinite else complex(sp.N(expected_expr))
            sign = float(sp.sign(expected_expr)) if infinite else 0.0

            for p in probes:
                value = complex(sp.N(input_expr.subs(valuation).subs(var, p)))
                if infinite:
                    if not (abs(value) > 1e3 and value.real * sign > 0):
                        return _disagree()
                elif not (abs(value - expected) < 1e-3 * max(1.0, abs(expected))):
                    return _disagree()
            return VerificationResult.success(
                "Limit verified by numeric spot-check near the point"
            )
        except (TypeError, ValueError, OverflowError):
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Numeric spot-check not possible",
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════════

    def _boolean_value(self, value: sp.Basic) -> bool | None:
        """Return the truth value of boolean-looking outputs (plain or SymPy)."""
        if isinstance(value, (BooleanTrue, BooleanFalse, bool)):
            return bool(value)
        return None

    def _difference(self, left: sp.Basic, right: sp.Basic) -> sp.Basic:
        """For equations compare lhs - rhs; for ordinary expressions compare left - right."""
        left_bool = self._boolean_value(left)
        right_bool = self._boolean_value(right)
        if isinstance(left, sp.Equality) and isinstance(right, sp.Equality):
            return (left.lhs - left.rhs) - (right.lhs - right.rhs)
        if isinstance(left, sp.Equality):
            if right_bool is not None:
                # SymPy may simplify an identity/contradiction equation to True/False
                return sp.Integer(0) if right_bool else sp.Integer(1)
            return left.lhs - left.rhs - right
        if isinstance(right, sp.Equality):
            if left_bool is not None:
                return sp.Integer(0) if left_bool else sp.Integer(1)
            return left - (right.lhs - right.rhs)
        return left - right

    def _extract_variable_from_command(
        self, command: str, operation: str
    ) -> str | None:
        """Extract the operation variable from sympy_command."""
        if operation == "differentiate":
            # diff(expr, x, 2) or diff(expr, x)
            match = re.search(r"diff\(expr,\s*(\w+)(?:,\s*\d+)?\)", command)
            return match.group(1) if match else None
        if operation == "integrate":
            # integrate(expr, x) or integrate(expr, (x, 0, 1))
            match = re.search(r"integrate\(expr,\s*(?:\(\s*)?(\w+)", command)
            return match.group(1) if match else None
        return None

    @staticmethod
    def _extract_order_from_command(command: str) -> int:
        """The differentiation order in ``diff(expr, x, 2)``; 1 when omitted."""
        match = re.search(r"diff\(expr,\s*\w+\s*,\s*(\d+)\s*\)", command)
        return int(match.group(1)) if match else 1

    def _collect_warnings(
        self,
        _input_expr: sp.Basic,
        output_expr: sp.Basic,
        _assumptions: dict[str, dict[str, bool]],
    ) -> list[str]:
        """Collect lightweight sanity warnings."""
        warnings: list[str] = []
        expr_str = str(output_expr)

        # The argument of exp should be dimensionless (the framework currently cannot do full dimensional analysis, so this is only a hint)
        if "exp(" in expr_str:
            warnings.append(
                "Expression contains exp(...). Ensure the argument is dimensionless."
            )
        if "log(" in expr_str:
            warnings.append(
                "Expression contains log(...). Ensure the argument is positive in the domain."
            )
        if "/" in expr_str or "**(-1" in expr_str:
            warnings.append(
                "Expression contains division. Ensure denominators cannot be zero."
            )

        return warnings

    def _inconclusive_with_conflicts(
        self, message: str, conflicts: list[dict[str, Any]]
    ) -> VerificationResult:
        """Return an INCONCLUSIVE result with assumption conflict information."""
        details: dict[str, Any] = {}
        if conflicts:
            details["assumption_conflicts"] = conflicts
        return VerificationResult(
            status=VerificationStatus.INCONCLUSIVE,
            message=message,
            details=details,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Serialization helpers
# ═══════════════════════════════════════════════════════════════════════════════


def verification_result_to_json(result: VerificationResult) -> str:
    """Serialize VerificationResult to a JSON string storable in DerivationStep."""
    return json.dumps(
        {
            "status": result.status.value,
            "message": result.message,
            "details": result.details,
            "dimension_check": result.dimension_check,
            "reverse_check": result.reverse_check,
            "boundary_check": result.boundary_check,
            "is_verified": result.is_verified,
        },
        ensure_ascii=False,
    )


def verification_result_from_json(data: str) -> VerificationResult:
    """Restore VerificationResult from a JSON string."""
    parsed = json.loads(data)
    return VerificationResult(
        status=VerificationStatus(parsed.get("status", "inconclusive")),
        message=parsed.get("message", ""),
        details=parsed.get("details", {}),
        dimension_check=parsed.get("dimension_check"),
        reverse_check=parsed.get("reverse_check"),
        boundary_check=parsed.get("boundary_check"),
    )
