"""Tests for staging-store junk quarantine (plan + execute)."""

from __future__ import annotations

from pathlib import Path

import yaml

from symkit.infrastructure.staging_prune import execute_prune, plan_prune


def _write(staging: Path, category: str, fid: str, **data) -> Path:
    d = staging / category
    d.mkdir(parents=True, exist_ok=True)
    payload = {"id": fid, "name": fid, "sympy_str": "x + 1", **data}
    path = d / f"{fid}.yaml"
    path.write_text(yaml.dump(payload, allow_unicode=True), encoding="utf-8")
    return path


class TestPlanPrune:
    def test_junk_detection_rules(self, tmp_path):
        staging = tmp_path / "staging"
        junk_author = _write(staging, "d", "e2e_copy", author="mcp_e2e_test")
        junk_name = _write(staging, "d", "v1", name="verified_test")
        junk_name2 = _write(staging, "d", "v2", name="inconclusive_test")
        real = _write(staging, "d", "pendulum-abc123", name="Pendulum", author="user")
        plan = plan_prune(staging)
        moved = {src for src, _ in plan.moves}
        assert moved == {junk_author, junk_name, junk_name2}
        assert plan.kept == [real]

    def test_unparseable_files_are_kept(self, tmp_path):
        staging = tmp_path / "staging"
        staging.mkdir()
        bad = staging / "bad.yaml"
        bad.write_text("{{{ nope", encoding="utf-8")
        plan = plan_prune(staging)
        assert plan.moves == []
        assert plan.kept == [bad]


class TestExecutePrune:
    def test_execute_moves_to_quarantine_and_is_idempotent(self, tmp_path):
        staging = tmp_path / "staging"
        junk = _write(staging, "d", "e2e_copy", author="mcp_e2e_test")
        real = _write(staging, "d", "real-1", name="Real formula", author="user")
        plan = plan_prune(staging)
        assert execute_prune(plan) == 1
        assert not junk.exists()
        assert (staging / "_quarantine" / "d" / "e2e_copy.yaml").exists()
        assert real.exists()
        # Second pass: quarantined files are skipped by the scanner.
        assert plan_prune(staging).moves == []
