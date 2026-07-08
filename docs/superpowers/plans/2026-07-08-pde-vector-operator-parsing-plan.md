# PDE 与向量算子解析扩展实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 SymKit MCP 的文本与 LaTeX 输入路径都能自然解析 PDE 与向量算子写法，包括 `D/Dt`、`Div`、`Grad`、`Dot`、`Curl`、`Laplacian` 等。

**Architecture:** 在 `expression_parser.py` 中扩展受保护的向量算子函数名，并新增大写物质导数 `D/Dt` 的正则预处理；在 `formula.py` 的 LaTeX 预处理中同步支持 `\frac{D}{Dt}`。所有向量算子继续作为 `sympy.Function` 保留符号语义，不引入 `sympy.vector` 真实运算。

**Tech Stack:** Python 3.12, SymPy, pytest, ruff, mypy, uv

## Global Constraints

- 必须保持现有小写写法（`div`、`grad`、`curl`、`laplacian`、`Del`、`nabla`、`convective`）完全兼容。
- 不得修改 MCP 工具签名或 `symkit_mcp/tools/` 目录中的业务逻辑。
- 文件行数软限制 200 / 硬限制 400；函数行数软限制 30 / 硬限制 50。
- 新增逻辑必须有对应测试；提交前必须跑 `pytest → ruff → mypy`。
- 只使用项目已声明的依赖，不引入新包。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `src/symkit/domain/expression_parser.py` | 扩展受保护向量算子名；新增大写物质导数预处理；构建 `local_dict` 保护新算子 |
| `src/symkit/domain/formula.py` | 扩展 LaTeX 向量算子预处理，新增 `\frac{D}{Dt}` 支持 |
| `tests/test_expression_parser.py` | 新增大写算子、物质导数、SA 方程回归测试 |
| `ARCHITECTURE.md` / `docs/symkit-design.md` | 更新解析器支持的写法列表 |

---

### Task 1: 扩展受保护向量算子函数名

**Files:**
- Modify: `src/symkit/domain/expression_parser.py:248-257`
- Test: `tests/test_expression_parser.py:221-269` 附近新增测试类

**Interfaces:**
- Consumes: `_VECTOR_CALCULUS_NAMES` tuple, `_build_vector_calculus_local_dict()`
- Produces: `parse_expression_string()` 现在能识别 `Div`、`Grad`、`Dot`、`Curl`、`Laplacian` 为符号函数

- [ ] **Step 1: 写失败测试**

在 `tests/test_expression_parser.py` 中 `TestVectorCalculusParsing` 类之后新增 `TestUppercaseVectorOperators`：

```python
class TestUppercaseVectorOperators:
    """Uppercase vector-calculus aliases parse as user-defined symbolic functions."""

    def test_uppercase_div_parses(self):
        expr, error = parse_expression_string("Div(rho*u) = 0")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Div(rho*u)"

    def test_uppercase_grad_parses(self):
        expr, error = parse_expression_string("Grad(p) = rho * Grad(phi)")
        assert error is None
        assert expr.is_Equality
        assert "Grad(p)" in str(expr.lhs)
        assert "Grad(phi)" in str(expr.rhs)

    def test_uppercase_dot_parses(self):
        expr, error = parse_expression_string(
            "Dot(Grad(u), Grad(u)) = 0"
        )
        assert error is None
        assert expr.is_Equality
        assert "Dot(Grad(u), Grad(u))" in str(expr.lhs)

    def test_uppercase_curl_parses(self):
        expr, error = parse_expression_string("Curl(u) = 0")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Curl(u)"

    def test_uppercase_laplacian_parses(self):
        expr, error = parse_expression_string("Laplacian(u) = f")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Laplacian(u)"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_expression_parser.py::TestUppercaseVectorOperators -v
```

Expected: 5 FAILED，错误包含 `can't multiply sequence` 或 SymPy 解析失败。

- [ ] **Step 3: 最小实现**

在 `src/symkit/domain/expression_parser.py` 中修改 `_VECTOR_CALCULUS_NAMES`：

