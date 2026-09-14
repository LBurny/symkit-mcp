"""Content-hash identity and slug generation for formula entries.

Lives in infrastructure (not domain) because canonicalization needs SymPy;
the domain layer only stores the resulting plain-string hash.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

_SINGLE_EQ_RE = re.compile(r"^[^=]+=(?![=])[^=]+$")


def _canonical_expression(expr_str: str) -> str:
    """Canonicalize via SymPy srepr; fall back to whitespace-stripped text."""
    text = expr_str.strip()
    if not text:
        return ""
    try:
        from sympy import Eq, srepr, sympify

        if "==" in text:
            lhs, rhs = text.split("==", 1)
            expr = Eq(sympify(lhs.strip()), sympify(rhs.strip()))
        elif _SINGLE_EQ_RE.match(text):
            lhs, rhs = text.split("=", 1)
            expr = Eq(sympify(lhs.strip()), sympify(rhs.strip()))
        else:
            expr = sympify(text)
        return str(srepr(expr))
    except Exception:
        return re.sub(r"\s+", "", text)


def content_hash(expr_str: str) -> str:
    """Return a 12-char content hash of the canonical expression.

    An empty or unparseable-but-blank expression returns ``""``: it has no
    content identity, so callers must not treat unrelated blank entries as
    duplicates of one another.
    """
    canonical = _canonical_expression(expr_str)
    if not canonical:
        return ""
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


def _normalize_parsed(expr: Any) -> Any:
    """Re-evaluate a parse tree with SymPy's default (evaluating) constructors.

    ``parse_user_expression`` parses expressions with ``evaluate=False`` so
    derivation tools keep unevaluated divisions; that also leaves ``x*x`` as
    ``Mul(x, x)`` instead of ``Pow(x, 2)``. Rebuilding each node restores the
    commutative/power normalizations the previous ``sympify``-based fingerprint
    relied on, while keeping the reserved-name Symbol bindings the parser
    resolved (``E``/``I`` stay Symbols, not Euler's number / the imaginary unit).
    """
    from sympy import Basic

    if not isinstance(expr, Basic) or not expr.args:
        return expr
    try:
        return expr.func(*(_normalize_parsed(arg) for arg in expr.args))
    except Exception:
        return expr


def _node_signature(node: Any, cache: dict[Any, Any]) -> Any:
    """Name-independent structural signature of ``node``.

    Numbers key on their value, symbols on their assumption set (so two
    symbols differing only by assumptions never collide), and composites on
    the function name plus child signatures. Add/Mul are commutative, so
    their child signatures are sorted; every other node keeps positional
    order (``a**b`` and ``b**a`` stay distinct). Every signature tuple starts
    with a string, so heterogeneous signatures remain mutually comparable.
    """
    from sympy import Basic

    if not isinstance(node, Basic):
        return ("raw", repr(node))
    if node in cache:
        return cache[node]
    if node.is_Number:
        result: Any = ("N", str(node))
    elif node.is_Symbol:
        result = ("S", tuple(sorted(node.assumptions0.items())))
    else:
        name = type(node).__name__
        children = [_node_signature(arg, cache) for arg in node.args]
        if name in ("Add", "Mul") and node.is_commutative:
            children.sort()
        result = (name, tuple(children))
    cache[node] = result
    return result


def _render(node: Any, cache: dict[Any, str]) -> str:
    """Deterministic serialization with Add/Mul operands sorted by text.

    SymPy's own printer orders commutative operands by symbol name; sorting
    the (already-renamed) operand strings removes that name dependence.
    """
    from sympy import Basic

    if not isinstance(node, Basic) or not node.args:
        return str(node)
    if node in cache:
        return cache[node]
    name = type(node).__name__
    parts = [_render(arg, cache) for arg in node.args]
    if name in ("Add", "Mul") and node.is_commutative:
        parts.sort()
    text = f"{name}({','.join(parts)})"
    cache[node] = text
    return text


# A symbol occurrence's embedding context: the chain of (ancestor signature,
# child position) from the root. ``-1`` marks a commutative ancestor, whose
# operand order is not structural.
_Context = tuple[tuple[Any, int], ...]


def _is_commutative(node: Any) -> bool:
    """True for Add/Mul nodes, whose operands may be reordered."""
    return type(node).__name__ in ("Add", "Mul") and bool(node.is_commutative)


def _symbol_contexts(root: Any) -> dict[Any, tuple[_Context, ...]]:
    """Name-independent embedding context of every free symbol.

    Sorting the per-occurrence ancestor chains yields a descriptor that
    distinguishes structural roles (``Pow`` base vs exponent) without ever
    consulting a symbol name, so an order-reversing rename cannot move a
    symbol onto a different placeholder.
    """
    from sympy import Basic

    contexts: dict[Any, list[_Context]] = {}

    def walk(node: Any, chain: _Context, sig_cache: dict[Any, Any]) -> None:
        if isinstance(node, Basic) and node.is_Symbol:
            contexts.setdefault(node, []).append(chain)
            return
        if not isinstance(node, Basic) or not node.args:
            return
        signature = _node_signature(node, sig_cache)
        commutative = _is_commutative(node)
        children = list(node.args)
        if commutative:
            children.sort(key=lambda child: _node_signature(child, sig_cache))
        for index, child in enumerate(children):
            walk(child, chain + ((signature, -1 if commutative else index),), sig_cache)

    walk(root, (), {})
    return {sym: tuple(sorted(chains)) for sym, chains in contexts.items()}


def _render_context(node: Any, contexts: dict[Any, Any]) -> str:
    """Name-independent rendering of a subtree, for signature tie-breaks."""
    from sympy import Basic

    if isinstance(node, Basic) and node.is_Symbol:
        return "S" + repr(contexts.get(node, ()))
    if not isinstance(node, Basic) or not node.args:
        return repr(_node_signature(node, {}))
    name = type(node).__name__
    parts = [_render_context(arg, contexts) for arg in node.args]
    if _is_commutative(node):
        parts.sort()
    return f"{name}({','.join(parts)})"


def _ordered_children(
    node: Any, sig_cache: dict[Any, Any], contexts: dict[Any, Any]
) -> list[Any]:
    """Operands of ``node`` in name-independent canonical order."""
    children = list(node.args)
    if _is_commutative(node):
        children.sort(
            key=lambda child: (
                _node_signature(child, sig_cache),
                contexts[child] if child in contexts else _render_context(child, contexts),
            )
        )
    return children


def _collect_paths(
    node: Any,
    prefix: tuple[int, ...],
    paths: dict[Any, list[tuple[int, ...]]],
    sig_cache: dict[Any, Any],
    contexts: dict[Any, Any],
) -> None:
    """Record every occurrence path of each free symbol under ``node``."""
    from sympy import Basic

    if isinstance(node, Basic) and node.is_Symbol:
        paths.setdefault(node, []).append(prefix)
        return
    if not isinstance(node, Basic) or not node.args:
        return
    for index, child in enumerate(_ordered_children(node, sig_cache, contexts)):
        _collect_paths(child, prefix + (index,), paths, sig_cache, contexts)


def _alpha_rename(expr: Any) -> Any:
    """Unify ``Eq(a, b)`` to ``a - b`` and alpha-rename free symbols.

    Placeholders ``c0, c1, ...`` are assigned from each symbol's occurrence
    path multiset. Operands of the commutative Add/Mul are ordered by
    structural signature and the symbol's name-independent embedding context,
    so no placeholder depends on a symbol's name rank (not even a
    base/exponent or order-reversing rename). Each placeholder keeps its
    source symbol's assumption set, so symbols that differ only by
    assumptions do not collide.
    """
    from sympy import Eq

    from symkit.domain.assumption_binding import resolve_assumed_symbol

    if isinstance(expr, Eq):
        expr = expr.lhs - expr.rhs
    paths: dict[Any, list[tuple[int, ...]]] = {}
    _collect_paths(expr, (), paths, {}, _symbol_contexts(expr))
    ordered = sorted(
        paths,
        key=lambda sym: (
            sorted(paths[sym]),
            sym.name,
            sorted(sym.assumptions0.items()),
        ),
    )
    mapping = {
        sym: resolve_assumed_symbol(f"c{i}", sym.assumptions0)
        for i, sym in enumerate(ordered)
    }
    return expr.xreplace(mapping) if mapping else expr


def _structural_digest(expr: Any) -> str:
    """Alpha-invariant digest of an already-parsed expression."""
    canonical = _render(_alpha_rename(_normalize_parsed(expr)), {})
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


def try_structural_hash(expr_str: str) -> str | None:
    """Structural fingerprint, or ``None`` when the input cannot be parsed.

    Strict variant used by the search structural channel: unlike
    :func:`structural_hash` it never falls back to a text hash, so a text query
    cannot accidentally collide with an entry whose expression is unparseable.
    Parsing goes through :func:`symkit.domain.expression_parser.parse_user_expression`,
    which rebinds reserved SymPy names used as variables to Symbols.
    """
    text = expr_str.strip()
    if not text:
        return None
    try:
        from symkit.domain.expression_parser import parse_user_expression

        expr, _error = parse_user_expression(text)
        if expr is None:
            return None
        return _structural_digest(expr)
    except Exception:
        return None


def structural_hash(expr_str: str) -> str:
    """Return a 12-char alpha-invariant structural fingerprint.

    Unlike :func:`content_hash` (name-sensitive, used for staging ids), two
    expressions equal up to free-symbol renaming, free-symbol names that
    collide with SymPy reserved constants (``E``, ``I``, ...), and ``Eq(a, b)``
    vs ``a - b`` share a digest. Parse failures fall back to the same
    whitespace-stripped text hash as :func:`content_hash`; blank input yields
    ``""``.
    """
    text = expr_str.strip()
    if not text:
        return ""
    digest = try_structural_hash(text)
    if digest is not None:
        return digest
    return hashlib.sha1(re.sub(r"\s+", "", text).encode("utf-8")).hexdigest()[:12]


_SLUG_BAD_RE = re.compile(r"[^a-z0-9一-鿿]+")


def slugify(text: str, *, max_len: int = 40) -> str:
    """Lowercase ASCII/CJK slug ('reynolds_number'); '' if nothing usable."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    slug = _SLUG_BAD_RE.sub("_", normalized).strip("_")
    return slug[:max_len].strip("_")


def staging_id(name: str, expr_str: str) -> str:
    """Deterministic staging id: '<slug>-<hash6>'; identical content → identical id."""
    return f"{slugify(name) or 'formula'}-{content_hash(expr_str)[:6]}"
