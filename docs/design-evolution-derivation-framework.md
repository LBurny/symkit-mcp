# 设计演化：从模板系统到推导框架

> **Date**: 2026-01-01  
> **Status**: Architecture Decision Record  
> **Impact**: 🔴 Major - 改变整个系统内核设计

---

## 📜 演化历程

### 初始设计（v0.1）：完整推导模板

**概念**：为每类问题预先定义完整的推导步骤模板

```yaml
# 范例：安全带张力分析模板
template:
  id: seatbelt_tension_analysis
  parameters: [M1, M2, v, m, k]
  steps:
    - id: 1
      formula: "M1 * v = (M1 + M2) * v_f"
      solve_for: v_f
    - id: 2
      formula: "Delta_v = v - v_f"
    - id: 3
      formula: "(1/2) * m * Delta_v**2 = (1/2) * k * x**2"
      solve_for: x
    - id: 4
      formula: "T_max = k * x"
```

**问题**：
- ❌ 无法穷举所有可能的问题
- ❌ 每个新问题都需要新模板
- ❌ 无法处理问题变体（例如：加入摩擦力）
- ❌ 缺乏理论基础追溯

---

### 关键洞察（用户启发）

> **User**: "公式可能是被证明的（但也是理想化的）... 但公式可以变化：例如 F=ma，但加入摩擦力呢？"

**内核问题**：
1. 公式来自理想化定理（Lean4 可证明）
2. 现实问题需要修正项（friction, drag, heat_loss...）
3. 不可能为所有「理想化 + 修正组合」预先建模板

**模拟**：
- ❌ 错误：为每道菜预先写好完整食谱
- ✅ 正确：提供基础烹饪技法 + 食材库，可组合创造

---

### 新设计（v0.2）：可组合推导框架

**内核概念**：`Principle + Modifications → Derived Form`

```
┌──────────────────────────────────────────────────────────┐
│  基础原理 (Principles)                                   │
│  - Newton's 2nd Law: F = ma [Lean4 证明 ✓]              │
│  - Momentum Conservation [Lean4 证明 ✓]                 │
│  - Energy Conservation [Lean4 证明 ✓]                   │
└──────────────────────────────────────────────────────────┘
                    ↓ + 修正项
┌──────────────────────────────────────────────────────────┐
│  修正项库 (Modifications)                                │
│  - Friction: -μ * N                                      │
│  - Air Drag: -(1/2) * ρ * v² * Cd * A                   │
│  - Heat Loss: -h * A * ΔT                               │
└──────────────────────────────────────────────────────────┘
                    ↓ 动态组合
┌──────────────────────────────────────────────────────────┐
│  推导引擎 (Derivation Engine)                            │
│  - 根据问题特征选择 principle                            │
│  - 根据现实条件添加 modifications                        │
│  - 编译成 sympy-mcp 调用串行                             │
│  - 验证维度和合理性                                      │
└──────────────────────────────────────────────────────────┘
                    ↓ 结果
┌──────────────────────────────────────────────────────────┐
│  精确计算 + 推导追溯 + (可选) Lean4 证明                │
└──────────────────────────────────────────────────────────┘
```

---

## 🏗️ 新架构设计

### 1. Principles Library

**格式**：
```yaml
# formulas/principles/newtons_second_law.yaml
principle:
  id: newtons_second_law
  name: 牛顿第二定律
  
  # 基础形式（理想化）
  base_form: "F = m * a"
  
  # Lean4 验证
  lean4_reference:
    module: "Mathlib.Physics.Classical.Newton"
    theorem: "newton_second_law"
    proven: true
  
  # 变量定义
  variables:
    F: {description: "合力", unit: "N", type: "vector"}
    m: {description: "质量", unit: "kg", type: "positive_real"}
    a: {description: "加速度", unit: "m/s²", type: "vector"}
  
  # 适用条件
  conditions:
    - "质点近似或刚体"
    - "惯性参考系"
```

### 2. Modifications Library