```python
_VECTOR_CALCULUS_NAMES: tuple[str, ...] = (
    "div",
    "grad",
    "curl",
    "laplace",
    "laplacian",
    "Del",
    "nabla",
    "convective",
    "dot",          # lowercase dot product
    "Div",
    "Grad",
    "Dot",
    "Curl",
    "Laplacian",
)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_expression_parser.py::TestUppercaseVectorOperators -v
```

Expected: 5 PASSED

- [ ] **Step 5: 提交**

```bash
git add src/symkit/domain/expression_parser.py tests/test_expression_parser.py
git commit -m "feat(expression_parser): protect uppercase vector calculus aliases"
```

---

### Task 2: 实现大写物质导数 D/Dt 预处理

**Files:**
- Modify: `src/symkit/domain/expression_parser.py:291-358`
- Test: `tests/test_expression_parser.py` 新增 `TestMaterialDerivative`

**Interfaces:**
- Consumes: `preprocess_leibniz_derivatives()`
- Produces: `D(u)/Dt` 和 `D/Dt(u)` 转换为 `Derivative(u, t)`

- [ ] **Step 1: 写失败测试**

在 `tests/test_expression_parser.py` 中新增 `TestMaterialDerivative`：

```python
class TestMaterialDerivative:
    """Uppercase D/Dt is converted to Derivative(..., t)."""

    def test_material_derivative_fraction_form(self):
        expr, error = parse_expression_string("D(u)/Dt = f")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Derivative(u, t)"

    def test_material_derivative_function_form(self):
        expr, error = parse_expression_string("D/Dt(u) = f")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Derivative(u, t)"

    def test_material_derivative_in_transport_equation(self):
        expr, error = parse_expression_string(
            "D(rho)/Dt + Div(rho*u) = 0"
        )
        assert error is None
        assert expr.is_Equality
        lhs = str(expr.lhs)
        assert "Derivative(rho, t)" in lhs
        assert "Div(rho*u)" in lhs
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_expression_parser.py::TestMaterialDerivative -v
```

Expected: 3 FAILED，报错 `can't multiply sequence by non-int of type 'Mul'`。

- [ ] **Step 3: 最小实现**

在 `src/symkit/domain/expression_parser.py` 中，紧接 `_LEIBNIZ_HIGHER_ORDER_RE` 之后、`_leibniz_first_repl` 之前添加正则与替换函数：

```python
# Regex for uppercase material derivative D(u)/Dt.
_MATERIAL_DERIVATIVE_RE: re.Pattern[str] = re.compile(
    r"\bD\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*/\s*\bDt\b",
)

# Regex for uppercase material derivative function form D/Dt(u).
_MATERIAL_DERIVATIVE_FUNC_RE: re.Pattern[str] = re.compile(
    r"\bD/Dt\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
)

# Regex for higher-order material derivative D^2 u / Dt^2.
_MATERIAL_DERIVATIVE_HO_RE: re.Pattern[str] = re.compile(
    r"\bD\^(\d+)\s*([A-Za-z_][A-Za-z0-9_]*)\s*/\s*\bDt\b\^(\d+)",
)


def _material_derivative_repl(match: re.Match[str]) -> str:
    """Convert D(u)/Dt to Derivative(u, t)."""
    return f"Derivative({match.group(1)}, t)"


def _material_derivative_func_repl(match: re.Match[str]) -> str:
    """Convert D/Dt(u) to Derivative(u, t)."""
    return f"Derivative({match.group(1)}, t)"


def _material_derivative_ho_repl(match: re.Match[str]) -> str:
    """Convert D^2 u / Dt^2 to Derivative(u, (t, 2))."""
    numerator_order = int(match.group(1))
    denominator_order = int(match.group(3))
    if numerator_order != denominator_order:
        return match.group(0)
    variable = match.group(2)
    return f"Derivative({variable}, (t, {numerator_order}))"
```

然后修改 `preprocess_leibniz_derivatives()`：

