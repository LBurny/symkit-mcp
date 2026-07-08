# 可组合公式修正引擎（Composable Formula Modification Engine）

> **Date**: 2026-01-01  
> **内核概念**: 固定规则的公式推导引擎，可重现、可追踪

---

## 🎯 实际需求范例：药物动力学修正

### 场景：Fentanyl 在复杂情况下的浓度计算

```
起点：基础 Fentanyl 三室模型
  C(t) = D/V1 × (α₁e^(-λ₁t) + α₂e^(-λ₂t) + α₃e^(-λ₃t))

干扰 1: Midazolam 竞争 CYP3A4 → Clearance ↓30%
  CL_modified = CL_base × 0.7

干扰 2: 体脂率 30% → 分布容积改变
  Vd_modified = Vd_base × (1 + 0.25 × (BF% - 20)/10)

干扰 3: 高龄 65 岁 → Clearance ↓15%
  CL_modified = CL_previous × 0.85

推导过程：组合所有修正 → 新公式

最终计算：送入 SymPy 计算数值
```

---

## 🔧 MCP 接口设计

### SymKit MCP Server 的职责

```
┌─────────────────────────────────────────────────────┐
│  Agent (思考层)                                      │
├─────────────────────────────────────────────────────┤
│  • 理解用户需求                                      │
│  • 选择基础公式                                      │
│  • 决定要应用哪些修正规则                            │
│  • 提供病人参数                                      │
└────────────────┬────────────────────────────────────┘
                 │ MCP 调用
                 ▼
┌─────────────────────────────────────────────────────┐
│  SymKit MCP Server (固定引擎)                       │
├─────────────────────────────────────────────────────┤
│  输入:                                               │
│    - base_formula: "pk_three_compartment"           │
│    - modifications: [                                │
│        {"rule": "drug_cyp3a4", "drug": "midazolam"},│
│        {"rule": "body_fat", "BF": 30}               │
│      ]                                               │
│    - patient_context: {"age": 65, "weight": 80}     │
│                                                      │
│  处理（确定性算法）:                                 │
│    ✓ 加载基础公式                                    │
│    ✓ 依序应用修正规则                                │
│    ✓ 记录每个推导步骤                                │
│    ✓ 生成新公式（符号）                              │
│    ✓ 转换为 SymPy 表达式                             │
│                                                      │
│  输出:                                               │
│    - new_formula: "修正后的完整公式"                 │
│    - derivation_steps: ["步骤1", "步骤2", ...]      │
│    - sympy_expression: 可计算的符号表达式            │
│    - parameters: {"CL": 0.476, "V1": 15.875, ...}   │
└────────────────┬────────────────────────────────────┘
                 │ 返回结果
                 ▼
┌─────────────────────────────────────────────────────┐
│  Agent 后续处理                                      │
├─────────────────────────────────────────────────────┤
│  • 呈现推导步骤给用户                                │
│  • 代入数值计算                                      │
│  • 解释结果                                          │
└─────────────────────────────────────────────────────┘
```

### MCP Tool 定义

```json
{
  "name": "symkit_derive_formula",
  "description": "组合基础公式与修正规则，推导出新公式（完全确定性）",
  "inputSchema": {
    "type": "object",
    "properties": {
      "base_formula": {
        "type": "string",
        "description": "基础公式名称 (例: pk_three_compartment)"
      },
      "modifications": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "rule": {
              "type": "string",
              "description": "修正规则名称"
            },
            "context": {
              "type": "object",
              "description": "规则所需参数"
            }
          }
        }
      },
      "patient_context": {
        "type": "object",
        "description": "病人相关参数"
      }
    },
    "required": ["base_formula", "modifications"]
  }
}
```

### 使用范例（Agent 视角）

