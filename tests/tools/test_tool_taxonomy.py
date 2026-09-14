"""Tool taxonomy contract: every tool must have a non-Other category and
every category must carry a description.

The registry is built by registering all tools on a throwaway FastMCP
instance, mirroring how ``tool_categories`` reads the live registry.
"""

from mcp.server.fastmcp import FastMCP

from symkit_mcp.tools import register_all_tools
from symkit_mcp.tools.orchestration import _CATEGORY_DESCRIPTIONS

EXPECTED_CATEGORIES: dict[str, set[str]] = {
    "Unified Math": {"math"},
    "Assumptions": {"assume", "show_assumptions", "assume_for_step", "list_assumptions",
                    "clear_step_assumptions", "unassume", "clear_assumptions"},
    "Verification": {"session_verify_step", "session_verify_session", "check_assumption_conflicts",
                     "session_certify", "lean_status"},
    "Symbol Semantics": {"register_symbol", "lookup_symbol", "check_symbol_conflicts",
                         "list_domain_symbols"},
    "Formula Library": {"formula_search", "formula_get", "formula_add", "formula_promote",
                        "formula_remove", "formula_reindex", "formula_stats", "formula_categories"},
    "Session Management": {"session_start", "session_resume", "session_status", "session_show",
                           "session_explain", "session_complete", "session_rollback", "session_abort",
                           "session_add_note", "session_list", "session_load_formula",
                           "session_set_goal", "session_suggest_formulas", "session_record_step",
                           "session_get_steps"},
    "Output": {"generate_output"},
    "High-Level Orchestration": {"derive", "intent_execute", "list_patterns"},
    "Meta": {"tool_categories", "tool_recommend"},
}


def _registered_tools():
    mcp = FastMCP("taxonomy-test")
    register_all_tools(mcp)
    return mcp._tool_manager._tools  # noqa: SLF001


def test_tool_count_is_46():
    assert len(_registered_tools()) == 46


def test_every_tool_has_known_category():
    tools = _registered_tools()
    known = set().union(*EXPECTED_CATEGORIES.values())
    for name, tool in tools.items():
        category = (tool.meta or {}).get("category", "Other")
        assert category != "Other", f"{name} fell into Other"
        assert name in known, f"{name} not in expected taxonomy"


def test_category_membership_matches_exactly():
    tools = _registered_tools()
    actual: dict[str, set[str]] = {}
    for name, tool in tools.items():
        actual.setdefault((tool.meta or {}).get("category", "Other"), set()).add(name)
    assert actual == EXPECTED_CATEGORIES


def test_every_category_has_description():
    for category in EXPECTED_CATEGORIES:
        assert _CATEGORY_DESCRIPTIONS.get(category), f"{category} missing description"
