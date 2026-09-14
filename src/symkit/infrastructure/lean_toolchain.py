"""Lean 4 + Mathlib toolchain discovery, readiness detection, and bootstrap.

The Lean certification lane is optional: when no toolchain is installed every
other SymKit behavior is unchanged. This module owns the infrastructure side of
the lane: locating ``lake``, deciding whether the hidden workspace is usable,
and (via :func:`bootstrap`) installing the toolchain on explicit user request.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from symkit.domain.paths import user_data_dir

_STAMP = ".symkit-lean-ready"
_ELAN_EXE = "lake.exe" if os.name == "nt" else "lake"
_LEAN_EXE = "lean.exe" if os.name == "nt" else "lean"
_SETUP_HINT = "run `symkit-lean-setup` once in a terminal"
_USER_AGENT = "symkit-lean-setup"
# elan is distributed via GitHub Releases; release.lean-lang.org only serves
# Lean toolchains and 404s (often 403s on the default urllib UA) for elan.
_ELAN_BASE = "https://github.com/leanprover/elan/releases/latest/download"
_SUPPORTED_PLATFORMS = "windows-x86_64, linux-x86_64, macos-x86_64, macos-arm64"
_MACHINE_ALIASES = {"amd64": "x86_64", "aarch64": "arm64"}
# (sys.platform, canonical machine) -> (release asset, archive kind)
_ELAN_ASSETS: dict[tuple[str, str], tuple[str, str]] = {
    ("win32", "x86_64"): ("elan-x86_64-pc-windows-msvc.zip", "zip"),
    ("linux", "x86_64"): ("elan-x86_64-unknown-linux-gnu.tar.gz", "tar"),
    ("darwin", "arm64"): ("elan-aarch64-apple-darwin.tar.gz", "tar"),
    ("darwin", "x86_64"): ("elan-x86_64-apple-darwin.tar.gz", "tar"),
}
_VERSION_RE = re.compile(r"version (\d+\.\d+\.\d+)")
_LAKEFILE_TEMPLATE = (
    'name = "symkit_lean_workspace"\n'
    "defaultTargets = []\n\n"
    "[[require]]\n"
    'name = "mathlib"\n'
    'scope = "leanprover-community"\n'
    'rev = "v{version}"\n'
)
_SMOKE_SOURCE = (
    # Same header the certification lane uses (lean_batch._HEADER); rationals
    # because the proof must survive even before the Real instances load.
    "import Mathlib.Tactic.FieldSimp\n"
    "import Mathlib.Tactic.Ring\n"
    "import Mathlib.Data.Real.Basic\n\n"
    "example : (2 : \u211a) + 2 = 4 := by ring\n"
    "example (a : \u211a) (h : a \u2260 0) : (3 * a) / a = 3 := by\n"
    "  field_simp\n"
)


@dataclass(frozen=True)
class LeanStatus:
    """Availability of the Lean certification backend and its metadata."""

    available: bool
    reason: str = ""
    lake_path: str | None = None
    workspace: str | None = None
    toolchain: str | None = None
    mathlib_rev: str | None = None


def lean_workspace_dir() -> Path:
    """Return the hidden Lean workspace directory under the user data dir."""
    return user_data_dir() / "lean-workspace"


def find_lake() -> Path | None:
    """Locate ``lake``: ``ELAN_HOME`` first, then PATH, then the default elan dir.

    ``ELAN_HOME`` wins over ``PATH`` so the elan install the user pointed at is
    the one whose toolchains get used. Checking ``PATH`` first meant a default
    ``~/.elan/bin/lake`` silently shadowed ``ELAN_HOME``, and since ``lake``
    resolves toolchains against *its own* elan home, the first certified step
    triggered a fresh multi-GB toolchain download elsewhere (round-17 A3).
    """
    elan_home = os.environ.get("ELAN_HOME")
    if elan_home:
        redirected = Path(elan_home) / "bin" / _ELAN_EXE
        if redirected.exists():
            return redirected
    found = shutil.which("lake")
    if found:
        return Path(found)
    fallback = Path.home() / ".elan" / "bin" / _ELAN_EXE
    return fallback if fallback.exists() else None


def _read_stamp(stamp: Path) -> dict[str, Any] | None:
    """Parse the readiness stamp, returning None when it is missing/corrupt."""
    try:
        data = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _elan_home_of(lake: Path) -> Path | None:
    """Return the elan home owning ``lake`` (``<home>/bin/lake``), if any."""
    bin_dir = lake.parent
    if bin_dir.name != "bin":
        return None
    home = bin_dir.parent
    return home if (home / "toolchains").is_dir() else None


def _pinned_toolchain_version(workspace: Path) -> str | None:
    """Parse ``vX.Y.Z`` out of the workspace's ``lean-toolchain`` file."""
    try:
        text = (workspace / "lean-toolchain").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    name = text.rsplit(":", 1)[-1].lstrip("v").strip()
    return name or None