**格式**：
```yaml
# formulas/modifications/friction.yaml
modification:
  id: friction
  name: 摩擦力
  
  # 数学表达
  term: "- mu * N"
  
  # 物理意义
  description: |
    摩擦力与正向力成正比，方向与运动方向相反
  
  # 适用条件
  conditions:
    - "有接触面"
    - "有相对运动或运动趋势"
  
  # 变量
  variables:
    mu: {description: "摩擦系数", type: "positive_real", typical_range: [0, 1]}
    N: {description: "正向力", unit: "N", type: "positive_real"}
  
  # 典型数值
  typical_values:
    static_friction:
      steel_on_steel: 0.74
      rubber_on_concrete: 0.9
      ice_on_ice: 0.1
    kinetic_friction:
      steel_on_steel: 0.57
      rubber_on_concrete: 0.7
      ice_on_ice: 0.03
```

### 3. Derivation Engine (MCP Tools)

```python
@mcp.tool()
def derive_variant(
    principle_id: str,
    modifications: list[str],
    solve_for: str = None
):
    """
    推导变体公式
    
    Example:
        derive_variant(
            principle_id="newtons_second_law",
            modifications=["friction", "air_resistance"],
            solve_for="a"
        )
        
        返回：
        {
            "derivation_steps": [
                {"step": 0, "equation": "F = m * a", "description": "基础形式"},
                {"step": 1, "add": "friction", "equation": "F - μN = m * a"},
                {"step": 2, "add": "air_resistance", "equation": "F - μN - (1/2)ρv²CdA = m * a"},
                {"step": 3, "solve": "a", "result": "a = (F - μN - (1/2)ρv²CdA) / m"}
            ],
            "final_form": "a = (F - μN - (1/2)ρv²CdA) / m",
            "lean4_traceable": true
        }
    """
```

### 4. Derived Forms Library (可选快捷)

社群贡献的常见问题预组合：

```yaml
# formulas/derived_forms/mechanics/sliding_with_friction.yaml
derived_form:
  id: sliding_with_friction
  name: 斜面滑动（含摩擦）
  
  based_on:
    principle: newtons_second_law
    modifications: [gravity, friction]
  
  derivation:
    - base: "F = m * a"
    - add_gravity: "m * g * sin(θ) + ... = m * a"
    - add_friction: "m * g * sin(θ) - μ * m * g * cos(θ) = m * a"
    - simplify: "a = g * (sin(θ) - μ * cos(θ))"
  
  final_form: "a = g * (sin(theta) - mu * cos(theta))"
  
  # 仍然可追溯到基础原理
  traceable_to: "newtons_second_law"
```

---

## 🎓 教育价值

### 对比范例：湿滑路面刹车

**❌ 旧系统（黑箱）**
```
User: "车 1500kg，50km/h，湿路面 μ=0.3，刹车距离？"
System: "公式是 s = v²/(2μg) = 32.8m"
User: "为什么？"
System: "..." (无法解释)
```

**✅ 新系统（可追溯）**
```
User: "车 1500kg，50km/h，湿路面 μ=0.3，刹车距离？"

Agent: "让我从基础推导：

Step 1: 基础原理
  牛顿第二定律: F = ma
  来源: Mathlib.Physics.Classical.Newton [Lean4 证明 ✓]

Step 2: 识别受力
  问题提到「刹车」「湿路面」
  → 需要添加 friction modification
  
Step 3: 应用修正
  F = ma
  刹车力来自摩擦: F = -μmg
  代入: -μmg = ma
  简化: a = -μg

Step 4: 运动学计算
  v² = v₀² + 2as
  刹车到停止(v=0): 0 = v₀² + 2(-μg)s
  解出: s = v₀²/(2μg)

Step 5: 代入数值
  v₀ = 50 km/h = 13.89 m/s
  s = (13.89)²/(2 × 0.3 × 9.8) = 32.8 m

结论: 刹车距离 32.8 公尺"

User: "完全理解了！"
```

---

## 🔗 与其他系统的关系

### SymKit 在生态系统中的位置

```
┌─────────────────────────────────────────────────────────┐
│  Lean4 + Mathlib (形式化证明)                           │
│  - 提供基础定理的数学证明                               │
│  - 保证 principles 的逻辑正确性                         │
│  - 类型检查、定理证明                                   │
└─────────────────────────────────────────────────────────┘
                    ↓ 理论基础
┌─────────────────────────────────────────────────────────┐
│  SymKit (推导编排)                                     │
│  - 桥接形式化定理和工程应用                             │
│  - 提供 principles + modifications                      │
│  - 动态组合推导                                         │
│  - 维度检查、合理性验证                                 │
└─────────────────────────────────────────────────────────┘
                    ↓ 推导步骤
┌─────────────────────────────────────────────────────────┐
│  sympy-mcp (符号运算)                                   │
│  - 精确运行每一步计算                                   │
│  - 解方程、积分、微分                                   │
│  - 符号简化、代数操作                                   │
└─────────────────────────────────────────────────────────┘
```

