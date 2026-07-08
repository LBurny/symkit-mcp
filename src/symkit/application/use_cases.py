"""
SymKit Application Use Cases

Use cases implement application-specific business rules.
They orchestrate the flow of data to and from entities,
and direct those entities to use their domain logic.
"""

from dataclasses import dataclass
from typing import Any

from symkit.domain.entities import Derivation, DerivationStep, Expression
from symkit.domain.services import SymbolicEngine, Verifier
from symkit.domain.value_objects import (
    CalculationResult,
    MathContext,
    VerificationResult,
)


@dataclass
class CalculateUseCase:
    """
    Use case for performing symbolic calculations.

    Handles: simplification, evaluation, basic operations.
    """

    engine: SymbolicEngine

    def execute(
        self,
        expression: str,
        operation: str = "simplify",
        context: MathContext | None = None,
        **kwargs: Any,
    ) -> CalculationResult:
        """
        Execute a calculation operation.

        Args:
            expression: Mathematical expression as string
            operation: Operation to perform (simplify, evaluate, expand, factor)
            context: Mathematical context for the operation
            **kwargs: Additional operation-specific arguments

        Returns:
            CalculationResult with the result or error
        """
        import time

        start = time.perf_counter()

        try:
            # Parse expression
            expr = self.engine.parse(expression, context)
            if not expr.is_valid:
                return CalculationResult.from_error(f"Failed to parse: {expression}")

            # Perform operation
            match operation:
                case "simplify":
                    result_expr = self.engine.simplify(expr, context)
                case "evaluate":
                    result_expr = self._evaluate(expr, context, **kwargs)
                case _:
                    return CalculationResult.from_error(f"Unknown operation: {operation}")

            elapsed = (time.perf_counter() - start) * 1000

            return CalculationResult(
                success=True,
                result=result_expr.raw,
                latex=result_expr.latex,
                computation_time_ms=elapsed,
            )

        except Exception as e:
            return CalculationResult.from_error(str(e))

    def _evaluate(self, expr: Expression, context: MathContext | None, **kwargs: Any) -> Expression:
        """Evaluate expression with substitutions."""
        if "substitutions" in kwargs:
            return self.engine.substitute(expr, kwargs["substitutions"], context)
        return self.engine.simplify(expr, context)


@dataclass
class SimplifyUseCase:
    """
    Use case for expression simplification.

    Provides various simplification strategies.
    """

    engine: SymbolicEngine

    def execute(
        self,
        expression: str,
        strategy: str = "default",  # noqa: ARG002 - reserved for future use
        context: MathContext | None = None,
    ) -> CalculationResult:
        """
        Simplify an expression.

        Args:
            expression: Expression to simplify
            strategy: Simplification strategy (default, trigonometric, radical)
            context: Mathematical context

        Returns:
            CalculationResult with simplified expression
        """
        try:
            expr = self.engine.parse(expression, context)
            if not expr.is_valid:
                return CalculationResult.from_error(f"Failed to parse: {expression}")

            result = self.engine.simplify(expr, context)

            return CalculationResult(
                success=True,
                result=result.raw,
                latex=result.latex,
            )
        except Exception as e:
            return CalculationResult.from_error(str(e))


@dataclass
class DeriveUseCase:
    """
    Use case for mathematical derivations.

    Handles multi-step derivations with step tracking.
    """

    engine: SymbolicEngine
    verifier: Verifier | None = None

    def execute(
        self,
        goal: str,
        premises: list[str],
        steps: list[dict[str, Any]],
        context: MathContext | None = None,
        verify: bool = True,
    ) -> Derivation:
        """
        Execute a derivation.

        Args:
            goal: What we're trying to derive
            premises: Starting expressions
            steps: List of derivation steps to execute
            context: Mathematical context
            verify: Whether to verify each step

        Returns:
            Derivation object with results
        """
        derivation = Derivation(goal=goal)

        # Parse premises
        for premise_str in premises:
            expr = self.engine.parse(premise_str, context)
            derivation.premises.append(expr)

        # Execute steps
        current_expr = derivation.premises[-1] if derivation.premises else None

        for i, step_def in enumerate(steps, 1):
            operation = step_def.get("operation", "simplify")

            if current_expr is None:
                break

            # Execute the step
            result_expr = self._execute_step(current_expr, operation, step_def, context)

            step = DerivationStep(
                step_number=i,
                operation=operation,
                input_expr=current_expr,
                output_expr=result_expr,
                justification=step_def.get("justification", ""),
                rule_applied=step_def.get("rule", ""),
            )
            derivation.add_step(step)
            current_expr = result_expr

        # Set conclusion
        if current_expr:
            derivation.conclusion = current_expr

        # Verify if requested
        if verify and self.verifier:
            verification = self.verifier.verify_derivation(derivation, context)
            derivation.is_verified = verification.is_verified

        return derivation

    def _execute_step(
        self,
        expr: Expression,
        operation: str,
        step_def: dict[str, Any],
        context: MathContext | None,
    ) -> Expression:
        """Execute a single derivation step."""
        match operation:
            case "simplify":
                return self.engine.simplify(expr, context)
            case "differentiate":
                var = step_def.get("variable", "x")
                order = step_def.get("order", 1)
                return self.engine.differentiate(expr, var, order, context)
            case "integrate":
                var = step_def.get("variable", "x")
                return self.engine.integrate(expr, var, context=context)
            case "substitute":
                subs = step_def.get("substitutions", {})
                return self.engine.substitute(expr, subs, context)
            case _:
                return expr


@dataclass
class VerifyUseCase:
    """
    Use case for verifying mathematical results.

    Performs various verification checks.
    """

    engine: SymbolicEngine
    verifier: Verifier

    def execute(
        self,
        original: str,
        result: str,
        operation: str,
        context: MathContext | None = None,
    ) -> VerificationResult:
        """
        Verify a calculation result.

        Args:
            original: Original expression
            result: Result to verify
            operation: Operation that was performed
            context: Mathematical context

        Returns:
            VerificationResult with verification status
        """
        try:
            original_expr = self.engine.parse(original, context)
            result_expr = self.engine.parse(result, context)

            return self.verifier.verify_step(original_expr, result_expr, operation, context)
        except Exception as e:
            return VerificationResult.failure(f"Verification error: {e}")

    def verify_equality(
        self,
        expr1: str,
        expr2: str,
        context: MathContext | None = None,
    ) -> VerificationResult:
        """
        Verify that two expressions are equal.

        Args:
            expr1: First expression
            expr2: Second expression
            context: Mathematical context

        Returns:
            VerificationResult
        """
        try:
            e1 = self.engine.parse(expr1, context)
            e2 = self.engine.parse(expr2, context)

            if self.engine.equals(e1, e2, context):
                return VerificationResult.success("Expressions are equal")
            else:
                return VerificationResult.failure(
                    "Expressions are not equal",
                    expr1=expr1,
                    expr2=expr2,
                )
        except Exception as e:
            return VerificationResult.failure(f"Comparison error: {e}")