```python
def preprocess_leibniz_derivatives(expr_str: str) -> str:
    """Convert Leibniz derivative notation (e.g. ``dX/dY``) into SymPy ``Derivative(...)``.

    Supports first-order forms like ``dX/dY`` and higher-order forms like
    ``d^2X/dY^2``. Also supports uppercase material derivative ``D(X)/Dt``.
    Non-matching ``d`` or ``D`` tokens are left untouched.
    """
    result = _LEIBNIZ_HIGHER_ORDER_RE.sub(_leibniz_higher_repl, expr_str)
    result = _LEIBNIZ_FIRST_ORDER_RE.sub(_leibniz_first_repl, result)
    result = _MATERIAL_DERIVATIVE_HO_RE.sub(_material_derivative_ho_repl, result)
    result = _MATERIAL_DERIVATIVE_RE.sub(_material_derivative_repl, result)
    result = _MATERIAL_DERIVATIVE_FUNC_RE.sub(_material_derivative_func_repl, result)
    return result
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_expression_parser.py::TestMaterialDerivative -v
```

Expected: 3 PASSED

- [ ] **Step 5: 提交**

```bash
git add src/symkit/domain/expression_parser.py tests/test_expression_parser.py
git commit -m "feat(expression_parser): support uppercase material derivative D/Dt"
```

---

### Task 3: 在 LaTeX 路径中支持 \frac{D}{Dt}

**Files:**
- Modify: `src/symkit/domain/formula.py:62-127`
- Test: `tests/test_formula.py`（若存在）或 `tests/test_expression_parser.py` 的 `TestUserExpressionParser`

**Interfaces:**
- Consumes: `_preprocess_latex_vector_calculus()`
- Produces: LaTeX `\frac{D u}{D t}` 与 `\frac{D}{Dt} u` 转换为 `diff(u, t)`，最终被解析为 `Derivative(u, t)`

- [ ] **Step 1: 写失败测试**

如果 `tests/test_formula.py` 不存在，在 `tests/test_expression_parser.py` 的 `TestUserExpressionParser` 类中新增：

```python
    def test_latex_material_derivative_fraction(self):
        expr, error = parse_user_expression(r"\frac{D u}{D t} = f")
        assert error is None
        assert expr.is_Equality
        assert "Derivative(u, t)" in str(expr.lhs)

    def test_latex_material_derivative_prefix(self):
        expr, error = parse_user_expression(r"\frac{D}{Dt}(u) = f")
        assert error is None
        assert expr.is_Equality
        assert "Derivative(u, t)" in str(expr.lhs)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_expression_parser.py::TestUserExpressionParser::test_latex_material_derivative_fraction tests/test_expression_parser.py::TestUserExpressionParser::test_latex_material_derivative_prefix -v
```

Expected: 2 FAILED，解析结果不含 `Derivative(u, t)`。

- [ ] **Step 3: 最小实现**

在 `src/symkit/domain/formula.py` 的 `_preprocess_latex_vector_calculus()` 中，在第 8 步（梯度转换）之前插入第 7.5 步物质导数转换：

```python
    # 7. Material derivative: \frac{D u}{D t} -> diff(u, t)
    #    Must run before gradient conversion so \nabla in the same expression stays intact.
    s = re.sub(
        r"\\frac\{D\s+" + ident + r"\}\{D\s+([A-Za-z])\}",
        r"diff(\1\2, \3)",
        s,
    )
    s = re.sub(
        r"\\frac\{D\}\{Dt\}\s*" + ident,
        r"diff(\1\2, t)",
        s,
    )
    s = re.sub(
        r"\\frac\{D\}\{Dt\}\s*\(\s*" + ident + r"\s*\)",
        r"diff(\1\2, t)",
        s,
    )
```