def _toolchain_installed(lake: Path, workspace: Path) -> bool | None:
    """Whether ``lake``'s elan home already holds the pinned toolchain.

    ``None`` means undecidable (not an elan layout, or no version to compare),
    so callers must not block on it.
    """
    home = _elan_home_of(lake)
    version = _pinned_toolchain_version(workspace)
    if home is None or version is None:
        return None
    dotted = f"leanprover--lean4---v{version}"
    return any(
        (home / "toolchains" / name).is_dir()
        for name in (dotted, dotted.replace(".", "-"))
    )


def detect_status(workspace: Path | None = None) -> LeanStatus:
    """Return whether the Lean backend is ready, without touching the network."""
    lake = find_lake()
    if lake is None:
        return LeanStatus(False, f"lake not found (PATH, ELAN_HOME, ~/.elan); {_SETUP_HINT}")
    ws = Path(workspace) if workspace is not None else lean_workspace_dir()
    stamp = ws / _STAMP
    if not (ws / "lakefile.toml").exists() or not stamp.exists():
        return LeanStatus(
            False,
            f"Lean workspace not initialized; {_SETUP_HINT}",
            lake_path=str(lake),
            workspace=str(ws),
        )
    data = _read_stamp(stamp)
    if data is None:
        return LeanStatus(
            False,
            f"Lean readiness stamp is unreadable; {_SETUP_HINT}",
            lake_path=str(lake),
            workspace=str(ws),
        )
    if _toolchain_installed(lake, ws) is False:
        # Running `lake` here would make elan download this toolchain into the
        # wrong elan home (A3). Tell the user instead of stalling for minutes.
        return LeanStatus(
            False,
            "the selected lake does not own the pinned Lean toolchain; point "
            f"ELAN_HOME at the elan install that ran `symkit-lean-setup`, or re-run "
            f"it so `lake` resolves the pinned version ({_SETUP_HINT})",
            lake_path=str(lake),
            workspace=str(ws),
        )
    return LeanStatus(
        True, "", lake_path=str(lake), workspace=str(ws),
        toolchain=data.get("toolchain"), mathlib_rev=data.get("mathlib_rev"),
    )


def _elan_asset() -> tuple[str, str]:
    """Return ``(asset filename, archive kind)`` for this platform and machine."""
    system = sys.platform
    if system.startswith("linux"):
        system = "linux"
    machine = platform.machine().lower()
    machine = _MACHINE_ALIASES.get(machine, machine)
    asset = _ELAN_ASSETS.get((system, machine))
    if asset is None:
        raise RuntimeError(
            f"no elan build for {sys.platform}/{platform.machine()}; "
            f"supported platforms: {_SUPPORTED_PLATFORMS}"
        )
    return asset


def _download(url: str, dest: Path) -> None:
    """Fetch ``url`` with an explicit UA (the CDN rejects the urllib default)."""
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request) as response, dest.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _extract_elan(archive: Path, kind: str, init_name: str, dest_dir: Path) -> Path:
    """Extract the ``elan-init`` binary from a zip/tar.gz archive."""
    if kind == "zip":
        with zipfile.ZipFile(archive) as bundle:
            names = [n for n in bundle.namelist() if Path(n).name == init_name]
            if not names:
                raise OSError(f"{init_name} not found in {archive.name}")
            payload = bundle.read(names[0])
    else:
        with tarfile.open(archive, "r:gz") as bundle:
            entries = [m for m in bundle.getmembers() if Path(m.name).name == init_name]
            handle = bundle.extractfile(entries[0]) if entries else None
            if handle is None:
                raise OSError(f"{init_name} not found in {archive.name}")
            payload = handle.read()
    init = dest_dir / init_name
    init.write_bytes(payload)
    return init


def _install_elan(runner: Callable[..., Any]) -> None:
    """Download the elan installer from GitHub Releases and run it non-interactively."""
    asset, kind = _elan_asset()
    url = f"{_ELAN_BASE}/{asset}"
    init_name = "elan-init.exe" if sys.platform == "win32" else "elan-init"
    print(f"Downloading elan from {url}...")
    workdir = Path(tempfile.mkdtemp(prefix="symkit-elan-"))
    try:
        _download(url, workdir / asset)
        init = _extract_elan(workdir / asset, kind, init_name, workdir)
        if os.name != "nt":
            init.chmod(init.stat().st_mode | 0o111)
        runner([str(init), "-y", "--default-toolchain", "stable"])
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise OSError(f"Failed to install elan from {url}: {exc}") from exc


def _ensure_lake(yes: bool, runner: Callable[..., Any]) -> Path | None:
    """Return a usable ``lake``, optionally installing elan when missing."""
    lake = find_lake()
    if lake is not None:
        return lake
    if not yes:
        print("lake was not found. Re-run `symkit-lean-setup --yes` to install Lean.")
        return None
    try:
        _install_elan(runner)
    except (OSError, RuntimeError) as exc:
        print(f"Failed to download or run the elan installer: {exc}")
        return None
    return find_lake()


