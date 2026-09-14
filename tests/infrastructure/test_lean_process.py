"""Tests for the Lean subprocess tree-kill helper (round-17 A2)."""

from __future__ import annotations

import os
import sys
import textwrap
import time
from pathlib import Path

from symkit.infrastructure.lean_process import run_with_tree_timeout

_PARENT_THAT_SPAWNS_A_CHILD = """
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open("child_pid.txt", "w").write(str(child.pid))
time.sleep(120)
"""


def _shim(tmp_path: Path, body: str) -> list[str]:
    script = tmp_path / "fake_lake.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(script)]


def _child_pid(tmp_path: Path) -> int:
    for _ in range(50):
        pid_file = tmp_path / "child_pid.txt"
        if pid_file.exists():
            return int(pid_file.read_text(encoding="utf-8"))
        time.sleep(0.1)
    raise AssertionError("the shim never reported its child pid")


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_timeout_kills_the_grandchild_too(tmp_path):
    """A killed lake must not leave the compiler/install child it spawned."""
    command = _shim(tmp_path, _PARENT_THAT_SPAWNS_A_CHILD)
    returncode, _out, _err, timed_out = run_with_tree_timeout(command, tmp_path, 1.0)

    assert timed_out is True
    assert returncode != 0
    child = _child_pid(tmp_path)
    for _ in range(50):
        if not _is_alive(child):
            break
        time.sleep(0.1)
    assert not _is_alive(child), f"grandchild {child} survived the tree kill"


def test_successful_run_returns_output_and_exit_code(tmp_path):
    command = _shim(
        tmp_path,
        "import sys; print('hello'); print('oops', file=sys.stderr); sys.exit(3)\n",
    )
    returncode, stdout, stderr, timed_out = run_with_tree_timeout(command, tmp_path, 30.0)

    assert (returncode, timed_out) == (3, False)
    assert "hello" in stdout
    assert "oops" in stderr
