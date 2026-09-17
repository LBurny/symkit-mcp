"""Unit tests for the one-shot code-execution engine."""

from __future__ import annotations

import pytest

from symkit.infrastructure.code_exec import run_python, screen_code


class TestScreen:
    @pytest.mark.parametrize(
        "source",
        [
            "import os",
            "import os.path",
            "from subprocess import run",
            "import urllib.request",
            "open('f.txt')",
            "f = open",
            "__import__('os')",
            "eval('1+1')",
            "x = input()",
        ],
    )
    def test_banned_constructs_are_rejected(self, source: str) -> None:
        outcome = screen_code(source)
        assert outcome is not None
        assert outcome.status == "rejected"
        assert outcome.reason

    @pytest.mark.parametrize(
        "source",
        [
            "import sympy",
            "import numpy as np",
            "from sympy import sin, symbols",
            "x = symbols('x')",
            "result = 2 + 2",
        ],
    )
    def test_legitimate_constructs_pass(self, source: str) -> None:
        assert screen_code(source) is None

    def test_syntax_error_is_error_not_rejected(self) -> None:
        outcome = screen_code("def (")
        assert outcome is not None
        assert outcome.status == "error"
        assert "SyntaxError" in outcome.stderr


class TestRun:
    def test_sympy_result_captured_with_srepr(self) -> None:
        outcome = run_python(
            "x = symbols('x')\nresult = integrate(x**2, x)", timeout_seconds=30
        )
        assert outcome.status == "success"
        assert outcome.result_repr == "x**3/3"
        assert outcome.result_srepr is not None
        assert outcome.result_srepr.startswith("Mul(")
        assert outcome.result_type == "Mul"
        assert outcome.exit_code == 0
        assert outcome.truncated == ()

    def test_plain_python_result_srepr_is_best_effort(self) -> None:
        outcome = run_python("result = 40 + 2", timeout_seconds=30)
        assert outcome.status == "success"
        assert outcome.result_repr == "42"
        assert outcome.result_type == "int"
        # srepr() sympifies plain ints, so a best-effort srepr still comes back.
        assert outcome.result_srepr == "42"

    def test_stdout_captured_and_pure(self) -> None:
        outcome = run_python("print('hello')", timeout_seconds=30)
        assert outcome.status == "success"
        assert "hello" in outcome.stdout
        assert outcome.result_repr is None

    def test_exception_goes_to_stderr_with_error_status(self) -> None:
        outcome = run_python("1/0", timeout_seconds=30)
        assert outcome.status == "error"
        assert "ZeroDivisionError" in outcome.stderr
        assert outcome.exit_code != 0

    def test_timeout_kills_process(self) -> None:
        outcome = run_python("while True: pass", timeout_seconds=1)
        assert outcome.status == "timeout"
        assert outcome.duration_ms < 15000

    def test_rejection_short_circuits_execution(self) -> None:
        outcome = run_python("import os", timeout_seconds=30)
        assert outcome.status == "rejected"
        assert outcome.reason is not None

    def test_stdout_truncation(self) -> None:
        outcome = run_python("print('x' * 20000)", timeout_seconds=30)
        assert outcome.status == "success"
        assert "stdout" in outcome.truncated
        assert len(outcome.stdout) < 9000


class TestRound22Surface:
    """Findings from the r22 black-box round (lanes A/C audit probes X1-X5)."""

    def test_result_srepr_is_bounded_like_repr(self) -> None:
        outcome = run_python('result = "x" * 9000', timeout_seconds=30)
        assert outcome.status == "success"
        assert outcome.result_repr is not None and "truncated" in outcome.result_repr
        assert outcome.result_srepr is not None and "truncated" in outcome.result_srepr
        assert len(outcome.result_srepr) < 8500
        # The flag names the sub-channel, not just the container.
        assert "result.repr" in outcome.truncated
        assert "result.srepr" in outcome.truncated

    def test_screen_failures_have_no_exit_code(self) -> None:
        # No process ever ran, so a numeric exit code is a fabricated success
        # signal (r22 task-13: exit_code 0 next to status "error").
        for source in ("def (", "open('f.txt')"):
            outcome = screen_code(source)
            assert outcome is not None
            assert outcome.exit_code is None

    def test_rejection_reason_is_actionable(self) -> None:
        outcome = screen_code("open('f.txt')")
        assert outcome is not None and outcome.status == "rejected"
        # Names the hit token AND says why / what to do instead.
        assert "'open'" in (outcome.reason or "")
        assert "not available" in (outcome.reason or "")

    def test_timeout_keeps_partial_stdout_and_carries_reason(self) -> None:
        outcome = run_python(
            "import time\nprint('line-before-sleep', flush=True)\ntime.sleep(30)",
            timeout_seconds=2,
        )
        assert outcome.status == "timeout"
        assert "line-before-sleep" in outcome.stdout
        assert outcome.reason is not None and "timed out" in outcome.reason
