"""Tests for the one-time Lean setup command (Task 4, fully mocked, no network)."""

from __future__ import annotations

import json

from symkit.infrastructure import lean_toolchain


def _fake_runner(calls: list[str], *, fail_smoke: bool = False):
    def run(cmd, **_kw):
        calls.append(" ".join(map(str, cmd)))

        class R:
            returncode = 1 if (fail_smoke and "Smoke.lean" in calls[-1]) else 0
            stdout = "Lean (version 4.24.0, x86_64-w64-windows, commit abc, Release)"
            stderr = ""

        return R()

    return run


def test_bootstrap_writes_workspace_and_stamp(monkeypatch, tmp_path):
    fake_lake = tmp_path / "lake"
    fake_lake.write_text("", encoding="utf-8")
    monkeypatch.setattr(lean_toolchain, "find_lake", lambda: fake_lake)
    workspace = tmp_path / "ws"
    calls: list[str] = []
    status = lean_toolchain.bootstrap(
        yes=True, toolchain=None, workspace=workspace, runner=_fake_runner(calls)
    )
    lakefile = (workspace / "lakefile.toml").read_text(encoding="utf-8")
    assert 'rev = "v4.24.0"' in lakefile
    assert status.available is True
    assert status.toolchain == "4.24.0"
    assert any("cache" in c and "get" in c for c in calls)
    stamp = json.loads((workspace / lean_toolchain._STAMP).read_text(encoding="utf-8"))
    assert stamp["toolchain"] == "4.24.0"


def test_bootstrap_aborts_when_smoke_fails(monkeypatch, tmp_path):
    fake_lake = tmp_path / "lake"
    fake_lake.write_text("", encoding="utf-8")
    monkeypatch.setattr(lean_toolchain, "find_lake", lambda: fake_lake)
    workspace = tmp_path / "ws"
    calls: list[str] = []
    status = lean_toolchain.bootstrap(
        yes=True,
        toolchain=None,
        workspace=workspace,
        runner=_fake_runner(calls, fail_smoke=True),
    )
    assert status.available is False
    assert not (workspace / lean_toolchain._STAMP).exists()
