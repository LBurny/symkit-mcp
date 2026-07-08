# 扩展 PDE 与向量算子解析设计

**日期**: 2026-07-08  
**范围**: `src/symkit/domain/expression_parser.py`、`src/symkit/domain/formula.py`、相关测试与文档  
**目标**: 让 SymKit MCP 的文本与 LaTeX 输入路径都能自然解析 PDE 与向量算子写法，解决 SA 湍流方程中 `D/Dt`、`Div`、`Grad`、`Dot` 等符号无法解析的问题。

---

## 1. 背景

当前 `parse_expression_string()` 对以下自然写法不支持：

- 大写 Leibniz 物质导数：`D(nu_tilde)/Dt`、`D/Dt(nu_tilde)`
- 大写向量算子：`Div(...)`、`Grad(...)`、`Dot(...)`、`Curl(...)`、`Laplacian(...)`
- 文本路径的偏导数符号：`∂u/∂t`、`∂_t u`（LaTeX 路径已部分支持）

这些写法在流体力学、湍流模型、传热传质等 PDE 场景中非常常见。本次扩展保持现有小写算子完全兼容，仅新增自然别名和预处理规则。

---

## 2. 设计目标

1. **自然数学写法可用**：用户可以直接输入 `D(nu_tilde)/Dt = ... + Div(...)` 而不必改写。
2. **大小写不敏感地支持常见算子**：`div`/`Div`、`grad`/`Grad`、`dot`/`Dot` 等价。
3. **LaTeX 路径同步**：`\frac{D}{Dt}`、大写 `\nabla` 相关命令也能正确转换。
4. **保持符号函数语义**：继续使用 `sympy.Function` 包装向量算子，不引入 `sympy.vector` 的真实向量运算。
5. **向后兼容**：现有小写写法、测试用例行为不变。

---

## 3. 改动范围

### 3.1 `src/symkit/domain/expression_parser.py`

#### 新增/扩展预处理函数

- `preprocess_leibniz_derivatives()`
  - 现有：支持 `dX/dY`、`d^2X/dY^2`
  - 新增：支持大写物质导数 `D(X)/Dt`、`D/Dt(X)`、`D X/Dt`，输出 `Derivative(X, t)`
  - 新增：支持高阶形式 `D^2 X / Dt^2`，输出 `Derivative(X, (t, 2))`

- `preprocess_vector_calculus()`
  - 现有：支持 `Del^2(u)` / `nabla^2(u)` → `laplacian(u)`，`(u*Del)*v` → `convective(u, v)`
  - 本次新增：保持现有逻辑不变；大写算子由 `_VECTOR_CALCULUS_NAMES` 直接保护为符号函数。

- `_VECTOR_CALCULUS_NAMES`
  - 新增 `dot`（小写点积）以及大写别名：`Div`、`Grad`、`Dot`、`Curl`、`Laplacian`。
  - 这样 `Div(A)`、`Grad(f)`、`Dot(Grad(u), Grad(u))` 等会被解析为对应名称的 `sympy.Function`。

#### 预处理顺序

保持当前顺序不变：

```
preprocess_unicode → preprocess_vector_calculus → preprocess_diff_to_derivative → preprocess_leibniz_derivatives → convert_equals_to_eq
```

大写算子（`Div`/`Grad`/`Dot`/`Curl`/`Laplacian`）直接作为受保护函数名交给 `parse_expr`；大写物质导数（`D/Dt`）在 `preprocess_leibniz_derivatives` 中转换。

### 3.2 `src/symkit/domain/formula.py`

- `_preprocess_latex_vector_calculus()`
  - 新增：`\frac{D}{Dt} u` / `\frac{D u}{D t}` / `\operatorname{D} u / D t` → `diff(u, t)` 或 `Derivative(u, t)`
  - 保持现有 `\nabla \cdot`、 `\nabla`、 `\nabla^2`、 `(u \cdot \nabla) v` 处理不变。

- `_VECTOR_CALCULUS_FUNC_RE` 中的正则扩展为包含大写形式：`Div|Grad|Dot|Curl|Laplacian`。

### 3.3 测试

在 `tests/test_expression_parser.py` 新增：

- `TestMaterialDerivative`
  - `D(u)/Dt` → `Derivative(u, t)`
  - `D/Dt(u)` → `Derivative(u, t)`
  - 在完整方程中解析
- `TestUppercaseVectorOperators`
  - `Div(A)`、`Grad(f)`、`Dot(Grad(u), Grad(u))` 解析为符号函数
- `TestSpalartAllmarasEquation`
  - 用户提供的完整 SA 输运方程能成功解析为 `Equality`

在 `tests/test_formula.py` 或对应 LaTeX 测试文件中新增：

- `\frac{D \nu_t}{D t}` 解析测试
- `\nabla \cdot`、`\nabla`、`\nabla^2` 的兼容性回归测试（确保不破坏）

### 3.4 文档

- 更新 `ARCHITECTURE.md` 中解析器支持的写法列表。
- 如 `README.md` 或 `docs/symkit-design.md` 有表达式语法说明，同步补充。

---

## 4. 数据流

```
用户输入
  │
  ▼
parse_user_expression()
  │
  ├─ 文本路径 ──► parse_expression_string()
  │                  │
  │                  ├─ preprocess_unicode()
  │                  ├─ preprocess_vector_calculus()
  │                  ├─ preprocess_diff_to_derivative()
  │                  ├─ preprocess_leibniz_derivatives() ← 大写 D/Dt 转换
  │                  ├─ _convert_equals_to_eq()
  │                  ├─ 构建 local_dict（保护保留名/向量算子，含大写别名）
  │                  └─ parse_expr()
  │
  └─ LaTeX 路径 ──► FormulaParser.parse()
                     │
                     ├─ _strip_latex_environments()
                     ├─ _preprocess_latex_greek()
                     ├─ _preprocess_latex_vector_calculus() ← 新增 D/Dt
                     ├─ parse_latex() → SymPy 表达式
                     └─ 内部再用 parse_expression_string() 兜底
```

---

## 5. 错误处理与降级

- 预处理失败时不得静默吞掉异常；若正则替换导致不匹配，应保留原字符串继续解析。
- 对于未识别的算子，保持现有行为：由 `parse_expr` 给出原生日化错误。本次不引入新的“建议写法”错误提示，但后续可作为增强项。
- 大写 `D` 仅在被调用为函数（`D(...)`）时才解析为物质导数；单独的 `D` 符号仍作为普通变量处理。

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 大写算子与用户的自定义符号冲突 | 低 | 仅在函数调用形式（带括号）时生效； bare 符号不受影响 |
| 预处理正则过度匹配 | 中 | 使用 whole-word 边界、单元测试覆盖边界情况 |
| LaTeX 预处理顺序影响既有转换 | 中 | 保持现有顺序，新增物质导数转换在最后 |
| 改变现有表达式解析结果 | 中 | 跑全量 pytest + ruff + mypy 确保回归 |

---

## 7. 成功标准

- 用户提供的 SA 方程能成功通过 `session_record_step` 或 `math()` 解析。
- 新增测试覆盖大写物质导数、大写向量算子、完整 SA 方程。
- 现有测试全部通过：`uv run pytest`、`uv run ruff check src/ tests/`、`uv run mypy src/`。
- 文档已更新。

---

## 8. 不做什么

- 不引入 `sympy.vector` 的真实向量运算语义；`div`/`grad` 等仍作为符号函数。
- 不修改 MCP 工具签名或 `symkit_mcp/tools/` 目录中的业务逻辑。
- 不解决所有可能的 PDE 符号写法，只覆盖本次高频场景。
