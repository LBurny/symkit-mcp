# Audio Circuit Design - SymKit 领域规划

> **Domain**: Audio Electronics / Analog Circuit Design  
> **Priority**: ⭐⭐⭐ High (User Interest)  
> **Status**: Planning Phase

---

## 🎵 领域概述

音响电路学涉及仿真信号处理、放大器设计、滤波器设计等。这个领域特别适合推导框架，因为：

1. **基础原理明确**：欧姆定律、KVL/KCL、转移函数
2. **修正项丰富**：寄生电容、非理想 Op-amp、负载效应
3. **实用性强**：实际电路总是非理想的

---

## 📐 Principles（基础原理）

### 1. Ohm's Law
```yaml
principle:
  id: ohms_law
  name: 欧姆定律
  base_form: "V = I * R"
  lean4_reference:
    module: "Mathlib.Physics.Electrical.Ohm"
    theorem: "ohms_law"
  
  variables:
    V: {description: "电压", unit: "V", type: "real"}
    I: {description: "电流", unit: "A", type: "real"}
    R: {description: "电阻", unit: "Ω", type: "positive_real"}
```

### 2. Kirchhoff's Voltage Law (KVL)
```yaml
principle:
  id: kvl
  name: 克希荷夫电压定律
  base_form: "Σ(V_i) = 0"  # 回路电压和为零
  
  description: |
    沿着闭合回路，电压降的代数和为零
```

### 3. Transfer Function (理想)
```yaml
principle:
  id: transfer_function
  name: 转移函数
  base_form: "H(s) = V_out(s) / V_in(s)"
  
  laplace_domain: true
```

---

## 🔧 Modifications（修正项）

### 1. Parasitic Capacitance（寄生电容）
```yaml
modification:
  id: parasitic_capacitance
  name: 寄生电容
  
  term: "1 / (1 + s*R*C_parasitic)"
  
  description: |
    实际电路中，PCB 走线、组件引脚都会产生寄生电容
    在高频时影响显著
  
  typical_values:
    pcb_trace_per_cm: "0.1-1 pF"
    smd_resistor: "0.05-0.5 pF"
    through_hole: "1-5 pF"
  
  when_to_use:
    - "高频应用 (>100kHz)"
    - "精密电路设计"
```

### 2. Op-Amp Non-Ideal (非理想运算放大器)
```yaml
modification:
  id: opamp_non_ideal
  name: 非理想运算放大器
  
  modifications:
    finite_gain:
      term: "A_ol / (1 + A_ol * beta)"
      description: "有限开回路增益"
      typical: "A_ol = 10^5 ~ 10^6"
    
    input_bias_current:
      term: "+ I_bias * R"
      description: "输入偏置电流造成的电压偏移"
      typical: "1 pA ~ 100 nA"
    
    slew_rate_limit:
      description: "输出电压变化率限制"
      typical: "0.5 ~ 50 V/μs"
    
    gbw_product:
      description: "增益带宽积限制"
      typical: "1 ~ 100 MHz"
```

### 3. Load Effect（负载效应）
```yaml
modification:
  id: load_effect
  name: 负载效应
  
  term: "Z_out || Z_load"
  
  description: |
    输出阻抗与负载阻抗并联
    影响实际输出电压和频率响应
  
  when_to_use:
    - "低阻抗负载"
    - "长传输线"
    - "多级放大器级联"
```

### 4. Thermal Noise（热噪声）
```yaml
modification:
  id: thermal_noise
  name: 热噪声 (Johnson-Nyquist)
  
  term: "sqrt(4 * k_B * T * R * BW)"
  
  variables:
    k_B: {value: "1.38e-23", unit: "J/K", description: "波兹曼常数"}
    T: {unit: "K", description: "绝对温度"}
    R: {unit: "Ω", description: "电阻值"}
    BW: {unit: "Hz", description: "带宽"}
  
  typical_scenario: "低噪声前级设计"
```

---

## 🎯 Derived Forms（常见电路）

### 1. RC Low-Pass Filter (实际)
```yaml
derived_form:
  id: rc_lowpass_with_parasitics
  name: RC 低通滤波器（考虑寄生效应）
  
  based_on:
    principle: transfer_function
    modifications: [parasitic_capacitance, load_effect]
  
  ideal_form: "H(s) = 1 / (1 + s*R*C)"
  
  with_parasitics:
    equation: |
      H(s) = 1 / (1 + s*R*(C + C_parasitic))
    
    effect: |
      - 实际截止频率降低
      - f_c_actual < f_c_ideal
```

