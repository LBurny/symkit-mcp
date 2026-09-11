"""
测试步骤 CRUD 功能
"""

from symkit.domain.derivation_session import DerivationSession


def test_step_crud():
    """测试步骤的 CRUD 操作"""
    # 创建测试会话
    session = DerivationSession(session_id="test", name="CRUD Test")

    # ═══════════════════════════════════════════════════════════════════════
    # Create: 创建步骤
    # ═══════════════════════════════════════════════════════════════════════
    session.load_formula("x**2 + y**2", formula_id="f1")
    session.load_formula("a*b + x", formula_id="f2")  # 确保有 x 变量
    session.substitute("x", "a+b")

    assert session.step_count == 3, f"Expected 3 steps, got {session.step_count}"
    print(f"✅ Create: {session.step_count} steps created")

    # ═══════════════════════════════════════════════════════════════════════
    # Read: 读取步骤
    # ═══════════════════════════════════════════════════════════════════════
    result = session.get_step(2)
    assert result["success"], f"Get step failed: {result}"
    assert result["step"]["step_number"] == 2
    print("✅ Read: Step 2 retrieved successfully")

    # 测试边界情况
    result = session.get_step(0)
    assert not result["success"], "Step 0 should fail"

    result = session.get_step(100)
    assert not result["success"], "Step 100 should fail"
    print("✅ Read: Edge cases handled correctly")

    # ═══════════════════════════════════════════════════════════════════════
    # Update: 更新步骤
    # ═══════════════════════════════════════════════════════════════════════
    result = session.update_step(
        step_number=2,
        notes="这是测试注记",
        assumptions=["假设 a > 0"],
        limitations=["仅适用于正数"],
    )
    assert result["success"], f"Update failed: {result}"
    assert "notes" in result["updated_fields"]
    assert "assumptions" in result["updated_fields"]
    assert "limitations" in result["updated_fields"]
    print(f"✅ Update: Step 2 updated - {result['updated_fields']}")

    # 验证更新成功
    result = session.get_step(2)
    assert result["step"]["notes"] == "这是测试注记"
    assert result["step"]["assumptions"] == ["假设 a > 0"]
    print("✅ Update: Verified update persisted")

    # ═══════════════════════════════════════════════════════════════════════
    # Delete: 删除步骤（只能删最后一步）
    # ═══════════════════════════════════════════════════════════════════════
    # 尝试删除非最后一步（应该失败）
    result = session.delete_step(1)
    assert not result["success"], "Should not be able to delete step 1"
    print("✅ Delete: Correctly rejected deletion of non-last step")

    # 删除最后一步
    result = session.delete_step(3)
    assert result["success"], f"Delete last step failed: {result}"
    assert session.step_count == 2
    print(f"✅ Delete: Last step deleted, now {session.step_count} steps")

    # ═══════════════════════════════════════════════════════════════════════
    # Rollback: 回滚到指定步骤
    # ═══════════════════════════════════════════════════════════════════════
    # 先加回一些步骤
    session.load_formula("z**3", formula_id="f3")
    session.substitute("z", "x+1")
    assert session.step_count == 4

    # 回滚到步骤 1
    result = session.rollback_to_step(1)
    assert result["success"], f"Rollback failed: {result}"
    assert result["deleted_count"] == 3
    assert session.step_count == 1
    print(f"✅ Rollback: Rolled back to step 1, deleted {result['deleted_count']} steps")

    # 回滚到 0（清空所有）
    result = session.rollback_to_step(0)
    assert result["success"]
    assert session.step_count == 0
    assert session.current_expression is None
    print("✅ Rollback: Rolled back to 0, cleared all steps")

    # ═══════════════════════════════════════════════════════════════════════
    # Insert: 插入说明
    # ═══════════════════════════════════════════════════════════════════════
    session.load_formula("a + b + c", formula_id="f1")
    session.load_formula("c * d + a", formula_id="f2")  # 确保有 a 变量
    session.substitute("a", "c")

    assert session.step_count == 3, f"Expected 3 steps, got {session.step_count}"

    # 在步骤 1 之后插入说明
    result = session.insert_note_after_step(
        after_step=1,
        note="这是在步骤 1 和 2 之间插入的说明",
        note_type="observation",
        related_variables=["a", "b"],
    )
    assert result["success"], f"Insert failed: {result}"
    assert result["inserted_at"] == 2
    assert session.step_count == 4
    print(f"✅ Insert: Note inserted at position {result['inserted_at']}")

    # 验证步骤编号正确
    for i, step in enumerate(session.steps):
        assert step.step_number == i + 1, f"Step {i + 1} has wrong number: {step.step_number}"
    print("✅ Insert: Steps correctly renumbered")

    print("\n🎉 All CRUD tests passed!")


def test_step_crud_with_latex_subscripts_and_max():
    r"""LaTeX 下标符号和 \max 必须能完整经历 CRUD 而不在 sympify 时失败."""
    session = DerivationSession(session_id="latex-crud", name="LaTeX CRUD Test")

    # 加载包含下标符号和 \max 的 SST 涡粘公式
    result = session.load_formula(
        "\\mu_t = \\frac{\\rho a_1 k}{\\max(a_1 \\omega, F_2 S)}",
        formula_id="sst_nu_t",
    )
    assert result["success"], f"Load failed: {result}"
    assert session.step_count == 1

    # 在此步骤后插入说明（这里曾经因为 sympify 'mu_{t}' 失败）
    result = session.insert_note_after_step(
        after_step=1,
        note="SST 模型通过 Bradshaw 假设限制涡粘上限",
        note_type="observation",
        related_variables=["mu_t", "omega", "F_2"],
    )
    assert result["success"], f"Insert note failed: {result}"
    assert result["inserted_at"] == 2
    assert session.step_count == 2

    # 验证回滚能正确恢复包含特殊符号的表达式
    session.load_formula("k = \\frac{1}{2} \\overline{u_i' u_i'}", formula_id="k_def")
    assert session.step_count == 3

    result = session.rollback_to_step(2)
    assert result["success"], f"Rollback failed: {result}"
    assert session.step_count == 2
    assert session.current_expression is not None

    # 验证删除最后一步也能恢复
    result = session.delete_step(2)
    assert result["success"], f"Delete failed: {result}"
    assert session.step_count == 1
    assert session.current_expression is not None

    # 持久化并重新加载会话
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "latex_crud_session.json"
        session.save(path)
        loaded = DerivationSession.load(path)

    assert loaded.step_count == 1
    assert loaded.current_expression is not None
    assert str(loaded.steps[0].output_expression) == str(session.steps[0].output_expression)

    print("🎉 LaTeX subscript / Max CRUD tests passed!")


if __name__ == "__main__":
    test_step_crud()
    test_step_crud_with_latex_subscripts_and_max()
