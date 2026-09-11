"""Anti-regression guards for the three assumption invariants.

These are structural tests: they fail on the *shape* of the code, not on a
particular input, so a future change that reintroduces the bug class is caught
even if nobody writes a case for the specific expression involved.

* I1 — assumptions never influence parsing.  Guarded here by a static scan that
  forbids building an assumption-bearing ``Symbol`` anywhere except the single
  sanctioned constructor, plus a per-entry-point function-notation matrix.
* I2 — verification never re-parses a display string.  Guarded by a
  reserved-name round-trip matrix through persistence and replay.
* I3 — one implementation of assumption binding.  Guarded by the static scan
  and by the table-identity check in test_assumption_application_contract.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import sympy as sp

from symkit.domain.derivation_session import DerivationSession
from symkit.domain.expr_io import safe_load_expression
from symkit.domain.expression_parser import _RESERVED_NAMES, parse_expression_string
from symkit.domain.value_objects import MathContext
from symkit.infrastructure.sympy_engine import SymPyEngine
from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

SRC = Path(__file__).resolve().parents[2] / "src"

# The only place allowed to build a Symbol that carries assumptions.
_ALLOWED_CONSTRUCTOR = "resolve_assumed_symbol"


def _make_tools():
    # ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


# ═══════════════════════════════════════════════════════════════════════════
# I1/I3 — static guard: assumption symbols have one constructor
# ═══════════════════════════════════════════════════════════════════════════


def _symbol_calls_with_keywords(tree: ast.AST) -> list[tuple[int, str]]:
    """Every ``Symbol(...)`` call that passes keyword arguments, with its owner.

    A call with keywords is one that attaches assumptions (``Symbol('x',
    positive=True)``) or forwards them (``Symbol('x', **props)``).  Bare
    ``Symbol(name)`` calls are fine — they carry no assumptions.
    """
    owner_of: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                owner_of[id(child)] = node.name

    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.keywords:
            continue
        func = node.func
        is_symbol = (isinstance(func, ast.Attribute) and func.attr == "Symbol") or (
            isinstance(func, ast.Name) and func.id == "Symbol"
        )
        if is_symbol:
            hits.append((node.lineno, owner_of.get(id(node), "<module>")))
    return hits


def test_assumption_bearing_symbols_have_a_single_constructor():
    """No module may build ``Symbol(name, **props)`` outside the shared helper.

    This is the structural version of the run-024 bug: any code that builds an
    assumption-bearing Symbol by hand is a new place where the assumption can
    end up applied to the wrong thing (a parse-time binding, a variable that
    does not match the expression, a verifier that disagrees with the engine).
    """
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, owner in _symbol_calls_with_keywords(tree):
            if owner == _ALLOWED_CONSTRUCTOR:
                continue
            offenders.append(f"{path.relative_to(SRC)}:{lineno} (in {owner})")

    assert not offenders, (
        "Assumption-bearing Symbol constructed outside "
        f"{_ALLOWED_CONSTRUCTOR}(): " + "; ".join(offenders)
    )


def test_the_sanctioned_constructor_exists():
    """Guard against the static test passing because the helper was renamed."""
    from symkit.domain import assumption_binding

    assert hasattr(assumption_binding, _ALLOWED_CONSTRUCTOR)


# ═══════════════════════════════════════════════════════════════════════════
# I1 — function notation survives every entry point
# ═══════════════════════════════════════════════════════════════════════════

_FUNCTION_NOTATION_CASES = [
    ("simplify", {"variable": None}, "k(x)"),
    ("expand", {"variable": None}, "k(x)*(x + 1)"),
    ("diff", {"variable": "x"}, "k(x)"),
    ("integrate", {"variable": "x"}, "k(x)"),
]


@pytest.mark.parametrize("operation,kwargs,expr", _FUNCTION_NOTATION_CASES)
def test_function_notation_survives_every_operation_under_assumption(
    fresh_session_manager, operation, kwargs, expr
):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"](f"fn_{operation}")
    tools["assume"]({"k": "positive"})

    res = tools["math"](
        operation=operation, expression=expr, session=False, **kwargs
    )

    assert res["success"], res
    # The function name must never appear as a bare symbol, i.e. `k(x)` was
    # never rewritten into a product.
    assert "k*x" not in res["expression"].replace(" ", ""), res["expression"]


def test_function_notation_survives_limit_under_assumption(fresh_session_manager):
    """A one-sided limit that SymPy leaves unevaluated must keep ``k(x)``.

    The limit of an undefined function is not evaluable, so ``k(x)`` at 0 with
    ``direction='+'`` comes back as ``Limit(k(x), x, 0, dir='+')`` — which is
    the useful case here: the *result itself* shows whether the call survived.
    """
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("fn_limit")
    tools["assume"]({"k": "positive"})

    res = tools["math"](
        operation="limit",
        expression="k(x)",
        variable="x",
        point="0",
        direction="+",
        session=True,
    )
    assert res["success"], res
    assert "k(x)" in res["expression"], res["expression"]
    assert "k*x" not in res["expression"].replace(" ", ""), res["expression"]

    step = _state.get_session().steps[-1]
    assert "Function('k')" in step.input_srepr, step.input_srepr
    assert "Mul(Symbol('k'), Symbol('x'))" not in step.input_srepr, step.input_srepr


def test_function_notation_survives_dsolve_under_assumption(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("fn_dsolve")
    tools["assume"]({"k": "positive"})

    res = tools["math"](
        operation="dsolve",
        expression="Derivative(v(t), t) = -k*v(t) + f(t)",
        variable="v",
        with_respect_to="t",
        session=False,
    )
    assert res["success"], res
    assert "f(t)" in res["expression"], res["expression"]


def test_engine_parse_never_rewrites_a_call_site_for_any_reserved_name():
    """Every reserved name used as a call site stays a call, not a product.

    Reserved names exist so a user's ``beta``/``E`` variable is not captured by
    SymPy's namespace.  That protection must not fire on a *call* site — doing
    so turned ``beta(x)`` into ``beta*x``.
    """
    engine = SymPyEngine()
    corrupted: list[str] = []

    for name in sorted(_RESERVED_NAMES):
        ctx = MathContext().with_assumption(name, positive=True)
        parsed = engine.parse(f"{name}(x)", ctx).sympy_expr
        if parsed is None:
            continue  # not a callable notation for this name; nothing to protect
        if sp.Symbol(name) in parsed.free_symbols:
            corrupted.append(f"{name}(x) -> {parsed}")

    assert not corrupted, "function notation corrupted under assumptions: " + "; ".join(
        corrupted
    )


def test_parser_protects_call_sites_against_caller_symbol_bindings():
    """The parser-level guard, independent of the engine."""
    corrupted: list[str] = []
    for name in sorted(_RESERVED_NAMES):
        parsed, _ = parse_expression_string(
            f"{name}(x)",
            convert_equation=True,
            local_dict={name: sp.Symbol(name, positive=True)},
        )
        if parsed is None:
            continue
        if sp.Symbol(name) in parsed.free_symbols:
            corrupted.append(f"{name}(x) -> {parsed}")
    assert not corrupted, "; ".join(corrupted)


# ═══════════════════════════════════════════════════════════════════════════
# I2 — reserved names round-trip through persistence and replay
# ═══════════════════════════════════════════════════════════════════════════


_RESERVED_ROUNDTRIP_EXPRESSIONS = [
    ("imaginary_unit", sp.Eq(sp.Symbol("x"), sp.I)),
    ("euler_number", sp.exp(sp.Integer(1))),
    ("latex_symbol", 2 * sp.Symbol("mu_{t}")),
    ("beta_function", sp.beta(sp.Symbol("x"), sp.Symbol("y"))),
]


@pytest.mark.parametrize("label,expr", _RESERVED_ROUNDTRIP_EXPRESSIONS)
def test_safe_load_expression_roundtrips_reserved_names(label, expr):
    del label
    loaded = safe_load_expression(str(expr), sp.srepr(expr))
    assert loaded is not None
    assert sp.srepr(loaded) == sp.srepr(expr), (
        f"{expr} round-tripped to {loaded} (display string {str(expr)!r})"
    )


def test_archived_steps_keep_reserved_names_through_save_and_load(
    fresh_session_manager, tmp_path
):
    """A session with reserved-name outputs verifies after a save/load cycle."""
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("roundtrip_matrix")
    tools["math"](operation="solve", expression="x**2 + 1", variable="x")
    tools["math"](operation="simplify", expression="exp(1)", session=True)

    session = _state.get_session()
    assert session is not None
    saved = session.save(tmp_path / "roundtrip_matrix.json")
    reloaded = DerivationSession.load(saved)

    for index in range(1, len(reloaded.steps) + 1):
        result = reloaded.verify_step(index)
        assert result["success"], result
        assert result["verification_status"] == "verified", (index, result)
