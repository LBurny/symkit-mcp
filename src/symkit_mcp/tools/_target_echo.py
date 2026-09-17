"""Target-expression validation and parsed echo for session goal setters (r22)."""

from __future__ import annotations

from symkit.domain.derivation_goal import DerivationGoal, parse_target_expression


def apply_target_override(
    parsed_goal: DerivationGoal, target_expression: str | None
) -> tuple[str | None, str | None]:
    """Apply an explicit ``target_expression``; return ``(parsed_echo, warning)``.

    The parsed form is echoed so a mangled target — e.g. a natural-language
    sentence silently read as algebra (r22 task-15) — is visible at goal-set
    time. An unparseable target disables matching with a warning instead of
    being stored to mismatch forever.
    """
    if not target_expression:
        return None, None
    target_obj = parse_target_expression(target_expression)
    if target_obj is None:
        return None, (
            f"target_expression {target_expression!r} could not be parsed as a "
            "mathematical expression; target matching is disabled."
        )
    parsed_goal.target_expression = target_expression
    return str(target_obj), None


def build_goal(
    goal: str | None,
    domain: str,
    target_variables: list[str] | None,
    target_expression: str | None,
) -> tuple[DerivationGoal | None, str | None, str | None]:
    """Assemble a goal from the setters' inputs; ``(goal, parsed echo, warning)``.

    ``None`` goal when the caller supplied nothing goal-like at all — a bare
    ``target_expression`` must still set the target (r22 task-15).
    """
    if not (goal or target_variables is not None or target_expression):
        return None, None, None
    parsed_goal = DerivationGoal.from_text(goal or "", domain=domain)
    if target_variables is not None:
        parsed_goal.target_variables = target_variables
    parsed, warning = apply_target_override(parsed_goal, target_expression)
    return parsed_goal, parsed, warning
