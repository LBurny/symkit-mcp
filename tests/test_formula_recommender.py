"""Tests for the FormulaRecommender — ranking, external-adapter merging, and fallback.

Covers:
- Local-result ranking by domain match and expression similarity (TestFormulaRecommender)
- External-adapter result merging, source labelling, top-k truncation, and
  graceful fallback when an adapter fails (TestFormulaRecommenderExternal)
"""

from __future__ import annotations

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit.domain.derivation_goal import DerivationGoal  # noqa: E402
from symkit.domain.formula_recommender import (  # noqa: E402
    FormulaInfoAdapter,
    FormulaRecommender,
)
from symkit.infrastructure.adapters.base import BaseAdapter, FormulaInfo  # noqa: E402
from symkit.infrastructure.derivation_repository import (  # noqa: E402
    DerivationRepository,
    DerivationResult,
)

# ---------------------------------------------------------------------------
# Shared local-result fixtures
# ---------------------------------------------------------------------------


def make_repo_with_results() -> DerivationRepository:
    repo = DerivationRepository()
    repo.register(
        DerivationResult(
            id="ns_incompressible",
            name="Incompressible Navier-Stokes",
            expression="rho*(diff(u,t) + u*diff(u,x)) + diff(p,x) - mu*diff(u,x,2)",
            variables={"rho": {}, "u": {}, "p": {}, "mu": {}, "t": {}, "x": {}},
            domain="fluid_dynamics",
            tags=["navier-stokes", "fluid", "incompressible"],
            description="Momentum equation for incompressible Newtonian fluid",
            application_context="Fluid dynamics and CFD",
            verified=True,
        )
    )
    repo.register(
        DerivationResult(
            id="schrodinger",
            name="Schrodinger Equation",
            expression="I*hbar*diff(psi,t) + hbar**2/(2*m)*diff(psi,x,2) - V*psi",
            variables={"psi": {}, "hbar": {}, "m": {}, "V": {}, "t": {}, "x": {}},
            domain="quantum_mechanics",
            tags=["quantum", "wave equation"],
            description="Time-dependent Schrodinger equation",
            verified=True,
        )
    )
    repo.register(
        DerivationResult(
            id="hookes_law",
            name="Hooke's Law",
            expression="F - k*x",
            variables={"F": {}, "k": {}, "x": {}},
            domain="solid_mechanics",
            tags=["elasticity", "spring"],
            description="Linear elastic restoring force",
            verified=False,
        )
    )
    return repo


def _repo_with_local_result() -> DerivationRepository:
    repo = DerivationRepository()
    repo.register(
        DerivationResult(
            id="local_ns",
            name="Incompressible Navier-Stokes",
            expression="rho*(diff(u,t) + u*diff(u,x)) + diff(p,x) - mu*diff(u,x,2)",
            variables={"rho": {}, "u": {}, "p": {}, "mu": {}, "t": {}, "x": {}},
            domain="fluid_dynamics",
            tags=["navier-stokes", "fluid"],
            description="Momentum equation",
            verified=True,
        )
    )
    return repo


# ---------------------------------------------------------------------------
# Local-result ranking
# ---------------------------------------------------------------------------


class TestFormulaRecommender:
    def test_recommender_ranks_domain_match(self):
        repo = make_repo_with_results()
        recommender = FormulaRecommender(repository=repo)
        goal = DerivationGoal.from_text("derive incompressible Navier-Stokes equations")
        results = recommender.recommend(goal, top_k=5)
        assert results
        assert results[0]["formula_id"] == "ns_incompressible"
        assert "domain match" in results[0]["reason"]

    def test_recommender_finds_variable_overlap(self):
        repo = make_repo_with_results()
        recommender = FormulaRecommender(repository=repo)
        goal = DerivationGoal.from_text("derive F - k*x")
        results = recommender.recommend(goal, top_k=5)
        # Hooke's law should rank highly due to exact expression similarity
        ids = [r["formula_id"] for r in results]
        assert "hookes_law" in ids
        hookes = next(r for r in results if r["formula_id"] == "hookes_law")
        assert "expression similarity" in hookes["reason"]

    def test_empty_repository_returns_empty(self):
        recommender = FormulaRecommender(repository=DerivationRepository())
        goal = DerivationGoal.from_text("derive anything")
        assert recommender.recommend(goal) == []

    def test_external_adapter_is_used(self):
        class DummyAdapter:
            def search(self, query: str, limit: int = 5) -> list[dict[str, object]]:  # noqa: ARG002
                return [{"id": "ext1", "name": "External", "expression": "a+b", "domain": "general"}]

        repo = make_repo_with_results()
        recommender = FormulaRecommender(
            repository=repo,
            external_adapters=[DummyAdapter()],  # type: ignore[list-item]
        )
        goal = DerivationGoal.from_text("find an external formula")
        results = recommender.recommend(goal, top_k=10)
        sources = {r["source"] for r in results}
        # Local formulas should not be recommended when they are irrelevant to the goal.
        assert "local" not in sources
        assert "DummyAdapter" in sources
        assert any(r["formula_id"] == "ext1" for r in results)

    def test_unrelated_verified_result_not_recommended(self):
        repo = make_repo_with_results()
        repo.register(
            DerivationResult(
                id="gr_result",
                name="derive the Friedmann equations from Einstein field equations for a FLRW universe",
                expression="Eq(a(t), a0*t**n)",
                variables={"a": {}, "t": {}, "a0": {}, "n": {}},
                domain="general_relativity",
                tags=["general relativity", "cosmology"],
                description="Expansion scale factor in FLRW cosmology",
                verified=True,
            )
        )
        recommender = FormulaRecommender(repository=repo)
        goal = DerivationGoal.from_text(
            "derive the escape velocity of a planet from conservation of kinetic energy and gravitational potential energy"
        )
        results = recommender.recommend(goal, top_k=10)
        ids = {r["formula_id"] for r in results}
        assert "gr_result" not in ids


