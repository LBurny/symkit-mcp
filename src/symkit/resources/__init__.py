"""Resource files bundled with SymKit."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml


def resource_path(name: str) -> Path:
    """Return the filesystem path to a resource file bundled with SymKit."""
    return Path(files(__name__) / name)


def load_yaml_resource(name: str) -> Any:
    """Load a YAML resource file bundled with SymKit."""
    with files(__name__).joinpath(name).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
