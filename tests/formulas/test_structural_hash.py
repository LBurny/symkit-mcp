"""Tests for the alpha-invariant structural fingerprint.

``structural_hash`` is the *duplicate detection* fingerprint: two expressions
that are equal up to free-symbol renaming (and ``Eq(a, b)`` vs ``a - b``)
share a digest. ``content_hash`` stays name-sensitive and is not touched.
"""

from __future__ import annotations

from symkit.infrastructure.formula_identity import content_hash, structural_hash


class TestStructuralHash:
    def test_symbol_rename_invariant(self):
        assert structural_hash("g*z + p/rho + v**2/2") == structural_hash(
            "g*z + p/rho + u**2/2"
        )

    def test_eq_unified_with_difference(self):
        assert structural_hash("Eq(a, b)") == structural_hash("a - b")

    def test_equals_and_eq_forms_agree(self):
        assert structural_hash("Re = rho*v*L/mu") == structural_hash(
            "Re == rho*v*L/mu"
        )

    def test_commutative_and_pow_normalization_kept(self):
        assert structural_hash("rho*v*L/mu") == structural_hash("v*L*rho/mu")
        assert structural_hash("x * x") == structural_hash("x**2")

    def test_different_structure_differs(self):
        assert structural_hash("g*z + p/rho + v**2/2") != structural_hash(
            "g*z + p/rho"
        )

    def test_additive_constant_does_not_merge(self):
        # Regression fact: the two physically identical Bernoulli forms are NOT
        # structural duplicates because ``Eq(lhs, C)`` unifies to ``lhs - C``,
        # adding a free symbol. They are caught by the text channel instead.
        assert structural_hash("g*z+p/rho+v**2/2") != structural_hash(
            "Eq(g*z+p/rho+u**2/2, C)"
        )

    def test_multi_factor_denominator_rename_invariant(self):
        # Regression (rename clone whose denominator sorts last by name):
        # srepr orders Mul args by symbol name, so ``mu`` used to land on a
        # different placeholder than ``q4``. The structural role (denominator)
        # must drive the placeholder, not the name's alphabetical rank.
        assert structural_hash("rho*v*L/mu") == structural_hash("q1*q2*q3/q4")

    def test_eq_form_of_multi_factor_ratio_agrees(self):
        assert structural_hash("Re == q1*q2*q3/q4") == structural_hash(
            "Re = rho * v * L / mu"
        )

    def test_additive_rename_invariant(self):
        assert structural_hash("rho + v + L") == structural_hash("q1+q2+q3")

    def test_swap_is_alpha_renaming_for_ratio(self):
        # Contract: swapping the two free-symbol names IS an alpha-renaming
        # (``a/b`` maps to ``b/a`` under a<->b), so a name-agnostic fingerprint
        # must collide. Distinguishing them would require a name-sensitive
        # hash, which breaks ``rho*v*L/mu == q1*q2*q3/q4``.
        assert structural_hash("a/b") == structural_hash("b/a")

    def test_swap_is_alpha_renaming_for_difference(self):
        assert structural_hash("x-y") == structural_hash("y-x")

    def test_swap_is_alpha_renaming_for_power(self):
        assert structural_hash("a**b") == structural_hash("b**a")

    def test_order_reversing_rename_on_shared_symbol(self):
        # ``x`` appears in both additive terms; renaming in reverse name order
        # must not change which placeholder its role gets.
        assert structural_hash("2*x*y + x*z") == structural_hash("2*r*q + r*p")

    def test_noncommutative_roles_survive_rename(self):
        # Base vs exponent roles are positional, not name-driven: swapping the
        # two symbol names while keeping the structure must not change the
        # fingerprint.
        assert structural_hash("g**f + (f+g)/h**2") == structural_hash(
            "f**g + (g+f)/h**2"
        )

    def test_assumption_distinct_symbols_not_merged(self):
        # A positive symbol carries a different placeholder signature than a
        # plain one, so the two expressions stay distinct under alpha-renaming.
        positive = "Symbol('x', positive=True) + y"
        plain = "a + b"
        assert structural_hash(positive) != structural_hash(plain)

    def test_empty_has_no_structural_identity(self):
        assert structural_hash("") == ""
        assert structural_hash("   ") == ""

    def test_unparseable_falls_back_deterministically(self):
        h1 = structural_hash("not an (expr")
        assert h1 == structural_hash("not an (expr")
        assert len(h1) == 12

    def test_content_hash_unchanged_by_structural_api(self):
        # Guard: adding the structural path must not alter content_hash.
        assert content_hash("g*z + p/rho + v**2/2") != content_hash(
            "g*z + p/rho + u**2/2"
        )
