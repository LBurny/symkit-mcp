"""Orchestration Tools — High-level derivation and intent routing

Provides:
- derive(): One-shot high-level derivation entry point
- intent_execute(): Natural language intent routing
- list_patterns(): List available derivation patterns
- tool_categories(): Categorized tool index
- tool_recommend(): Recommend tools based on current session/task

These tools sit above the 59 low-level tools and make SymKit easier
to use for both end users and LLM agents.
"""

from __future__ import annotations

import re
from typing import Any

from symkit.domain.derivation_goal import DerivationGoal
from symkit.domain.derivation_pattern import (
    DerivationPattern,
    get_pattern_template,
)
from symkit.domain.derivation_pattern import (
    list_patterns as _list_patterns,
)
from symkit.domain.derivation_session import DerivationSession
from symkit.domain.formula import FormulaSource
from symkit.domain.formula_recommender import (
    FormulaInfoAdapter,
    FormulaSourceAdapter,
    create_all_external_adapters,
    create_default_external_adapters,
)
from symkit_mcp.tools._state import get_manager, set_session


def _slugify(name: str) -> str:
    """Convert a goal/description into a snake_case session name."""
    s = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[-\s]+", "_", s)[:64]


def _parse_assumption(assumption: str) -> tuple[str, list[str]] | None:
    """Parse simple assumption strings like 'x is positive real'."""
    parts = assumption.strip().split()
    if len(parts) >= 3 and parts[1] == "is":
        return parts[0], parts[2:]
    # Also support "x > 0" or "x: positive" but only extract variable name for now
    if assumption:
        return parts[0], [" ".join(parts[1:])]
    return None


def _build_external_adapters(
    sources: list[str] | None,
) -> list[FormulaSourceAdapter]:
    """Build a list of external formula adapter wrappers from the source names.

    ``sources=None`` is treated as requesting all external sources, consistent with
    the ``derive`` documentation.
    """
    if sources is None:
        return create_all_external_adapters()

    source_set = {s.lower().strip() for s in sources}
    if "all" in source_set:
        return create_all_external_adapters()
    if not source_set:
        return create_default_external_adapters()

    adapters: list[FormulaSourceAdapter] = []
    if "scipy" in source_set:
        try:
            from symkit.infrastructure.adapters import ScipyConstantsAdapter

            adapters.append(FormulaInfoAdapter(ScipyConstantsAdapter()))
        except Exception:
            pass
    if "wikidata" in source_set:
        try:
            from symkit.infrastructure.adapters import get_wikidata_adapter

            adapters.append(FormulaInfoAdapter(get_wikidata_adapter()))
        except Exception:
            pass
    if "biomodels" in source_set:
        try:
            from symkit.infrastructure.adapters import get_biomodels_adapter

            adapters.append(FormulaInfoAdapter(get_biomodels_adapter()))
        except Exception:
            pass

    return adapters


def _load_given_formulas(
    session: DerivationSession,
    given: list[str] | None,
) -> list[dict[str, Any]]:
    """Load base formulas into a session, returning load results."""
    results: list[dict[str, Any]] = []
    if not given:
        return results

    for idx, item in enumerate(given, start=1):
        formula_id = f"given_{idx}"
        # Try to extract a name from equation-like strings "name = expr"
        if "=" in item:
            lhs, _ = item.split("=", 1)
            lhs_clean = lhs.strip()
            if lhs_clean and " " not in lhs_clean and not any(
                c in lhs_clean for c in "+-*/()^"
            ):
                formula_id = f"given_{lhs_clean}"

        result = session.load_formula(
            formula_input=item,
            formula_id=formula_id,
            source=FormulaSource.USER_INPUT,
            name=formula_id,
        )
        results.append({"formula_id": formula_id, "input": item, "result": result})
    return results


