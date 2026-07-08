# 可重现符号推导工具调查

> **Date**: 2026-01-01  
> **Key Question**: 有没有「可重现的符号推导引擎」（不依赖 Agent 思考）？

---

## 🎯 问题的精确定义

### 我们需要什么？

```
┌─────────────────────────────────────────────┐
│  不是这个：Agent 决定推导策略               │
├─────────────────────────────────────────────┤
│  User: "证明 ∫x²dx = x³/3"                  │
│  Agent: 思考... 决定用幂次规则...           │
│  sympy-mcp: 运行计算                        │
│  → 问题：每次可能走不同路径（不可重现）     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  而是这个：固定的推导引擎                   │
├─────────────────────────────────────────────┤
│  User: derive(∫x²dx, method="power_rule")   │
│  Engine: 应用幂次规则（固定算法）            │
│  Output: x³/3 + 详细步骤                    │
│  → 每次相同输入 = 相同输出（可重现）        │
└─────────────────────────────────────────────┘
```

### 内核需求

```yaml
ideal_derivation_engine:
  input:
    expression: "∫x²dx"
    goal: "求积分"
    method: "power_rule"  # 或自动选择
    
  process:
    - 识别表达式类型
    - 应用固定规则库
    - 生成推导步骤
    - 验证结果
    
  output:
    result: "x³/3 + C"
    steps:
      - "识别为多项式积分"
      - "应用幂次规则: ∫xⁿdx = xⁿ⁺¹/(n+1)"
      - "n=2, 得 x³/3"
      - "加积分常数 C"
    traceable: true
    reproducible: true  # 关键！
    
  不需要:
    - Agent 思考
    - 启发式搜索
    - 机器学习
```

---

## 🔧 现有工具调查

### 类别 1: 定理证明助手（最接近理想）

#### 1.1 Lean4 ⭐⭐⭐⭐⭐

```lean4
-- Lean4 可以做到完全可重现的推导
theorem integrate_x_squared :
  ∫ x^2 = x^3/3 + C := by
  rw [integral_pow]  -- 应用幂次规则
  norm_num          -- 简化数值
  
-- 特点：
-- ✅ 每个步骤都是确定性的 tactic
-- ✅ 完全可重现
-- ✅ 可以生成证明树
-- ❌ 但需要手动写证明
-- ❌ 不是「自动推导引擎」
```

**评估**：
- **可重现性**: ⭐⭐⭐⭐⭐ (完美)
- **自动化程度**: ⭐⭐ (需要手动证明)
- **适用性**: 适合验证已知推导，不适合探索
- **学习曲线**: 陡峭

**是否符合需求**：
- ✅ 可重现
- ❌ 不是自动推导引擎
- 用途：验证 SymKit 的推导是否正确

#### 1.2 Coq / Isabelle

类似 Lean4，都是定理证明助手。

---

### 类别 2: 商业符号系统（有推导能力）

#### 2.1 Mathematica / Wolfram Language ⭐⭐⭐⭐

```mathematica
(* Mathematica 有 step-by-step 推导 *)
Integrate[x^2, x, GenerateConditions -> False]
(* 输出: x^3/3 *)

(* 但也可以用 Rubi (Rule-based Integrator) *)
Int[x^2, x]
(* 返回推导步骤 *)

(* 特点： *)
(* ✅ 有规则库（Rule-based） *)
(* ✅ 可以追踪步骤 *)
(* ✅ 确定性算法 *)
(* ❌ 商业软件（昂贵） *)
(* ❌ 封闭原代码 *)
```

**Rubi (Rule-based Integration)**：
- Mathematica 的积分引擎
- 基于 **6000+ 规则**
- 完全确定性（相同输入 = 相同输出）
- 可以导出推导步骤

**评估**：
- **可重现性**: ⭐⭐⭐⭐⭐
- **自动化程度**: ⭐⭐⭐⭐⭐
- **适用性**: 广（微积分、代数、微分方程）
- **缺点**: 商业软件，$$$

**是否符合需求**：
- ✅ 可重现
- ✅ 自动推导
- ✅ 有推导步骤
- ❌ 昂贵，不开源

#### 2.2 Maple ⭐⭐⭐⭐

类似 Mathematica，也有规则基推导。

---

### 类别 3: 开源符号系统

#### 3.1 SymPy (Python) ⭐⭐⭐

