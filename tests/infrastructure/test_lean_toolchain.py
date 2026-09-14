"""Tests for Lean toolchain discovery, readiness detection, and elan install."""

from __future__ import annotations

import io
import json
import tarfile
import urllib.error
import zipfile
from pathlib import Path

import pytest

from symkit.infrastructure import lean_toolchain


def _no_lake(monkeypatch, home: Path) -> None:
    monkeypatch.setattr(lean_toolchain.shutil, "which", lambda _name: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))


def test_unavailable_without_lake(monkeypatch, tmp_path):
    _no_lake(monkeypatch, tmp_path)
    status = lean_toolchain.detect_status()
    assert status.available is False
    assert lean_toolchain.setup_command() in status.reason
    assert status.lake_path is None


def test_smoke_source_matches_certification_lane():
    """The smoke proof must compile under the imports the certification lane
    actually uses (FieldSimp + Ring), with rationals.

    The original smoke used `(1 : ℝ)` under only `Mathlib.Tactic.Ring` — that
    module's transitive imports carry no `Real` algebra instances, so `ring`
    could never close the goal and setup always failed at the smoke step
    (round-13 D12).  Rationals have core-backed instances, so the smoke now
    exercises both tactics on `ℚ`, mirroring the certification header.
    """
    source = lean_toolchain._SMOKE_SOURCE
    assert "import Mathlib.Tactic.Ring" in source
    assert "import Mathlib.Tactic.FieldSimp" in source
    assert "import Mathlib.Data.Real.Basic" in source
    assert "by ring" in source
    assert "field_simp" in source


def test_lake_present_but_workspace_missing(monkeypatch, tmp_path):
    fake_lake = tmp_path / "lake"
    fake_lake.write_text("", encoding="utf-8")
    monkeypatch.setattr(lean_toolchain.shutil, "which", lambda _name: str(fake_lake))
    workspace = tmp_path / "ws_missing"
    status = lean_toolchain.detect_status(workspace=workspace)
    assert status.available is False
    assert status.lake_path == str(fake_lake)
    assert lean_toolchain.setup_command() in status.reason


def _install_mathlib(workspace, version: str = "4.24.0", *, built: bool = True) -> None:
    """Lay down the on-disk markers ``detect_status`` reads for readiness."""
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "lakefile.toml").write_text('name = "ws"\n', encoding="utf-8")
    (workspace / "lean-toolchain").write_text(
        f"leanprover/lean4:v{version}", encoding="utf-8"
    )
    (workspace / lean_toolchain._STAMP).write_text(
        json.dumps({"toolchain": version, "mathlib_rev": f"v{version}"}), encoding="utf-8"
    )
    (workspace / "lake-manifest.json").write_text(
        json.dumps({"packages": [{"name": "mathlib", "rev": "deadbeef"}]}), encoding="utf-8"
    )
    package = workspace / ".lake" / "packages" / "mathlib"
    package.mkdir(parents=True, exist_ok=True)
    (package / "Mathlib.lean").write_text("-- mathlib\n", encoding="utf-8")
    if built:
        (package / ".lake" / "build" / "lib" / "lean").mkdir(parents=True, exist_ok=True)


def _fake_lake(monkeypatch, tmp_path, *, with_toolchain: bool = True):
    """A lake under a fake elan home; returns ``(lake, elan_home)``."""
    elan_home = tmp_path / "elan"
    lake = elan_home / "bin" / lean_toolchain._ELAN_EXE
    lake.parent.mkdir(parents=True, exist_ok=True)
    lake.write_text("", encoding="utf-8")
    (elan_home / "toolchains").mkdir(parents=True, exist_ok=True)
    if with_toolchain:
        (elan_home / "toolchains" / "leanprover--lean4---v4.24.0").mkdir()
    monkeypatch.setattr(lean_toolchain.shutil, "which", lambda _name: str(lake))
    return lake, elan_home


def test_unavailable_when_mathlib_is_not_built(monkeypatch, tmp_path):
    """Toolchain + stamp alone are not enough: a stamp left over from a bootstrap
    whose Mathlib was deleted must not report ready (round-lean)."""
    _, elan_home = _fake_lake(monkeypatch, tmp_path)
    monkeypatch.setenv("ELAN_HOME", str(elan_home))
    workspace = tmp_path / "ws_ready"
    _install_mathlib(workspace, built=False)

    status = lean_toolchain.detect_status(workspace=workspace)

    assert status.available is False
    assert status.mathlib_found is True and status.mathlib_ready is False
    assert "Mathlib" in status.reason and "cache is not built" in status.reason