**关键差异**：

| 系统 | 做什么 | 不做什么 |
|------|--------|----------|
| **Lean4** | 证明定理的逻辑正确性 | 不做数值计算、不处理实际问题 |
| **SymKit** | 提供推导框架、组合公式 | 不做符号运算、不做形式化证明 |
| **sympy-mcp** | 运行精确符号运算 | 不知道该用什么公式、不验证物理意义 |

---

## 🎯 实作优先级

### Phase 1: 内核框架 (当前)
- [x] 设计 principles 格式
- [x] 设计 modifications 格式
- [ ] 实作 `derive_variant()` MCP tool
- [ ] 创建第一组范例：Newton's 2nd Law + friction

### Phase 2: 优先领域（用户兴趣）
- [ ] **Audio Circuits**: 音响电路学
  - Op-amp 滤波器设计
  - 频率响应分析
  - 失真分析
  - 阻抗匹配
- [ ] **Pharmacokinetics**: 药物动力学
  - 一室/二室/三室模型
  - 首过效应
  - 药物清除率
  - 稳态浓度
- [ ] Mechanics: friction, drag, springs, gravity（基础）

### Phase 3: 扩展领域
- [ ] General Circuits: resistance, capacitance, inductance
- [ ] Thermodynamics: heat_loss, non_ideal_gas

### Phase 4: Lean4 连接
- [ ] 标注每个 principle 的 Lean4 来源
- [ ] 实作 `verify_with_lean4()` tool
- [ ] 创建 Lean4 ↔ SymKit 映射

### Phase 4: 社群生态
- [ ] 提供 modification 贡献模板
- [ ] 创建 derived_forms 审核机制
- [ ] 文档和教学范例

---

## 📚 灵感来源

### 主要启发

1. **用户洞察**（2026-01-01）
   > "公式可能是被证明的（但也是理想化的）... 但公式可以变化：例如 F=ma，但加入摩擦力呢？"
   
   **关键认知**：不可能穷举所有问题，应该提供可组合的基础单元

2. **Stephen Diehl - sympy-mcp 项目**
   - 论文：["The Future of Math is Weird"](https://www.stephendiehl.com/posts/future_math_weird/)
   - GitHub: https://github.com/sdiehl/sympy-mcp
   - 启发：LLM 不擅长符号运算，应该用专门工具（sympy）

3. **Lean4 + Mathlib**
   - 形式化数学证明系统
   - 提供理论基础来源
   - 保证公式的数学正确性

### 参考架构

- **Domain-Specific Languages (DSL)**：半角式化表达层
- **Component-Based Design**：可组合的设计模式
- **Microkernel Architecture**：内核小、可扩展

---

## 📊 影响分析

### 对现有代码的影响

| 模块 | 影响 | 迁移策略 |
|------|------|----------|
| `templates/*.yaml` | 🔴 格式改变 | 转换为 derived_forms |
| `tools/template.py` | 🔴 大幅重写 | 改为 derivation.py |
| `docs/template-system-design.md` | 🟡 需更新 | 标注为旧版 |
| MCP Server 接口 | 🟢 添加工具 | 向后兼容 |

### 对用户体验的影响

**优点**：
- ✅ 可以处理更多问题变体
- ✅ 推导过程清晰可追溯
- ✅ 教育价值提升
- ✅ 理论基础明确（Lean4）

**潜在挑战**：
- ⚠️ Agent 需要更多推理（选择 modifications）
- ⚠️ 初期 principles 数量有限
- ⚠️ 需要创建良好的错误提示

---

## ✅ 决策确认

**决策**：采用「可组合推导框架」取代「完整模板系统」

**批准**：Architecture Decision (2026-01-01)

**下一步**：实作第一组 principle (Newton's 2nd Law) + modification (friction)

---

## 📎 相关文档

- 原始设计：[docs/template-system-design.md](./template-system-design.md)
- 架构文档：[ARCHITECTURE.md](../ARCHITECTURE.md)

---

**Revision History**:
- 2026-01-01: 初始版本 - 记录从模板到框架的演化
