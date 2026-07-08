# 推导模板系统设计文档

## 1. 内核理念

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  模板 ≠ 答案                                                                │
│  模板 = 推导的「骨架」+ 「提示」                                            │
│                                                                             │
│  • Agent 负责：选择模板、填入参数、与 User 讨论                             │
│  • 模板提供：推导步骤、需要的公式、参数检查清单                             │
│  • sympy-mcp 负责：精确运行每一步符号运算                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. 模板格式设计 (YAML)

### 2.1 基本结构

```yaml
# template_schema.yaml
template:
  id: string           # 唯一识别码
  name: string         # 人类可读名称
  domain: string       # 领域：mechanics, circuits, pharmacokinetics, etc.
  tags: [string]       # 标签，用于搜索
  description: string  # 描述这个模板解决什么问题
  
  # 参数定义
  parameters:
    required:          # 必要参数
      - name: string
        symbol: string
        type: string   # positive_real, real, integer, etc.
        unit: string   # SI 单位
        description: string
    optional:          # 可选参数（有默认值）
      - name: string
        symbol: string
        default: value
        unit: string
        description: string
  
  # 推导步骤
  steps:
    - id: number
      name: string
      description: string
      action: string   # solve, substitute, simplify, integrate, etc.
      
      # 这一步的输入输出
      inputs: [symbol]
      outputs: [symbol]
      
      # 提示 Agent 用什么公式/方法
      hint:
        formula: string        # 公式名称或表达式
        sympy_mcp_tool: string # 建议使用的 sympy-mcp 工具
        explanation: string    # 解释这一步在做什么
      
      # 验证条件
      verification:
        dimension_check: boolean
        expected_form: string   # 预期结果的形式
  
  # 最终输出
  outputs:
    - symbol: string
      name: string
      unit: string
      description: string
  
  # 代码生成模板
  code_template:
    python: string     # Jinja2 模板
    docstring: string
```

### 2.2 完整范例：安全带张力分析