> 注意：LaTeX 输入中 `t` 作为时间变量通常直接用 `t`，因此第二、三种形式硬编码为 `t`。如果 `\frac{D u}{D x}` 形式使用变量 `㬛`，第一种形式会捕获变量名。

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_expression_parser.py::TestUserExpressionParser::test_latex_material_derivative_fraction tests/test_expression_parser.py::TestUserExpressionParser::test_latex_material_derivative_prefix -v
```

Expected: 2 PASSED

- [ ] **Step 5: 提交**

```bash
git add src/symkit/domain/formula.py tests/test_expression_parser.py
git commit -m "feat(formula): support \\frac{D}{Dt} material derivative in LaTeX"
```

---

### Task 4: 添加 Spalart-Allmaras 方程端到端回归测试

**Files:**
- Test: `tests/test_expression_parser.py`

**Interfaces:**
- Consumes: `parse_expression_string()`
- Produces: 用户提供的 SA 方程能解析为 `Equality` 且 `error` 为 `None`

- [ ] **Step 1: 写测试**

在 `tests/test_expression_parser.py` 的 `TestComplexExpressions` 类中新增：

```python
    def test_spalart_allmaras_transport_equation(self):
        expr, error = parse_expression_string(
            "Eq(D(nu_tilde)/Dt, c_b1*S_tilde*nu_tilde - c_w1*f_w*(nu_tilde/d)**2 + "
            "(1/sigma)*Div((nu + nu_tilde)*Grad(nu_tilde)) + "
            "(c_b2/sigma)*Dot(Grad(nu_tilde), Grad(nu_tilde)))"
        )
        assert error is None, f"Parse error: {error}"
        assert expr.is_Equality
        lhs = str(expr.lhs)
        rhs = str(expr.rhs)
        assert "Derivative(nu_tilde, t)" in lhs
        assert "Div((nu + nu_tilde)*Grad(nu_tilde))" in rhs
        assert "Dot(Grad(nu_tilde), Grad(nu_tilde))" in rhs
```

- [ ] **Step 2: 运行测试确认通过**

```bash
uv run pytest tests/test_expression_parser.py::TestComplexExpressions::test_spalart_allmaras_transport_equation -v
```

Expected: 1 PASSED（如果 Task 1 和 Task 2 已完成）

- [ ] **Step 3: 提交**

```bash
git add tests/test_expression_parser.py
git commit -m "test(expression_parser): add Spalart-Allmaras transport equation regression"
```

---

### Task 5: 全量验证与 lint

**Files:**
- 所有已修改文件

- [ ] **Step 1: 运行全量测试**

```bash
uv run pytest
```

Expected: 全部通过（或至少没有新增的失败）

- [ ] **Step 2: 运行 ruff**

```bash
uv run ruff check src/ tests/
```

Expected: 无错误

- [ ] **Step 3: 运行 mypy**

```bash
uv run mypy src/
```

Expected: 无新增类型错误

- [ ] **Step 4: 提交（如 lint 有自动修复）**

```bash
git add -A
git commit -m "chore: ruff/mypy compliance for pde vector operator parsing" || echo "no changes"
```

---

### Task 6: 更新文档

**Files:**
- Modify: `ARCHITECTURE.md` 或 `docs/symkit-design.md` 中解析器相关章节

- [ ] **Step 1: 定位文档中表达式解析/支持的写法部分**

使用 grep 查找：

```bash
grep -n "Leibniz\|dX/dY\|vector\|div\|grad" ARCHITECTURE.md docs/symkit-design.md
```

- [ ] **Step 2: 在支持的写法列表中追加**

例如在 `docs/symkit-design.md` 的表达式解析章节新增：

```markdown
- 物质导数：`D(u)/Dt`、`D/Dt(u)`、LaTeX `\frac{D u}{D t}`、 `\frac{D}{Dt} u` 均解析为 `Derivative(u, t)`。
- 大写向量算子别名：`Div(...)`、`Grad(...)`、`Dot(...)`、`Curl(...)`、`Laplacian(...)` 与小写形式等价，均作为符号函数保留。
```

- [ ] **Step 3: 提交**

```bash
git add ARCHITECTURE.md docs/symkit-design.md
git commit -m "docs: document uppercase D/Dt and vector operator aliases"
```

---

## 计划自检

**Spec 覆盖检查：**
- 大写物质导数 `D/Dt` → Task 2
- 大写向量算子 `Div`/`Grad`/`Dot`/`Curl`/`Laplacian` → Task 1
- 小写 `dot` 支持 → Task 1
- LaTeX `\frac{D}{Dt}` 支持 → Task 3
- SA 方程端到端测试 → Task 4
- 验证命令 → Task 5
- 文档更新 → Task 6

**Placeholder 扫描：** 本计划无 TBD、TODO、"appropriate error handling" 等占位符。

**类型一致性检查：** 所有新增函数签名与现有 `_leibniz_first_repl` / `_build_vector_calculus_local_dict` 保持一致；`_MATERIAL_DERIVATIVE_*` 为 `re.Pattern[str]` 类型。

---

## 执行方式选择

**Plan complete and saved to `docs/superpowers/plans/2026-07-08-pde-vector-operator-parsing-plan.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach?