```python
from sympy import *
x = symbols('x')

# 基本积分
integrate(x**2, x)
# 输出: x**3/3

# 但推导步骤有限
from sympy.integrals.manualintegrate import manualintegrate
manualintegrate(x**2, x)
# 可以返回一些步骤，但不完整

# SymPy 的 rewrite 系统
expr = sin(x)**2 + cos(x)**2
expr.rewrite(cos)
# 可以重写表达式，但不是完整推导
```

**评估**：
- **可重现性**: ⭐⭐⭐⭐ (算法确定)
- **自动化程度**: ⭐⭐⭐⭐
- **推导步骤**: ⭐⭐ (有限)
- **适用性**: 广

**是否符合需求**：
- ✅ 可重现
- ✅ 自动化
- ⚠️ 推导步骤不够详细
- ✅ 开源，免费

**可能的解决方案**：
```python
# 扩展 SymPy 的 manualintegrate
from sympy.integrals.manualintegrate import (
    manualintegrate,
    integral_steps
)

# integral_steps 会返回推导树
steps = integral_steps(x**2, x)
print(steps)
# 这可能是最接近的开源方案
```

#### 3.2 SageMath ⭐⭐⭐

集成多种符号系统（Maxima, SymPy, Singular...），但推导能力类似 SymPy。

#### 3.3 Maxima ⭐⭐⭐

```lisp
/* Maxima 有一些推导追踪 */
integrate(x^2, x);
/* x^3/3 */

/* 可以设置 trace */
trace(integrate);
integrate(x^2, x);
/* 会显示内部调用 */
```

**评估**：
- 老牌系统，稳定
- 推导步骤有限
- Lisp 语法（学习曲线）

---

### 类别 4: 专门推导工具

#### 4.1 Symbolab / Wolfram Alpha ⭐⭐⭐⭐

```
Wolfram Alpha:
  Query: "integrate x^2 step by step"
  Output: 完整推导步骤
  
  ✅ 详细步骤
  ✅ 易用
  ❌ 需要订阅（Pro）
  ❌ 不能作为 API（有限制）
  ❌ 不能集成到系统
```

**评估**：
- 对人类很好
- 但不适合作为后端引擎

#### 4.2 Sympy.integrals.manualintegrate (开源) ⭐⭐⭐⭐

```python
from sympy import *
from sympy.integrals.manualintegrate import manualintegrate, integral_steps

x = symbols('x')

# 手动积分（返回步骤）
result = manualintegrate(x**2, x)
print(result)  # x**3/3

# 取得推导步骤
steps = integral_steps(x**2, x)
print(steps)

# 输出类似：
# IntegralInfo(
#   integrand=x**2,
#   variable=x,
#   context=...,
#   parts=[
#     ConstantTimesRule(constant=1, other=x**2, substep=...),
#     PowerRule(base=x, exp=2)
#   ]
# )
```

**这可能是最接近的开源方案！**

**评估**：
- **可重现性**: ⭐⭐⭐⭐⭐
- **自动化程度**: ⭐⭐⭐⭐
- **推导步骤**: ⭐⭐⭐⭐
- **适用性**: 中（主要针对积分）
- **开源**: ✅

---

### 类别 5: Term Rewriting 系统

#### 5.1 egg (Rust) - E-graphs ⭐⭐⭐⭐

```rust
// egg: Equality Saturation
// 用于自动推导和优化

use egg::*;

define_language! {
    enum SimpleLanguage {
        Num(i32),
        "+" = Add([Id; 2]),
        "*" = Mul([Id; 2]),
        Symbol(Symbol),
    }
}

// 定义重写规则
let rules: &[Rewrite<SimpleLanguage, ()>] = &[
    rewrite!("commute-add"; "(+ ?a ?b)" => "(+ ?b ?a)"),
    rewrite!("commute-mul"; "(* ?a ?b)" => "(* ?b ?a)"),
    rewrite!("add-zero"; "(+ ?a 0)" => "?a"),
    rewrite!("mul-one"; "(* ?a 1)" => "?a"),
    // ... more rules
];

// 应用规则推导
let runner = Runner::default()
    .with_expr(&"(+ x 0)".parse().unwrap())
    .run(rules);

// 结果：x
```

**评估**：
- **可重现性**: ⭐⭐⭐⭐⭐
- **灵活性**: ⭐⭐⭐⭐⭐
- **推导步骤**: ⭐⭐⭐⭐ (可追踪 e-graph)
- **适用性**: 需要手动定义规则
- **语言**: Rust (有 Python binding)