```yaml
template:
  id: seatbelt_tension_analysis
  name: "安全带张力分析"
  domain: mechanics
  tags: [collision, safety, spring, energy_conservation]
  description: |
    分析车辆碰撞时安全带的最大张力。
    结合动量守恒（碰撞）和能量守恒（安全带伸长）。
  
  parameters:
    required:
      - name: vehicle_1_mass
        symbol: M1
        type: positive_real
        unit: kg
        description: 车辆 1 的质量
      
      - name: vehicle_2_mass
        symbol: M2
        type: positive_real
        unit: kg
        description: 车辆 2 的质量（被撞车辆，初始静止）
      
      - name: initial_velocity
        symbol: v
        type: positive_real
        unit: m/s
        description: 车辆 1 的初始速度
      
      - name: person_mass
        symbol: m
        type: positive_real
        unit: kg
        description: 乘客质量
      
      - name: seatbelt_spring_constant
        symbol: k
        type: positive_real
        unit: N/m
        description: 安全带的等效弹簧系数
    
    optional:
      - name: safety_factor
        symbol: SF
        type: positive_real
        default: 3.0
        description: 材料设计的安全系数
      
      - name: collision_angle
        symbol: theta
        type: real
        default: 0
        unit: rad
        description: 碰撞角度（0 = 正向碰撞）
  
  # 推导前的检查
  preconditions:
    - check: "M2 > 0"
      message: "车辆 2 必须有质量（非零）"
    - check: "v > 0"
      message: "初始速度必须为正"
    - check: "k > 0"
      message: "弹簧系数必须为正"
  
  steps:
    - id: 1
      name: momentum_conservation
      description: 使用动量守恒计算碰撞后速度
      action: solve
      inputs: [M1, M2, v]
      outputs: [v_f]
      hint:
        formula: "M1 * v = (M1 + M2) * v_f"
        sympy_mcp_tool: solve_algebraically
        explanation: |
          假设完全非弹性碰撞（两车黏在一起），
          碰撞前总动量 = 碰撞后总动量
      verification:
        dimension_check: true
        expected_form: "M1 * v / (M1 + M2)"
    
    - id: 2
      name: velocity_change
      description: 计算乘客的速度变化量
      action: substitute
      inputs: [v, v_f]
      outputs: [Delta_v]
      hint:
        formula: "Delta_v = v - v_f"
        sympy_mcp_tool: substitute_expression
        explanation: |
          乘客相对于车辆的速度变化
          这是安全带需要吸收的速度
      verification:
        dimension_check: true
        expected_form: "M2 * v / (M1 + M2)"
    
    - id: 3
      name: energy_conservation
      description: 使用能量守恒计算安全带伸长量
      action: solve
      inputs: [Delta_v, m, k]
      outputs: [x]
      hint:
        formula: "(1/2) * m * Delta_v**2 = (1/2) * k * x**2"
        sympy_mcp_tool: solve_algebraically
        explanation: |
          乘客的动能 = 安全带的弹性位能
          (1/2)mΔv² = (1/2)kx²
      verification:
        dimension_check: true
        expected_form: "Delta_v * sqrt(m / k)"
    
    - id: 4
      name: max_tension
      description: 计算安全带最大张力
      action: substitute
      inputs: [k, x]
      outputs: [T_max]
      hint:
        formula: "T_max = k * x"
        sympy_mcp_tool: substitute_expression
        explanation: |
          弹簧力 F = kx
          在最大伸长时，张力最大
      verification:
        dimension_check: true
        expected_form: "Delta_v * sqrt(m * k)"
    
    - id: 5
      name: material_requirement
      description: 计算材料强度要求
      action: multiply
      inputs: [T_max, SF]
      outputs: [sigma_required]
      hint:
        formula: "sigma_required = T_max * SF"
        explanation: |
          工程设计需要考虑安全系数
          SF = 2.0 (一般), 3.0 (安全关键), 4.0 (航空)
      verification:
        dimension_check: true
  
  outputs:
    - symbol: v_f
      name: 碰撞后速度
      unit: m/s
      description: 碰撞后两车共同速度
    
    - symbol: Delta_v
      name: 速度变化量
      unit: m/s
      description: 乘客相对速度变化
    
    - symbol: x
      name: 安全带伸长量
      unit: m
      description: 安全带最大伸长
    
    - symbol: T_max
      name: 最大张力
      unit: N
      description: 安全带承受的最大张力
    
    - symbol: sigma_required
      name: 材料强度要求
      unit: N
      description: 考虑安全系数后的强度要求
  
  # 最终公式（供验证用）
  final_formulas:
    T_max: "M2 * v * sqrt(m * k) / (M1 + M2)"
    T_max_with_angle: "M2 * v * cos(theta) * sqrt(m * k) / (M1 + M2)"
  
  # 代码生成模板
  code_template:
    python: |
      def calculate_seatbelt_tension(
          M1: float,  # {{ parameters.M1.description }} [{{ parameters.M1.unit }}]
          M2: float,  # {{ parameters.M2.description }} [{{ parameters.M2.unit }}]
          v: float,   # {{ parameters.v.description }} [{{ parameters.v.unit }}]
          m: float,   # {{ parameters.m.description }} [{{ parameters.m.unit }}]
          k: float,   # {{ parameters.k.description }} [{{ parameters.k.unit }}]
          SF: float = {{ parameters.SF.default }},  # {{ parameters.SF.description }}
      ) -> dict:
          """
          {{ template.description }}
          
          Auto-generated by SymKit from template: {{ template.id }}
          """
          import math
          
          # Step 1: {{ steps[0].description }}
          v_f = M1 * v / (M1 + M2)
          
          # Step 2: {{ steps[1].description }}
          delta_v = v - v_f
          
          # Step 3: {{ steps[2].description }}
          x = delta_v * math.sqrt(m / k)
          
          # Step 4: {{ steps[3].description }}
          T_max = k * x
          
          # Step 5: {{ steps[4].description }}
          sigma_required = T_max * SF
          
          return {
              "v_f": v_f,
              "delta_v": delta_v,
              "x": x,
              "T_max": T_max,
              "sigma_required": sigma_required,
          }
  
  # 相关资源
  references:
    - "动量守恒定律"
    - "能量守恒定律"
    - "弹性力学 - 虎克定律"
  
  # 可能的变体
  variants:
    - id: seatbelt_tension_with_angle
      description: 考虑碰撞角度的版本
      modifications:
        - step: 2
          formula: "Delta_v = (v - v_f) * cos(theta)"
    
    - id: seatbelt_tension_partial_inelastic
      description: 部分非弹性碰撞（考虑能量损失）
      additional_parameters:
        - name: restitution_coefficient
          symbol: e
          type: real
          range: [0, 1]
```