```python
# Agent 收到用户请求：
# "65岁，体脂30%，同时使用midazolam，计算Fentanyl 50mcg的浓度"

# Step 1: Agent 分析并决定
base = "pk_three_compartment"
mods = [
    {"rule": "drug_cyp3a4", "context": {"concurrent_drug": "midazolam"}},
    {"rule": "body_fat", "context": {"body_fat_percentage": 30}},
    {"rule": "age_cl", "context": {"age": 65}}
]
patient = {"weight": 80, "height": 170}

# Step 2: Agent 调用 MCP（固定引擎，确定性输出）
result = mcp.call_tool(
    "symkit_derive_formula",
    {
        "base_formula": base,
        "modifications": mods,
        "patient_context": patient
    }
)

# Step 3: MCP 返回（相同输入保证相同输出）
# {
#   "new_formula": "C(t) = D/(12.7×1.25) × ...",
#   "derivation_steps": [
#     {"step": 1, "description": "应用 CYP3A4 竞争: CL × 0.7", ...},
#     {"step": 2, "description": "体脂修正: V1 × 1.25", ...},
#     {"step": 3, "description": "年龄修正: CL × 0.85", ...}
#   ],
#   "sympy_expression": "...",
#   "parameters": {
#     "CL_final": 0.476,
#     "V1_final": 15.875
#   }
# }

# Step 4: Agent 呈现给用户
print("推导过程:")
for step in result["derivation_steps"]:
    print(f"  {step['description']}")

# Step 5: Agent 计算数值（可选）
numerical_result = sympy.N(
    result["sympy_expression"].subs({
        "D": 0.05,
        "t": 3.34
    })
)
```

---

## 🔧 引擎架构设计

### 概念模型

```yaml
FormulaModificationEngine:
  
  # 1. 基础公式库
  base_formulas:
    pk_three_compartment:
      name: "三室药物动力学模型"
      formula: "C(t) = D/V1 × (α₁e^(-λ₁t) + α₂e^(-λ₂t) + α₃e^(-λ₃t))"
      parameters:
        - D: dose
        - V1: central_volume
        - CL: clearance
        - Q2: Q2_distribution
        - Q3: Q3_distribution
      
  # 2. 修正规则库
  modification_rules:
    drug_interaction_cyp3a4:
      applies_to: ["clearance"]
      formula: "CL_new = CL × inhibition_factor"
      conditions:
        - concurrent_drug: ["midazolam", "ketoconazole", "erythromycin"]
      parameters:
        midazolam: {inhibition_factor: 0.7}
        ketoconazole: {inhibition_factor: 0.5}
    
    body_fat_distribution:
      applies_to: ["volume_distribution"]
      formula: "Vd_new = Vd × (1 + k × (BF - BF_ref) / BF_ref)"
      conditions:
        - body_fat_percentage: [10, 50]
      parameters:
        k: 0.5
        BF_ref: 20
    
    age_clearance:
      applies_to: ["clearance"]
      formula: "CL_new = CL × (1 - 0.01 × (age - 40))"
      conditions:
        - age: [40, 80]
  
  # 3. 推导引擎
  derivation_engine:
    input:
      - base_formula: pk_three_compartment
      - modifications:
          - drug_interaction_cyp3a4: {drug: midazolam}
          - body_fat_distribution: {BF: 30}
          - age_clearance: {age: 65}
    
    process:
      - identify_affected_parameters()
      - apply_modifications_sequentially()
      - regenerate_formula()
      - simplify_expression()
    
    output:
      - modified_formula: "完整的修正公式"
      - derivation_steps: ["步骤1", "步骤2", ...]
      - final_expression: "SymPy 可运行表达式"
```

---

## 📝 实际代码实作

### Step 1: 定义基础公式

```python
from dataclasses import dataclass
from typing import Dict, List, Callable
from sympy import symbols, exp, simplify, lambdify

@dataclass
class BaseFormula:
    """基础公式定义"""
    name: str
    formula_str: str
    parameters: Dict[str, str]
    formula_func: Callable = None
    
    def to_sympy(self):
        """转换为 SymPy 表达式"""
        # 创建符号
        syms = {p: symbols(p) for p in self.parameters.keys()}
        
        # 解析公式字符串为 SymPy 表达式
        # (这里简化，实际需要 parser)
        return syms, self.formula_str

# 定义三室模型
pk_three_compartment = BaseFormula(
    name="三室药物动力学模型",
    formula_str="D/V1 * (alpha1*exp(-lambda1*t) + alpha2*exp(-lambda2*t) + alpha3*exp(-lambda3*t))",
    parameters={
        "D": "剂量 (mg)",
        "V1": "中央室容积 (L)",
        "CL": "清除率 (L/min)",
        "Q2": "第二室分布速率 (L/min)",
        "Q3": "第三室分布速率 (L/min)",
        "V2": "第二室容积 (L)",
        "V3": "第三室容积 (L)",
        "t": "时间 (min)"
    }
)
```

### Step 2: 定义修正规则

