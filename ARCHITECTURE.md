# Architecture

SymKit MCP Architecture Document (v1.5.0)

---

## System Overview

SymKit is a **general-purpose symbolic derivation engine** that provides AI agents with precise symbolic reasoning capabilities through the Model Context Protocol (MCP).

```
┌─────────────────────────────────────────────────────────────────┐
│                      AI Agent (Claude, etc.)                     │
├─────────────────────────────────────────────────────────────────┤
│                     MCP Protocol Layer                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              symkit_mcp (47 Tools)                          ││
│  │  ┌───────────┐ ┌───────────┐ ┌───────────────┐ ┌─────────┐ ││
│  │  │  Session  │ │   Math    │ │ Tool Discovery│ │ Formula │ ││
│  │  │ 17 tools  │ │  1 tool   │ │  2 tools      │ │ 5 tools │ ││
│  │  └─────┬─────┘ └─────┬─────┘ └───────┬───────┘ └────┬────┘ ││
│  │        │             │             │              │         ││
│  │  ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌──────┴──────┐ ││
│  │  │  Symbol   │ │Assumption │ │  Codegen  │ │Derivation/  │ ││
│  │  │  4 tools  │ │  8 tools  │ │  1 tool   │ │Orchestration│ ││
│  │  └───────────┘ └───────────┘ └───────────┘ │  3 tools    │ ││
│  │                                            └─────────────┘ ││
│  └─────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│                     symkit (Core Library)                       │
│  ┌───────────────┐  ┌─────────────────┐  ┌───────────────────┐  │
│  │    Domain     │  │   Application   │  │  Infrastructure   │  │
│  │  Pure Logic   │◄─│   Use Cases     │──►│   Persistence    │  │
│  └───────────────┘  └─────────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## DDD Layered Architecture

### 1. Domain Layer (`src/symkit/domain/`)

Pure business logic with no external dependencies.

| Module | Description |
|--------|-------------|
| `entities/` | Formula, DerivationStep, DerivationSession |
| `value_objects/` | Expression, Assumption, Metadata |
| `services/` | SymPyEngine, DerivationEngine |
| `repositories/` | FormulaRepository (abstract interface) |
| `assumption_binding.py` | Sole implementation of assumption → Symbol binding (`resolve_assumed_symbol`, `apply_assumptions`); owns the property whitelist and conflict table. Assumptions are applied *after* parsing, onto free symbols only (invariant I1/I3) |
| `expr_io.py` | srepr-first reconstruction of archived expressions (`safe_load_expression`); verification replays the archived object instead of re-parsing a display string (invariant I2) |
| `parser_call_sites.py` | 共享解析器的调用位名称处理：小写 `max(`/`min(` 改写为自动求值的 `Max`/`Min`；同名「裸符号 + 函数调用」双用时把调用位改写为 `<name>__call` 并绑定 `Function('<name>')`，裸符号保持 `Symbol`、假设仅作用于符号 |
| `derivation_outcome.py` | 会话收尾的共享推导：交付物选取（`representative_expression` 的零收尾/血脉规则，非零常数与注记步清零 `zero_outcome`）、目标三元态语义（显式目标才有 matches/score，文本挖掘的 target 不授予） |
| `final_result.py` | 会话收尾的结果选取与判定分级：手工记录等式的同一性判定（`recorded_step_verdict`）、suspect_identity 分级（`classify_suspect_identity` / `numeric_residual_verdict`：数值证伪仅限显式等式断言，跳过含未求值聚合的差式）、`select_headline` 跳过 failed 步选取最终表达式；布尔塌缩等式主张恢复（`asserted_equation_verdict`）、差式咨询的两顶项语义门与 `A - B` 指称措辞 |
| `recorded_claim.py` | 手工记录等式的文本机械与折叠修复：`equation_claim_sides` 拆 `A = B` 主张、数值等式折叠成布尔后的非求值 `Eq` 重建（`unevaluated_equality`，保留残差披露）、纯数值差式的容差判定（`numeric_difference_verdict`，截断小数为 inconclusive 而非 failed） |
| `expression_form.py` | 表达式的「书写形态」谓词：`is_difference_form` 只在前方存在非负项时才把否定项视为差式 `A - B`（前导负项如 `-x**2 + x*(x+1)` 属普通代数，不触发 suspect 警告）、`recorded_leading_negative` 从记录字符串识别前导一元负号（srepr 会重排项序，只有显示串保留该语法） |
| `units.py` / `dimensional_analysis.py` | 单位解析与量纲一致性检查（纯领域逻辑，无外部依赖）：量纲向量、四则运算/函数传播规则、问题诊断 |
| `lean_types.py` | Lean 认证通道的共享契约：`LeanStatement` / `LeanOutcome` 值对象、`LeanChecker` Protocol、`UntranslatableError`；domain 定义接口，infrastructure 实现 |
| `lean_translation.py` | SymPy → Lean 4 表达式翻译（有理式片段：+−*/整数次幂）；变量分母要求显式非零假设，片段外构造抛 `UntranslatableError`；`clear_denominators` 生成保结构的分子形态（field→ring 兜底用） |

### 2. Application Layer (`src/symkit/application/`)

Coordinates Domain and Infrastructure. Re-exported from `symkit/__init__.py` as the
programmatic library API; the MCP layer calls domain services directly and does not route
through these classes.

| Module | Description |
|--------|-------------|
| `use_cases.py` | `CalculateUseCase`, `SimplifyUseCase`, `DeriveUseCase`, `VerifyUseCase` — public library entry points |
| `formula_catalog.py` | Formula catalog over the SQLite FTS5 index; composition root for the formula layers |
| `lean_certification.py` | `certify_session` 用例：重放会话中的代数等式步骤、经 `LeanChecker` 批量内核复核，结果写入步骤 `details.lean`；从不改动既有判定，分歧以 `discrepancies` 报告；输入输出逐字相同的步记为 `trivial`（不计入 `proven`、不进内核）；可接受认证时传入的额外假设；field 步 unproven 时以清分母多项式形式重试（lane `field+ring`，分母因子带非零 binders） |

### 3. Infrastructure Layer (`src/symkit/infrastructure/`)

Interfaces to external systems.

| Module | Description |
|--------|-------------|
| `sympy_engine.py` | `SymbolicEngine` implementation over SymPy (calculus, matrix, ODE, transforms, vector calculus) |
| `numeric_eval.py` | 有限 `Sum` 的数值求值：≥30 位工作精度先精确求和，抵消检测触发精度加倍并告警；支撑 `evalf` 及其验证 |
| `vector_input.py` | `curl`/`divergence` 的向量场输入归一：逗号分量串 / 3 元列表 / 3x1 矩阵 / `N.i,N.j,N.k` 形式统一为 `CoordSys3D` 场，标量输入显式报错而非静默成零；`normalize_derivatives` 规范化混合偏导变量序 |
| `formula_files.py` / `formula_index_store.py` | YAML layer reader and the SQLite FTS5 index store |
| `derivation_repository.py` | Session JSON persistence |
| `verifier.py` | `BasicVerifier` — the `Verifier` abstract interface's only concrete adapter, consumed by `application/use_cases.py` |
| `lean_toolchain.py` | Lean 工具链检测与一次性 bootstrap（`symkit-lean-setup` 控制台脚本：elan + 固定 toolchain + Mathlib 缓存，就绪戳 `.symkit-lean-ready`）；`lake` 查找以 `ELAN_HOME` 优先于 `PATH`，并校验所选 elan home 已持有工作区钉住的 toolchain，避免认证时触发重复下载；无工具链时全链路优雅降级 |
| `lean_batch.py` | `LeanChecker` 的批处理实现：把全部待证定理渲染进一个 `SymkitCheck.lean`，单次 `lake env lean` 运行，按错误行号归属定理；进程级失败不得标记任何定理为已证；超时由 `lean_process` 杀掉整棵进程树 |
| `lean_process.py` | Lean 子进程的进程树管理：以独立进程组启动（Windows 用 `taskkill /F /T`，POSIX 用 `killpg`）并在超时时整树强杀，避免残留孤儿进程占用 elan toolchain 锁 |
| `adapters/` | External formula/constant sources (Wikidata, SciPy CODATA, BioModels) |

### 4. MCP Layer (`src/symkit_mcp/`)

MCP protocol interface, independent of the core library.

| Module | Description |
|--------|-------------|
| `server.py` | MCP Server entry point |
| `tools/` | 47 MCP tool implementations |
| `tools/_math_dispatch.py` | `math()` internals: operation dispatch, expression parsing, per-operation parameter audit |
| `tools/_op_helpers.py` | `solve`/`integrate` 的装配与守卫：系统解响应装配（头条非排除根、布尔解丢弃）、特殊函数反导数警示、`method=risch`、幂变量/不等式/集合字面量的 curated 拒绝 |
| `tools/_math_recording.py` | `math()` 落步与展示：provenance（original/replacement/limit 方向/evalf 代入点）、算子桶映射、失败调用的注记步、会话级假设快照 |
| `tools/_target_echo.py` | 目标表达式的校验与解析回显：`session_start`/`session_set_goal` 的 goal 装配（裸 `target_expression` 无 goal 也生效）、`target_parsed` 回显与不可解析警告 |
| `tools/_headline_override.py` | `session_complete(final_expression=...)` 的显式交付物通道：统一解析器校验、结果字段与落库表达式接管 |
| `tools/_session_views.py` | 会话视图与验证摘要装配 |
| `tools/_library_gate.py` | 公式落库的量纲门禁：声明单位可判定不一致时拒绝写库（`not_saved_reason`），单位不全照常走 staging |
| `tools/_assumption_text.py` | 假设子句校验：表达式型假设的 curated 拒绝（防空白切碎） |
| `tools/_state.py` | Process-global current session/context shared by all tool modules |
| `tools/_unit_context.py` | MCP 层单位接线：聚合会话单位（公式变量 + 符号注册表）、`dimension` 操作、验证链的量纲后置检查 |
| `tools/_formula_governance.py` | 公式写入治理：变量单位必填（`"-"` 为显式无量纲哨兵）、`similar_to` 近重复提示（结构指纹优先、FTS 兜底）、单位回填 |
| `tools/_system_solve.py` | 列表输入的系统 `solve`：逐解假设过滤（`filtered_by_assumptions`）、多解头条告警 |
| `tools/certification.py` | Verification 类别：`lean_status` 环境探针（委托 `lean_toolchain.describe_environment`，报告解析到的 toolchain/Mathlib/工作区路径、来源变量、缺失层与下一步命令；默认只读、不下载，`warmup=true` 时经同一批检查器编译平凡 ring 定理预热工作区缓存并诚实报告结果）；`session_certify` 委托 `application/lean_certification.py`，可选 `assumptions` 参数在认证时补前提，不可用时指向 `lean_status()` |
| `tools/execute.py` | Execution 类别：`python_exec` 逃生舱——委托 `infrastructure/code_exec.py` 在一次性子进程中执行 LLM 提交的 Python 代码，纯计算通道、不落会话 |

---

## Tool Categories (47 Tools)

| Category | Count | Description |
|----------|-------|-------------|
| **Unified Math** | 1 | Unified math entry point (33 operations: calculus, matrices, ODE, transforms, numeric `evalf`, dimensional consistency `dimension`, etc.) |
| **Assumptions** | 7 | Multi-level assumption engine: `assume` / `show_assumptions` (global context) plus step/session-level `assume_for_step`, `list_assumptions`, `clear_step_assumptions`, `unassume`, `clear_assumptions` |
| **Verification** | 5 | Step/session verification and assumption-conflict detection: `session_verify_step`, `session_verify_session`, `session_certify`, `check_assumption_conflicts`, `lean_status`. 会话存在单位信息时，验证链自动附加量纲一致性检查（不一致的步标为 `failed`）；`session_certify` 可选地用 Lean 4 + Mathlib 内核复核代数等式步骤，结果写入 `details.lean`，永不改动既有判定，`session_verify_session` 汇总附带 `lean`（proven/unproven）计数 |
| **Symbol Semantics** | 4 | Symbol registration, lookup, and conflict detection |
| **Formula Library** | 8 | Formula search and curation over a persistent SQLite FTS5 index (trigram tokenizer, CJK-capable); three tiers — bundled seeds (read-only), staging (session-derived, demoted in ranking), curated (user-added / promoted via `formula_promote`); content-hash dedup collapses duplicate entries; `formula_reindex` rebuilds after hand edits; `formula_stats` reports tier counts。写入路径要求每个变量携带非空 `unit`（`"-"` 表示未知/无量纲），成功时返回 `similar_to` 近重复提示（α-不变结构指纹优先，FTS 文本兜底）；`formula_promote` 落盘 `curated: true`，`formula_get` 透出 `curated`，`formula_stats` 另报结构重复组 `structural_duplicate_groups`。`verified` 表示验证器跑过，`curated` 表示人工晋升，二者语义独立 |
| **Session Management** | 15 | Derivation session management and step operations; graded overall verification (a chain is verified when nothing failed and at least one substantive step verified) |
| **Output** | 1 | `generate_output(format=...)`: Markdown report / LaTeX / Python function / standalone SymPy script from verified steps |
| **High-Level Orchestration** | 3 | High-level derivation orchestration (`derive`, `intent_execute`, `list_patterns`) |
| **Meta** | 2 | Tool discovery and recommendations (`tool_categories`, `tool_recommend`) |
| **Execution** | 1 | `python_exec`：一次性隔离子进程执行 Python/sympy 代码的逃生舱（预载 `from sympy import *`，`result` 变量回传 repr+srepr，复用 `lean_process.run_with_tree_timeout` 杀树超时，默认 10s、上限 60s，AST 粗筛拒绝明显的文件/网络/进程逃逸，`SYMKIT_DISABLE_CODE_EXEC=1` 关闭） |

---

## Data Flow

```
User Request → MCP Tool → Use Case → Domain Service → SymPy Engine
                                           │
                                           ▼
                              Infrastructure (YAML/JSON)
```

### Derivation Workflow Example

1. `session_start()` - Start a session.
2. `session_record_step()` - Record each step.
3. `math()` - Perform symbolic operations (differentiation, integration, solving, etc.).
4. `session_show()` - Display the current state.
5. `session_complete()` - Persist the session.

---

## Directory Structure

```
symkit-mcp/
├── src/
│   ├── symkit/              # Core Library (DDD)
│   │   ├── domain/          # Pure business logic
│   │   ├── application/     # Use-case coordination
│   │   └── infrastructure/  # Persistence, external adapters
│   └── symkit_mcp/          # MCP Server
│       ├── server.py        # Entry point
│       └── tools/           # 47 tools
├── formulas/                # Formula library
│   ├── library/             # Seed formulas (YAML, by category)
│   └── derived/             # Session-derived formulas (runtime output)
├── examples/                # Python examples
├── tests/                   # Tests
└── pyproject.toml
```

---

## Tech Stack

- **Python**: 3.10+
- **SymPy**: Symbolic computation engine
- **MCP SDK**: Model Context Protocol
- **uv**: Package manager
- **Ruff**: Linter
- **pytest**: Testing framework

---

## Related Documents

- [README.md](README.md) - Project overview
- [CONSTITUTION.md](CONSTITUTION.md) - Development principles