def test_ready_without_stamp_when_files_are_present(monkeypatch, tmp_path):
    """Readiness is judged from disk, so a workspace copied from another machine
    stays usable after its advisory stamp is lost."""
    _, elan_home = _fake_lake(monkeypatch, tmp_path)
    monkeypatch.setenv("ELAN_HOME", str(elan_home))
    workspace = tmp_path / "ws_copied"
    _install_mathlib(workspace)
    (workspace / lean_toolchain._STAMP).unlink()

    status = lean_toolchain.detect_status(workspace=workspace)

    assert status.available is True
    assert status.stamp_present is False
    assert status.mathlib_ready is True


def test_available_with_stamp(monkeypatch, tmp_path):
    fake_lake = tmp_path / "lake"
    fake_lake.write_text("", encoding="utf-8")
    monkeypatch.setattr(lean_toolchain.shutil, "which", lambda _name: str(fake_lake))
    workspace = tmp_path / "ws_ready"
    _install_mathlib(workspace)
    status = lean_toolchain.detect_status(workspace=workspace)
    assert status.available is True
    assert status.lake_path == str(fake_lake)
    assert status.workspace == str(workspace)
    assert status.toolchain == "4.24.0"
    assert status.mathlib_rev == "v4.24.0"


# --- structured environment report (lean_status) ---


def test_describe_environment_reports_resolved_paths_and_next_step(monkeypatch, tmp_path):
    _, elan_home = _fake_lake(monkeypatch, tmp_path, with_toolchain=False)
    monkeypatch.setenv("ELAN_HOME", str(elan_home))
    workspace = tmp_path / "ws"
    _install_mathlib(workspace)

    report = lean_toolchain.describe_environment(
        lean_toolchain.detect_status(workspace=workspace)
    )

    assert report["available"] is False
    assert report["ready_for_certification"] is False
    assert report["resolved_from"]["ELAN_HOME"] == str(elan_home)
    assert report["resolved_from"]["lake_source"] == "ELAN_HOME"
    assert "toolchain" in report["missing"]
    assert report["next_step"] and "--yes" in report["next_step"]


def test_describe_environment_ready_reports_no_next_step(monkeypatch, tmp_path):
    _, elan_home = _fake_lake(monkeypatch, tmp_path)
    monkeypatch.setenv("ELAN_HOME", str(elan_home))
    workspace = tmp_path / "ws"
    _install_mathlib(workspace)

    report = lean_toolchain.describe_environment(
        lean_toolchain.detect_status(workspace=workspace)
    )

    assert report["available"] is True
    assert report["missing"] == [] and report["next_step"] is None
    assert report["mathlib"] == {"dependency": True, "built": True, "rev": "v4.24.0"}
    assert report["stamp"] == {"present": True, "advisory": True}


def test_setup_command_does_not_assume_a_path_entry():
    """The next step must work on any machine, so it names the running interpreter
    rather than a console script that may not be on PATH."""
    command = lean_toolchain.setup_command()
    assert command.startswith(lean_toolchain.sys.executable)
    assert "-m symkit.infrastructure.lean_toolchain" in command


def test_reason_and_next_step_quote_the_same_setup_command(monkeypatch, tmp_path):
    """Every degraded branch must not offer two different commands for the same
    action: the hint embedded in `reason` has to be the one `next_step` names
    (round-leanstatus task-02 W-2)."""
    _no_lake(monkeypatch, tmp_path)
    status = lean_toolchain.detect_status()
    report = lean_toolchain.describe_environment(status)

    assert lean_toolchain.setup_command() in status.reason
    assert lean_toolchain.setup_command() in (report["next_step"] or "")


# --- elan installer acquisition (network and runner mocked, nothing downloaded) ---


class _FakeResponse(io.BytesIO):
    """Context-manager stand-in for ``urlopen``'s response."""

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> bool:
        self.close()
        return False


def _set_platform(monkeypatch, system: str, machine: str) -> None:
    monkeypatch.setattr(lean_toolchain.sys, "platform", system)
    monkeypatch.setattr(lean_toolchain.platform, "machine", lambda: machine)


