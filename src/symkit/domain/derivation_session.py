"""
DerivationSession - Derivation session

Stateful derivation process management, supporting:
- Multi-step tracking
- Complete provenance recording
- Persistence (prevents interruption)
- Automatic verification for each step
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import sympy as sp

from symkit.domain.assumption_binding import apply_assumptions
from symkit.domain.assumption_engine import AssumptionEngine
from symkit.domain.derivation_goal import (
    DerivationGoal,
)
from symkit.domain.derivation_outcome import (
    apply_auto_verification,
    completion_outcome,
    compute_goal_progress,
    failed_operation_steps,
    is_note_step,
    resolve_target_reached,
    select_representative_expression,
    steps_summary,
)
from symkit.domain.derivation_pattern import DerivationPattern
from symkit.domain.derivation_planner import DerivationPlanner
from symkit.domain.expr_io import safe_load_expression
from symkit.domain.final_result import (
    is_numerically_zero,
    suspect_identity_steps,
    suspect_identity_warning,
)
from symkit.domain.formula import Formula, FormulaParser, FormulaSource, ParseError
from symkit.domain.formula_recommender import (
    FormulaRecommender,
    FormulaSourceAdapter,
    create_default_external_adapters,
)
from symkit.domain.math_domain import MathDomain
from symkit.domain.paths import user_sessions_dir
from symkit.domain.step_verifier import (
    StepVerifier,
    verification_result_from_json,
    verification_result_to_json,
)
from symkit.domain.symbol_registry import (
    SymbolRegistry,
    SymbolScope,
)
from symkit.domain.value_objects import VerificationResult, VerificationStatus
from symkit.infrastructure.derivation_repository import get_repository


def _library_candidates() -> list[dict[str, Any]]:
    """Snapshot the formula index as recommender candidate dicts.

    Reads the persistent index, which the write paths (formula_add,
    session_complete, formula_promote) update synchronously, so entries
    added in this process are visible immediately. Any failure (missing
    index file, unreadable DB) degrades to no candidates rather than
    blocking derive().
    """
    try:
        from symkit.domain.paths import user_index_path
        from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore

        store = SqliteFormulaIndexStore(user_index_path())
        store.open()
        try:
            formulas = store.all()
        finally:
            store.close()
        candidates: list[dict[str, Any]] = []
        for f in formulas:
            candidates.append({
                "formula_id": f.id,
                "name": f.name,
                "expression": f.sympy_str or f.latex,
                "domain": f.domain,
                "verified": f.verified,
                "description": f.description,
                "application_context": f.application_context,
                "tags": list(f.tags),
                "derivation_steps": list(f.derivation_steps),
                "variables": dict(f.variables),
                "source": "library",
            })
        return candidates
    except Exception:
        return []


def _free_symbols(value: Any) -> set[sp.Symbol]:
    if isinstance(value, (list, tuple)):
        return {s for item in value for s in _free_symbols(item)}
    return value.free_symbols if isinstance(value, sp.Basic) else set()


class OperationType(Enum):
    """Derivation operation types."""

    LOAD_FORMULA = "load_formula"
    PARSE = "parse"
    SUBSTITUTE = "substitute"
    SIMPLIFY = "simplify"
    CANCEL = "cancel"
    EXPAND = "expand"
    FACTOR = "factor"
    SOLVE = "solve"
    DIFFERENTIATE = "differentiate"
    INTEGRATE = "integrate"
    LIMIT = "limit"
    SERIES = "series"
    DSOLVE = "dsolve"
    EVALF = "evalf"
    MATRIX_OP = "matrix_op"
    VECTOR_OP = "vector_op"
    TRANSFORM = "transform"
    COMBINE = "combine"
    CUSTOM = "custom"


class StepStatus(Enum):
    """Step status."""

    SUCCESS = "success"
    FAILED = "failed"
    PENDING_VERIFICATION = "pending_verification"


@dataclass
class DerivationStep:
    """
    Derivation step record.

    Fully records every operation; this is key to academic value.
    Contains human knowledge (notes) and constraints (assumptions/limitations).
    """

    step_number: int
    operation: OperationType
    description: str

    # Input/output
    input_expressions: dict[str, str]  # {"formula_id": "expression_str"}
    output_expression: str
    output_latex: str

    # SymPy execution record
    sympy_command: str  # The actual SymPy command executed
    output_srepr: str = ""  # Machine-readable round-trip SymPy srepr representation
    input_srepr: str = ""  # srepr of the step's representative input expression

    # 🆕 Human knowledge injection
    notes: str = ""  # Human insight, observation, explanation
    assumptions: list[str] = field(default_factory=list)  # Assumptions for this step
    limitations: list[str] = field(default_factory=list)  # Limitations of this step

    # Verification
    status: StepStatus = StepStatus.SUCCESS
    verification_result: str = ""

    # Timestamp
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "operation": self.operation.value,
            "description": self.description,
            "input_expressions": self.input_expressions,
            "output_expression": self.output_expression,
            "output_latex": self.output_latex,
            "output_srepr": self.output_srepr,
            "input_srepr": self.input_srepr,
            "sympy_command": self.sympy_command,
            # 🆕 Human knowledge
            "notes": self.notes,
            "assumptions": self.assumptions,
            "limitations": self.limitations,
            # Verification
            "status": self.status.value,
            "verification_result": self.verification_result,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DerivationStep:
        return cls(
            step_number=data["step_number"],
            operation=OperationType(data["operation"]),
            description=data["description"],
            input_expressions=data["input_expressions"],
            output_expression=data["output_expression"],
            output_latex=data["output_latex"],
            output_srepr=data.get("output_srepr", ""),
            input_srepr=data.get("input_srepr", ""),
            sympy_command=data["sympy_command"],
            # 🆕 Human knowledge
            notes=data.get("notes", ""),
            assumptions=data.get("assumptions", []),
            limitations=data.get("limitations", []),
            # Verification
            status=StepStatus(data["status"]),
            verification_result=data.get("verification_result", ""),
            timestamp=data.get("timestamp", ""),
        )


class SessionStatus(Enum):
    """Session status."""

    ACTIVE = "active"  # In progress
    PAUSED = "paused"  # Paused (persisted)
    COMPLETED = "completed"  # Completed
    FAILED = "failed"  # Failed


@dataclass
class DerivationSession:
    """
    Derivation session.

    Manages a complete derivation process and supports persistence.
    """

    # Identification
    session_id: str
    name: str
    description: str = ""
    domain: str = ""  # Math/physics domain tag (e.g., "fluid_dynamics", "quantum_mechanics")
    pattern: DerivationPattern = DerivationPattern.DIRECT_MANIPULATION

    # State
    status: SessionStatus = SessionStatus.ACTIVE
    formulas: dict[str, Formula] = field(default_factory=dict)
    current_expression: sp.Basic | None = None  # Basic includes Expr and Equality
    current_formula_id: str | None = None

    # History
    steps: list[DerivationStep] = field(default_factory=list)

    # Symbol semantics registry (runtime, not directly serialized to JSON)
    symbol_registry: SymbolRegistry = field(init=False)

    # Multi-level assumption engine (runtime)
    assumption_engine: AssumptionEngine = field(init=False)

    # Automatic verification toggle
    auto_verify: bool = True

    # Step verifier (runtime)
    verifier: StepVerifier = field(init=False)

    # Derivation goal (optional, for goal-aware planning)
    goal: DerivationGoal | None = None

    # External formula adapters (runtime)
    external_adapters: list[FormulaSourceAdapter] | None = None

    # Formula recommender (runtime)
    recommender: FormulaRecommender = field(init=False)

    # Step planner (runtime)
    planner: DerivationPlanner = field(init=False)

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    author: str = ""
    tags: list[str] = field(default_factory=list)

    # Persistence path
    _persist_path: Path | None = None

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = str(uuid.uuid4())[:8]
        # Initialize symbol registry and load domain defaults
        self.symbol_registry = SymbolRegistry()
        domain = MathDomain.from_string(self.domain) if self.domain else MathDomain.GENERAL
        for name, assumption in self.symbol_registry.get_domain_default_assumptions(domain).items():
            self.symbol_registry.register(
                name=name,
                meaning=f"Domain default symbol for {domain.value}",
                domain=domain,
                scope=SymbolScope.DOMAIN,
                common_assumptions=[assumption],
                source_type="domain_default",
            )
        # Initialize multi-level assumption engine
        self.assumption_engine = AssumptionEngine(domain=domain)
        # Initialize step verifier (assumption-aware)
        self.verifier = StepVerifier(symbol_registry=self.symbol_registry)
        # Initialize formula recommender with local derived formulas.
        # Use the global repository singleton so tests that reset it (and
        # fixtures that point it at a temp dir) are honored; this also avoids
        # accidentally loading real persisted formulas from the CWD.
        repo = get_repository()
        adapters = self.external_adapters if self.external_adapters is not None else create_default_external_adapters()
        self.recommender = FormulaRecommender(repository=repo, external_adapters=adapters)
        # Initialize goal-aware planner
        self.planner = DerivationPlanner()

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def formula_ids(self) -> list[str]:
        return list(self.formulas.keys())

    def _update_timestamp(self) -> None:
        self.updated_at = datetime.now().isoformat()

    def _add_step(
        self,
        operation: OperationType,
        description: str,
        input_expressions: dict[str, str],
        output_expr: sp.Basic,  # Basic includes Expr and Equality
        sympy_command: str,
        status: StepStatus = StepStatus.SUCCESS,
        # 🆕 Human knowledge
        notes: str = "",
        assumptions: list[str] | None = None,
        limitations: list[str] | None = None,
        prior_expr: sp.Basic | None = None,
        input_srepr: str = "",
    ) -> DerivationStep:
        """Add a step record (with human knowledge and automatic verification).

        ``input_srepr`` defaults to the srepr of ``prior_expr`` when the caller
        already holds the live input object.  The input is deliberately never
        re-parsed from ``input_expressions`` here: re-parsing a display string
        does not round-trip for ``E``/``I`` or LaTeX-derived symbols (invariant
        I2, run-024 regression).
        """
        if not input_srepr and isinstance(prior_expr, sp.Basic):
            input_srepr = sp.srepr(prior_expr)

        step = DerivationStep(
            step_number=len(self.steps) + 1,
            operation=operation,
            description=description,
            input_expressions=input_expressions,
            output_expression=str(output_expr),
            output_latex=sp.latex(output_expr),
            output_srepr=sp.srepr(output_expr),
            input_srepr=input_srepr,
            sympy_command=sympy_command,
            notes=notes,
            assumptions=assumptions or [],
            limitations=limitations or [],
            status=status,
        )

        # Automatic verification (resilient: a verifier crash must not drop the step)
        if self.auto_verify:
            apply_auto_verification(self, step, prior_expr)

        self.steps.append(step)
        self._update_timestamp()

        # Automatic persistence
        if self._persist_path:
            self.save()

        return step

    def load_formula(
        self,
        formula_input: str | dict[str, Any],
        formula_id: str | None = None,
        source: FormulaSource = FormulaSource.USER_INPUT,
        source_detail: str = "",
        set_as_current: bool = True,
        **metadata: Any,
    ) -> dict[str, Any]:
        """
        Load a formula.

        Args:
            formula_input: Formula input (multiple formats supported)
            formula_id: Formula ID (optional, auto-generated if not provided)
            source: Source tag
            source_detail: Detailed source
            set_as_current: Whether to set as current expression
            **metadata: Extra metadata

        Returns:
            Operation result
        """
        # Generate ID
        if formula_id is None:
            formula_id = f"f{len(self.formulas) + 1}"

        # Parse formula
        result = FormulaParser.parse(
            formula_input,
            formula_id,
            source=source,
            source_detail=source_detail,
            **metadata,
        )

        if isinstance(result, ParseError):
            return result.to_dict()

        # Save formula
        self.formulas[formula_id] = result

        if set_as_current:
            self.current_expression = result.expression
            self.current_formula_id = formula_id

        # Record step
        self._add_step(
            operation=OperationType.LOAD_FORMULA,
            description=f"Load formula '{formula_id}' from {source.value}",
            input_expressions={formula_id: result.original_input},
            output_expr=result.expression,
            sympy_command=f"parse('{result.original_input}')",
            input_srepr=sp.srepr(result.expression),
        )

        # Register symbol semantics and detect conflicts
        symbol_names = list(result.symbol_names)
        if self.domain:
            self.symbol_registry.register_formula_symbols(
                formula_id=formula_id,
                symbol_names=symbol_names,
                domain=self.domain,
            )
        conflicts = self.symbol_registry.detect_conflicts(symbol_names)
        return {
            "success": True,
            "formula_id": formula_id,
            "expression": result.sympy_str,
            "latex": result.latex,
            "variables": symbol_names,
            "source": source.value,
            "source_detail": source_detail,
            "step_number": self.step_count,
            "symbol_conflicts": conflicts,
            "symbol_warnings": [
                f"'{c['symbol']}' has multiple meanings: {c['meanings']}"
                for c in conflicts
            ],
        }

    def substitute(
        self,
        target_var: str,
        replacement: str | sp.Expr,
        in_formula: str | None = None,
        description: str = "",
        # 🆕 Human knowledge
        notes: str = "",
        assumptions: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Substitution operation.

        Args:
            target_var: Variable to replace
            replacement: Replacement expression
            in_formula: Formula in which to substitute (defaults to current)
            description: Operation description
            notes: Human insight, observation, explanation
            assumptions: Assumptions for this step
            limitations: Limitations for this step

        Returns:
            Operation result
        """
        # Determine target expression
        if in_formula:
            if in_formula not in self.formulas:
                return {
                    "success": False,
                    "error": f"Formula '{in_formula}' not found",
                    "available_formulas": self.formula_ids,
                }
            expr = self.formulas[in_formula].expression
        elif self.current_expression is not None:
            expr = self.current_expression
        else:
            return {
                "success": False,
                "error": "No current expression. Load a formula first.",
            }

        # Check whether variable exists
        symbol_names = {str(s) for s in _free_symbols(expr)}
        if target_var not in symbol_names:
            return {
                "success": False,
                "error": f"Variable '{target_var}' not found in expression",
                "available_variables": list(symbol_names),
            }

        # Parse replacement expression
        if isinstance(replacement, str):
            try:
                replacement_expr = sp.sympify(replacement)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Cannot parse replacement: {e}",
                }
        else:
            replacement_expr = replacement

        # Execute substitution
        target_symbol = sp.Symbol(target_var)
        try:
            new_expr = expr.subs(target_symbol, replacement_expr)
        except Exception as e:
            return {
                "success": False,
                "error": f"Substitution failed: {e}",
            }

        # Update current expression
        self.current_expression = new_expr

        # Record step
        desc = description or f"Substitute {target_var} = {replacement}"
        self._add_step(
            operation=OperationType.SUBSTITUTE,
            description=desc,
            input_expressions={
                "original": str(expr),
                "replacement": f"{target_var} = {replacement}",
            },
            output_expr=new_expr,
            sympy_command=f"expr.subs({target_var}, {replacement})",
            notes=notes,
            assumptions=assumptions,
            limitations=limitations,
            prior_expr=expr,
        )

        return {
            "success": True,
            "expression": str(new_expr),
            "latex": sp.latex(new_expr),
            "step_number": self.step_count,
            "substituted": {target_var: str(replacement_expr)},
            "notes": notes,
            "assumptions": assumptions or [],
            "limitations": limitations or [],
        }

    def simplify(
        self,
        method: str = "auto",
        description: str = "",
        # 🆕 Human knowledge
        notes: str = "",
        assumptions: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Simplify the current expression.

        Args:
            method: Simplification method ("auto", "trig", "radical", "expand_then_simplify")
            description: Operation description
            notes: Human insight
            assumptions: Assumptions for this step
            limitations: Limitations for this step

        Returns:
            Operation result
        """
        if self.current_expression is None:
            return {
                "success": False,
                "error": "No current expression to simplify",
            }

        original = self.current_expression

        try:
            if method == "trig":
                new_expr = sp.trigsimp(original)
                cmd = "trigsimp(expr)"
            elif method == "radical":
                new_expr = sp.radsimp(original)
                cmd = "radsimp(expr)"
            elif method == "expand_then_simplify":
                new_expr = sp.simplify(sp.expand(original))
                cmd = "simplify(expand(expr))"
            else:  # auto
                new_expr = sp.simplify(original)
                cmd = "simplify(expr)"
        except Exception as e:
            return {
                "success": False,
                "error": f"Simplification failed: {e}",
            }

        self.current_expression = new_expr

        # Record step
        desc = description or f"Simplify using {method} method"
        self._add_step(
            operation=OperationType.SIMPLIFY,
            description=desc,
            input_expressions={"original": str(original)},
            output_expr=new_expr,
            sympy_command=cmd,
            notes=notes,
            assumptions=assumptions,
            limitations=limitations,
            prior_expr=original,
        )

        return {
            "success": True,
            "expression": str(new_expr),
            "latex": sp.latex(new_expr),
            "step_number": self.step_count,
            "method": method,
            "changed": str(original) != str(new_expr),
            "notes": notes,
            "assumptions": assumptions or [],
            "limitations": limitations or [],
        }

    def solve_for(
        self,
        variable: str,
        description: str = "",
        # 🆕 Human knowledge
        notes: str = "",
        assumptions: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Solve for a variable.

        Args:
            variable: Variable to solve for
            description: Operation description
            notes: Human insight
            assumptions: Assumptions for this step
            limitations: Limitations for this step

        Returns:
            Operation result (may have multiple solutions)
        """
        if self.current_expression is None:
            return {
                "success": False,
                "error": "No current expression to solve",
            }

        expr = self.current_expression
        var_symbol = sp.Symbol(variable)

        # Check whether variable exists
        if var_symbol not in _free_symbols(expr):
            return {
                "success": False,
                "error": f"Variable '{variable}' not in expression",
                "available_variables": [str(s) for s in _free_symbols(expr)],
            }

        try:
            solutions = sp.solve(expr, var_symbol)
        except Exception as e:
            return {
                "success": False,
                "error": f"Solve failed: {e}",
            }

        if not solutions:
            return {
                "success": False,
                "error": f"No solution found for {variable}",
            }

        # Take the first solution as the current expression
        first_solution = solutions[0]
        solution_eq = sp.Eq(var_symbol, first_solution)
        self.current_expression = solution_eq

        # Record step
        desc = description or f"Solve for {variable}"
        self._add_step(
            operation=OperationType.SOLVE,
            description=desc,
            input_expressions={"equation": str(expr)},
            output_expr=solution_eq,
            sympy_command=f"solve(expr, {variable})",
            notes=notes,
            assumptions=assumptions,
            limitations=limitations,
            prior_expr=expr,
        )

        return {
            "success": True,
            "variable": variable,
            "solutions": [str(s) for s in solutions],
            "solutions_latex": [sp.latex(s) for s in solutions],
            "primary_solution": str(first_solution),
            "step_number": self.step_count,
            "notes": notes,
            "assumptions": assumptions or [],
            "limitations": limitations or [],
        }

    def differentiate(
        self,
        variable: str,
        order: int = 1,
        description: str = "",
        # 🆕 Human knowledge
        notes: str = "",
        assumptions: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Differentiate.

        Args:
            variable: Differentiation variable
            order: Order
            description: Operation description
            notes: Human insight
            assumptions: Assumptions for this step
            limitations: Limitations for this step
        """
        if self.current_expression is None:
            return {"success": False, "error": "No current expression"}

        original = self.current_expression
        var_symbol = sp.Symbol(variable)

        try:
            new_expr = sp.diff(original, var_symbol, order)
        except Exception as e:
            return {"success": False, "error": f"Differentiation failed: {e}"}

        self.current_expression = new_expr

        desc = description or f"Differentiate w.r.t. {variable} (order {order})"
        self._add_step(
            operation=OperationType.DIFFERENTIATE,
            description=desc,
            input_expressions={"original": str(original)},
            output_expr=new_expr,
            sympy_command=f"diff(expr, {variable}, {order})",
            notes=notes,
            assumptions=assumptions,
            limitations=limitations,
            prior_expr=original,
        )

        return {
            "success": True,
            "expression": str(new_expr),
            "latex": sp.latex(new_expr),
            "step_number": self.step_count,
            "notes": notes,
            "assumptions": assumptions or [],
            "limitations": limitations or [],
        }

    def integrate(
        self,
        variable: str,
        lower: str | None = None,
        upper: str | None = None,
        description: str = "",
        # 🆕 Human knowledge
        notes: str = "",
        assumptions: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Integrate.

        Args:
            variable: Integration variable
            lower: Lower bound
            upper: Upper bound
            description: Operation description
            notes: Human insight
            assumptions: Assumptions for this step
            limitations: Limitations for this step
        """
        if self.current_expression is None:
            return {"success": False, "error": "No current expression"}

        original = self.current_expression
        var_symbol = sp.Symbol(variable)

        try:
            if lower is not None and upper is not None:
                lower_val = sp.sympify(lower)
                upper_val = sp.sympify(upper)
                new_expr = sp.integrate(original, (var_symbol, lower_val, upper_val))
                cmd = f"integrate(expr, ({variable}, {lower}, {upper}))"
            else:
                new_expr = sp.integrate(original, var_symbol)
                cmd = f"integrate(expr, {variable})"
        except Exception as e:
            return {"success": False, "error": f"Integration failed: {e}"}

        self.current_expression = new_expr

        desc = description or f"Integrate w.r.t. {variable}"
        self._add_step(
            operation=OperationType.INTEGRATE,
            description=desc,
            input_expressions={"original": str(original)},
            output_expr=new_expr,
            sympy_command=cmd,
            notes=notes,
            assumptions=assumptions,
            limitations=limitations,
            prior_expr=original,
        )

        return {
            "success": True,
            "expression": str(new_expr),
            "latex": sp.latex(new_expr),
            "step_number": self.step_count,
            "notes": notes,
            "assumptions": assumptions or [],
            "limitations": limitations or [],
        }

    # Step verification

    def _last_computed_expression(self) -> sp.Basic | None:
        """The most recent step output, walking past steps that have none.

        A note computes nothing and carries no output, so restoring the session
        cursor after a delete or rollback must skip it rather than clear the
        expression (2026-09-12 black-box round).
        """
        for step in reversed(self.steps):
            expr = safe_load_expression(
                step.output_expression, step.output_srepr
            )
            if expr is not None:
                return expr
        return None

    def outcome_expression(self) -> sp.Basic | None:
        """What the derivation produced, as opposed to what ran last.

        ``current_expression`` legitimately follows every step, so a trailing
        evalf probe (a numeric residual, a constant) would be handed back as the
        answer. An explicit None check, not ``or``: a SymPy Equality has no
        truth value.
        """
        outcome = self.representative_expression()
        return self.current_expression if outcome is None else outcome

    def _resolve_prior_expr(self, step_number: int) -> sp.Basic | None:
        """Resolve the expression before the specified step (for re-verification)."""
        if step_number <= 1:
            return None
        prev_step = self.steps[step_number - 2]
        return safe_load_expression(
            prev_step.output_expression,
            prev_step.output_srepr,
        )

    def representative_expression(self) -> sp.Basic | None:
        """The step output that best represents this derivation's outcome.

        Selection order (implemented in
        :func:`symkit.domain.derivation_outcome.select_representative_expression`):

        1. A closing exact-zero self-check (r14 task-08); a trailing nonzero
           constant is useless (run-008), a zero superseded by ANY later step
           output — symbolic or nonzero constant — is a residual (r19 F2a), and
           note/empty-output steps leave the chain untouched.
        2. The last symbolic output involving a goal target variable.
        3. The last lineage output, else the last symbolic output, else the
           current expression; a step consuming the previous output continues
           the lineage across renames, and notes do not break it (r17 audit1).
        """
        targets: list[str] = []
        if self.goal is not None and self.goal.target_variables:
            targets = list(self.goal.target_variables)
        return select_representative_expression(self.steps, targets, self.current_expression)

    def verify_step(self, step_number: int) -> dict[str, Any]:
        """Re-verify a single step.

        Args:
            step_number: Step number (1-based)

        Returns:
            Verification result
        """
        if step_number < 1 or step_number > len(self.steps):
            return {
                "success": False,
                "error": f"Step {step_number} not found. Valid range: 1-{len(self.steps)}",
            }

        step = self.steps[step_number - 1]
        prior_expr = self._resolve_prior_expr(step_number)
        verification = self.verifier.verify_step(
            step,
            prior_expr=prior_expr,
            assumption_engine=self.assumption_engine,
        )

        if verification.status == VerificationStatus.VERIFIED:
            step.status = StepStatus.SUCCESS
        elif verification.status == VerificationStatus.INCONCLUSIVE:
            step.status = StepStatus.PENDING_VERIFICATION
        else:
            step.status = StepStatus.FAILED
        step.verification_result = verification_result_to_json(verification)

        self._update_timestamp()
        if self._persist_path:
            self.save()

        return {
            "success": True,
            "step_number": step_number,
            "status": step.status.value,
            "verification_status": verification.status.value,
            "verification_message": verification.message,
            "verification": verification.details,
            "step": step.to_dict(),
        }

    def verify_derivation(self) -> dict[str, Any]:
        """Verify the whole derivation chain and return a summary.

        Pure note steps (``session_add_note``, failed-call traces) carry no
        mathematical claim: excluded from every count and step-number list,
        still visible in ``session_get_steps`` (r19 F5).
        """
        substantive = [step for step in self.steps if not is_note_step(step)]
        summary: dict[str, Any] = {
            "total": len(substantive),
            "verified": 0, "failed": 0, "inconclusive": 0,
            "failed_steps": [], "inconclusive_steps": [], "suspect_identity_steps": [],
            "assumption_conflicts": self.assumption_engine.detect_conflicts(),
        }

        verified_substantive = 0
        for step in substantive:
            if step.verification_result:
                record = verification_result_from_json(step.verification_result)
            else:
                record = VerificationResult(
                    status=VerificationStatus.INCONCLUSIVE,
                    message="No verification record",
                )
            if record.status == VerificationStatus.VERIFIED:
                summary["verified"] += 1
                # LOAD_FORMULA verification is trivial; only real checks may promote
                # the chain to overall "verified".
                if step.operation != OperationType.LOAD_FORMULA:
                    verified_substantive += 1
            elif record.status == VerificationStatus.FAILED:
                summary["failed"] += 1
                summary["failed_steps"].append(step.step_number)
            else:
                summary["inconclusive"] += 1
                summary["inconclusive_steps"].append(step.step_number)

        # Graded semantics: "verified" = nothing failed and at least one
        # substantive step verified; inconclusive steps do not poison the chain.
        if summary["failed"] > 0:
            summary["overall"] = "failed"
        elif verified_substantive > 0:
            summary["overall"] = "verified"
        else:
            summary["overall"] = "inconclusive"

        # Disclose flagged identities without touching the failed-driven overall.
        flagged = suspect_identity_steps(self.steps)
        summary["suspect_identity_steps"] = flagged
        if flagged:
            summary["warnings"] = [suspect_identity_warning(flagged)]

        # Failed ``math(session=True)`` calls are kept as note-type traces and
        # stay out of every count above (r19 F5); an operator reading only the
        # summary cannot tell an attempt failed at all (r22 task-07).
        failed_ops = failed_operation_steps(self.steps)
        if failed_ops:
            summary["failed_operation_steps"] = failed_ops

        return summary

    def set_goal(self, goal: DerivationGoal) -> None:
        """Set the derivation goal."""
        self.goal = goal
        # If the goal detects a more specific domain, update the session domain
        if goal.domain and not self.domain:
            self.domain = goal.domain
        self._update_timestamp()

    def recommend_formulas(self, top_k: int = 5) -> list[dict[str, Any]]:
        """Recommend available formulas based on the goal.

        Besides the derivation repository, the live formula library is read
        on every call so that a formula added with ``formula_add`` moments
        earlier is immediately visible to ``derive()`` (run-021: the
        recommender used to read only the repository snapshot, so fresh
        library entries were invisible until a server restart).
        """
        if self.goal is None:
            return []
        return self.recommender.recommend(
            self.goal, top_k=top_k, extra_candidates=_library_candidates()
        )

    def plan_next_steps(self, max_steps: int = 5) -> list[dict[str, Any]]:
        """Return goal-aware next-step suggestions."""
        return self.planner.plan_next_steps(self, max_steps=max_steps)

    def _apply_assumptions_to_expr(
        self,
        expr: sp.Basic,
        assumptions: dict[str, dict[str, bool]] | None,
    ) -> sp.Basic:
        """Bind the given assumptions onto the free symbols of *expr*.

        Delegates to :func:`symkit.domain.assumption_binding.apply_assumptions`
        so session replay, the engine, the verifier and the math dispatcher all
        agree on how assumptions become symbols (invariant I3).
        """
        return apply_assumptions(expr, assumptions)

    def _expressions_equivalent(
        self,
        current: sp.Basic,
        target: sp.Basic,
        assumptions: dict[str, dict[str, bool]] | None = None,
    ) -> bool:
        """Robustly check whether two SymPy objects represent the same expression.

        Equalities are compared on the (lhs - rhs) form so that different
        orderings of the sides still match.  With *assumptions* both sides are
        simplified first, so ``sqrt(2*G*M/R)`` matches
        ``sqrt(2)*sqrt(G)*sqrt(M)/sqrt(R)`` under a positive assumption.
        When only one side is an Equality, the other matches either side of it:
        a target ``Eq(Phi, rhs)`` is reached by the bare ``rhs`` (r23 F12a).
        """
        if current == target:
            return True
        try:
            current = self._apply_assumptions_to_expr(current, assumptions)
            target = self._apply_assumptions_to_expr(target, assumptions)
            if isinstance(current, sp.Equality) and isinstance(target, sp.Equality):
                current_form = current.lhs - current.rhs
                target_form = target.lhs - target.rhs
                return is_numerically_zero(sp.simplify(current_form - target_form))
            if isinstance(current, sp.Equality) != isinstance(target, sp.Equality):
                eq, other = (
                    (current, target)
                    if isinstance(current, sp.Equality)
                    else (target, current)
                )
                return self._expressions_equivalent(
                    eq.lhs, other, assumptions
                ) or self._expressions_equivalent(eq.rhs, other, assumptions)
            return is_numerically_zero(sp.simplify(current - target))
        except Exception:
            return False

    def compute_progress(self, current_override: sp.Basic | None = None) -> dict[str, Any]:
        """Progress relative to the goal (tri-state ``matches_target``, r19 F4).

        ``current_override``: an explicit deliverable (``complete``'s
        ``final_expression``) is judged instead of the chain current (r22).
        """
        return compute_goal_progress(self, current_override)

    def get_steps(self) -> list[dict[str, Any]]:
        """Get all steps."""
        return [s.to_dict() for s in self.steps]

    def get_step(self, step_number: int) -> dict[str, Any]:
        """
        Get details of a single step.

        Args:
            step_number: Step number (1-based)

        Returns:
            Step details
        """
        if step_number < 1 or step_number > len(self.steps):
            return {
                "success": False,
                "error": f"Step {step_number} not found. Valid range: 1-{len(self.steps)}",
            }

        step = self.steps[step_number - 1]
        return {
            "success": True,
            "step": step.to_dict(),
        }

    def update_step(
        self,
        step_number: int,
        description: str | None = None,
        notes: str | None = None,
        assumptions: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Update step metadata (does not change calculation results).

        Args:
            step_number: Step number (1-based)
            description: New description (None means no update)
            notes: New notes (None means no update)
            assumptions: New assumptions (None means no update)
            limitations: New limitations (None means no update)

        Returns:
            Update result
        """
        if step_number < 1 or step_number > len(self.steps):
            return {
                "success": False,
                "error": f"Step {step_number} not found. Valid range: 1-{len(self.steps)}",
            }

        step = self.steps[step_number - 1]
        updated_fields = []

        if description is not None:
            step.description = description
            updated_fields.append("description")

        if notes is not None:
            step.notes = notes
            updated_fields.append("notes")

        if assumptions is not None:
            step.assumptions = assumptions
            updated_fields.append("assumptions")

        if limitations is not None:
            step.limitations = limitations
            updated_fields.append("limitations")

        self._update_timestamp()

        # Automatic persistence
        if self._persist_path:
            self.save()

        return {
            "success": True,
            "step_number": step_number,
            "updated_fields": updated_fields,
            "step": step.to_dict(),
            "message": f"Step {step_number} updated: {', '.join(updated_fields)}",
        }

    def delete_step(self, step_number: int) -> dict[str, Any]:
        """
        Delete a single step (only the last step can be deleted, otherwise continuity is broken).

        Args:
            step_number: Step number (1-based)

        Returns:
            Deletion result
        """
        if step_number < 1 or step_number > len(self.steps):
            return {
                "success": False,
                "error": f"Step {step_number} not found. Valid range: 1-{len(self.steps)}",
            }

        if step_number != len(self.steps):
            return {
                "success": False,
                "error": f"Can only delete the last step ({len(self.steps)}). Use rollback_to_step() to delete multiple steps.",
            }

        deleted_step = self.steps.pop()
        self._update_timestamp()

        # Restore previous step's expression
        self.current_expression = self._last_computed_expression()

        # Automatic persistence
        if self._persist_path:
            self.save()

        return {
            "success": True,
            "deleted_step": deleted_step.to_dict(),
            "new_step_count": len(self.steps),
            "current_expression": str(self.current_expression) if self.current_expression is not None else None,
            "message": f"Step {step_number} deleted.",
        }

    def rollback_to_step(self, step_number: int) -> dict[str, Any]:
        """
        Roll back to the specified step (deletes all steps after it).

        Args:
            step_number: Step number to roll back to (1-based, this step is kept)

        Returns:
            Rollback result
        """
        if step_number < 0 or step_number > len(self.steps):
            return {
                "success": False,
                "error": f"Invalid step number. Valid range: 0-{len(self.steps)} (0 = reset all)",
            }

        if step_number == len(self.steps):
            return {
                "success": True,
                "message": "Already at this step, nothing to rollback.",
                "step_count": len(self.steps),
            }

        # Record steps that will be deleted
        deleted_steps = self.steps[step_number:]
        deleted_count = len(deleted_steps)

        # Perform rollback
        self.steps = self.steps[:step_number]

        # Restore current expression
        self.current_expression = self._last_computed_expression()

        self._update_timestamp()

        # Automatic persistence
        if self._persist_path:
            self.save()

        return {
            "success": True,
            "rolled_back_to": step_number,
            "deleted_count": deleted_count,
            "deleted_steps": [s.step_number for s in deleted_steps],
            "new_step_count": len(self.steps),
            "current_expression": str(self.current_expression) if self.current_expression is not None else None,
            "current_latex": sp.latex(self.current_expression) if self.current_expression is not None else None,
            "message": f"Rolled back to step {step_number}. Deleted {deleted_count} step(s).",
        }

    def insert_note_after_step(
        self,
        after_step: int,
        note: str,
        note_type: str = "observation",
        related_variables: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Insert a note after the specified step (subsequent steps are renumbered).

        Args:
            after_step: Insert after this step (0 = very beginning)
            note: Note content
            note_type: Note type
            related_variables: Related variables

        Returns:
            Insertion result
        """
        if after_step < 0 or after_step > len(self.steps):
            return {
                "success": False,
                "error": f"Invalid position. Valid range: 0-{len(self.steps)}",
            }

        # A note computes nothing, so it must not carry an output: copying the
        # neighbour's expression made a text note look like it produced that value.
        note_emoji = {
            "assumption": "📋",
            "limitation": "⚠️",
            "observation": "💡",
            "correction": "🔧",
            "interpretation": "🔬",
            "application": "🎯",
            "reference": "📖",
        }.get(note_type, "📝")

        new_step = DerivationStep(
            step_number=after_step + 1,  # Temporary number, will be renumbered later
            operation=OperationType.CUSTOM,
            description=f"{note_emoji} [{note_type.upper()}] {note}"
            + (f"\n   Related: {', '.join(related_variables)}" if related_variables else ""),
            input_expressions={
                "note_type": note_type,
                "related_variables": str(related_variables or []),
            },
            output_expression="",
            output_latex="",
            output_srepr="",
            input_srepr="",
            sympy_command="# Note (no computation)",
        )

        # Insert step
        self.steps.insert(after_step, new_step)

        # Renumber
        for i, step in enumerate(self.steps):
            step.step_number = i + 1

        self._update_timestamp()

        # Automatic persistence
        if self._persist_path:
            self.save()

        return {
            "success": True,
            "inserted_at": after_step + 1,
            "new_step_count": len(self.steps),
            "message": f"Note inserted at step {after_step + 1}. Steps renumbered.",
        }

    def get_current(self) -> dict[str, Any]:
        """Get current state."""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "domain": self.domain,
            "status": self.status.value,
            "step_count": self.step_count,
            "current_expression": str(self.current_expression) if self.current_expression is not None else None,
            "current_latex": sp.latex(self.current_expression) if self.current_expression is not None else None,
            "formulas_loaded": self.formula_ids,
        }

    def complete(self, require_target_match: bool = False, final_override: sp.Basic | None = None) -> dict[str, Any]:
        """Complete the derivation.
        With ``require_target_match`` the session pauses (and reports failure)
        unless the current expression matches the goal target.  ``final_override``
        is a caller-declared deliverable: it supplies the headline and removes
        the "no result expression" requirement (r19x task-14).
        """
        if self.current_expression is None and final_override is None:
            return {"success": False, "error": "No result expression. Perform some derivation steps first."}

        verification_summary = self.verify_derivation()
        outcome, headline_fields = completion_outcome(
            self, verification_summary.get("failed_steps") or [], final_override
        )
        progress = self.compute_progress(current_override=final_override)
        target_reached = resolve_target_reached(progress.get("matches_target"), verification_summary.get("overall"))
        progress["matches_target"] = target_reached  # one judgment, two fields (r23 F12b)

        warnings: list[str] = []
        if not target_reached and self.goal is not None and self.goal.has_explicit_target():
            warnings.append("Current expression does not match the derivation target.")
        overall = verification_summary.get("overall")
        if overall != "verified":
            warnings.append(f"Verification status is '{overall}'; review the derivation before using it.")

        if require_target_match and not target_reached:
            self.status = SessionStatus.PAUSED
            self._update_timestamp()
            return {
                "success": False,
                "error": "Target expression not reached. Continue the derivation or call complete(require_target_match=False).",
                "session_id": self.session_id,
                "name": self.name,
                "status": self.status.value,
                "final_expression": str(outcome),
                "final_latex": sp.latex(outcome),
                "total_steps": self.step_count,
                "verification_summary": verification_summary,
                "goal": self.goal.to_dict() if self.goal else None,
                "progress": progress,
                "target_reached": target_reached,
                "warnings": warnings,
                **headline_fields,
            }

        self.status = SessionStatus.COMPLETED
        self._update_timestamp()

        # Create complete derivation record. Steps are summarized, not embedded:
        # full records stay behind get_steps() so the preview cannot hide the warnings above.
        result = {
            "success": True,
            "session_id": self.session_id,
            "name": self.name,
            "status": self.status.value,
            "total_steps": self.step_count,
            "warnings": warnings,
            "target_reached": target_reached,
            "final_expression": str(outcome),
            "final_latex": sp.latex(outcome),
            "steps_summary": steps_summary(self.steps),
            "formulas_used": {fid: f.to_dict() for fid, f in self.formulas.items()},
            "verification_summary": verification_summary,
            "goal": self.goal.to_dict() if self.goal else None,
            "progress": progress,
            **headline_fields,
            "provenance": {
                "created_at": self.created_at,
                "completed_at": self.updated_at,
                "author": self.author,
            },
        }

        if self._persist_path:
            self.save()

        return result

    # Persistence

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "pattern": self.pattern.value,
            "status": self.status.value,
            "formulas": {fid: f.to_dict() for fid, f in self.formulas.items()},
            "current_expression": str(self.current_expression) if self.current_expression is not None else None,
            "current_expression_srepr": sp.srepr(self.current_expression) if self.current_expression is not None else None,
            "current_formula_id": self.current_formula_id,
            "steps": [s.to_dict() for s in self.steps],
            "auto_verify": self.auto_verify,
            "goal": self.goal.to_dict() if self.goal else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "author": self.author,
            "tags": self.tags,
            "unit_declarations": self.symbol_registry.unit_declarations(),
        }

    def save(self, path: Path | None = None) -> Path:
        """Save the session to a file (``path`` overrides the persist path)."""
        save_path = path or self._persist_path
        if save_path is None:
            save_path = user_sessions_dir() / f"session_{self.session_id}.json"

        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

        self._persist_path = save_path
        # Persisting is orthogonal to state: an ACTIVE session stays ACTIVE (save keeps it)
        # PAUSED, producing the confusing "status: paused" on session_start).

        return save_path

    @classmethod
    def load(cls, path: Path) -> DerivationSession:
        """Load a session from a file (``path`` is also its new persist path)."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        session = cls(
            session_id=data["session_id"],
            name=data["name"],
            description=data.get("description", ""),
            domain=data.get("domain", ""),
            pattern=DerivationPattern.from_string(data.get("pattern", "direct-manipulation")),
            status=SessionStatus(data["status"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            author=data.get("author", ""),
            tags=data.get("tags", []),
        )

        # Restore formulas (simplified, only expression)
        for fid, fdata in data.get("formulas", {}).items():
            result = FormulaParser.parse(
                fdata["expression"],
                fid,
                source=FormulaSource(fdata.get("source", "user_input")),
            )
            if isinstance(result, Formula):
                session.formulas[fid] = result
                if session.domain:
                    session.symbol_registry.register_formula_symbols(
                        formula_id=fid,
                        symbol_names=list(result.symbol_names),
                        domain=session.domain,
                    )

        # Restore explicit unit declarations (the registry itself is not serialized)
        session.symbol_registry.restore_unit_declarations(data.get("unit_declarations"))

        # Restore current expression
        if data.get("current_expression"):
            session.current_expression = safe_load_expression(
                data["current_expression"],
                data.get("current_expression_srepr", ""),
            )
        session.current_formula_id = data.get("current_formula_id")

        # Restore steps
        session.steps = [DerivationStep.from_dict(s) for s in data.get("steps", [])]

        # Restore auto-verification toggle
        session.auto_verify = data.get("auto_verify", True)

        # Restore goal
        goal_data = data.get("goal")
        if goal_data:
            session.goal = DerivationGoal(
                text=goal_data.get("text", ""),
                target_expression=goal_data.get("target_expression"),
                target_form=goal_data.get("target_form"),
                domain=goal_data.get("domain", ""),
                assumptions=goal_data.get("assumptions", []),
            )
            session.goal.set_target_variables(
                goal_data.get("target_variables", []),
                explicit=goal_data.get("target_variables_explicit", False),
            )

        # Set persistence path
        session._persist_path = path

        # Restore to ACTIVE
        if session.status == SessionStatus.PAUSED:
            session.status = SessionStatus.ACTIVE

        return session


# ═══════════════════════════════════════════════════════════════════════════
# Session manager
# ═══════════════════════════════════════════════════════════════════════════


class SessionManager:
    """
    Session manager.

    Manages multiple derivation sessions and supports persistence.
    """

    def __init__(self, sessions_dir: Path | None = None):
        self.sessions: dict[str, DerivationSession] = {}
        self.sessions_dir = sessions_dir or user_sessions_dir()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        # Load existing sessions
        self._load_existing_sessions()

    def _load_existing_sessions(self) -> None:
        """Load existing sessions."""
        for session_file in self.sessions_dir.glob("session_*.json"):
            try:
                session = DerivationSession.load(session_file)
                self.sessions[session.session_id] = session
            except Exception:
                pass  # Skip corrupted files

    def create(
        self,
        name: str,
        description: str = "",
        domain: str = "",
        author: str = "",
        pattern: DerivationPattern = DerivationPattern.DIRECT_MANIPULATION,
        auto_persist: bool = True,
        external_adapters: list[FormulaSourceAdapter] | None = None,
    ) -> DerivationSession:
        """Create a new session."""
        session = DerivationSession(
            session_id="",  # Will be auto-generated
            name=name,
            description=description,
            domain=domain,
            pattern=pattern,
            author=author,
            external_adapters=external_adapters,
        )

        if auto_persist:
            session._persist_path = self.sessions_dir / f"session_{session.session_id}.json"
            session.save()

        self.sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> DerivationSession | None:
        """Get a session."""
        return self.sessions.get(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions."""
        return [
            {
                "session_id": s.session_id,
                "name": s.name,
                "status": s.status.value,
                "step_count": s.step_count,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in self.sessions.values()
        ]

    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id not in self.sessions:
            return False

        session = self.sessions.pop(session_id)
        if session._persist_path and session._persist_path.exists():
            session._persist_path.unlink()

        return True


# Global session manager
_manager: SessionManager | None = None


def get_session_manager(sessions_dir: Path | None = None) -> SessionManager:
    """Get the global session manager."""
    global _manager
    if _manager is None:
        _manager = SessionManager(sessions_dir)
    return _manager
