"""Tool-layer tests for python_exec (env switch, timeout clamp, response shape)."""

from __future__ import annotations

import pytest

from symkit_mcp.tools.execute import _clamp_timeout, python_exec_impl


def test_disabled_env_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYMKIT_DISABLE_CODE_EXEC", "1")
    response = python_exec_impl("result = 1")
    assert response["status"] == "disabled"
    assert "SYMKIT_DISABLE_CODE_EXEC" in response["message"]


def test_clamp_timeout_bounds() -> None:
    assert _clamp_timeout(0) == 1
    assert _clamp_timeout(-5) == 1
    assert _clamp_timeout(10) == 10
    assert _clamp_timeout(999) == 60


def test_success_response_shape() -> None:
    response = python_exec_impl("result = 40 + 2", timeout_seconds=30)
    assert response["status"] == "success"
    assert response["result"]["repr"] == "42"
    assert response["result"]["type"] == "int"
    assert response["exit_code"] == 0
    assert "duration_ms" in response


def test_rejected_response_carries_reason() -> None:
    response = python_exec_impl("import os")
    assert response["status"] == "rejected"
    assert response["reason"]


def test_response_echoes_effective_timeout() -> None:
    response = python_exec_impl("result = 1", timeout_seconds=30)
    assert response["timeout_seconds"] == 30


def test_clamped_timeout_is_disclosed() -> None:
    response = python_exec_impl("result = 1", timeout_seconds=999)
    assert response["timeout_seconds"] == 60


def test_syntax_error_response_has_null_exit_code() -> None:
    response = python_exec_impl("result = (1 + 2")
    assert response["status"] == "error"
    assert response["exit_code"] is None


def test_timeout_response_has_reason_and_partial_stdout() -> None:
    response = python_exec_impl(
        "import time\nprint('partial', flush=True)\ntime.sleep(30)",
        timeout_seconds=2,
    )
    assert response["status"] == "timeout"
    assert response["reason"]
    assert "partial" in response["stdout"]
    assert response["timeout_seconds"] == 2