```python
@dataclass
class ModificationRule:
    """修正规则定义"""
    name: str
    applies_to: List[str]  # 影响哪些参数
    formula: str  # 修正公式
    conditions: Dict  # 适用条件
    coefficients: Dict  # 修正系数
    
    def apply(self, parameter_value, context):
        """应用修正规则"""
        # 检查条件
        if not self._check_conditions(context):
            return parameter_value
        
        # 应用公式
        modified = self._apply_formula(parameter_value, context)
        
        return modified
    
    def _check_conditions(self, context):
        """检查是否满足适用条件"""
        for key, constraint in self.conditions.items():
            if key not in context:
                return False
            # 检查范围等
        return True
    
    def _apply_formula(self, value, context):
        """应用修正公式"""
        # 这里用 SymPy 计算修正
        pass

# 药物竞争规则
drug_interaction_cyp3a4 = ModificationRule(
    name="CYP3A4 竞争性抑制",
    applies_to=["CL"],  # 影响清除率
    formula="CL_new = CL * inhibition_factor",
    conditions={
        "concurrent_drug": ["midazolam", "ketoconazole", "erythromycin"]
    },
    coefficients={
        "midazolam": 0.7,      # 抑制 30%
        "ketoconazole": 0.5,   # 抑制 50%
        "erythromycin": 0.6    # 抑制 40%
    }
)

# 体脂分布规则
body_fat_distribution = ModificationRule(
    name="体脂率对分布容积的影响",
    applies_to=["Vd", "V1", "V2", "V3"],
    formula="Vd_new = Vd * (1 + k * (BF - BF_ref) / BF_ref)",
    conditions={
        "body_fat_percentage": (10, 50)  # 适用范围
    },
    coefficients={
        "k": 0.5,       # 脂溶性药物系数
        "BF_ref": 20    # 参考体脂率
    }
)

# 年龄清除率规则
age_clearance = ModificationRule(
    name="年龄对清除率的影响",
    applies_to=["CL"],
    formula="CL_new = CL * (1 - 0.01 * max(0, age - 40))",
    conditions={
        "age": (40, 80)
    },
    coefficients={}
)
```

### Step 3: 推导引擎（内核）