def _build_initial_plan(
    pattern: DerivationPattern,
    goal: str,
    given: list[str] | None,
) -> dict[str, Any]:
    """Build a recommended plan based on the selected derivation pattern."""
    template = get_pattern_template(pattern)
    steps = list(template.typical_steps)

    # Tailor first step if user provided explicit given formulas
    if given:
        steps[0] = f"Load {len(given)} base formula(s) into the session"

    return {
        "pattern": pattern.value,
        "pattern_description": template.description,
        "goal": goal,
        "recommended_steps": steps,
        "suggested_operations": template.suggested_operations,
        "typical_verifications": template.typical_verifications,
    }


def register_orchestration_tools(mcp: Any) -> None:
    """Register high-level orchestration tools."""

    @mcp.tool(
        meta={
            "category": "High-Level Orchestration",
            "example": 'derive("derive incompressible NS", given=["continuity", "momentum"], domain="fluid_dynamics", pattern="conservation+constitutive")',
        }
    )
    def derive(
        goal: str,
        given: list[str] | None = None,
        assumptions: list[str] | None = None,
        domain: str = "general",
        pattern: str | None = None,
        target_expression: str | None = None,
        auto_load: bool = True,
        external_sources: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        🚀 High-level derivation entry point — start a derivation from a goal.

        Args:
            goal: Natural-language description of what to derive
            given: Base formulas or expressions to load as starting points
            assumptions: List of assumptions (e.g., ["rho is positive"])
            domain: Math/physics domain (e.g., "fluid_dynamics")
            pattern: Derivation pattern. If None, auto-selected from goal.
            target_expression: Expected final SymPy expression (optional)
            auto_load: If True, load the given formulas into the session
            external_sources: External formula sources to include in recommendations
                (e.g., ["wikidata", "biomodels", "scipy"] or ["all"]).
                Defaults to all sources; network failures are silently ignored.

        Returns:
            Session info + goal + derivation plan + recommended formulas + next steps
        """
        # Parse goal and auto-select pattern from goal if not provided
        parsed_goal = DerivationGoal.from_text(goal, domain=domain)
        if target_expression:
            parsed_goal.target_expression = target_expression
        selected_pattern = (
            DerivationPattern.from_string(pattern)
            if pattern
            else DerivationPattern.from_goal(parsed_goal)
        )

        manager = get_manager()
        session_name = _slugify(goal) or "derivation"
        external_adapters = _build_external_adapters(external_sources)
        session = manager.create(
            name=session_name,
            description=goal,
            domain=domain,
            pattern=selected_pattern,
            auto_persist=True,
            external_adapters=external_adapters,
        )
        session.set_goal(parsed_goal)
        set_session(session)

        # Apply assumptions to global math context and session assumption engine.
        # Explicit assumptions (e.g. "G is positive") are applied to the engine;
        # goal-derived keywords are kept for display.
        from symkit.domain.assumption_engine import AssumptionLevel
        from symkit_mcp.tools._state import get_context, set_context

        all_applied: list[str] = list(assumptions or [])
        ctx = get_context()
        if assumptions:
            for a in assumptions:
                parsed = _parse_assumption(a)
                if parsed:
                    var, props = parsed
                    prop_list = [p for p in props if p]
                    if prop_list:
                        ctx = ctx.with_assumption(var, **dict.fromkeys(prop_list, True))
                        session.assumption_engine.assume(
                            var, *prop_list, level=AssumptionLevel.SESSION
                        )
            set_context(ctx)

        # Make explicit assumptions visible in the goal object and response.
        if all_applied:
            parsed_goal.assumptions = list(dict.fromkeys(parsed_goal.assumptions + all_applied))

        # Load given formulas
        loaded = []
        if auto_load and given:
            loaded = _load_given_formulas(session, given)

        # Build plan from pattern
        plan = _build_initial_plan(selected_pattern, goal, given)

        # Goal-aware formula recommendations and next steps
        recommended_formulas = session.recommend_formulas(top_k=5)
        goal_next_steps = session.plan_next_steps(max_steps=5)

        # Collect conflicts
        all_symbol_names: set[str] = set()
        for r in loaded:
            all_symbol_names.update(r["result"].get("variables", []))
        symbol_conflicts = session.symbol_registry.detect_conflicts(list(all_symbol_names))
        assumption_conflicts = session.assumption_engine.detect_conflicts()

        progress = session.compute_progress()

        return {
            "success": True,
            "session_id": session.session_id,
            "session_name": session.name,
            "domain": session.domain,
            "pattern": plan["pattern"],
            "pattern_description": plan["pattern_description"],
            "goal": parsed_goal.to_dict(),
            "assumptions_applied": all_applied,
            "formulas_loaded": len(loaded),
            "loaded_formulas": [
                {
                    "formula_id": r["formula_id"],
                    "input": r["input"],
                    "success": r["result"].get("success", False),
                    "expression": r["result"].get("expression"),
                }
                for r in loaded
            ],
            "recommended_formulas": recommended_formulas,
            "plan": plan,
            "recommended_next_steps": goal_next_steps,
            "progress": progress,
            "symbol_conflicts": symbol_conflicts,
            "assumption_conflicts": assumption_conflicts,
            "has_warnings": bool(symbol_conflicts or assumption_conflicts),
            "display_text": (
                f"🚀 **Derivation Started: {session.name}**\n\n"
                f"**Goal:** {goal}\n"
                f"**Domain:** {domain}\n"
                f"**Pattern:** {plan['pattern']} — {plan['pattern_description']}\n\n"
                f"**Formulas loaded:** {len(loaded)}\n"
                f"**Recommended formulas:** {len(recommended_formulas)}\n"
                f"**Progress:** {progress['progress_score']:.0%}"
                + (
                    "\n\n⚠️ **Warnings detected:**\n"
                    + "\n".join(f"- {c['message']}" for c in assumption_conflicts)
                    + "\n".join(f"- '{c['symbol']}' is ambiguous" for c in symbol_conflicts)
                    if symbol_conflicts or assumption_conflicts
                    else ""
                )
            ),
        }

    @mcp.tool(
        meta={
            "category": "High-Level Orchestration",
            "example": 'intent_execute("derive Navier-Stokes equations")',
        }
    )
    def intent_execute(
        intent: str,
        expression: str | None = None,
        variable: str | None = None,
        session: bool = True,
    ) -> dict[str, Any]:
        """
        🎯 Natural-language intent router — map a request to the right tool chain.

        Understands common math/derivation intents and returns the recommended
        tool(s) to call. The agent can then execute the recommended tool(s) directly.

        Args:
            intent: Natural language request
                    (e.g., "derive NS equations", "simplify this", "verify derivative", "solve for x")
            expression: Optional expression to operate on
            variable: Optional variable for differentiation/solving
            session: Whether to use session-based derivation (default True)

        Returns:
            intent_type, recommended tool chain, and examples

        Example:
            intent_execute("derive the temperature corrected elimination rate",
                           expression="C0 * exp(-k*t)")
        """
        intent_lower = intent.lower()

        # Intent classification
        intent_type = "direct"
        if any(k in intent_lower for k in ("derive", "推导", "obtain", "get the equation")):
            intent_type = "derive"
        elif any(k in intent_lower for k in ("simplify", "化简", "reduce")):
            intent_type = "simplify"
        elif any(k in intent_lower for k in ("verify", "验证", "check", "validate")):
            intent_type = "verify"
        elif any(k in intent_lower for k in ("solve", "求解", "isolate")):
            intent_type = "solve"
        elif any(k in intent_lower for k in ("compare", "比较", "difference")):
            intent_type = "compare"
        elif any(k in intent_lower for k in ("explain", "解释", "describe", "meaning")):
            intent_type = "explain"
        elif any(k in intent_lower for k in ("differentiate", "微分", "derivative")):
            intent_type = "differentiate"
        elif any(k in intent_lower for k in ("integrate", "积分", "integral")):
            intent_type = "integrate"

        # Build recommendation
        tool_chain = []
        if intent_type == "derive":
            tool_chain = [
                {
                    "tool": "derive",
                    "reason": "Start a structured derivation with goal and base formulas",
                    "example": 'derive("<your goal>", given=["<formula1>", "<formula2>"], domain="<domain>")',
                }
            ]
        elif intent_type == "simplify":
            tool_chain = [
                {
                    "tool": "math",
                    "operation": "simplify",
                    "reason": "Simplify the given expression",
                    "example": f'math("simplify", "{expression or "<expression>"}", session={session})',
                }
            ]
        elif intent_type == "differentiate":
            tool_chain = [
                {
                    "tool": "math",
                    "operation": "diff",
                    "reason": "Differentiate with respect to the variable",
                    "example": f'math("diff", "{expression or "<expression>"}", variable="{variable or "x"}", session={session})',
                }
            ]
        elif intent_type == "integrate":
            tool_chain = [
                {
                    "tool": "math",
                    "operation": "integrate",
                    "reason": "Integrate with respect to the variable",
                    "example": f'math("integrate", "{expression or "<expression>"}", variable="{variable or "x"}", session={session})',
                }
            ]
        elif intent_type == "verify":
            tool_chain = [
                {
                    "tool": "math",
                    "operation": "simplify",
                    "reason": "Simplify the expression to verify it reduces to the expected form",
                    "example": f'math("simplify", "{expression or "<expression>"}", session={session})',
                }
            ]
        elif intent_type == "solve":
            tool_chain = [
                {
                    "tool": "math",
                    "operation": "solve",
                    "reason": "Solve for the specified variable",
                    "example": f'math("solve", "{expression or "<equation>"}", variable="{variable or "x"}", session={session})',
                }
            ]
        elif intent_type == "compare":
            tool_chain = [
                {
                    "tool": "math",
                    "operation": "simplify",
                    "reason": "Simplify the difference of two expressions to check equivalence",
                    "example": 'math("simplify", "<expr1> - <expr2>", session=True)',
                }
            ]
        elif intent_type == "explain":
            tool_chain = [
                {
                    "tool": "session_explain",
                    "reason": "Get a natural-language summary of the derivation",
                    "example": "session_explain()",
                }
            ]
        else:
            tool_chain = [
                {
                    "tool": "intent_execute",
                    "reason": "Intent was not recognized; try rephrasing or use tool_recommend",
                    "example": f'intent_execute("{intent}")',
                }
            ]

        return {
            "success": True,
            "intent": intent,
            "intent_type": intent_type,
            "expression": expression,
            "variable": variable,
            "use_session": session,
            "recommended_tool_chain": tool_chain,
            "display_text": (
                f"🎯 **Intent:** {intent_type}\n\n"
                f"'{intent}'\n\n"
                f"**Recommended tool chain:**\n" +
                "\n".join(f"- {t['tool']}: {t['reason']}" for t in tool_chain)
            ),
        }

    @mcp.tool(
        meta={
            "category": "High-Level Orchestration",
            "example": "list_patterns()",
        }
    )
    def list_patterns() -> dict[str, Any]:
        """
        📋 List all available derivation patterns.

        Returns:
            Descriptions, typical steps, and suggested operations for each pattern.
        """
        return _list_patterns()

    @mcp.tool(
        meta={
            "category": "High-Level Orchestration",
            "example": "tool_categories()",
        }
    )
    def tool_categories() -> dict[str, Any]:
        """
        🧰 List SymKit tools organized by category.

        Returns:
            Categorized tool index with descriptions and examples.
        """
        return {
            "categories": [
                {
                    "name": "High-Level Orchestration",
                    "description": "Goal-driven derivation and intent routing",
                    "tools": [
                        "derive",
                        "intent_execute",
                        "list_patterns",
                        "tool_categories",
                        "tool_recommend",
                    ],
                },
                {
                    "name": "Unified Math",
                    "description": "Mathematica-style single-entry math operations",
                    "tools": ["math", "assume", "show_assumptions"],
                },
                {
                    "name": "Session Management",
                    "description": "Create, resume, and control derivation sessions",
                    "tools": [
                        "session_start",
                        "session_resume",
                        "session_status",
                        "session_show",
                        "session_explain",
                        "session_complete",
                        "session_rollback",
                        "session_add_note",
                        "session_list",
                        "session_load_formula",
                        "session_set_goal",
                        "session_suggest_formulas",
                        "session_record_step",
                        "session_get_steps",
                        "session_verify_step",
                        "session_verify_session",
                    ],
                },
                {
                    "name": "Formula Search",
                    "description": "Find base formulas from external sources",
                    "tools": [
                        "formula_search",
                        "formula_get",
                        "formula_constants",
                        "formula_pk_models",
                        "formula_kinetic_laws",
                        "formula_categories",
                    ],
                },
                {
                    "name": "Code Generation",
                    "description": "Generate executable code and reports",
                    "tools": [
                        "generate_python_function",
                        "generate_latex_derivation",
                        "generate_derivation_report",
                        "generate_sympy_script",
                    ],
                },
            ]
        }

    @mcp.tool(
        meta={
            "category": "High-Level Orchestration",
            "example": 'tool_recommend("simplify a polynomial")',
        }
    )
    def tool_recommend(
        task: str,
        domain: str = "general",
    ) -> dict[str, Any]:
        """
        💡 Recommend the best tool(s) for a given task.

        Args:
            task: Brief description of what you want to do
            domain: Optional domain context

        Returns:
            Recommended tool with rationale and example
        """
        task_lower = task.lower()
        recommendations = []

        if any(k in task_lower for k in ("derive", "推导", "obtain")):
            recommendations.append({
                "tool": "derive",
                "rationale": "Use goal-driven derivation for complex multi-step derivations",
                "example": 'derive("<goal>", given=["<formula1>", "<formula2>"], domain="<domain>")',
            })
        elif any(k in task_lower for k in ("simplify", "化简", "reduce")):
            recommendations.append({
                "tool": "math",
                "operation": "simplify",
                "rationale": "Unified math tool handles all simplification needs",
                "example": 'math("simplify", "<expression>")',
            })
        elif any(k in task_lower for k in ("differentiate", "微分", "derivative")):
            recommendations.append({
                "tool": "math",
                "operation": "diff",
                "rationale": "Differentiate any expression with respect to a variable",
                "example": 'math("diff", "<expression>", variable="x", order=1)',
            })
        elif any(k in task_lower for k in ("integrate", "积分", "integral")):
            recommendations.append({
                "tool": "math",
                "operation": "integrate",
                "rationale": "Integrate with respect to a variable, definite or indefinite",
                "example": 'math("integrate", "<expression>", variable="x")',
            })
        elif any(k in task_lower for k in ("solve", "求解", "isolate")):
            recommendations.append({
                "tool": "math",
                "operation": "solve",
                "rationale": "Solve equation or expression for a variable",
                "example": 'math("solve", "<equation>", variable="x")',
            })
        elif any(k in task_lower for k in ("verify", "验证", "check")):
            recommendations.append({
                "tool": "math",
                "operation": "simplify",
                "rationale": "Simplify the difference of two expressions to verify equality",
                "example": 'math("simplify", "<expr1> - <expr2>", session=False)',
            })
        elif any(k in task_lower for k in ("dimension", "量纲", "unit")):
            recommendations.append({
                "tool": "math",
                "operation": "simplify",
                "rationale": "Simplify the expression; perform manual dimensional analysis on the result",
                "example": 'math("simplify", "<expression>", session=False)',
            })
        elif any(k in task_lower for k in ("session", "会话", "show")):
            recommendations.append({
                "tool": "session_show",
                "rationale": "Display current derivation state and formula",
                "example": "session_show()",
            })
        else:
            recommendations.append({
                "tool": "intent_execute",
                "rationale": "Let the framework parse your intent and route to the right tool",
                "example": f'intent_execute("{task}")',
            })

        return {
            "success": True,
            "task": task,
            "domain": domain,
            "recommendations": recommendations,
        }
