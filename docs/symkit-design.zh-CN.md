# SymKit MCP 项目设计文档

> 文档版本：0.2
> 最后更新：2026-07-03
> 适用代码版本：`symkit-mcp` 0.2.4（`src/symkit/` 与 `src/symkit_mcp/`）

---

## 目录

1. [项目概述](#1-项目概述)
2. [设计目标](#2-设计目标)
3. [架构总览](#3-架构总览)
4. [分层设计](#4-分层设计)
   - 4.1 Domain 层
   - 4.2 Application 层
   - 4.3 Infrastructure 层
   - 4.4 MCP Tool 层
5. [核心领域模型](#5-核心领域模型)
   - 5.1 DerivationSession
   - 5.2 DerivationStep
   - 5.3 Formula / FormulaInfo
   - 5.4 DerivationGoal / DerivationPattern
   - 5.5 AssumptionEngine / MathContext
   - 5.6 SymbolRegistry
6. [表达式解析管道](#6-表达式解析管道)
7. [推导生命周期](#7-推导生命周期)
8. [MCP 工具设计](#8-mcp-工具设计)
   - 8.1 工具分类
   - 8.2 math() 统一数学工具
   - 8.3 推导会话工具（session）
   - 8.4 公式检索工具（formula）
   - 8.5 假设工具（assumptions）
   - 8.6 编排工具（orchestration）
9. [外部适配器](#9-外部适配器)
10. [步骤验证](#10-步骤验证)
11. [假设与冲突检测](#11-假设与冲突检测)
12. [持久化与回读](#12-持久化与回读)
13. [状态管理](#13-状态管理)
14. [测试策略](#14-测试策略)
15. [设计原则](#15-设计原则)
16. [附录](#16-附录)
    - A. 术语表
    - B. 关键文件索引
    - C. 快速入口

---

## 1. 项目概述

**SymKit MCP** 是一个面向 AI Agent 的符号推理 MCP（Model Context Protocol）服务器。它基于 SymPy 提供精确的符号计算、公式推导、步骤验证和外部公式检索能力，并把整个推导过程以可审计、可追溯、可复用的方式记录下来。

SymKit 是**领域无关**的通用公式推导引擎，适用于物理、工程、化学、生物、经济等任何需要数学公式的领域。它强调：

- **可验证性**：每一步推导都会自动或半自动地做反向验证。
- **可追溯性**：每个步骤记录输入、输出、SymPy 命令、假设、限制和人工注释。
- **可复用性**：本地仓库和外部权威来源（Wikidata、BioModels、SciPy CODATA）共同为推导提供可引用公式。
- **人机协同**：支持在推导中插入假设、限制、观察、修正建议等非计算性知识。
- **LaTeX 友好**：原生支持 LaTeX 输入、下标符号、希腊字母和物理星号上标（如 `\beta^*`）。

项目的对外主契约是 41 个 MCP 工具，其中 `math()` 负责快速无状态/有状态计算，`session_start()` / `session_show()` / `session_complete()` 提供交互式推导会话，`derive()` 提供高层自动化入口。

---

## 2. 设计目标

| 目标 | 说明 |
|---|---|
| **精确计算** | 使用 SymPy 而不是自然语言近似，确保数学结果正确。 |
| **步骤审计** | 每个推导步骤都是不可变记录，包含完整上下文。 |
| **假设管理** | 支持全局/领域/会话/步骤四级假设，并能检测冲突。 |
| **公式推荐** | 根据目标文本、领域、变量和外部来源推荐可用公式。 |
| **可插拔引擎** | 通过 Protocol 抽象符号引擎、验证器、仓库，方便替换实现。 |
| **工具分层** | 既有 `math()` 等快速工具，也有 `session_*` 会话工具和 `derive()` 编排工具。 |
| **LaTeX 健壮性** | 复合 LaTeX 等式、星号上标、下标符号和 `\max`/`\min` 都能稳定解析。 |
| **表达式可回读** | 存储的表达式的字符串表示不一定可解析，因此额外保存 `srepr` 用于回读。 |
| **领域无关** | 核心工具不硬编码任何领域语义，由用户上下文提供领域含义。 |

---

## 3. 架构总览

```text
┌────────────────────────────────────────────────────────────────────┐
│                        MCP Client / AI Agent                       │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ MCP 协议
┌────────────────────────────────▼───────────────────────────────────┐
│                     MCP Tool 层 (src/symkit_mcp/tools/)             │
│  math / session / formula / assumptions / orchestration / symbols │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ 调用
┌────────────────────────────────▼───────────────────────────────────┐
│                  Application 层 (src/symkit/application/)      │
│         CalculateUseCase / DeriveUseCase / VerifyUseCase          │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ 领域接口
┌────────────────────────────────▼───────────────────────────────────┐
│                     Domain 层 (src/symkit/domain/)               │
│  DerivationSession, DerivationStep, AssumptionEngine,             │
│  StepVerifier, SymbolRegistry, FormulaRecommender, ...            │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ 适配器接口
┌────────────────────────────────▼───────────────────────────────────┐
│                  Infrastructure 层 (src/symkit/infrastructure/)   │
│  SymPyEngine, DerivationRepository, ScipyConstantsAdapter,        │
│  WikidataFormulaAdapter, BioModelsAdapter, ...                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. 分层设计

### 4.1 Domain 层

负责业务规则、实体和领域服务。核心文件：

| 文件 | 主要职责 |
|---|---|
| `src/symkit/domain/derivation_session.py` | `DerivationSession`、`SessionManager` 及操作实现。新增 `output_srepr` 与 `_safe_load_expression`。 |
| `src/symkit/domain/step_verifier.py` | 假设感知的步骤验证引擎。 |
| `src/symkit/domain/assumption_engine.py` | 多级假设存储与冲突检测。 |
| `src/symkit/domain/formula.py` | `Formula` 值对象、解析器、来源枚举。支持复合 LaTeX 等式拆分、`\max`/`\min` 映射、`^*` 上标处理。 |
| `src/symkit/domain/formula_recommender.py` | 本地+外部公式推荐与 `FormulaSourceAdapter` 协议。 |
| `src/symkit/domain/derivation_goal.py` | 自然语言目标解析。 |
| `src/symkit/domain/derivation_pattern.py` | 推导模式与模板。 |
| `src/symkit/domain/derivation_planner.py` | 目标感知的下一步建议。 |
| `src/symkit/domain/symbol_registry.py` | 领域符号语义注册表。 |
| `src/symkit/domain/value_objects.py` | `MathContext`、`VerificationResult`、`StepStatus` 等。 |
| `src/symkit/domain/entities.py` | `Expression` 等数据类。 |
| `src/symkit/domain/services.py` | `SymbolicEngine`、`Verifier`、`FormulaRepository` 协议。 |

### 4.2 Application 层

粗粒度用例，协调 Domain 与 Infrastructure，但不包含 SymPy 细节：

| 文件 | 主要职责 |
|---|---|
| `src/symkit/application/use_cases.py` | `CalculateUseCase`、`SimplifyUseCase`、`DeriveUseCase`、`VerifyUseCase`。 |

### 4.3 Infrastructure 层

技术实现细节：

| 文件 | 主要职责 |
|---|---|
| `src/symkit/infrastructure/sympy_engine.py` | SymPy 实现的 `SymbolicEngine`。 |
| `src/symkit/infrastructure/derivation_repository.py` | YAML 持久化的 `DerivationRepository`。 |
| `src/symkit/infrastructure/adapters/scipy_constants.py` | SciPy CODATA 物理常数适配器。 |
| `src/symkit/infrastructure/adapters/wikidata_formulas.py` | Wikidata SPARQL 公式检索适配器。 |
| `src/symkit/infrastructure/adapters/biomodels.py` | BioModels SBML 模型适配器。 |
| `src/symkit/infrastructure/adapters/base.py` | `BaseAdapter`、`FormulaInfo` 统一格式。 |
| `src/symkit/infrastructure/verifier.py` | 基础 `Verifier` 实现。 |

### 4.4 MCP Tool 层

对外暴露 41 个 MCP 工具，每个模块聚焦一类能力：

| 文件 | 主要职责 |
|---|---|
| `src/symkit_mcp/server.py` | FastMCP 服务入口。 |
| `src/symkit_mcp/tools/__init__.py` | 统一注册所有工具。 |
| `src/symkit_mcp/tools/math.py` | `math()` 统一数学工具、`assume()`、`show_assumptions()`。 |
| `src/symkit_mcp/tools/session.py` | 统一推导会话工作流工具。 |
| `src/symkit_mcp/tools/formula.py` | 外部公式检索工具。 |
| `src/symkit_mcp/tools/assumptions.py` | 假设工具。 |
| `src/symkit_mcp/tools/orchestration.py` | 高层编排工具 `derive()`、`intent_execute()` 等。 |
| `src/symkit_mcp/tools/symbols.py` | 符号注册工具。 |
| `src/symkit_mcp/tools/codegen.py` | 代码/LaTeX/报告生成。 |
| `src/symkit_mcp/tools/_state.py` | 全局状态（`SessionManager`、当前会话、`MathContext`）。 |
| `src/symkit_mcp/tools/_expression_parser.py` | 统一解析器兼容 shim。 |

---

## 5. 核心领域模型

### 5.1 DerivationSession

`DerivationSession` 是 SymKit 的核心有状态容器，位于 `src/symkit/domain/derivation_session.py`。它维护：

- `current_expression`：当前表达式（`sp.Basic`）。
- `steps`：推导步骤列表（`list[DerivationStep]`）。
- `formulas`：已加载的公式映射（`formula_id -> Formula`）。
- `goal`：当前推导目标（`DerivationGoal`）。
- `pattern`：推导模式（`DerivationPattern`）。
- `assumption_engine`：`AssumptionEngine` 实例。
- `symbol_registry`：`SymbolRegistry` 实例。
- `verifier`：`StepVerifier` 实例。
- `recommender`：`FormulaRecommender` 实例。
- `planner`：`DerivationPlanner` 实例。

主要方法：

- `load_formula`：加载并解析公式。
- `substitute / simplify / solve_for / differentiate / integrate`：执行推导操作。
- `verify_step / verify_derivation`：验证步骤或全部步骤。
- `set_goal / recommend_formulas / plan_next_steps`：目标驱动推荐。
- `rollback_to_step / insert_note_after_step`：步骤管理。
- `complete / save / load`：完成与持久化。
- `_safe_load_expression`：使用 `srepr` 优先策略回读存储表达式。

### 5.2 DerivationStep

`DerivationStep` 记录每一步推导的完整上下文：

```python
step_number: int
operation: OperationType
description: str
input_expressions: dict[str, str]    # 例如 {"original": "x**3"}
output_expression: str               # 人类可读的 str(expr)
output_latex: str
output_srepr: str                    # 机器可回读的 sp.srepr(expr)
sympy_command: str
assumptions: list[str]
notes: str
limitations: list[str]
verification_result: str
status: StepStatus
timestamp: str
```

每个步骤是不可变记录，用于学术溯源和审计。`output_srepr` 是关键：LaTeX 下标符号如 `\mu_t` 会变成 `Symbol('mu_{t}')`，其 `str()` 不是合法 Python 输入，因此 `srepr` 是回读的唯一可靠方式。

### 5.3 Formula / FormulaInfo

- `Formula`（`src/symkit/domain/formula.py`）是内部值对象，支持从 SymPy 字符串、LaTeX、Python 表达式或字典解析。
- `FormulaInfo`（`src/symkit/infrastructure/adapters/base.py`）是外部适配器的统一输出格式，字段包括 `id`、`name`、`expression`、`latex`、`variables`、`source`、`category`、`description`、`tags` 等。
- `Formula` 包含 `parse_warnings` 字段，用于提示复合输入中仅记录了第一条等式。

### 5.4 DerivationGoal / DerivationPattern

- `DerivationGoal` 解析自然语言目标（如 "derive Navier-Stokes from conservation laws"），提取领域、目标形式、目标变量和假设。
- `DerivationPattern` 提供高层推导策略模板，例如：
  - `CONSERVATION_CONSTITUTIVE`：守恒+本构关系
  - `VARIATIONAL`：变分原理
  - `OPERATOR_CORRESPONDENCE`：算子对应
  - `SERIES_APPROXIMATION`：级数近似
  - `EIGENMODE_ANALYSIS`：本征模分析
  - `DIRECT_MANIPULATION`：直接代数操作

### 5.5 AssumptionEngine / MathContext

- `MathContext`（`src/symkit/domain/value_objects.py`）携带假设、坐标系、简化级别和领域。
- `AssumptionEngine`（`src/symkit/domain/assumption_engine.py`）支持四级假设：
  1. `GLOBAL`
  2. `DOMAIN`
  3. `SESSION`
  4. `STEP`

它负责合并、覆盖和冲突检测。

### 5.6 SymbolRegistry

`SymbolRegistry`（`src/symkit/domain/symbol_registry.py`）为符号赋予领域语义：

- 记录符号含义、默认单位、适用领域和作用域。
- 提供流体动力学、量子力学、电磁学、热力学等领域的默认符号。
- 检测同一符号在不同语境下被赋予不同含义的冲突。

---

## 6. 表达式解析管道

`parse_user_expression`（`src/symkit/domain/expression_parser.py`）和 `FormulaParser`（`src/symkit/domain/formula.py`）共同构成统一的表达式解析层。管道如下：

```text
用户输入 (LaTeX / SymPy / Unicode / 自然方程)
        │
        ▼
  LaTeX 检测 (FormulaParser._is_latex)
        │
        ├─ 是 LaTeX ──▶ FormulaParser._parse_latex
        │                  │
        │                  ▼
        │            1. 预处理 ^* 上标：\beta^* → \beta_{\star}
        │            2. 检查括号平衡
        │            3. 拆分复合等式（\quad, ,, ;）
        │            4. 取第一条等式解析
        │            5. parse_latex 解析
        │            6. 重命名占位符：beta_{star} → beta_star
        │            7. 映射 \max / \min → Max / Min
        │            8. 提取变量，返回 Formula
        │
        └─ 否 LaTeX ──▶ parse_expression_string
                          │
                          ▼
                    1. Unicode/Greek 替换
                    2. Leibniz 导数记号 dX/dY → Derivative(X, Y)
                    3. 单等式转换 A = B → Eq(A, B)
                    4. 保留名保护（beta, gamma, S, N 等）
                    5. parse_expr 解析
```

关键设计点：

- **复合等式**：LaTeX 中 `"A = B, \quad C = D"` 现在只记录 `A = B`，其余等式通过 `parse_warnings` 提示。
- **星号上标**：`\beta^*` 这类物理常数命名被转换为 `beta_star` 单一符号。
- **`\max` 映射**：`parse_latex` 对 `\max` 支持不完整，后处理为 SymPy `Max`。
- **保留名保护**：`beta * x` 中的 `beta` 是符号而非函数；`sin(x)` 仍是函数。

---

## 7. 推导生命周期

```text
开始 (session_start)
    │
    ▼
加载公式 (session_load_formula) ──► 解析为 Formula 并设置 current_expression
    │
    ▼
执行操作 (math() 操作，如 substitute / simplify / diff / integrate / solve)
    │
    ▼
自动验证 (session_verify_step) ──► StepVerifier 检查输入/输出关系
    │
    ▼
迭代或添加人工注释 (session_add_note / session_rollback / insert_note_after_step)
    │
    ▼
完成 (session_complete)
    │
    ▼
持久化 (save / DerivationRepository)
```

回滚/删除/插入说明时，`DerivationSession` 不再直接 `sp.sympify(step.output_expression)`，而是优先使用 `step.output_srepr`，因此含 LaTeX 下标的会话也能安全地恢复当前表达式。

---

## 8. MCP 工具设计

### 8.1 工具分类

SymKit 共暴露 41 个 MCP 工具，按功能分为 8 类：

| 工具模块 | 代表工具 | 数量 | 定位 |
|---|---|---|---|
| `math` | `math()` | 1 | 统一计算入口 |
| `session` | `session_start`、`session_show`、`session_complete` 等 | 17 | 统一推导会话工作流 |
| `assumptions` | `assume`、`show_assumptions`、`assume_for_step`、`list_assumptions`、`check_assumption_conflicts`、`clear_step_assumptions` | 6 | 全局与步骤级假设管理 |
| `formula` | `formula_search`、`formula_get`、`formula_add`、`formula_categories` | 4 | 外部公式检索 |
| `symbols` | `register_symbol`、`lookup_symbol`、`list_domain_symbols`、`check_symbol_conflicts` | 4 | 符号语义管理 |
| `codegen` | `generate_python_function`、`generate_latex_derivation`、`generate_derivation_report`、`generate_sympy_script` | 4 | 代码/报告生成 |
| `orchestration` | `derive()`、`intent_execute()`、`list_patterns()` | 3 | 高层自动化编排 |
| `meta` | `tool_categories()`、`tool_recommend()` | 2 | 工具发现与推荐 |

`math()` 已覆盖以前分散在多个工具中的功能，统一为单一入口，避免 LLM 在众多旧工具中迷失。

### 8.2 math() 统一数学工具

`math(operation, expression, ...)` 是面向 LLM 的主要工具。`operation` 参数决定具体行为：

| 类别 | 操作 |
|---|---|
| 解析/简化 | `parse`、`simplify`、`expand`、`factor`、`collect`、`cancel`、`apart`、`together`、`trigsimp`、`powsimp`、`radsimp`、`combsimp` |
| 求解 | `solve`、`substitute` |
| 微积分 | `diff`、`integrate`、`limit`、`series` |
| ODE | `dsolve` |
| 矢量 | `gradient`、`divergence`、`curl`、`laplacian` |
| 矩阵 | `det`、`inv`、`eigenvals`、`eigenvects` |
| 积分变换 | `laplace`、`ilaplace`、`fourier`、`ifourier` |

重要参数：

- `variable`：主变量（微分/积分/求解变量，或矢量操作的坐标列表）。
- `with_respect_to`：第二变量（ODE 自变量、积分变换目标变量）。
- `substitution`：字典形式的替换映射。
- `lower` / `upper`：定积分上下界。
- `assumptions`：当前计算的符号假设，格式如 `["x is positive"]`。
- `session`：`True` 时记录到当前推导会话。
- `description` / `notes`：记录到步骤中的人类知识。

### 8.3 推导会话工具（session）

`session.py` 是统一的推导会话工作流入口，所有与推导状态相关的操作都通过 `session_*` 工具完成。它内部复用 `DerivationSession`，因此具备完整的步骤溯源、自动验证和持久化能力。

统一会话工具包括：

- `session_start(name, domain=..., goal=...)`：创建新会话，可一并设置目标。
- `session_resume(session_id)`：恢复已保存会话。
- `session_status()` / `session_show(show_steps=True)`：查看当前状态、进度、下一步建议和验证摘要。
- `session_explain(...)`：用自然语言总结当前推导。
- `session_complete(...)`：完成并保存推导结果。
- `session_rollback(to_step)` / `session_abort()`：回滚或暂停会话。
- `session_add_note(...)`：记录人类洞见。现在安全支持 LaTeX 下标符号。
- `session_load_formula(expression, formula_id=...)`：加载公式到当前会话。支持复合 LaTeX 等式。
- `session_set_goal(goal)`：设置/更新推导目标。
- `session_suggest_formulas(top_k=...)`：基于目标推荐可用公式。
- `session_record_step(...)`：记录手动或外部计算得到的步骤。
- `session_get_steps()`：获取所有步骤。
- `session_verify_step(step_number)` / `session_verify_session()`：手动触发单步或全链验证。
- `session_list()`：列出所有已保存会话。

### 8.4 公式检索工具（formula）

- `formula_search(query, source="wikidata+scipy", domain=None, limit=10)`：跨来源搜索。
- `formula_get(id, source="wikidata")`：获取单个公式详情。
- `formula_constants(category=None, query="")`：列出 SciPy 物理常数。
- `formula_categories()` / `formula_pk_models()` / `formula_kinetic_laws()`：按领域分类检索。

### 8.5 假设工具（assumptions）

- `assume(variables)`：设置全局/会话级假设（作用于 `MathContext`）。
- `show_assumptions()`：展示当前假设。
- `assume_for_step(symbol, property)`：设置当前步骤的临时假设。
- `list_assumptions(level)`：列出指定级别假设。
- `check_assumption_conflicts()`：检测冲突。

### 8.6 编排工具（orchestration）

- `derive(goal, given=None, domain=None, external_sources=None)`：根据目标自动选择模式、推荐公式并返回完整计划。
- `intent_execute(intent)`：根据意图执行工具链。
- `tool_categories()` / `tool_recommend(...)`：工具发现与推荐。
- `list_patterns()`：列出可用推导模式。

> **注意**：`derive()` 是高层编排入口，如果目标链很长或启用了网络适配器（如 `wikidata`），可能触发 MCP 客户端超时。建议复杂推导拆分为 `session_start` + `math(..., session=True)` 多步执行，或避免使用外部网络源。

---

## 9. 外部适配器

外部适配器位于 `src/symkit/infrastructure/adapters/`，实现统一的 `FormulaSourceAdapter` 协议：

| 适配器 | 数据来源 | 适用场景 |
|---|---|---|
| `ScipyConstantsAdapter` | SciPy CODATA | 物理常数（c、h、G 等） |
| `WikidataFormulaAdapter` | Wikidata SPARQL | 跨领域物理/化学/工程公式 |
| `BioModelsAdapter` | BioModels SBML | 药代/酶动力学模型 |

`FormulaRecommender`（`src/symkit/domain/formula_recommender.py`）把本地 `DerivationRepository` 和外部适配器聚合起来，按以下维度排序：

- 关键词/标签重叠
- 领域匹配
- 变量重叠
- 来源可信度

默认仅启用离线 SciPy 适配器（`create_default_external_adapters`），避免默认依赖网络；需要网络时可通过 `create_all_external_adapters()` 启用 Wikidata 和 BioModels。

---

## 10. 步骤验证

`StepVerifier`（`src/symkit/domain/step_verifier.py`）对每个 `DerivationStep` 执行验证：

1. **重建输入/输出**：优先使用 `output_srepr` 解析 SymPy 对象；无 `srepr` 时回退到 `str()` 或统一 parser。
2. **假设冲突检测**：如果当前假设存在矛盾，验证结论降级为失败。
3. **操作特定检查**：
   - **Simplify / Expand / Factor**：`simplify(output - input) == 0`。
   - **Differentiate**：反向积分 `integrate(output) == input`（允许常数差异）。
   - **Integrate**：反向微分 `diff(output) == input`。
   - **Substitute**：将替换应用到原始表达式，检查是否等于输出。
   - **Solve**：将解代回原方程，检查是否成立（处理 `BooleanTrue`/`BooleanFalse`）。
4. **Warning 收集**：检查 `exp`/`log` 参数、除零风险等。

验证结果封装为 `VerificationResult`（`src/symkit/domain/value_objects.py`），包含：

- `status`：`VERIFIED`、`FAILED`、`INCONCLUSIVE`
- `message`：人类可读的验证结论
- `details`：残差、反向检查、边界检查、假设冲突等

---

## 11. 假设与冲突检测

`AssumptionEngine` 支持四级假设，优先级从低到高：

1. **GLOBAL**（全局默认）
2. **DOMAIN**（领域默认，如流体力学中的 `rho > 0`）
3. **SESSION**（会话级，由 `assume()` 或 `assume_for_step` 设置）
4. **STEP**（步骤级，由 `assume_for_step()` 设置）

合并规则：高优先级覆盖低优先级。冲突检测识别互斥假设，例如同一符号同时被声明为 `positive` 和 `negative`、`real` 和 `imaginary`。

`MathContext` 把假设传递给符号解析和 SymPy 引擎，使 `sqrt(x**2)` 在 `x positive` 下能简化为 `x`。

---

## 12. 持久化与回读

### 12.1 表达式存储策略

`DerivationStep` 同时保存三种表达式表示：

- `output_expression`：`str(expr)`，人类可读，但不一定能回读（如 `mu_{t}` 不是合法 Python 标识符）。
- `output_latex`：`sp.latex(expr)`，用于展示。
- `output_srepr`：`sp.srepr(expr)`，机器可回读，是恢复的可靠来源。

`DerivationSession._safe_load_expression(expr_str, srepr_str)` 的回读优先级：

1. `srepr_str` → `sp.sympify`
2. `expr_str` → `sp.sympify`
3. `expr_str` → `parse_user_expression`
4. 失败返回 `None`

### 12.2 会话持久化

- `SessionManager.create()` 在配置的 `derivation_sessions` 目录下创建会话。
- `DerivationSession.save()` 将会话序列化为 JSON，包含 `current_expression_srepr`。
- `SessionManager.load(session_id)` 恢复会话，使用 `output_srepr` 重建当前表达式。

### 12.3 推导结果仓库

- `DerivationRepository`（`src/symkit/infrastructure/derivation_repository.py`）以 YAML 格式存储 `DerivationResult`。
- 支持注册、查询、搜索、列表、更新、删除。
- `session_complete()` 自动将验证后的推导结果通过该仓库保存。

### 12.4 公式来源

- 本地推导结果可作为公式被后续推导加载。
- 外部适配器结果以 `FormulaInfo` 形式进入推荐列表，可被 `session_load_formula()` 加载。

---

## 13. 状态管理

全局状态集中在 `src/symkit_mcp/tools/_state.py`：

```python
_manager: SessionManager | None = None          # 会话管理器
_current_session: DerivationSession | None = None  # 当前活跃会话
_current_context: MathContext = MathContext()   # 当前数学上下文（假设等）
```

提供工具：

- `get_manager()` / `set_manager(...)`
- `get_session()` / `set_session(...)`
- `get_context()` / `set_context(...)`

这种设计让所有 MCP 工具共享同一会话和假设上下文，同时保持领域层无状态。

---

## 14. 测试策略

测试按功能分层组织，位于 `tests/`，共享夹具（`MockMCP`、`fresh_session_manager`）集中于 `tests/conftest.py`：

| 测试文件 | 覆盖范围 |
|---|---|
| `test_domain.py` | 基础领域实体 |
| `test_domain_services.py` | 推导模式、符号、假设 |
| `test_sympy_engine.py` | SymPy 引擎实现 |
| `test_expression_parser.py` | 表达式解析，含 LaTeX 复合等式、下标、`\max`、星号上标 |
| `test_derivation_engine.py` | 推导引擎逻辑 |
| `test_derivation_examples.py` | 端到端算例 |
| `test_derivation_examples_extended.py` | 扩展端到端算例与边界情形 |
| `test_session_tools.py` | 现代会话工具 |
| `test_session_verification.py` | 会话级自动验证 |
| `test_session_verify_tools.py` | 会话验证与完成工具 |
| `test_session_goal_tools.py` | 目标驱动的推导与推荐工具 |
| `test_step_verifier.py` | 步骤验证 |
| `test_step_crud.py` | 步骤 CRUD，含 LaTeX 下标/Max 回读 |
| `test_orchestration_tools.py` | 编排工具 |
| `test_orchestration_external.py` | 编排中的外部源集成 |
| `test_derivation_goal.py` | 目标解析 |
| `test_derivation_planner.py` | 规划器 |
| `test_formula_recommender.py` | 公式推荐器排序与外部适配器合并 |
| `test_external_adapters.py` | 外部公式适配器集成 |
| `test_formula_search.py` | 公式搜索框架 |
| `test_math_transforms.py` | 经由 `math()` 的积分变换 |
| `test_unified_math_coverage.py` | `math()` 统一工具覆盖 |

当前测试状态：293 个测试全部通过，Ruff 与 MyPy 无错误。

---

## 15. 设计原则

1. **Ports and Adapters（端口与适配器）**  
   通过 `SymbolicEngine`、`Verifier`、`FormulaRepository`、`FormulaSourceAdapter` 等协议，把 SymPy 与外部网络源隔离在基础设施层。

2. **领域驱动设计（DDD）**  
   业务规则集中在 `DerivationSession`、`AssumptionEngine`、`StepVerifier` 等富领域对象中，MCP 层只负责参数转换和结果展示。

3. **不可变审计记录**  
   每个 `DerivationStep` 记录完整上下文，确保推导过程可重现、可学术引用。

4. **Result 模式而非异常**  
   `VerificationResult` 和工具返回的 `dict` 使用 `success`/`error` 模式，便于 LLM 理解和重试。

5. **OperationType 分类**  
   用枚举对推导操作分类，使验证器能自动选择正确的验证策略。

6. **统一解析层**  
   `expression_parser.py` 和 `FormulaParser` 统一处理 Unicode/Greek、LaTeX、方程转换、保留名保护、复合等式拆分和 `\max`/`^*` 映射，避免各工具重复实现。

7. **表达式可回读**  
   用 `srepr` 保存表达式的规范形式，确保 LaTeX 下标、特殊函数名等都能在持久化和回滚后正确恢复。

8. **可插拔外部来源**  
   通过 `FormulaInfo` 和 `FormulaSourceAdapter` 把 Wikidata、BioModels、SciPy 统一接入推荐器。

9. **领域无关性**  
   核心工具不硬编码任何领域语义，工具名称和接口保持通用，由用户上下文提供领域含义。

---

## 16. 附录

### A. 术语表

| 术语 | 说明 |
|---|---|
| MCP | Model Context Protocol，模型上下文协议 |
| Derivation | 公式推导，从已知公式/假设得到新公式的过程 |
| Step | 推导步骤，不可变的操作记录 |
| Formula | 可复用的数学公式或常数 |
| Assumption | 对符号性质的声明（如 positive、real） |
| Verification | 对推导结果正确性的自动/半自动检查 |
| MathContext | 携带假设、坐标系、简化级别和领域的计算上下文 |
| Adapter | 把外部来源转换为项目内部统一格式的适配器 |
| srepr | SymPy 的规范表达式字符串，可安全回读 |
| LaTeX round-trip | LaTeX 输入经解析、存储、再回读后仍保持语义一致 |

### B. 关键文件索引

| 文件 | 说明 |
|---|---|
| `src/symkit/domain/derivation_session.py` | 推导会话与会话管理器 |
| `src/symkit/domain/step_verifier.py` | 步骤验证 |
| `src/symkit/domain/assumption_engine.py` | 假设引擎 |
| `src/symkit/domain/formula.py` | 公式解析与 LaTeX 处理 |
| `src/symkit/domain/formula_recommender.py` | 公式推荐 |
| `src/symkit/infrastructure/sympy_engine.py` | SymPy 引擎 |
| `src/symkit/infrastructure/derivation_repository.py` | YAML 推导仓库 |
| `src/symkit_mcp/tools/math.py` | 统一数学工具 |
| `src/symkit_mcp/tools/session.py` | 统一推导会话工具 |
| `src/symkit_mcp/tools/formula.py` | 公式检索 |
| `src/symkit_mcp/tools/orchestration.py` | 编排工具 |
| `src/symkit_mcp/tools/_state.py` | 全局状态 |
| `src/symkit_mcp/tools/_expression_parser.py` | 统一解析器兼容 shim |
| `tests/test_expression_parser.py` | 表达式解析测试 |
| `tests/test_step_crud.py` | 步骤 CRUD 测试 |

### C. 快速入口

- 启动服务：`python -m symkit_mcp.server`
- 快速计算：`math("diff", "x**3", variable="x")`
- 开始推导：`session_start("k-omega derivation", domain="fluid_dynamics")`
- 加载公式：`session_load_formula("\\mu_t = \\frac{k}{\\omega}", formula_id="eddy_viscosity")`
- 记录步骤：`session_record_step("\\omega = \\frac{\\varepsilon}{\\beta^* k}", "Wilcox definition of omega")`
- 自动推导：`derive("derive k-omega turbulence model", domain="fluid_dynamics", external_sources=[])`

### D. 已知限制与建议

- `derive()` 在长推导或启用网络适配器时可能触发 MCP 客户端超时；复杂任务建议分步使用 `session_start` + `math(..., session=True)`。
- 复合 LaTeX 等式 `"A = B, \\quad C = D"` 仅记录第一条等式，其余会生成 `parse_warnings`，请单独调用记录。
- 含网络的外部适配器默认不启用，避免默认依赖网络。
- 当前版本共 41 个 MCP 工具；`formula_pk_models` 和 `formula_kinetic_laws` 是历史遗留的领域分类工具，后续可能重命名为更通用的名称。

