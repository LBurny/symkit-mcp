"""
Session Management Tools — Derivation session management

A lightweight session manager supporting:
- Starting / resuming / suspending / completing sessions
- Step rollback
- Status display
- Human knowledge notes
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sympy as sp

from symkit.domain.derivation_goal import DerivationGoal
from symkit.domain.derivation_pattern import (
    DerivationPattern,
    get_pattern_template,
)
from symkit.domain.derivation_session import DerivationSession
from symkit.domain.expression_parser import parse_user_expression
from symkit.domain.formula import FormulaSource
from symkit.infrastructure.derivation_repository import (
    DerivationResult,
    get_repository,
)
from symkit_mcp.tools._state import get_context, get_manager, get_session, set_session


def _detect_risks(session: DerivationSession) -> list[dict[str, str]]:
    """Analyze current expression for common risks."""
    risks: list[dict[str, str]] = []
    if session.current_expression is None:
        return risks

    expr = session.current_expression
    free_symbols = {str(s) for s in expr.free_symbols}

    # Risk: no free symbols (constant result)
    if not free_symbols:
        risks.append({
            "level": "info",
            "type": "constant_expression",
            "message": "Current expression has no free symbols — it is a constant.",
        })

    # Risk: symbols without assumptions
    ctx = get_context()
    symbols_without_assumptions = [
        s for s in free_symbols
        if s not in ctx.assumptions or not ctx.assumptions[s]
    ]
    if symbols_without_assumptions:
        risks.append({
            "level": "info",
            "type": "unconstrained_symbols",
            "message": (
                "Some symbols have no assumptions set: "
                f"{', '.join(symbols_without_assumptions)}. "
                "Consider using assume() to improve simplification and verification."
            ),
        })

    # Risk: exponential with potentially dimensional argument
    expr_str = str(expr)
    if "exp(" in expr_str:
        risks.append({
            "level": "info",
            "type": "dimensionless_argument",
            "message": "Expression contains exp(...). Ensure the argument is dimensionless.",
        })

    # Risk: assumption conflicts across levels
    assumption_conflicts = session.assumption_engine.detect_conflicts()
    for conflict in assumption_conflicts:
        risks.append({
            "level": "warning",
            "type": "assumption_conflict",
            "message": conflict["message"],
        })

    # Risk: symbol semantic conflicts
    symbol_conflicts = session.symbol_registry.detect_conflicts(list(free_symbols))
    for conflict in symbol_conflicts:
        risks.append({
            "level": "warning",
            "type": "symbol_semantic_conflict",
            "message": (
                f"'{conflict['symbol']}' is ambiguous: "
                f"{'; '.join(conflict['meanings'])}. "
                "Consider using register_symbol() to clarify."
            ),
        })

    return risks


def _verification_summary(session: DerivationSession) -> dict[str, Any]:
    """Return a human-readable verification summary for the session."""
    summary = session.verify_derivation()
    display_lines = [
        "🔍 Verification Summary:",
        f"  Verified: {summary['verified']}",
        f"  ✅ verified: {summary['verified']}",
        f"  ❌ failed: {summary['failed']}",
        f"  ⚠️ inconclusive: {summary['inconclusive']}",
    ]
    if summary.get("failed_steps"):
        display_lines.append(
            f"  Failed steps: {', '.join(str(s) for s in summary['failed_steps'])}"
        )
    if summary.get("inconclusive_steps"):
        display_lines.append(
            f"  Inconclusive steps: {', '.join(str(s) for s in summary['inconclusive_steps'])}"
        )
    if summary.get("assumption_conflicts"):
        display_lines.append(
            f"  ⚠️ assumption conflicts: {len(summary['assumption_conflicts'])}"
        )
    summary["display_text"] = "\n".join(display_lines)
    return summary


def _suggest_next_steps(session: DerivationSession) -> list[dict[str, Any]]:
    """Suggest next operations based on current state and domain."""
    suggestions = []

    if session.current_expression is None:
        suggestions.append({
            "tool": "math",
            "operation": "parse",
            "reason": "Load an expression to begin the derivation",
            "example": 'math("parse", "<expression>")',
        })
        return suggestions

    expr_str = str(session.current_expression)
    has_equation = "=" in expr_str or isinstance(session.current_expression, sp.Equality)
    has_multiple_symbols = len(session.current_expression.free_symbols) > 1

    # Domain-specific suggestions
    domain = session.domain or "general"
    if domain == "fluid_dynamics":
        suggestions.append({
            "tool": "math",
            "operation": "simplify",
            "reason": "Fluid derivations often need simplification after applying incompressibility",
            "example": 'math("simplify", "<current expression>")',
        })
    elif domain == "quantum_mechanics":
        suggestions.append({
            "tool": "math",
            "operation": "diff",
            "reason": "Quantum derivations often involve operator/differential substitutions",
            "example": 'math("diff", "<current expression>", variable="x")',
        })
    elif domain == "pharmacokinetics":
        suggestions.append({
            "tool": "math",
            "operation": "substitute",
            "reason": "Combine PK models by substituting one formula into another",
            "example": 'math("substitute", "<current expression>", substitution={"<var>": "<expr>"})',
        })

    # General suggestions
    if has_equation:
        suggestions.append({
            "tool": "math",
            "operation": "solve",
            "reason": "Solve the equation for a target variable",
            "example": 'math("solve", "<equation>", variable="<target>")',
        })
    elif has_multiple_symbols:
        suggestions.append({
            "tool": "math",
            "operation": "substitute",
            "reason": "Substitute a relationship to reduce the number of variables",
            "example": 'math("substitute", "<expression>", substitution={"<var>": "<replacement>"})',
        })
    else:
        suggestions.append({
            "tool": "math",
            "operation": "simplify",
            "reason": "Simplify the current expression",
            "example": 'math("simplify", "<expression>")',
        })

    suggestions.append({
        "tool": "session_explain",
        "reason": "Get a natural-language summary of the derivation so far",
        "example": "session_explain()",
    })

    suggestions.append({
        "tool": "session_complete",
        "reason": "Finalize and save the derivation when satisfied",
        "example": "session_complete(description=\"...\", assumptions=[\"...\"])",
    })

    return suggestions

def register_session_tools(mcp: Any) -> None:
    """Register session management tools."""

    @mcp.tool(
        meta={
            "category": "Session Management",
            "example": 'session_start("ns_derivation", domain="fluid_dynamics")',
        }
    )
    def session_start(
        name: str,
        description: str = "",
        domain: str = "general",
        pattern: str = "direct-manipulation",
        goal: str | None = None,
        author: str = "",
    ) -> dict[str, Any]:
        """
        Start a new derivation session

        Args:
            name: Derivation name
            description: Derivation description
            domain: Math/physics domain tag
            pattern: Derivation pattern
            goal: Natural-language goal (optional)
            author: Author

        Returns:
            Session information
        """
        manager = get_manager()
        session = manager.create(
            name=name,
            description=description,
            domain=domain,
            pattern=DerivationPattern.from_string(pattern),
            author=author,
            auto_persist=True,
        )
        if goal:
            parsed_goal = DerivationGoal.from_text(goal, domain=domain)
            session.set_goal(parsed_goal)
        set_session(session)

        return {
            "success": True,
            "session_id": session.session_id,
            "name": session.name,
            "domain": session.domain,
            "pattern": session.pattern.value,
            "goal": session.goal.to_dict() if session.goal else None,
            "status": session.status.value,
            "message": f"Session '{name}' started. Use math(session=True) for derivation steps.",
        }

    @mcp.tool()
    def session_resume(session_id: str) -> dict[str, Any]:
        """
        Resume a suspended derivation session

        Args:
            session_id: Session ID

        Returns:
            Session status
        """
        manager = get_manager()
        session = manager.get(session_id)

        if session is None:
            return {
                "success": False,
                "error": f"Session '{session_id}' not found",
                "available_sessions": [s["session_id"] for s in manager.list_sessions()],
            }

        set_session(session)
        return {
            "success": True,
            "session_id": session.session_id,
            "name": session.name,
            "domain": session.domain,
            "status": session.status.value,
        "step_count": session.step_count,
        "current_expression": str(session.current_expression)
        if session.current_expression is not None
        else None,
        "message": "Session resumed. Continue with math(session=True).",
    }

    @mcp.tool()
    def session_status() -> dict[str, Any]:
        """Get the current session status."""
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() or session_resume().",
            }
        return {"success": True, **session.get_current()}

    @mcp.tool(
        meta={
            "category": "Session Management",
            "example": "session_show(show_steps=True)",
        }
    )
    def session_show(show_steps: bool = False) -> dict[str, Any]:
        """
        Show the current derivation state and formula

        ⚠️ Must be called after each derivation operation to show the user the result!

        Args:
            show_steps: Whether to show all step history

        Returns:
            Current formula LaTeX and derivation state
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() first.",
                "display_text": "❌ No active derivation session.",
            }

        goal = session.goal.to_dict() if session.goal else None
        progress = session.compute_progress()
        recommended_formulas = session.recommend_formulas(top_k=3) if session.goal else []

        expr = session.current_expression
        if expr is None:
            base_display = f"📊 **{session.name}** (Step {len(session.steps)})\n\n_No formula loaded yet_"
            if goal:
                base_display += (
                    f"\n\n🎯 **Goal:** {goal['text']}\n"
                    f"**Target form:** {goal['target_form'] or 'derive_expression'}"
                )
                if goal.get('assumptions'):
                    base_display += f"\n**Assumptions:** {', '.join(goal['assumptions'])}"
            return {
                "success": True,
                "session_name": session.name,
                "step_count": len(session.steps),
                "status": session.status.value,
                "latex": "",
                "goal": goal,
                "progress": progress,
                "recommended_formulas": recommended_formulas,
                "display_text": base_display,
            }

        latex_str = sp.latex(expr)
        display_lines = [
            f"📊 **{session.name}** (Step {len(session.steps)}, {session.status.value})",
            f"🏷️ Domain: {session.domain or 'general'}",
        ]
        if goal:
            display_lines.append(f"🎯 Goal: {goal['text']}")
            display_lines.append(f"📈 Progress: {progress['progress_score']:.0%}")
            if goal.get('assumptions'):
                display_lines.append(f"📝 Assumptions: {', '.join(goal['assumptions'])}")
        display_lines.extend(["", "$$", f"{latex_str}", "$$"])
        display_text = "\n".join(display_lines)

        result = {
            "success": True,
            "session_name": session.name,
            "session_id": session.session_id,
            "domain": session.domain,
            "step_count": len(session.steps),
            "status": session.status.value,
            "latex": latex_str,
            "sympy": str(expr),
            "goal": goal,
            "progress": progress,
            "recommended_formulas": recommended_formulas,
            "display_text": display_text,
        }

        if show_steps and session.steps:
            steps_summary = []
            for step in session.steps:
                steps_summary.append({
                    "step": step.step_number,
                    "operation": step.operation.value,
                    "description": (step.description[:60] + "..." if len(step.description) > 60
                                    else step.description),
                    "latex": step.output_latex or step.output_expression,
                })
            result["steps"] = steps_summary

        # Collect next-step suggestions and risks
        next_steps = _suggest_next_steps(session)
        risks = _detect_risks(session)
        verification = _verification_summary(session)
        goal_steps = session.plan_next_steps(max_steps=3) if session.goal else []

        # Use pattern recorded in session (fallback to direct-manipulation)
        pattern_used = session.pattern.value

        result.update({
            "next_steps": next_steps[:3],
            "goal_steps": goal_steps,
            "risks": risks,
            "verification_summary": verification,
            "pattern_used": pattern_used,
            "pattern_description": get_pattern_template(
                DerivationPattern.from_string(pattern_used)
            ).description,
        })

        # Enhance display text with suggestions and risks
        display_lines = [result["display_text"]]
        if goal_steps:
            display_lines.append("\n🧭 **Goal-aware next steps:**")
            for s in goal_steps:
                op = s.get("operation", "")
                display_lines.append(f"- `{s['tool']}` ({op}): {s['reason']}")
        elif next_steps:
            display_lines.append("\n💡 **Next steps:**")
            for s in next_steps[:3]:
                op = s.get("operation", "n/a")
                display_lines.append(f"- `{s['tool']}` ({op}): {s['reason']}")
        if recommended_formulas:
            display_lines.append("\n📚 **Recommended formulas:**")
            for f in recommended_formulas:
                display_lines.append(f"- `{f['formula_id']}` ({f.get('name', '')}): {f.get('reason', '')}")
        if risks:
            display_lines.append("\n⚠️ **Risks / Notes:**")
            for r in risks:
                display_lines.append(f"- {r['message']}")
        display_lines.append("\n" + verification["display_text"])
        result["display_text"] = "\n".join(display_lines)

        return result

    @mcp.tool(
        meta={
            "category": "Session Management",
            "example": "session_explain(level='medium')",
        }
    )
    def session_explain(
        level: str = "medium",
        focus: str | None = None,
    ) -> dict[str, Any]:
        """
        🗣️ Explain the current derivation in natural language.

        Generates a human-readable summary of the derivation so far, including:
        - The overall goal (session name/description)
        - What formulas were loaded
        - What operations were performed and why
        - Key assumptions and limitations recorded
        - The current result

        Args:
            level: Detail level — "short", "medium" (default), or "detailed"
            focus: Optional aspect to focus on ("assumptions", "steps", "result")

        Returns:
            Natural-language summary and structured metadata
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() first.",
                "display_text": "❌ No active session to explain.",
            }

        lines: list[str] = []
        lines.append(f"**{session.name}**")
        if session.goal:
            lines.append(f"🎯 Goal: {session.goal.text}")
            if session.goal.target_expression:
                lines.append(f"🎯 Target expression: {session.goal.target_expression}")
            if session.goal.assumptions:
                lines.append(f"📝 Assumptions: {', '.join(session.goal.assumptions)}")
        elif session.description:
            lines.append(f"Goal: {session.description}")
        lines.append(f"Domain: {session.domain or 'general'} | Step {len(session.steps)}")

        # Progress
        progress = session.compute_progress()
        if progress.get("has_goal"):
            lines.append(f"📈 Progress: {progress['progress_score']:.0%}")
            if progress['matches_target']:
                lines.append("✅ Current expression matches the target.")
            if progress['remaining_gaps']:
                lines.append(f"Remaining gaps: {', '.join(progress['remaining_gaps'])}")

        # Formulas loaded
        if session.formulas:
            lines.append("\n**Base formulas loaded:**")
            for fid, formula in session.formulas.items():
                lines.append(f"- `{fid}`: {formula.sympy_str}")

        # Step summary
        if session.steps:
            lines.append("\n**Derivation steps:**")
            for step in session.steps:
                op = step.operation.value
                desc = step.description
                lines.append(f"{step.step_number}. *{op}* — {desc}")
                if step.assumptions:
                    lines.append(f"   - Assumptions: {', '.join(step.assumptions)}")
                if step.limitations:
                    lines.append(f"   - Limitations: {', '.join(step.limitations)}")
        else:
            lines.append("\n_No steps recorded yet._")

        # Current result
        if session.current_expression is not None:
            lines.append(f"\n**Current result:** {sp.latex(session.current_expression)}")
        else:
            lines.append("\n_No current expression._")

        # Verification status
        verification = _verification_summary(session)
        lines.append(f"\n{verification['display_text']}")
        if verification.get("assumption_conflicts"):
            lines.append("⚠️ Resolve assumption conflicts before trusting the derivation.")

        # Focus handling
        if focus == "assumptions":
            all_assumptions = list(session.goal.assumptions) if session.goal else []
            for step in session.steps:
                all_assumptions.extend(step.assumptions)
            # Deduplicate while preserving order
            seen: set[str] = set()
            unique_assumptions = []
            for a in all_assumptions:
                if a not in seen:
                    seen.add(a)
                    unique_assumptions.append(a)
            lines.append(f"\n**All recorded assumptions:** {', '.join(unique_assumptions) if unique_assumptions else 'None'}")
        elif focus == "steps":
            lines.append("\n_Focus on steps shown above._")
        elif focus == "result":
            if session.current_expression is not None:
                lines.append(f"\n_Focus on result:_ `{str(session.current_expression)}`")

        # Limit detail level
        display_text = "\n".join(lines)
        if level == "short":
            display_text = (
                f"**{session.name}** ({len(session.steps)} steps) — "
                f"current: {sp.latex(session.current_expression) if session.current_expression is not None else 'none'}"
            )

        return {
            "success": True,
            "session_name": session.name,
            "session_id": session.session_id,
            "domain": session.domain,
            "step_count": len(session.steps),
            "level": level,
            "focus": focus,
            "summary": display_text,
            "display_text": display_text,
        }

    @mcp.tool()
    def session_complete(
        description: str = "",
        application_context: str = "",
        assumptions: list[str] | None = None,
        limitations: list[str] | None = None,
        references: list[str] | None = None,
        tags: list[str] | None = None,
        auto_save: bool = True,
        require_target_match: bool = False,
    ) -> dict[str, Any]:
        """
        Complete the derivation and auto-save

        Args:
            description: Formula description (physical/mathematical meaning)
            application_context: Usage context (when to use this formula)
            assumptions: Derivation assumptions
            limitations: Usage limitations
            references: References
            tags: Tags
            auto_save: Whether to auto-save (default True)
            require_target_match: If True, the derivation will only be saved as
                completed when the current expression matches the goal target.
                Default is False for backward compatibility, but a warning is
                still returned if the target is not reached.

        Returns:
            Complete derivation record
        """
        session = get_session()
        if session is None:
            return {"success": False, "error": "No active session."}

        result = session.complete(require_target_match=require_target_match)
        if not result.get("success"):
            return result

        verification_summary = result.get("verification_summary", {})
        warnings = list(result.get("warnings", []))
        is_verified = (
            verification_summary.get("overall") == "verified"
            and verification_summary.get("total", 0) > 0
        )
        verification_method = "step_verifier" if is_verified else ""
        verified_at = datetime.now().isoformat() if is_verified else None

        saved_path = None
        if auto_save:
            try:
                # Use the global repository singleton (defaults to the per-user
                # derived-formula directory) rather than a CWD-relative path.
                repo = get_repository()
                derivation_result = DerivationResult(
                    id=session.session_id,
                    name=session.name,
                    expression=str(session.current_expression),
                    variables={
                        str(s): {"description": "", "unit": ""}
                        for s in (session.current_expression.free_symbols
                                  if session.current_expression is not None else [])
                    },
                    derived_from=list(session.formulas.keys()),
                    derivation_steps=[step["description"] for step in result["steps"]],
                    assumptions=assumptions or [],
                    verified=is_verified,
                    verification_method=verification_method,
                    verified_at=verified_at,
                    description=description,
                    domain=session.domain,
                    application_context=application_context,
                    limitations=limitations or [],
                    references=references or [],
                    tags=tags or [],
                    author=session.author,
                    category=session.domain or "derived",
                )
                repo.register(derivation_result)
                saved_path = repo.save(session.session_id)
            except Exception as e:
                warnings.append(f"Completed but save failed: {e}")

        set_session(None)
        if saved_path:
            result["saved_to"] = str(saved_path)
            result["message"] = f"Derivation completed and saved to {saved_path}"
        if warnings:
            result["warnings"] = warnings
        return result

    @mcp.tool()
    def session_rollback(to_step: int) -> dict[str, Any]:
        """
        Roll back to the specified step

        Keep steps up to and including the specified step, and delete steps after it.
        After rolling back, you can continue the derivation from that step (taking a different path).

        Args:
            to_step: Step number to roll back to (1-based); 0 = clear all

        Returns:
            Rollback result
        """
        session = get_session()
        if session is None:
            return {"success": False, "error": "No active session."}
        return session.rollback_to_step(to_step)

    @mcp.tool()
    def session_abort() -> dict[str, Any]:
        """
        Suspend the current derivation (session is saved to disk)

        Returns:
            Operation result
        """
        session = get_session()
        if session is None:
            return {"success": False, "error": "No active session."}
        session_id = session.session_id
        session.save()
        set_session(None)
        return {
            "success": True,
            "message": f"Session '{session_id}' saved. Use session_resume('{session_id}') to continue.",
            "session_id": session_id,
        }

    @mcp.tool()
    def session_add_note(
        note: str,
        note_type: str = "observation",
        related_variables: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Add a human knowledge note to the derivation (non-computational step)

        Args:
            note: Note content
            note_type: "assumption", "limitation", "observation",
                       "correction", "interpretation", "application", "reference"
            related_variables: Related variables

        Returns:
            Record result
        """
        session = get_session()
        if session is None:
            return {"success": False, "error": "No active session."}
        return session.insert_note_after_step(
            after_step=len(session.steps),
            note=note,
            note_type=note_type,
            related_variables=related_variables,
        )

    @mcp.tool()
    def session_list() -> dict[str, Any]:
        """List all saved derivation sessions."""
        manager = get_manager()
        sessions = manager.list_sessions()
        return {
            "success": True,
            "sessions": sessions,
            "count": len(sessions),
        }

    @mcp.tool(
        meta={
            "category": "Session Management",
            "example": 'session_load_formula("x**2 + 3*x")',
        }
    )
    def session_load_formula(
        expression: str,
        formula_id: str | None = None,
        source: str = "user_input",
    ) -> dict[str, Any]:
        """Load a formula into the current session.

        Correct workflow for derivation from an external source:
            1. formula_search("<concept>", domain="<domain>")
            2. formula_get(result["id"], source=result["source"], load_into_session=True)
            3. math(..., session=True) to derive or transform
            4. session_complete(...) to finalize and save

        Args:
            expression: Formula or expression string (e.g. "rho * v * L / mu" or
                       a LaTeX string). For formulas loaded via formula_get, you can
                       pass formula["sympy_str"] or formula["latex"].
            formula_id: Optional custom formula ID.
            source: Source label (e.g. "user_input", "scipy", "wikidata").

        Returns:
            Load result with formula_id, expression and LaTeX.
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() first.",
            }
        try:
            formula_source = FormulaSource(source)
        except ValueError:
            formula_source = FormulaSource.USER_INPUT
        return session.load_formula(
            expression,
            formula_id=formula_id,
            source=formula_source,
            source_detail=source,
        )

    @mcp.tool(
        meta={
            "category": "Session Management",
            "example": 'session_set_goal("derive work-energy theorem", target_expression="W = ΔK")',
        }
    )
    def session_set_goal(
        goal: str,
        target_expression: str | None = None,
    ) -> dict[str, Any]:
        """Set a natural-language derivation goal for the current session.

        Args:
            goal: Natural-language goal text.
            target_expression: Optional explicit target expression (e.g.
                "v = sqrt(2*G*M/R)").  When provided, it overrides the
                automatically-extracted target expression.

        Returns:
            Parsed goal and session status.
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() first.",
            }
        parsed_goal = DerivationGoal.from_text(goal, domain=session.domain)
        if target_expression:
            parsed_goal.target_expression = target_expression
        session.set_goal(parsed_goal)
        return {
            "success": True,
            "goal": parsed_goal.to_dict(),
            "session_id": session.session_id,
            "message": f"Goal set: {parsed_goal.text}",
        }

    @mcp.tool(
        meta={
            "category": "Session Management",
            "example": "session_suggest_formulas()",
        }
    )
    def session_suggest_formulas(top_k: int = 5) -> dict[str, Any]:
        """Suggest formulas that may help reach the current session goal.

        Args:
            top_k: Maximum number of suggestions.

        Returns:
            List of recommended formulas with rationale.
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() first.",
            }
        if session.goal is None:
            return {
                "success": False,
                "error": "No goal set. Use session_set_goal() first.",
            }
        recommendations = session.recommend_formulas(top_k=top_k)
        return {
            "success": True,
            "recommendations": recommendations,
            "count": len(recommendations),
            "session_id": session.session_id,
        }

    @mcp.tool(
        meta={
            "category": "Session Management",
            "example": 'session_record_step("x**2 + 1", "hand-calculated result")',
        }
    )
    def session_record_step(
        expression: str,
        description: str,
        operation: str = "custom",  # noqa: ARG001
        notes: str = "",
        assumptions: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        """Manually record a derivation step (e.g. a result computed outside the tool).

        The ``expression`` argument is parsed through the unified parser, which
        supports SymPy strings, natural equations (``A = B``), Leibniz derivative
        notation (``dX/dY``), Greek/Unicode math, and LaTeX.

        Args:
            expression: Result expression string (SymPy or LaTeX).
            description: Human-readable step description.
            operation: Ignored. Manual steps are always recorded as OperationType.CUSTOM
                to prevent a user-supplied operation label (e.g. "simplify") from being
                falsely reported as automatically verified.
            notes: Human insight / observation.
            assumptions: Step-specific assumptions.
            limitations: Step-specific limitations.

        Returns:
            Recorded step details.
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() first.",
            }

        new_expr, error = parse_user_expression(expression)
        if new_expr is None:
            return {
                "success": False,
                "error": f"Cannot parse expression '{expression}': {error}",
            }

        from symkit.domain.derivation_session import OperationType

        # Manually recorded steps have unknown provenance, so they must not be
        # disguised as automatically verifiable canonical operations (e.g.,
        # simplify/differentiate), otherwise the verification results would appear
        # successful without any mathematical check having been performed. Therefore,
        # they are uniformly marked as CUSTOM.
        op_type = OperationType.CUSTOM

        prior = session.current_expression
        session.current_expression = new_expr
        step = session._add_step(
            operation=op_type,
            description=description,
            input_expressions={"original": expression},
            output_expr=new_expr,
            sympy_command="manual_record",  # Non-executable descriptor to avoid being run as SymPy code
            notes=notes,
            assumptions=assumptions,
            limitations=limitations,
            prior_expr=prior,
        )
        return {
            "success": True,
            "step": step.to_dict(),
            "step_number": step.step_number,
            "expression": str(new_expr),
            "latex": sp.latex(new_expr),
            "verification_status": step.status.value,
        }

    @mcp.tool(
        meta={
            "category": "Session Management",
            "example": "session_get_steps()",
        }
    )
    def session_get_steps() -> dict[str, Any]:
        """Return all recorded steps in the current session.

        Returns:
            List of steps with metadata.
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() first.",
            }
        steps = session.get_steps()
        return {
            "success": True,
            "steps": steps,
            "count": len(steps),
            "session_id": session.session_id,
        }

    @mcp.tool(
        meta={
            "category": "Session Management",
            "example": "session_verify_step(1)",
        }
    )
    def session_verify_step(step_number: int = -1) -> dict[str, Any]:
        """Re-verify a single step in the current session.

        Args:
            step_number: 1-based step number. Defaults to -1 (last step).

        Returns:
            Verification result.
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() first.",
            }
        if step_number <= 0:
            step_number = len(session.steps)
        return session.verify_step(step_number)

    @mcp.tool(
        meta={
            "category": "Session Management",
            "example": "session_verify_session()",
        }
    )
    def session_verify_session() -> dict[str, Any]:
        """Verify the entire derivation chain in the current session.

        Returns:
            Summary with total, verified, failed and inconclusive counts.
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() first.",
            }
        summary = _verification_summary(session)
        return {"success": True, **summary}