# ---------------------------------------------------------------------------
# External-adapter merging and fallback
# ---------------------------------------------------------------------------


class FakeExternalAdapter(BaseAdapter):
    """External adapter that returns two canned formulas."""

    @property
    def source_name(self) -> str:
        return "fake_external"

    def search(self, _query: str, _limit: int = 10) -> list[FormulaInfo]:
        return [
            FormulaInfo(
                id="ext_1",
                name="External Newton",
                expression="F - m*a",
                sympy_str="F - m*a",
                source="fake_external",
                category="classical_mechanics",
                description="Newton's second law",
                tags=["mechanics"],
            ),
            FormulaInfo(
                id="ext_2",
                name="External Constant",
                expression="c",
                sympy_str="c",
                source="fake_external",
                category="constants",
            ),
        ]

    def get_formula(self, _formula_id: str) -> FormulaInfo | None:
        return None


class FailingAdapter(BaseAdapter):
    """Adapter that raises to verify graceful fallback."""

    @property
    def source_name(self) -> str:
        return "failing"

    def search(self, _query: str, _limit: int = 10) -> list[FormulaInfo]:
        raise RuntimeError("network failure")

    def get_formula(self, _formula_id: str) -> FormulaInfo | None:
        return None


class TestFormulaRecommenderExternal:
    def test_merges_local_and_external_results(self):
        repo = _repo_with_local_result()
        recommender = FormulaRecommender(
            repository=repo,
            external_adapters=[FormulaInfoAdapter(FakeExternalAdapter())],
        )
        goal = DerivationGoal.from_text("derive equations in fluid dynamics")
        results = recommender.recommend(goal, top_k=10)
        sources = {r["source"] for r in results}
        assert "local" in sources
        assert "fake_external" in sources

    def test_external_source_label_preserved(self):
        recommender = FormulaRecommender(
            repository=DerivationRepository(),
            external_adapters=[FormulaInfoAdapter(FakeExternalAdapter())],
        )
        goal = DerivationGoal.from_text("find external formula")
        results = recommender.recommend(goal, top_k=10)
        assert all(r["source"] == "fake_external" for r in results)

    def test_top_k_truncates_merged_results(self):
        repo = _repo_with_local_result()
        recommender = FormulaRecommender(
            repository=repo,
            external_adapters=[FormulaInfoAdapter(FakeExternalAdapter())],
        )
        goal = DerivationGoal.from_text("derive equations")
        results = recommender.recommend(goal, top_k=2)
        assert len(results) <= 2

    def test_failing_external_adapter_ignored(self):
        repo = _repo_with_local_result()
        recommender = FormulaRecommender(
            repository=repo,
            external_adapters=[
                FormulaInfoAdapter(FailingAdapter()),
                FormulaInfoAdapter(FakeExternalAdapter()),
            ],
        )
        goal = DerivationGoal.from_text("derive equations")
        results = recommender.recommend(goal, top_k=10)
        # The failing adapter should not crash the recommendation; local + fake results remain.
        assert any(r["source"] == "fake_external" for r in results)
        assert all(r["source"] != "failing" for r in results)

    def test_no_external_adapters_still_works(self):
        repo = _repo_with_local_result()
        recommender = FormulaRecommender(repository=repo)
        goal = DerivationGoal.from_text("derive Navier-Stokes")
        results = recommender.recommend(goal, top_k=5)
        assert results
        assert all(r["source"] == "local" for r in results)