def _detect_version(
    lake: Path, pinned: str | None, runner: Callable[..., Any]
) -> str | None:
    """Return the Lean version to pin, from ``--toolchain`` or ``lean --version``."""
    if pinned:
        return pinned.lstrip("v").strip()
    lean = lake.parent / _LEAN_EXE
    try:
        proc = runner([str(lean), "--version"], capture_output=True, text=True)
    except OSError as exc:
        print(f"Could not run `lean --version`: {exc}")
        return None
    match = _VERSION_RE.search(proc.stdout or "")
    if match is None:
        tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip().splitlines()
        detail = tail[-1][:200] if tail else "no output"
        print(f"Could not parse a Lean version from `lean --version` output: {detail}")
        return None
    return match.group(1)


def _write_workspace(workspace: Path, version: str) -> None:
    """Write the pinned toolchain and lakefile into the workspace."""
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "lean-toolchain").write_text(
        f"leanprover/lean4:v{version}", encoding="utf-8"
    )
    (workspace / "lakefile.toml").write_text(
        _LAKEFILE_TEMPLATE.format(version=version), encoding="utf-8"
    )


def _fetch_mathlib(lake: Path, workspace: Path, runner: Callable[..., Any]) -> bool:
    """Resolve dependencies and download the prebuilt Mathlib cache."""
    print("Updating dependencies (`lake update`)...")
    try:
        if runner([str(lake), "update"], cwd=workspace).returncode != 0:
            print("`lake update` failed.")
            return False
        print("Downloading prebuilt Mathlib (`lake exe cache get`)...")
        if runner([str(lake), "exe", "cache", "get"], cwd=workspace).returncode != 0:
            print("`lake exe cache get` failed.")
            return False
    except OSError as exc:
        print(f"Lean dependency setup failed: {exc}")
        return False
    return True


def _run_smoke(lake: Path, workspace: Path, runner: Callable[..., Any]) -> bool:
    """Compile a trivial ``ring`` proof to verify the workspace is usable."""
    print("Running kernel smoke test...")
    (workspace / "Smoke.lean").write_text(_SMOKE_SOURCE, encoding="utf-8")
    try:
        proc = runner(
            [str(lake), "env", "lean", "Smoke.lean"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        print(f"Smoke test could not run: {exc}")
        return False
    if proc.returncode != 0:
        print("Smoke test failed; the Lean workspace is not usable.")
        return False
    return True


def _write_stamp(workspace: Path, version: str) -> None:
    """Record the readiness stamp so ``detect_status`` reports available."""
    stamp = {
        "toolchain": version,
        "mathlib_rev": f"v{version}",
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    (workspace / _STAMP).write_text(json.dumps(stamp), encoding="utf-8")


def bootstrap(
    yes: bool,
    toolchain: str | None,
    workspace: Path,
    runner: Callable[..., Any] = subprocess.run,
) -> LeanStatus:
    """Install Lean 4 + Mathlib into ``workspace``; return the resulting status."""
    lake = _ensure_lake(yes, runner)
    if lake is None:
        return LeanStatus(False, "lake unavailable; install elan manually and retry")
    version = _detect_version(lake, toolchain, runner)
    if version is None:
        return LeanStatus(
            False, "could not determine the Lean version", lake_path=str(lake)
        )
    _write_workspace(workspace, version)
    if not _fetch_mathlib(lake, workspace, runner):
        return LeanStatus(
            False, "Lean dependency setup failed",
            lake_path=str(lake), workspace=str(workspace),
        )
    if not _run_smoke(lake, workspace, runner):
        return LeanStatus(
            False, "kernel smoke test failed",
            lake_path=str(lake), workspace=str(workspace),
        )
    _write_stamp(workspace, version)
    return detect_status(workspace=workspace)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``symkit-lean-setup``."""
    parser = argparse.ArgumentParser(
        prog="symkit-lean-setup",
        description="Install Lean 4 + Mathlib for the SymKit certification lane.",
    )
    parser.add_argument(
        "--yes", action="store_true", help="install elan without prompting"
    )
    parser.add_argument(
        "--toolchain", default=None,
        help="pin a specific Lean version (e.g. v4.24.0) instead of stable",
    )
    args = parser.parse_args(argv)
    print("Setting up Lean 4 + Mathlib for SymKit (this can take a while)...")
    status = bootstrap(
        yes=args.yes, toolchain=args.toolchain, workspace=lean_workspace_dir()
    )
    if status.available:
        print(f"Lean {status.toolchain} + Mathlib {status.mathlib_rev} is ready.")
        return 0
    print(f"Setup failed: {status.reason}")
    return 1