def _patch_download(monkeypatch, payload: bytes) -> list:
    requests: list = []

    def fake_urlopen(request, *_args, **_kwargs):
        requests.append(request)
        return _FakeResponse(payload)

    monkeypatch.setattr(lean_toolchain.urllib.request, "urlopen", fake_urlopen)
    return requests


def _zip_bytes(member: str, payload: bytes = b"fake-elan-binary") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, payload)
    return buffer.getvalue()


def _tar_gz_bytes(member: str, payload: bytes = b"fake-elan-binary") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(member)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _record_runner(calls: list) -> object:
    def run(cmd, **_kwargs):
        target = Path(str(cmd[0]))
        calls.append((list(map(str, cmd)), target.exists()))

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    return run


def test_install_elan_windows_fetches_zip_and_runs_extracted_exe(monkeypatch):
    _set_platform(monkeypatch, "win32", "AMD64")
    requests = _patch_download(monkeypatch, _zip_bytes("elan-init.exe"))
    calls: list = []
    lean_toolchain._install_elan(_record_runner(calls))

    request = requests[0]
    assert "github.com/leanprover/elan/releases" in request.full_url
    assert request.full_url.endswith(".zip")
    assert request.get_header("User-agent") == "symkit-lean-setup"
    command, existed = calls[0]
    assert Path(command[0]).name == "elan-init.exe"
    assert existed is True
    assert command[1:] == ["-y", "--default-toolchain", "stable"]


def test_install_elan_linux_fetches_tar_gz_and_runs_extracted_binary(monkeypatch):
    _set_platform(monkeypatch, "linux", "x86_64")
    requests = _patch_download(monkeypatch, _tar_gz_bytes("elan-init"))
    calls: list = []
    lean_toolchain._install_elan(_record_runner(calls))

    request = requests[0]
    assert request.full_url.endswith("elan-x86_64-unknown-linux-gnu.tar.gz")
    assert request.get_header("User-agent") == "symkit-lean-setup"
    command, existed = calls[0]
    assert Path(command[0]).name == "elan-init"
    assert existed is True
    assert command[1:] == ["-y", "--default-toolchain", "stable"]


def test_install_elan_macos_arm64_asset(monkeypatch):
    _set_platform(monkeypatch, "darwin", "arm64")
    requests = _patch_download(monkeypatch, _tar_gz_bytes("elan-init"))
    lean_toolchain._install_elan(_record_runner([]))
    assert requests[0].full_url.endswith("elan-aarch64-apple-darwin.tar.gz")


def test_install_elan_unsupported_platform_lists_matrix(monkeypatch):
    _set_platform(monkeypatch, "freebsd", "x86_64")
    with pytest.raises(RuntimeError) as excinfo:
        lean_toolchain._install_elan(_record_runner([]))
    message = str(excinfo.value)
    assert "freebsd" in message
    assert "windows" in message and "linux" in message and "macos" in message


def test_install_elan_http_error_message_contains_url(monkeypatch):
    _set_platform(monkeypatch, "win32", "AMD64")
    url = f"{lean_toolchain._ELAN_BASE}/elan-x86_64-pc-windows-msvc.zip"

    def boom(_request, *_args, **_kwargs):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(lean_toolchain.urllib.request, "urlopen", boom)
    with pytest.raises(OSError) as excinfo:
        lean_toolchain._install_elan(_record_runner([]))
    assert url in str(excinfo.value)


# --- ELAN_HOME-aware lake discovery ---


def test_find_lake_honors_elan_home(monkeypatch, tmp_path):
    monkeypatch.setattr(lean_toolchain.shutil, "which", lambda _name: None)
    elan_bin = tmp_path / "custom-elan" / "bin"
    elan_bin.mkdir(parents=True)
    lake = elan_bin / lean_toolchain._ELAN_EXE
    lake.write_text("", encoding="utf-8")
    monkeypatch.setenv("ELAN_HOME", str(tmp_path / "custom-elan"))
    assert lean_toolchain.find_lake() == lake


