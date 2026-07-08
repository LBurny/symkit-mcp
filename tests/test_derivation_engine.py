"""
Derivation Engine Integration Test

测试推导引擎的完整工作流程：
1. 创建会话
2. 加载多个公式
3. 运行代入操作
4. 简化
5. 完成并查看结果

The "Forge" in SymKit means we CREATE new formulas through derivation!
"""

import json
import tempfile
from pathlib import Path

from symkit.domain.derivation_session import SessionManager
from symkit.domain.formula import FormulaSource


def test_derivation_workflow() -> None:
    """测试完整的推导工作流程"""
    print("=" * 60)
    print("SymKit Derivation Engine Test")
    print("The 'Forge' in SymKit = CREATE new formulas through derivation")
    print("=" * 60)

    # 使用临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        persist_dir = Path(tmpdir)
        manager = SessionManager(persist_dir)

        # 1. 创建会话
        print("\n📝 Step 1: Create derivation session")
        session = manager.create(
            name="temp_corrected_elimination",
            description="Temperature-corrected drug elimination rate",
            author="Test User",
            auto_persist=True,
        )
        print(f"   Session ID: {session.session_id}")
        print(f"   Name: {session.name}")

        # 2. 加载基础公式 - 一级消除动力学
        print("\n📥 Step 2: Load base formulas")
        result1 = session.load_formula(
            formula_input="C_0 * exp(-k*t)",
            formula_id="one_compartment",
            source=FormulaSource.TEXTBOOK,
            source_detail="Goodman & Gilman's Pharmacology, Ch.2",
            name="One-compartment elimination",
            description="First-order elimination kinetics: C = C₀·e^(-kt)",
        )
        print(f"   Loaded: {result1['formula_id']}")
        print(f"   Expression: {result1['expression']}")
        print(f"   Source: {result1['source']}")

        # 3. 加载温度修正公式 (Arrhenius equation)
        result2 = session.load_formula(
            formula_input="k_ref * exp(E_a/R * (1/T_ref - 1/T))",
            formula_id="arrhenius",
            source=FormulaSource.TEXTBOOK,
            source_detail="Physical Chemistry, Atkins Ch.22",
            name="Arrhenius temperature correction",
            description="Rate constant temperature dependence",
        )
        print(f"   Loaded: {result2['formula_id']}")
        print(f"   Expression: {result2['expression']}")

        # 4. 代入操作 - 将 k 替换为温度修正版本
        print("\n🔄 Step 3: Substitute k with temperature-corrected version")
        # 先取得 arrhenius 公式的表达式
        arrhenius_expr = str(session.formulas["arrhenius"].expression)
        result3 = session.substitute(
            target_var="k",
            replacement=arrhenius_expr,  # 使用表达式字符串
            in_formula="one_compartment",
            description="Replace k with Arrhenius temperature-corrected rate constant",
        )
        print(f"   Success: {result3['success']}")
        print(f"   Expression: {result3['expression']}")
        print(f"   Substituted: {result3.get('substituted', {})}")

        # 5. 简化
        print("\n🔧 Step 4: Simplify the combined expression")
        result4 = session.simplify(
            method="auto",
            description="Simplify the temperature-corrected elimination formula",
        )
        print(f"   Success: {result4['success']}")
        print(f"   Simplified: {result4['expression']}")

        # 6. 查看所有步骤
        print("\n📋 Step 5: Review all derivation steps")
        steps = session.get_steps()
        for i, step in enumerate(steps, 1):
            print(f"   Step {i}: {step['operation']}")
            print(f"           Input: {step['input_expressions']}")
            print(f"           Output: {step['output_expression']}")
            print(f"           Command: {step['sympy_command']}")

        # 7. 检查持久化
        print("\n💾 Step 6: Test persistence")
        persist_file = persist_dir / f"session_{session.session_id}.json"
        print(f"   Persist file exists: {persist_file.exists()}")

        if persist_file.exists():
            with open(persist_file, encoding="utf-8") as f:
                saved_data = json.load(f)
            print(f"   Saved session name: {saved_data['name']}")
            print(f"   Saved step count: {len(saved_data['steps'])}")

        # 8. 完成推导
        print("\n✅ Step 7: Complete derivation")
        result_final = session.complete()
        print(f"   Success: {result_final['success']}")
        print(f"   Final expression: {result_final['final_expression']}")
        print(f"   Total steps: {result_final['total_steps']}")

        # 显示溯源信息
        print("\n📚 Provenance Information (Academic Value!):")
        formulas_used = result_final.get("formulas_used", {})
        for formula_id, formula_data in formulas_used.items():
            print(f"   {formula_id}:")
            print(f"      Source: {formula_data.get('source', 'N/A')}")
            print(f"      Detail: {formula_data.get('source_detail', 'N/A')}")

        print("\n" + "=" * 60)
        print("✨ Derivation Complete!")
        print("   We have FORGED a new formula from existing knowledge.")
        print("=" * 60)


def test_session_recovery() -> None:
    """测试会话恢复功能"""
    print("\n" + "=" * 60)
    print("Session Recovery Test")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        persist_dir = Path(tmpdir)

        # 创建并部分完成会话
        manager1 = SessionManager(persist_dir)
        session1 = manager1.create("recovery_test", auto_persist=True)
        session1.load_formula("x**2 + 2*x + 1", formula_id="quadratic")
        session_id = session1.session_id
        print(f"   Created session: {session_id}")
        print(f"   Steps before interruption: {session1.step_count}")

        # 仿真中断
        session1.save()
        del session1
        del manager1

        # 恢复会话
        print("\n   Simulating session recovery...")
        manager2 = SessionManager(persist_dir)
        session2 = manager2.get(session_id)

        if session2:
            print("   ✅ Session recovered!")
            print(f"   Steps after recovery: {session2.step_count}")
            print(f"   Formulas loaded: {session2.formula_ids}")

            # 继续推导
            session2.simplify()
            print(f"   Steps after continuation: {session2.step_count}")
        else:
            print("   ❌ Recovery failed!")


if __name__ == "__main__":
    test_derivation_workflow()
    test_session_recovery()
