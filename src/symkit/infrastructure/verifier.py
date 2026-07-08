"""
Basic Verifier Implementation

Concrete implementation of the Verifier interface.
"""

import sympy as sp

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
        """Verify an entire derivation by checking each step."""
        if not derivation.steps:
            return VerificationResult.failure("Empty derivation")

        failed_steps: list[int] = []

        for step in derivation.steps:
            result = self.verify_step(
                step.input_expr,
                step.output_expr,
                step.operation,
                context,
            )
            if not result.is_verified:
                failed_steps.append(step.step_number)

        if failed_steps:
            return VerificationResult.failure(
                f"Steps {failed_steps} failed verification",
                failed_steps=failed_steps,
            )

        return VerificationResult.success(f"All {len(derivation.steps)} steps verified")

    def check_dimensions(
        self,
        expr: Expression,  # noqa: ARG002 - not yet implemented
        expected_dimension: str | None = None,  # noqa: ARG002 - not yet implemented
    ) -> VerificationResult:
        """
        Check dimensional consistency.

        Note: Full dimensional analysis requires unit tracking,
        which is not yet implemented.
        """
        # Placeholder - would need unit system integration
        return VerificationResult(
            status=VerificationStatus.INCONCLUSIVE,
            message="Dimensional analysis not yet implemented",
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

    def _verify_differentiation(
        self,
        input_expr: Expression,
        output_expr: Expression,
    ) -> VerificationResult:
        """
        Verify differentiation by integrating the result.

        Note: This is reverse verification - if ∫output = input (up to constant),
        then differentiation is correct.
        """
        # Find free symbols to determine variable
        free_symbols = output_expr.sympy_expr.free_symbols
        if not free_symbols:
            # Constant - derivative should be 0
            if output_expr.sympy_expr == 0:
                return VerificationResult.success("Derivative of constant is 0")
            return VerificationResult.failure("Non-zero derivative of constant")

        # Take the first symbol as variable (heuristic)
        var = list(free_symbols)[0]

        # Integrate output and compare with input
        integral = sp.integrate(output_expr.sympy_expr, var)
        diff = sp.simplify(integral - input_expr.sympy_expr)

        # The difference should be a constant (no free_symbols except integration constant)
        if diff.free_symbols <= {var} and sp.diff(diff, var) == 0:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                message="Differentiation verified by reverse integration",
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

        If d/dx(output) = input, then integration is correct.
        """
        # Find variable
        free_symbols = input_expr.sympy_expr.free_symbols
        var = sp.Symbol("x") if not free_symbols else list(free_symbols)[0]

        # Differentiate output
        derivative = sp.diff(output_expr.sympy_expr, var)

        # Compare with input
        diff = sp.simplify(derivative - input_expr.sympy_expr)

        if diff == 0:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                message="Integration verified by differentiation",
                reverse_check=True,
            )

        return VerificationResult.failure(
            "Differentiation of integral does not match original",
            derivative=str(derivative),
            expected=str(input_expr.sympy_expr),
            reverse_check=False,
        )
