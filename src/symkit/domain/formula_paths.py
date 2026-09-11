"""Path safety for formula library writes.

Formula ids and categories reach the library from callers (including LLMs), so
they must be treated as untrusted: an id such as ``../../escaped`` would
otherwise write — or overwrite — files outside the library root. Domain layer
only: pathlib is stdlib, so this keeps the no-external-dependency rule.
"""

from __future__ import annotations

from pathlib import Path


class UnsafeFormulaPathError(ValueError):
    """Raised when an entry id or category would escape the library root."""


def safe_entry_path(root: Path, category: str, formula_id: str) -> Path:
    """Return the write target for an entry, refusing anything outside ``root``.

    An id must be a plain file name (no path separators); both the resolved
    category directory and the resolved target file must stay under the
    resolved root. Nested categories such as ``a/b`` remain allowed.
    """
    if not formula_id or formula_id in (".", ".."):
        raise UnsafeFormulaPathError(
            f"Unsafe formula path: id is not a usable file name: {formula_id!r}"
        )
    if "/" in formula_id or "\\" in formula_id:
        raise UnsafeFormulaPathError(
            f"Unsafe formula path: id must not contain path separators: {formula_id!r}"
        )

    target_dir = root / (category or "uncategorized")
    resolved_root = root.resolve()
    resolved_dir = target_dir.resolve()
    resolved_path = (resolved_dir / f"{formula_id}.yaml").resolve()
    if not resolved_dir.is_relative_to(resolved_root) or not resolved_path.is_relative_to(
        resolved_root
    ):
        raise UnsafeFormulaPathError(
            "Unsafe formula path: id/category escapes the library root "
            f"(id={formula_id!r} category={category!r})"
        )
    return target_dir / f"{formula_id}.yaml"
