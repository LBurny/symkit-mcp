"""Content-hash identity and slug generation for formula entries.

Lives in infrastructure (not domain) because canonicalization needs SymPy;
the domain layer only stores the resulting plain-string hash.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

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


_SLUG_BAD_RE = re.compile(r"[^a-z0-9一-鿿]+")


def slugify(text: str, *, max_len: int = 40) -> str:
    """Lowercase ASCII/CJK slug ('reynolds_number'); '' if nothing usable."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    slug = _SLUG_BAD_RE.sub("_", normalized).strip("_")
    return slug[:max_len].strip("_")


def staging_id(name: str, expr_str: str) -> str:
    """Deterministic staging id: '<slug>-<hash6>'; identical content → identical id."""
    return f"{slugify(name) or 'formula'}-{content_hash(expr_str)[:6]}"