def test_find_lake_elan_home_precedes_default_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(lean_toolchain.shutil, "which", lambda _name: None)
    home = tmp_path / "home"
    default = home / ".elan" / "bin" / lean_toolchain._ELAN_EXE
    default.parent.mkdir(parents=True)
    default.write_text("", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    custom = tmp_path / "custom" / "bin" / lean_toolchain._ELAN_EXE
    custom.parent.mkdir(parents=True)
    custom.write_text("", encoding="utf-8")
    monkeypatch.setenv("ELAN_HOME", str(tmp_path / "custom"))
    assert lean_toolchain.find_lake() == custom


def test_find_lake_without_elan_home_behavior_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(lean_toolchain.shutil, "which", lambda _name: None)
    monkeypatch.delenv("ELAN_HOME", raising=False)
    empty_home = tmp_path / "home"
    empty_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: empty_home))
    assert lean_toolchain.find_lake() is None


def test_find_lake_elan_home_beats_a_lake_on_path(monkeypatch, tmp_path):
    """ELAN_HOME must win over PATH, else a default ~/.elan/bin/lake on PATH
    shadows the elan install the user pointed at and the pinned toolchain is
    downloaded again into the wrong home (round-17 A3)."""
    on_path = tmp_path / "path-elan" / "bin" / lean_toolchain._ELAN_EXE
    on_path.parent.mkdir(parents=True)
    on_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(lean_toolchain.shutil, "which", lambda _name: str(on_path))
    homed = tmp_path / "homed-elan" / "bin" / lean_toolchain._ELAN_EXE
    homed.parent.mkdir(parents=True)
    homed.write_text("", encoding="utf-8")
    monkeypatch.setenv("ELAN_HOME", str(tmp_path / "homed-elan"))

    assert lean_toolchain.find_lake() == homed


def test_find_lake_falls_back_to_path_when_elan_home_lacks_lake(monkeypatch, tmp_path):
    monkeypatch.setenv("ELAN_HOME", str(tmp_path / "empty-elan"))
    on_path = tmp_path / "path-elan" / "bin" / lean_toolchain._ELAN_EXE
    on_path.parent.mkdir(parents=True)
    on_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(lean_toolchain.shutil, "which", lambda _name: str(on_path))

    assert lean_toolchain.find_lake() == on_path


def _ready_workspace(tmp_path: Path, version: str = "4.24.0") -> Path:
    """A workspace that is ready on disk (toolchain pin + Mathlib built)."""
    workspace = tmp_path / "ws"
    _install_mathlib(workspace, version)
    return workspace


def test_status_unavailable_when_selected_lake_lacks_the_pinned_toolchain(
    monkeypatch, tmp_path
):
    """A lake whose elan home lacks the pinned toolchain would trigger a fresh
    download, so the lane reports unavailable with a directing reason instead."""
    elan_home = tmp_path / "wrong-elan"
    lake = elan_home / "bin" / lean_toolchain._ELAN_EXE
    lake.parent.mkdir(parents=True)
    lake.write_text("", encoding="utf-8")
    (elan_home / "toolchains").mkdir()
    monkeypatch.setattr(lean_toolchain.shutil, "which", lambda _name: str(lake))

    status = lean_toolchain.detect_status(workspace=_ready_workspace(tmp_path))

    assert status.available is False
    assert "ELAN_HOME" in status.reason


def test_status_available_when_lake_owns_the_pinned_toolchain(monkeypatch, tmp_path):
    elan_home = tmp_path / "right-elan"
    lake = elan_home / "bin" / lean_toolchain._ELAN_EXE
    lake.parent.mkdir(parents=True)
    lake.write_text("", encoding="utf-8")
    (elan_home / "toolchains" / "leanprover--lean4---v4.24.0").mkdir(parents=True)
    monkeypatch.setattr(lean_toolchain.shutil, "which", lambda _name: str(lake))

    status = lean_toolchain.detect_status(workspace=_ready_workspace(tmp_path))

    assert status.available is True
    assert status.toolchain == "4.24.0"


def test_detect_version_surfaces_stderr_on_parse_failure(capsys, tmp_path):
    from symkit.infrastructure.lean_toolchain import _detect_version

    lake = tmp_path / "bin" / "lake.exe"
    lake.parent.mkdir()
    lake.touch()

    class _Result:
        stdout = ""
        stderr = "error: could not download file: SSL peer certificate was not OK"

    assert _detect_version(lake, None, lambda *_a, **_k: _Result()) is None
    assert "could not download" in capsys.readouterr().out
