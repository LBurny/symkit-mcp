"""Tests for formula content-hash identity and slug generation."""

from __future__ import annotations

from symkit.infrastructure.formula_identity import content_hash, slugify, staging_id


class TestContentHash:
    def test_orderless_addition_equal(self):
        assert content_hash("a + b") == content_hash("b + a")

    def test_mul_pow_canonical(self):
        assert content_hash("x * x") == content_hash("x**2")

    def test_single_vs_double_equals(self):
        assert content_hash("Re = rho * v * L / mu") == content_hash("Re == rho*v*L/mu")

    def test_eq_constructor_form(self):
        assert content_hash("Eq(T, 2*pi*sqrt(l/g))") == content_hash("T = 2*pi*sqrt(l/g)")

    def test_different_expressions_differ(self):
        assert content_hash("a + b") != content_hash("a + c")

    def test_unparseable_falls_back_deterministically(self):
        h1 = content_hash("not an (expr")
        assert h1 == content_hash("not an (expr")
        assert len(h1) == 12

    def test_empty_has_no_content_identity(self):
        # Empty is not a shared sentinel: unrelated entries with no expression
        # must not be grouped as duplicates of one another.
        assert content_hash("") == ""
        assert content_hash("   ") == ""


class TestSlugify:
    def test_basic(self):
        assert slugify("Reynolds Number!") == "reynolds_number"

    def test_cjk_kept(self):
        assert slugify("单摆周期") == "单摆周期"

    def test_max_len(self):
        assert len(slugify("x" * 100)) == 40

    def test_nothing_usable(self):
        assert slugify("!!!") == ""


class TestStagingId:
    def test_deterministic(self):
        a = staging_id("Pendulum", "T = 2*pi*sqrt(l/g)")
        b = staging_id("Pendulum", "T = 2*pi*sqrt(l/g)")
        assert a == b

    def test_format_and_fallback(self):
        sid = staging_id("Pendulum Period", "T = 2*pi*sqrt(l/g)")
        assert sid.startswith("pendulum_period-")
        assert len(sid.rsplit("-", 1)[1]) == 6
        assert staging_id("!!!", "a+b").startswith("formula-")