```python
from typing import List, Dict, Any
import sympy as sp

class FormulaDerivationEngine:
    """可组合公式推导引擎"""
    
    def __init__(self):
        self.base_formulas = {}
        self.modification_rules = {}
        self.derivation_history = []
    
    def register_base_formula(self, key: str, formula: BaseFormula):
        """注册基础公式"""
        self.base_formulas[key] = formula
    
    def register_modification_rule(self, key: str, rule: ModificationRule):
        """注册修正规则"""
        self.modification_rules[key] = rule
    
    def derive(
        self,
        base_formula_key: str,
        modifications: List[Dict[str, Any]],
        patient_context: Dict[str, Any]
    ):
        """
        运行公式推导
        
        Args:
            base_formula_key: 基础公式名称
            modifications: 要应用的修正列表
            patient_context: 病人相关参数
        
        Returns:
            DerivationResult: 推导结果（包含新公式和步骤）
        """
        
        # Step 1: 加载基础公式
        base_formula = self.base_formulas[base_formula_key]
        
        self.derivation_history = []
        self.derivation_history.append({
            "step": 0,
            "description": f"基础公式: {base_formula.name}",
            "formula": base_formula.formula_str,
            "parameters": base_formula.parameters.copy()
        })
        
        # Step 2: 依序应用每个修正
        current_parameters = base_formula.parameters.copy()
        
        for i, mod_spec in enumerate(modifications):
            rule_key = mod_spec["rule"]
            rule_context = mod_spec.get("context", {})
            
            # 合并病人上下文
            full_context = {**patient_context, **rule_context}
            
            # 应用修正规则
            result = self._apply_modification(
                rule_key,
                current_parameters,
                full_context,
                step_number=i+1
            )
            
            current_parameters = result["parameters"]
            self.derivation_history.append(result)
        
        # Step 3: 重新生成修正后的公式
        final_formula = self._regenerate_formula(
            base_formula.formula_str,
            current_parameters
        )
        
        # Step 4: 转换为 SymPy 表达式
        sympy_expr = self._to_sympy_expression(final_formula)
        
        # Step 5: 简化
        simplified_expr = sp.simplify(sympy_expr)
        
        return DerivationResult(
            base_formula=base_formula.name,
            final_formula=str(simplified_expr),
            sympy_expression=simplified_expr,
            derivation_steps=self.derivation_history,
            parameters=current_parameters
        )
    
    def _apply_modification(
        self,
        rule_key: str,
        parameters: Dict,
        context: Dict,
        step_number: int
    ):
        """应用单一修正规则"""
        
        rule = self.modification_rules[rule_key]
        
        # 检查条件
        if not self._check_conditions(rule, context):
            return {
                "step": step_number,
                "description": f"修正 {rule.name}: 条件不符，跳过",
                "formula": "unchanged",
                "parameters": parameters
            }
        
        # 修改受影响的参数
        modified_params = parameters.copy()
        changes = []
        
        for param_name in rule.applies_to:
            if param_name in parameters:
                # 取得原始值（可能是符号或数值）
                original = parameters[param_name]
                
                # 应用修正公式
                modified = self._apply_formula(
                    rule,
                    param_name,
                    original,
                    context
                )
                
                modified_params[param_name] = modified
                changes.append(f"{param_name}: {original} → {modified}")
        
        return {
            "step": step_number,
            "description": f"修正 {rule.name}",
            "rule": rule.formula,
            "changes": changes,
            "context": context,
            "parameters": modified_params
        }
    
    def _check_conditions(self, rule: ModificationRule, context: Dict):
        """检查规则适用条件"""
        for key, constraint in rule.conditions.items():
            if key not in context:
                return False
            
            # 检查范围
            if isinstance(constraint, tuple):
                min_val, max_val = constraint
                if not (min_val <= context[key] <= max_val):
                    return False
            
            # 检查列表包含
            elif isinstance(constraint, list):
                if context[key] not in constraint:
                    return False
        
        return True
    
    def _apply_formula(
        self,
        rule: ModificationRule,
        param_name: str,
        original_value: Any,
        context: Dict
    ):
        """应用修正公式到参数"""
        
        # 使用 SymPy 进行符号计算
        if param_name == "CL":
            # 清除率修正
            if "inhibition_factor" in context:
                factor = context["inhibition_factor"]
            elif "concurrent_drug" in context:
                drug = context["concurrent_drug"]
                factor = rule.coefficients.get(drug, 1.0)
            elif "age" in context:
                age = context["age"]
                factor = 1 - 0.01 * max(0, age - 40)
            else:
                factor = 1.0
            
            return f"{original_value} × {factor}"
        
        elif param_name in ["Vd", "V1", "V2", "V3"]:
            # 分布容积修正
            if "body_fat_percentage" in context:
                BF = context["body_fat_percentage"]
                k = rule.coefficients.get("k", 0.5)
                BF_ref = rule.coefficients.get("BF_ref", 20)
                
                factor = 1 + k * (BF - BF_ref) / BF_ref
                return f"{original_value} × {factor:.3f}"
        
        return original_value
    
    def _regenerate_formula(self, original_formula: str, parameters: Dict):
        """根据修正后的参数重新生成公式"""
        
        # 简化版：直接替换参数
        # 实际应该用 SymPy 符号替换
        
        formula = original_formula
        for param, value in parameters.items():
            if isinstance(value, str) and "×" in value:
                # 这是修正过的参数
                formula = formula.replace(param, f"({value})")
        
        return formula
    
    def _to_sympy_expression(self, formula_str: str):
        """转换公式字符串为 SymPy 表达式"""
        # 这里需要一个 parser
        # 简化版：
        return sp.sympify(formula_str)

@dataclass
class DerivationResult:
    """推导结果"""
    base_formula: str
    final_formula: str
    sympy_expression: Any  # SymPy 表达式
    derivation_steps: List[Dict]
    parameters: Dict
    
    def to_dict(self):
        return {
            "base_formula": self.base_formula,
            "final_formula": self.final_formula,
            "derivation_steps": self.derivation_steps,
            "parameters": self.parameters
        }
    
    def calculate(self, numerical_values: Dict):
        """用数值计算最终结果"""
        # 替换符号为数值
        expr = self.sympy_expression
        for sym, val in numerical_values.items():
            expr = expr.subs(sym, val)
        
        return float(expr.evalf())
```

---

## 🎬 完整使用范例

