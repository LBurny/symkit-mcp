"""Run a Lean command and kill its whole process tree on timeout.

``subprocess.run(timeout=...)`` kills only the direct child. The Lean driver
(``lake``) spawns the compiler and, during toolchain bootstrap, an elan install
child that holds the toolchain lock. Killing just ``lake`` leaves those children
orphaned and the lock held, so every later Lean call blocks forever waiting on a
dead install request. This module owns the tree-kill so the timeout leaves no
orphan behind (round-17 A2).
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_TIMEOUT_EXIT = -9
_TASKKILL_TIMEOUT = 10.0


def _run_child(command: Sequence[str], cwd: Path) -> subprocess.Popen[bytes]:
    """Start the command in its own process group so the tree can be signalled."""
    windows = sys.platform == "win32"
    # CREATE_NO_WINDOW keeps a windowed parent from flashing a console; it is
    # Windows-only, hence the getattr (mypy runs against a single platform).
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if windows else 0
    return subprocess.Popen(
        list(command),
        cwd=cwd,
        # DEVNULL keeps the child from inheriting our stdin: when the server
        # itself runs over MCP stdio, an inherited pipe handle wedges the
        # child's interpreter init and could let it swallow protocol bytes.
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # A fresh session makes the child a process-group leader (killpg target).
        start_new_session=not windows,
        creationflags=flags,
    )


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    """Force-kill ``process`` and every descendant it spawned; never raises."""
    if process.poll() is not None:
        return
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        if sys.platform == "win32":
            # /T walks the child tree; /F avoids a "terminate?" prompt.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                timeout=_TASKKILL_TIMEOUT,
            )
        else:
            os.killpg(os.getpgid(process.pid), 9)  # noqa: B009
    with contextlib.suppress(OSError):
        process.kill()


def run_with_tree_timeout(
    command: Sequence[str], cwd: Path, timeout: float
) -> tuple[int, str, str, bool]:
    """Run ``command`` in ``cwd``; return ``(returncode, stdout, stderr, timed_out)``.

    On timeout the whole process tree is killed before returning, so a cancelled
    run cannot leave an orphan holding the elan toolchain lock.
    """
    process = _run_child(command, cwd)
    try:
        out, err = process.communicate(timeout=timeout)
        return process.returncode, out.decode("utf-8", "replace"), err.decode(
            "utf-8", "replace"
        ), False
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        # Collect whatever the tree flushed before the kill: silently dropping
        # it leaves the caller with no hint where the run died (r22 task-14).
        out, err = process.communicate()
        return _TIMEOUT_EXIT, out.decode("utf-8", "replace"), err.decode(
            "utf-8", "replace"
        ), True