## 3. MCP Tools 设计

### 3.1 模板相关工具

```python
# tools/template.py

@mcp.tool()
def list_templates(
    domain: str | None = None,
    tag: str | None = None,
) -> dict:
    """列出可用的推导模板"""
    pass

@mcp.tool()
def get_template(
    template_id: str,
) -> dict:
    """获取模板详细信息"""
    pass

@mcp.tool()
def check_template_params(
    template_id: str,
    given_params: dict,
) -> dict:
    """检查参数完整性，返回缺少的参数"""
    pass

@mcp.tool()
def suggest_template(
    problem_description: str,
    domain: str | None = None,
) -> dict:
    """根据问题描述建议合适的模板"""
    pass

@mcp.tool()
def execute_template_step(
    template_id: str,
    step_id: int,
    params: dict,
    previous_results: dict | None = None,
) -> dict:
    """运行模板的单一步骤"""
    pass

@mcp.tool()
def generate_code_from_template(
    template_id: str,
    params: dict,
    language: str = "python",
) -> dict:
    """从模板生成可运行代码"""
    pass
```

## 4. 工作流程范例

### User 问题
> "质量 70kg 的人在 1500kg 的车子里，以 50km/h 撞到静止的 2000kg 车，
> 安全带系数 5000 N/m，求最大张力？"

### Agent 工作流程

```
1. Agent 分析问题
   → 识别：碰撞 + 安全带 + 张力
   
2. 调用 suggest_template("碰撞 安全带 张力", domain="mechanics")
   → 返回：seatbelt_tension_analysis (匹配度 0.95)
   
3. 调用 get_template("seatbelt_tension_analysis")
   → 获取模板详情、参数表表
   
4. 调用 check_template_params(
       template_id="seatbelt_tension_analysis",
       given_params={
           "M1": 1500, "M2": 2000, "v": 13.89,  # 50km/h → m/s
           "m": 70, "k": 5000
       }
   )
   → 返回：complete=True, missing=[]
   
5. 逐步运行（或询问 User 确认）
   
   5.1 execute_template_step(step_id=1, ...)
       → v_f = 5.95 m/s
       
   5.2 execute_template_step(step_id=2, ...)
       → Delta_v = 7.94 m/s
       
   5.3 execute_template_step(step_id=3, ...)
       → x = 0.94 m
       
   5.4 execute_template_step(step_id=4, ...)
       → T_max = 4700 N
       
   5.5 execute_template_step(step_id=5, ...)
       → sigma_required = 14100 N (SF=3.0)

6. 调用 generate_code_from_template(...)
   → 生成可运行的 Python 函数
```

## 5. 模板目录结构

```
symkit/
└── templates/
    ├── mechanics/
    │   ├── collision/
    │   │   ├── seatbelt_tension.yaml
    │   │   ├── elastic_collision_1d.yaml
    │   │   └── inelastic_collision_2d.yaml
    │   ├── projectile/
    │   │   ├── projectile_motion.yaml
    │   │   └── projectile_with_drag.yaml
    │   └── oscillation/
    │       ├── simple_harmonic.yaml
    │       └── damped_harmonic.yaml
    │
    ├── circuits/
    │   ├── filters/
    │   │   ├── rc_lowpass.yaml
    │   │   ├── rc_highpass.yaml
    │   │   └── rlc_bandpass.yaml
    │   └── amplifiers/
    │       └── opamp_inverting.yaml
    │
    ├── pharmacokinetics/
    │   ├── one_compartment.yaml
    │   ├── two_compartment.yaml
    │   └── michaelis_menten.yaml
    │
    └── thermodynamics/
        ├── carnot_cycle.yaml
        ├── ideal_gas_processes.yaml
        └── heat_engine_efficiency.yaml
```

## 6. 优势

1. **可复用**：模板可以跨问题复用
2. **可客制**：参数化设计，适应不同情境
3. **可追踪**：每步有明确的输入输出
4. **可验证**：内置维度检查和预期结果
5. **可扩展**：社群可以贡献新模板
6. **与 Agent 协作**：Agent 选择模板，User 确认参数