**非常接近理想！**

#### 5.2 Maude (Rewriting Logic)

```
Maude 也是 term rewriting 系统，类似 egg
但语法更学术化
```

---

## 🎯 最佳方案推荐

### 方案 A: SymPy manualintegrate + 扩展 ⭐⭐⭐⭐

**优点**：
- ✅ 开源、免费
- ✅ Python 生态
- ✅ 已有推导步骤功能
- ✅ 可扩展

**缺点**：
- ⚠️ 主要针对积分（微分较少）
- ⚠️ 需要扩展其他领域

**实作方式**：

```python
from sympy.integrals.manualintegrate import integral_steps
from sympy import *

class DerivationEngine:
    """可重现的推导引擎"""
    
    def integrate_with_steps(self, expr, var):
        """积分并返回完整步骤"""
        steps = integral_steps(expr, var)
        return {
            "result": integrate(expr, var),
            "method": self._extract_method(steps),
            "steps": self._format_steps(steps),
            "traceable": True,
            "reproducible": True
        }
    
    def _format_steps(self, steps):
        """格式化推导步骤为人类可读"""
        # 递归解析 IntegralInfo
        if hasattr(steps, 'parts'):
            return [self._format_step(part) for part in steps.parts]
        return []
    
    def _format_step(self, step):
        """格式化单一步骤"""
        if step.__class__.__name__ == 'PowerRule':
            return f"应用幂次规则: ∫x^{step.exp}dx = x^{step.exp+1}/{step.exp+1}"
        elif step.__class__.__name__ == 'ConstantTimesRule':
            return f"提出常数: {step.constant}"
        # ... more rules
        
# 使用
engine = DerivationEngine()
result = engine.integrate_with_steps(x**2, x)

print(result)
# {
#   "result": x**3/3,
#   "method": "PowerRule",
#   "steps": [
#     "应用幂次规则: ∫x²dx = x³/(2+1)",
#     "简化: x³/3"
#   ],
#   "reproducible": True
# }
```

**扩展到其他领域**：
```python
# 需要自己实作类似的 manual* 系统
class DerivationEngine:
    def differentiate_with_steps(self, expr, var):
        # 目前 SymPy 没有 manual_differentiate
        # 需要自己实作规则库
        pass
    
    def solve_with_steps(self, eq, var):
        # 需要实作代数解步骤
        pass
```

---

### 方案 B: egg (E-graphs) + Python binding ⭐⭐⭐⭐⭐

**优点**：
- ✅ 完全可重现
- ✅ 非常灵活（自定义规则）
- ✅ 效率高（e-graph 算法）
- ✅ 可追踪推导路径

**缺点**：
- ❌ 需要手动定义所有规则
- ❌ Rust（有 Python binding 但较新）
- ❌ 学习曲线较陡

**实作方式**：

```python
# 使用 egglog (egg 的 Python binding)
from egglog import *

# 定义语言
@dataclass
class Expr:
    pass

@dataclass
class Const(Expr):
    val: int

@dataclass
class Var(Expr):
    name: str

@dataclass
class Add(Expr):
    a: Expr
    b: Expr

@dataclass
class Mul(Expr):
    a: Expr
    b: Expr

# 定义规则
egraph = EGraph()

# 交换律
egraph.register(rewrite(Add(x, y)).to(Add(y, x)))
egraph.register(rewrite(Mul(x, y)).to(Mul(y, x)))

# 单比特
egraph.register(rewrite(Add(x, Const(0))).to(x))
egraph.register(rewrite(Mul(x, Const(1))).to(x))

# 分配律
egraph.register(rewrite(Mul(x, Add(y, z))).to(Add(Mul(x, y), Mul(x, z))))

# 运行推导
expr = Add(Var("x"), Const(0))
result = egraph.simplify(expr)
# 结果: Var("x")

# 可以追踪推导路径
path = egraph.extract_path(expr, result)
print(path)
# ["Apply add-zero rule: (+ x 0) -> x"]
```

**这是最理想的方案，但需要大量前期工作**。

---

### 方案 C: 混合方案（实用）⭐⭐⭐⭐

**结合多种工具**：