### 2. Inverting Amplifier (非理想 Op-amp)
```yaml
derived_form:
  id: inverting_amp_non_ideal
  name: 反相放大器（非理想）
  
  based_on:
    principle: opamp_inverting
    modifications: [opamp_non_ideal, load_effect]
  
  ideal_gain: "- R_f / R_in"
  
  actual_gain: |
    G = - (R_f / R_in) * (A_ol / (1 + A_ol * (1 + R_f/R_in)))
  
  frequency_response: |
    f_3dB = GBW / (1 + R_f/R_in)
```

### 3. Sallen-Key Filter (Active Filter)
```yaml
derived_form:
  id: sallen_key_lowpass
  name: Sallen-Key 低通滤波器
  
  topology: "二阶主动滤波器"
  
  transfer_function: |
    H(s) = K / (s² + s*(ω₀/Q) + ω₀²)
  
  parameters:
    omega_0: "sqrt(1/(R1*R2*C1*C2))"
    Q: "sqrt(R1*R2*C1*C2) / (R2*C1 + R1*C1*(1-K) + R2*C2)"
    K: "1 + R_f/R_in"  # Op-amp gain
  
  modifications_to_consider:
    - opamp_gbw_product: "限制高频性能"
    - component_tolerance: "影响 Q 值和共振频率"
```

---

## 🧪 应用场景范例

### 场景 1：设计麦克风前级放大器

**问题**：
> "设计一个麦克风前级，增益 60dB，输入阻抗 2kΩ，噪声要低"

**推导流程**：
1. **选择拓扑**：非反相放大器（高输入阻抗）
2. **基础计算**：
   - 增益 60dB = 1000 倍
   - G = 1 + R_f/R_in = 1000
3. **应用修正**：
   - `thermal_noise`：计算电阻产生的噪声
   - `opamp_input_noise`：选择低噪声 Op-amp
   - `bandwidth_limit`：GBW / G = 实际带宽
4. **组件选择**：
   - Op-amp: OPA1612 (低噪声，GBW=10MHz)
   - R_in = 2kΩ → R_f = 1.998 MΩ

### 场景 2：音响 EQ 设计

**问题**：
> "设计一个 1kHz 的 parametric EQ，可调 ±12dB"

**推导流程**：
1. **选择拓扑**：Band-pass filter + summing amplifier
2. **基础参数**：
   - Center frequency: f₀ = 1kHz
   - Q factor: 决定带宽
3. **应用修正**：
   - `component_tolerance`：实际中心频率偏移
   - `opamp_gbw`：确保频率响应平坦

---

## 📚 知识库结构

```
formulas/audio_circuits/
├── principles/
│   ├── ohms_law.yaml
│   ├── kvl.yaml
│   ├── kcl.yaml
│   ├── transfer_function.yaml
│   └── opamp_golden_rules.yaml
│
├── modifications/
│   ├── parasitic_capacitance.yaml
│   ├── opamp_non_ideal.yaml
│   ├── load_effect.yaml
│   ├── thermal_noise.yaml
│   └── component_tolerance.yaml
│
└── derived_forms/
    ├── filters/
    │   ├── rc_lowpass.yaml
    │   ├── sallen_key.yaml
    │   └── state_variable_filter.yaml
    ├── amplifiers/
    │   ├── inverting_amp.yaml
    │   ├── non_inverting_amp.yaml
    │   └── instrumentation_amp.yaml
    └── oscillators/
        ├── wien_bridge.yaml
        └── phase_shift.yaml
```

---

## 🎓 学习路径

### 初级：基础滤波器
1. RC passive filters
2. 理想 Op-amp 电路
3. 一阶系统分析

### 中级：主动电路
1. 多级放大器
2. 二阶滤波器 (Sallen-Key, MFB)
3. 非理想效应修正

### 高级：专业设计
1. 低噪声设计
2. 高频补偿
3. 稳定性分析

---

## 🔗 相关资源

- **教材**：《The Art of Electronics》 - Horowitz & Hill
- **工具**：LTSpice, Falstad Circuit Simulator
- **Package**：lcapy (Python symbolic circuit analysis)

---

## 📝 实作优先级

1. ✅ RC 低通滤波器（已有范例）
2. [ ] 反相放大器（考虑非理想 Op-amp）
3. [ ] Sallen-Key 滤波器
4. [ ] 麦克风前级完整设计范例

---

**Status**: 2026-01-01 - Domain planning completed  
**Next**: Implement first principle + modification example
