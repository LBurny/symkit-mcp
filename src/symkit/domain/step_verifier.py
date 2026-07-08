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

from symkit.domain.assumption_engine import AssumptionEngine
from symkit.domain.expression_parser import (
    parse_expression_string,
)
from symkit.domain.symbol_registry import SymbolRegistry
from symkit.domain.value_objects import VerificationResult, VerificationStatus

if TYPE_CHECKING:
    from symkit.domain.derivation_session import DerivationStep


# Whitelist of symbol properties recognizable by SymPy (used for parse_expr local_dict)
_ASSUMPTION_KEYWORDS: set[str] = {
    "real",
    "imaginary",
    "complex",
    "positive",
    "negative",
    "nonzero",
    "nonpositive",
    "nonnegative",
    "integer",
    "rational",
    "irrational",
    "finite",
    "infinite",
    "odd",
    "even",
    "prime",
    "composite",
    "extended_real",
    "extended_positive",
    "extended_negative",
    "extended_nonpositive",
    "extended_nonnegative",
    "commutative",
    "hermitian",
    "antihermitian",
}

# Conflicting property pairs: cannot both be passed as symbol assumptions to SymPy
_CONFLICT_PAIRS: set[tuple[str, str]] = {
    ("positive", "negative"),
    ("positive", "zero"),
    ("negative", "zero"),
    ("real", "imaginary"),
    ("integer", "irrational"),
}


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
        output_expr = self._parse(step.output_expression, assumptions)

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

    def _parse_step_input(
        self,
        step: DerivationStep,
        assumptions: dict[str, dict[str, bool]],
    ) -> sp.Basic | None:
        """Reconstruct the input SymPy object from the step's input expressions."""
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

    def _build_symbol_dict(
        self,
        expression: str,
        assumptions: dict[str, dict[str, bool]],
    ) -> dict[str, sp.Symbol]:
        """Construct a SymPy Symbol mapping with assumptions for free symbols in the expression.

        If active assumptions for a symbol conflict, ignore all assumptions for that symbol
        to avoid SymPy raising contradictory-assumption errors when creating the Symbol.
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

        local_dict: dict[str, sp.Symbol] = {}
        for name in names:
            props = assumptions.get(name, {})
            active = {p for p, v in props.items() if v and p in _ASSUMPTION_KEYWORDS}
            has_conflict = any(
                a in active and b in active for a, b in _CONFLICT_PAIRS
            )
            kwargs = (
                {}
                if has_conflict
                else {
                    prop: True
                    for prop in props
                    if prop in _ASSUMPTION_KEYWORDS
                }
            )
            local_dict[name] = sp.Symbol(name, **kwargs)
        return local_dict

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
        diff = sp.simplify(self._difference(input_expr, output_expr))
        if diff == 0:
            return VerificationResult.success(
                f"{operation.capitalize()} verified: expressions are equal"
            )

        # Try comparing after expansion
        diff_expanded = sp.simplify(
            sp.expand(self._difference(input_expr, output_expr))
        )
        if diff_expanded == 0:
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
        # If the output has no free symbols, it should be 0
        if not output_expr.free_symbols:
            if output_expr == 0:
                return VerificationResult.success("Derivative of constant is 0")
            return VerificationResult.failure("Non-zero derivative of constant")

        # Reverse integration
        integral = sp.integrate(output_expr, var_sym)
        diff = sp.simplify(integral - input_expr)
        if diff.free_symbols <= {var_sym} and sp.diff(diff, var_sym) == 0:
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
        _assumptions: dict[str, dict[str, bool]],
    ) -> VerificationResult:
        """Verify integration by reverse differentiation."""
        var = self._extract_variable_from_command(step.sympy_command, "integrate")
        if var is None:
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Could not determine integration variable",
            )

        var_sym = sp.Symbol(var)
        derivative = sp.diff(output_expr, var_sym)
        diff = sp.simplify(derivative - input_expr)
        if diff == 0:
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

    def _verify_substitution(
        self,
        step: DerivationStep,
        input_expr: sp.Basic,
        output_expr: sp.Basic,
        assumptions: dict[str, dict[str, bool]],
    ) -> VerificationResult:
        """Verify substitution operation."""
        replacement_str = step.input_expressions.get("replacement", "")
        if not replacement_str:
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Could not parse substitution mapping",
            )

        expected = input_expr
        for part in replacement_str.split(","):
            match = re.match(r"^(\w+)\s*=\s*(.+)$", part.strip())
            if not match:
                return VerificationResult(
                    status=VerificationStatus.INCONCLUSIVE,
                    message="Could not parse substitution mapping",
                )
            target_var = match.group(1)
            replacement_expr_str = match.group(2)
            target_sym = sp.Symbol(target_var)
            replacement_expr = self._parse(replacement_expr_str, assumptions)
            if replacement_expr is None:
                return VerificationResult(
                    status=VerificationStatus.INCONCLUSIVE,
                    message="Could not parse replacement expression",
                )
            expected = expected.subs(target_sym, replacement_expr)

        diff = sp.simplify(self._difference(expected, output_expr))
        if diff == 0:
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
        if diff == 0:
            return VerificationResult.success(
                "Solution verified by substitution back into original equation"
            )

        return VerificationResult.failure(
            "Solution does not satisfy the original equation",
            residual=str(diff),
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════════

    def _difference(self, left: sp.Basic, right: sp.Basic) -> sp.Basic:
        """For equations compare lhs - rhs; for ordinary expressions compare left - right."""
        if isinstance(left, sp.Equality) and isinstance(right, sp.Equality):
            return (left.lhs - left.rhs) - (right.lhs - right.rhs)
        if isinstance(left, sp.Equality):
            if isinstance(right, (BooleanTrue, BooleanFalse)):
                # SymPy may simplify an identity/contradiction equation to True/False
                return sp.Integer(0) if bool(right) else sp.Integer(1)
            return left.lhs - left.rhs - right
        if isinstance(right, sp.Equality):
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