```python
class SymKitEngine:
    """可重现推导引擎"""
    
    def __init__(self):
        # 使用 SymPy 作为后端
        self.sympy_engine = SymPyEngine()
        
        # 自定义规则库
        self.rules = self._load_rules()
    
    def derive(self, expr, goal, method=None):
        """
        可重现推导
        
        Args:
            expr: 起始表达式
            goal: 目标（"integrate", "differentiate", "solve"）
            method: 可选的方法（确保可重现）
        """
        
        if goal == "integrate":
            # 使用 SymPy manualintegrate
            return self.sympy_engine.integrate_with_steps(expr)
        
        elif goal == "differentiate":
            # 自定义微分推导
            return self._differentiate_with_steps(expr)
        
        elif goal == "solve":
            # 自定义代数求解推导
            return self._solve_with_steps(expr)
    
    def _differentiate_with_steps(self, expr):
        """
        微分推导（自定义实作）
        使用固定规则库
        """
        steps = []
        
        # 识别表达式类型
        if expr.is_Add:
            steps.append("应用和的微分: (u+v)' = u' + v'")
            # ...
        elif expr.is_Mul:
            steps.append("应用乘积法则: (uv)' = u'v + uv'")
            # ...
        elif expr.is_Pow:
            steps.append(f"应用幂次法则: (x^n)' = n*x^(n-1)")
            # ...
        
        return {
            "result": diff(expr),
            "steps": steps,
            "reproducible": True
        }
```

**评估**：
- ✅ 实用（结合现有工具）
- ✅ 渐进式改进（逐步添加规则）
- ✅ 可重现
- ⚠️ 需要持续开发

---

## 📊 工具对比总结

| 工具 | 可重现性 | 自动化 | 推导步骤 | 开源 | 易用性 | 推荐度 |
|------|---------|--------|---------|------|--------|--------|
| **Lean4** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ | ⭐⭐ | ⭐⭐⭐ |
| **Mathematica** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ❌ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **SymPy manual** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **egg (E-graphs)** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | ⭐⭐ | ⭐⭐⭐⭐ |
| **Wolfram Alpha** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ❌ | ⭐⭐⭐⭐⭐ | ⭐⭐ |

---

## 🎯 SymKit 的实践建议

### 短期方案：基于 SymPy manualintegrate

```python
# SymKit 推导引擎 v0.1
from sympy.integrals.manualintegrate import integral_steps
from sympy import *

class SymKitEngine:
    def derive(self, expr_str, operation):
        """固定的推导引擎"""
        expr = sympify(expr_str)
        
        if operation == "integrate":
            x = symbols('x')
            steps = integral_steps(expr, x)
            return self._format_result(steps)
    
    def _format_result(self, steps):
        return {
            "result": str(integrate(expr, x)),
            "steps": self._extract_steps(steps),
            "method": steps.__class__.__name__,
            "reproducible": True,
            "engine": "SymPy.manualintegrate"
        }
```

**优点**：
- ✅ 立即可用
- ✅ 开源免费
- ✅ Python 生态

**局限**：
- ⚠️ 目前只有积分
- ⚠️ 需要扩展其他操作

### 中期方案：扩展规则库

逐步添加：
- 微分推导
- 代数求解推导
- 三角恒等式推导
- 极限推导

### 长期方案：考虑 egg (E-graphs)

如果需要更灵活的推导系统。

---

## 💡 回答您的问题

### Q: 有没有现成的可重现符号推导工具？

**A: 有，但需要组合**

1. **立即可用**：
   - `sympy.integrals.manualintegrate` ✅
   - 提供积分的完整推导步骤
   - 完全可重现

2. **商业方案**：
   - Mathematica/Rubi ✅
   - 非常完整，但昂贵

3. **研究级**：
   - egg (E-graphs) ✅
   - 最灵活，但需要大量开发

### Q: SymKit 应该用哪个？

**推荐：从 SymPy manualintegrate 开始**

```python
# 这就是您需要的「固定引擎」
from sympy.integrals.manualintegrate import integral_steps

# 相同输入 → 相同输出（可重现）
steps = integral_steps(x**2, x)

# 返回详细推导树
# 不依赖 Agent 思考
# 完全确定性
```

**然后逐步扩展到其他操作**。

---

**Status**: 工具调查完成  
**Recommendation**: 使用 SymPy manualintegrate 作为起点，逐步扩展  
**Key Insight**: 可重现推导 ≠ 需要 AI，规则基系统就可以做到