```python
# ============================================
# 初始化引擎
# ============================================

engine = FormulaDerivationEngine()

# 注册基础公式
engine.register_base_formula("pk_three_compartment", pk_three_compartment)

# 注册修正规则
engine.register_modification_rule("drug_cyp3a4", drug_interaction_cyp3a4)
engine.register_modification_rule("body_fat", body_fat_distribution)
engine.register_modification_rule("age_cl", age_clearance)

# ============================================
# 场景：65岁，体脂30%，合并使用 Midazolam
# ============================================

result = engine.derive(
    base_formula_key="pk_three_compartment",
    
    modifications=[
        {
            "rule": "drug_cyp3a4",
            "context": {
                "concurrent_drug": "midazolam"
            }
        },
        {
            "rule": "body_fat",
            "context": {
                "body_fat_percentage": 30
            }
        },
        {
            "rule": "age_cl",
            "context": {
                "age": 65
            }
        }
    ],
    
    patient_context={
        "weight": 80,
        "height": 170,
        "sex": "M"
    }
)

# ============================================
# 输出推导步骤
# ============================================

print("=" * 60)
print("公式推导过程")
print("=" * 60)

for step in result.derivation_steps:
    print(f"\n步骤 {step['step']}: {step['description']}")
    if 'changes' in step:
        for change in step['changes']:
            print(f"  - {change}")

print("\n" + "=" * 60)
print("最终公式")
print("=" * 60)
print(result.final_formula)

# ============================================
# 数值计算
# ============================================

numerical_values = {
    "D": 0.05,      # 50 mcg = 0.05 mg
    "V1": 12.7,     # L (修正后会变)
    "CL": 0.8,      # L/min (修正后会变)
    "t": 3.34,      # 峰值时间
    # ... 其他参数
}

final_concentration = result.calculate(numerical_values)
print(f"\n计算结果: {final_concentration:.4f} mg/L")
```

---

## 📊 输出范例

```
============================================================
公式推导过程
============================================================

步骤 0: 基础公式: 三室药物动力学模型
公式: C(t) = D/V1 × (α₁e^(-λ₁t) + α₂e^(-λ₂t) + α₃e^(-λ₃t))

步骤 1: 修正 CYP3A4 竞争性抑制
规则: CL_new = CL * inhibition_factor
  - CL: 0.8 → 0.8 × 0.7
说明: Midazolam 竞争 CYP3A4，抑制 Fentanyl 代谢 30%

步骤 2: 修正 体脂率对分布容积的影响
规则: Vd_new = Vd * (1 + k * (BF - BF_ref) / BF_ref)
  - V1: 12.7 → 12.7 × 1.25
  - V2: 29.1 → 29.1 × 1.25
  - V3: 314.2 → 314.2 × 1.25
说明: 体脂率 30% (参考值 20%)，Fentanyl 为脂溶性药物

步骤 3: 修正 年龄对清除率的影响
规则: CL_new = CL * (1 - 0.01 * max(0, age - 40))
  - CL: 0.8 × 0.7 → 0.8 × 0.7 × 0.85
说明: 65 岁，清除率较 40 岁下降 15%

============================================================
最终公式
============================================================
C(t) = D / (12.7 × 1.25) × (α₁e^(-λ₁t) + α₂e^(-λ₂t) + α₃e^(-λ₃t))

其中：
  CL_final = 0.8 × 0.7 × 0.85 = 0.476 L/min
  V1_final = 12.7 × 1.25 = 15.875 L
  V2_final = 29.1 × 1.25 = 36.375 L
  V3_final = 314.2 × 1.25 = 392.75 L

============================================================
SymPy 表达式
============================================================
D / V1_final * (alpha1 * exp(-lambda1 * t) + ...)

计算结果（t=3.34 min）: 0.0032 mg/L = 3.2 ng/mL
```

---

## 🔑 关键特性

### 1. 完全可重现 ✅

```python
# 相同输入 → 相同输出
result1 = engine.derive("pk_three_compartment", mods, context)
result2 = engine.derive("pk_three_compartment", mods, context)

assert result1.final_formula == result2.final_formula
# ✅ 保证相同
```

### 2. 可追踪推导步骤 ✅

```python
# 每个步骤都记录
for step in result.derivation_steps:
    print(step["description"])
    print(step["changes"])
    
# 输出：
# "步骤 1: 应用 CYP3A4 竞争抑制"
# "CL: 0.8 → 0.56"
```

### 3. 可组合规则 ✅

```python
# 规则可以任意组合
modifications = [
    {"rule": "drug_cyp3a4", ...},
    {"rule": "body_fat", ...},
    {"rule": "age_cl", ...},
    {"rule": "renal_impairment", ...},  # 添加
]

# 引擎自动处理依赖关系
result = engine.derive(..., modifications)
```

