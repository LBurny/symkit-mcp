"""
Basic Verifier Implementation

Concrete implementation of the Verifier interface.
"""

import sympy as sp

from symkit.domain.dimensional_analysis import check_expression_dimensions
from symkit.domain.entities import Derivation, Expression
from symkit.domain.services import Verifier
from symkit.domain.value_objects import MathContext, VerificationResult, VerificationStatus


class BasicVerifier(Verifier):
    """
    Basic implementation of mathematical verification.

    Performs structural and algebraic verification of derivations.
    """

    def verify_step(
        self,
        step_input: Expression,
        step_output: Expression,
        operation: str,
        context: MathContext | None = None,  # noqa: ARG002 - reserved for future use
    ) -> VerificationResult:
        """Verify a single derivation step by checking the operation."""
        if not step_input.is_valid or not step_output.is_valid:
            return VerificationResult.failure(
                "Invalid expression in step",
                input_valid=step_input.is_valid,
                output_valid=step_output.is_valid,
            )

        match operation:
            case "simplify":
                return self._verify_simplification(step_input, step_output)
            case "differentiate":
                return self._verify_differentiation(step_input, step_output)
            case "integrate":
                return self._verify_integration(step_input, step_output)
            case "substitute":
                # Substitution is always valid if expressions are valid
                return VerificationResult.success("Substitution applied")
            case _:
                return VerificationResult(
                    status=VerificationStatus.INCONCLUSIVE,
                    message=f"Unknown operation: {operation}",
                )

    def verify_derivation(
        self,
        derivation: Derivation,
        context: MathContext | None = None,
    ) -> VerificationResult:
        """Verify an entire derivation by checking each step.

        Inconclusive steps (unknown operations, unprovable checks) are
        reported separately from failed ones instead of failing the whole
        derivation.
        """
        if not derivation.steps:
            return VerificationResult.failure("Empty derivation")

        failed_steps: list[int] = []
        inconclusive_steps: list[int] = []

        for step in derivation.steps:
            result = self.verify_step(
                step.input_expr,
                step.output_expr,
                step.operation,
                context,
            )
            if result.status == VerificationStatus.INCONCLUSIVE:
                inconclusive_steps.append(step.step_number)
            elif not result.is_verified:
                failed_steps.append(step.step_number)

        if failed_steps:
            return VerificationResult.failure(
                f"Steps {failed_steps} failed verification",
                failed_steps=failed_steps,
                inconclusive_steps=inconclusive_steps,
            )

        if inconclusive_steps:
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message=f"Steps {inconclusive_steps} could not be verified",
                details={"inconclusive_steps": inconclusive_steps},
            )

        return VerificationResult.success(f"All {len(derivation.steps)} steps verified")

    def check_dimensions(
        self,
        expr: Expression,
        expected_dimension: str | None = None,  # noqa: ARG002 - reserved
        *,
        unit_map: dict[str, str] | None = None,
    ) -> VerificationResult:
        """
        Check dimensional consistency of ``expr`` against ``unit_map``.

        ``unit_map`` maps symbol names to display unit strings (for example
        ``{"rho": "kg/m^3"}``). Without it there is nothing to check against,
        so the result is INCONCLUSIVE with ``dimension_check=None``. With unit
        information, a definite mismatch is FAILED and a coherent expression is
        VERIFIED; symbols lacking units keep the verdict INCONCLUSIVE.
        """
        if not unit_map or expr.sympy_expr is None:
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="No unit information available for dimensional analysis",
                dimension_check=None,
            )
        report = check_expression_dimensions(expr.sympy_expr, unit_map)
        details: dict[str, object] = {}
        if report.issues:
            details["dimension_issues"] = report.issues
        if report.unknown_symbols:
            details["dimension_unknown_symbols"] = report.unknown_symbols
        if report.dimensions:
            details["dimensions"] = report.dimensions

        if report.consistent is False:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                message="Dimensional inconsistency detected",
                details=details,
                dimension_check=False,
            )
        if report.consistent is True:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                message="Dimensions are consistent",
                details=details,
                dimension_check=True,
            )
        return VerificationResult(
            status=VerificationStatus.INCONCLUSIVE,
            message="Dimensions could not be determined for all symbols",
            details=details,
            dimension_check=None,
        )

    def _verify_simplification(
        self,
        input_expr: Expression,
        output_expr: Expression,
    ) -> VerificationResult:
        """Verify that simplification preserves equality."""
        diff = sp.simplify(input_expr.sympy_expr - output_expr.sympy_expr)

        if diff == 0:
            return VerificationResult.success("Simplification verified: expressions are equal")

        # Try harder - expand both and compare
        diff_expanded = sp.simplify(
            sp.expand(input_expr.sympy_expr) - sp.expand(output_expr.sympy_expr)
        )

        if diff_expanded == 0:
            return VerificationResult.success("Simplification verified after expansion")

        return VerificationResult.failure(
            "Simplification changes expression value",
            difference=str(diff),
        )

    @staticmethod
    def _candidate_variables(*exprs: Expression) -> list[sp.Symbol]:
        """Candidate variables: every free symbol, sorted by name.

        Sorting matters: set iteration order varies with PYTHONHASHSEED, and
        picking `list(free_symbols)[0]` made verdicts differ between processes.
        The fallback symbol lets constant-only checks still run.
        """
        symbols: set[sp.Symbol] = set()
        for expr in exprs:
            symbols |= expr.sympy_expr.free_symbols
        return sorted(symbols, key=lambda s: s.name) or [sp.Symbol("x")]

    def _verify_differentiation(
        self,
        input_expr: Expression,
        output_expr: Expression,
    ) -> VerificationResult:
        """
        Verify differentiation by integrating the result.

        Reverse check: if ∫output dvar equals input up to a constant for some
        candidate variable, the differentiation is correct.
        """
        for var in self._candidate_variables(input_expr, output_expr):
            integral = sp.integrate(output_expr.sympy_expr, var)
            diff = sp.simplify(integral - input_expr.sympy_expr)

            # diff must be constant w.r.t. var and carry no other free symbols
            if diff.free_symbols <= {var} and sp.diff(diff, var) == 0:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    message=f"Differentiation verified by reverse integration over {var}",
                    reverse_check=True,
                )

        return VerificationResult(
            status=VerificationStatus.INCONCLUSIVE,
            message="Could not verify differentiation",
            reverse_check=False,
        )

    def _verify_integration(
        self,
        input_expr: Expression,
        output_expr: Expression,
    ) -> VerificationResult:
        """
        Verify integration by differentiating the result.

        If d/dvar(output) = input for some candidate variable, the integration
        is correct.
        """
        derivative: sp.Expr | None = None
        for var in self._candidate_variables(input_expr, output_expr):
            derivative = sp.diff(output_expr.sympy_expr, var)
            if sp.simplify(derivative - input_expr.sympy_expr) == 0:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    message=f"Integration verified by differentiation over {var}",
                    reverse_check=True,
                )

        return VerificationResult.failure(
            "Differentiation of integral does not match original",
            derivative=str(derivative),
            expected=str(input_expr.sympy_expr),
            reverse_check=False,
        )
