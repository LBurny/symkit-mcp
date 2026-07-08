"""Centralized filesystem path resolution for SymKit.

SymKit stores three kinds of data:

1. **Bundled seed formulas** — read-only YAML files shipped inside the wheel
   under ``symkit.resources.seed_formulas``. Resolved via
   :mod:`importlib.resources` so they are found regardless of the current
   working directory (CWD) after ``pip install`` / ``uvx``.

2. **User-editable data** — the writable formula library and derived-formula
   repository. These live in a per-user data directory (see
   :func:`user_data_dir`) so that writes never target the read-only
   site-packages tree.

3. **Runtime state** — derivation session JSONs, also under the per-user data
   directory.

All paths here are CWD-independent. Modules that previously used relative
literals such as ``Path("formulas/library")`` or ``Path("derivation_sessions")``
must route through the helpers in this module instead.

The ``SYMKIT_DATA_DIR`` environment variable overrides the per-user data
directory root (useful for tests and self-contained deployments).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import platformdirs

_APP_NAME = "symkit"
_APP_AUTHOR = "symkit"

# Subdirectory layout under the user data dir.
_LIBRARY_SUBDIR = Path("formulas") / "library"
_DERIVED_SUBDIR = Path("formulas") / "derived"
_SESSIONS_SUBDIR = Path("derivation_sessions")

# Resource location for bundled seed formulas (read-only, ships in the wheel).
_SEED_RESOURCE_PACKAGE = "symkit.resources"
_SEED_RESOURCE_NAME = "seed_formulas"


def _env_override() -> Path | None:
    """Return the ``SYMKIT_DATA_DIR`` override path if set, else None."""
    raw = os.environ.get("SYMKIT_DATA_DIR")
    if not raw:
        return None
    return Path(raw)


@lru_cache(maxsize=1)
def user_data_dir() -> Path:
    """Return the writable per-user data root, creating it if missing.

    Honors the ``SYMKIT_DATA_DIR`` environment variable for tests / portable
    deployments; otherwise defers to :mod:`platformdirs` (e.g.
    ``~/.local/share/symkit`` on Linux, ``%LOCALAPPDATA%\\symkit`` on Windows,
    ``~/Library/Application Support/symkit`` on macOS).
    """
    override = _env_override()
    root = override if override is not None else Path(
        platformdirs.user_data_dir(_APP_NAME, _APP_AUTHOR)
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def bundled_seed_library_dir() -> Path:
    """Return the read-only directory of bundled seed formula YAMLs.

    These files ship inside the wheel under
    ``symkit/resources/seed_formulas/`` and are located via
    :mod:`importlib.resources` so they resolve correctly after install from any
    CWD. The returned path may point inside a zipped distribution; callers must
    only *read* from it.
    """
    from importlib.resources import files  # local import keeps domain layer clean

    # importlib.resources.files returns a Traversable, not a os.PathLike;
    # Path() accepts it at runtime but mypy cannot prove the subtype.
    return Path(files(_SEED_RESOURCE_PACKAGE) / _SEED_RESOURCE_NAME)  # type: ignore[arg-type]


def user_library_dir() -> Path:
    """Writable directory for user-added/edited formula YAMLs (overlay).

    User entries with the same id as a bundled seed override the seed.
    """
    path = user_data_dir() / _LIBRARY_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_derived_dir() -> Path:
    """Writable directory for derived-formula YAMLs produced by sessions."""
    path = user_data_dir() / _DERIVED_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_sessions_dir() -> Path:
    """Writable directory for derivation-session JSON files."""
    path = user_data_dir() / _SESSIONS_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path