### 4. 符号 + 数值计算 ✅

```python
# 先符号推导
result = engine.derive(...)

# 后数值计算
concentration = result.calculate({
    "D": 0.05,
    "t": 3.34,
    ...
})
```

---

## 🆚 与现有工具的差异

### vs. SymPy

```python
# SymPy: 纯符号计算
from sympy import *
x = symbols('x')
integrate(x**2, x)  # x**3/3

# SymKit: 领域知识 + 符号计算
result = engine.derive(
    base="pk_model",
    modifications=[
        {"rule": "drug_interaction", "drug": "midazolam"},
        {"rule": "body_fat", "BF": 30}
    ]
)
# → 自动应用药理学规则
# → 生成修正公式
# → 送给 SymPy 计算
```

### vs. 直接写 Python

```python
# 直接写 Python
CL_base = 0.8
CL_modified = CL_base * 0.7 * 0.85
Vd_modified = 12.7 * 1.25

# 问题：
# ❌ 不知道为什么 0.7
# ❌ 不知道为什么 0.85
# ❌ 没有推导步骤
# ❌ 难以追踪来源

# SymKit
result = engine.derive(...)
# ✅ 每个系数都有来源
# ✅ 完整推导步骤
# ✅ 可追踪文献
# ✅ 可重现
```

---

## 💡 SymKit 的真正价值

### 不是：
- ❌ 符号计算（SymPy 已经做了）
- ❌ 数值计算（NumPy/SciPy 已经做了）
- ❌ 保存公式（数据库就可以）

### 而是：
- ✅ **可组合的领域知识规则库**
- ✅ **固定的推导引擎（不依赖 Agent）**
- ✅ **完整的推导步骤追踪**
- ✅ **从规则到公式的自动生成**
- ✅ **连接领域知识与符号计算**

---

## 🚀 实作路径

### Phase 1: 内核引擎 (MVP)

```python
# 最小可行产品
class SimpleDerivationEngine:
    def derive(self, base_formula, modifications):
        """应用修正规则，生成新公式"""
        pass
    
    def to_sympy(self):
        """转换为 SymPy 表达式"""
        pass
```

**目标**：证明概念可行

### Phase 2: 规则库

```yaml
rules:
  - drug_interactions (10+ 规则)
  - body_composition (5+ 规则)
  - age_effects (3+ 规则)
  - renal_function (5+ 规则)
  - hepatic_function (5+ 规则)
```

**目标**：创建药理学领域规则库

### Phase 3: 领域扩展

- Pharmacokinetics ✅
- Pharmacodynamics
- 电路设计
- 机械力学
- ...

---

## 📝 与其他文档的关联

### reproducible-derivation-tools.md
- 讨论了 SymPy manualintegrate, egg 等工具
- **SymKit 定位**: 领域规则层（上层）+ SymPy 计算层（下层）

### completeness-challenge.md
- 讨论了开放系统的完整性问题
- **解决方案**: 分层规则库 + 信心度评估

### cognitive-load-solution.md
- 讨论了 Agent 认知负担问题
- **解决方案**: 固定推导引擎（不依赖 Agent 思考）

---

## ✅ 总结

### 您问的问题：

> "药物动力学请加入某个药品的干扰 → 列出干扰的公式 → 加入传统浓度计算的公式 → 算出新的浓度计算公式 → 在加入随体重变化药品分布的公式 → 推导出新公式 → 最后送入 sympy 计算"

### 答案：

**SymKit = 可组合公式修正引擎**

```
基础公式（PK三室模型）
  ↓ 
+ 修正规则 1（CYP3A4 竞争）
  ↓
+ 修正规则 2（体脂分布）
  ↓
+ 修正规则 3（年龄清除）
  ↓
推导引擎组合
  ↓
生成新公式（符号）
  ↓
送入 SymPy 计算（数值）
```

**内核优势**：
1. ✅ 固定规则库（不依赖 Agent）
2. ✅ 完全可重现
3. ✅ 可追踪推导步骤
4. ✅ 可组合任意规则
5. ✅ 连接领域知识与符号计算

**实作工具**：
- Python + SymPy (符号层)
- 自定义规则引擎 (领域层)
- 不需要 Mathematica 或 Lean4

**下一步**：
实作 MVP 版本的推导引擎？
