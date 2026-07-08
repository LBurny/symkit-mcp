# Architecture

SymKit MCP 架构文档 (v0.2.4)

---

## 系统概览

SymKit 是一个**通用符号推导引擎**，通过 MCP (Model Context Protocol) 为 AI 代理提供精确的符号推理能力。

```
┌─────────────────────────────────────────────────────────────────┐
│                      AI Agent (Claude, etc.)                     │
├─────────────────────────────────────────────────────────────────┤
│                     MCP Protocol Layer                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              symkit_mcp (41 Tools)                          ││
│  │  ┌───────────┐ ┌───────────┐ ┌───────────────┐ ┌─────────┐ ││
│  │  │  Session  │ │   Math    │ │ Tool Discovery│ │ Formula │ ││
│  │  │ 17 tools  │ │  1 tool   │ │  2 tools      │ │ 4 tools │ ││
│  │  └─────┬─────┘ └─────┬─────┘ └───────┬───────┘ └────┬────┘ ││
│  │        │             │             │              │         ││
│  │  ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌──────┴──────┐ ││
│  │  │  Symbol   │ │Assumption │ │  Codegen  │ │Derivation/  │ ││
│  │  │  4 tools  │ │  6 tools  │ │  4 tools  │ │Orchestration│ ││
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

## DDD 分层架构

### 1. Domain Layer (`src/symkit/domain/`)

纯业务逻辑，无外部依赖。

| 模块 | 说明 |
|------|------|
| `entities/` | Formula, DerivationStep, DerivationSession |
| `value_objects/` | Expression, Assumption, Metadata |
| `services/` | SymPyEngine, DerivationEngine |
| `repositories/` | FormulaRepository (抽象接口) |

### 2. Application Layer (`src/symkit/application/`)

协调 Domain 与 Infrastructure。

| 模块 | 说明 |
|------|------|
| `use_cases/` | 推导、验证、公式管理用例 |
| `dto/` | 数据传输对象 |

### 3. Infrastructure Layer (`src/symkit/infrastructure/`)

外部系统接口。

| 模块 | 说明 |
|------|------|
| `persistence/` | YAML/JSON 文件存储 |
| `formula_repository_impl.py` | FormulaRepository 实作 |

### 4. MCP Layer (`src/symkit_mcp/`)

MCP 协议接口，独立于内核库。

| 模块 | 说明 |
|------|------|
| `server.py` | MCP Server 入口 |
| `tools/` | 41 个 MCP 工具实作 |

---

## 工具分类 (41 Tools)

| 类别 | 数量 | 说明 |
|------|------|------|
| **Session** | 17 | 推导会话管理、步骤操作 |
| **Math** | 1 | 统一数学入口（微积分、矩阵、ODE、变换等） |
| **Assumption** | 6 | 符号假设管理 |
| **Formula** | 4 | 外部公式搜索与分类 |
| **Symbol** | 4 | 符号注册、查找、冲突检测 |
| **Codegen** | 4 | Python/LaTeX/Markdown/SymPy 生成 |
| **Derivation/Orchestration** | 3 | 高层推导编排 |
| **Tool Discovery** | 2 | 工具发现与推荐 |

---

## 数据流

```
User Request → MCP Tool → Use Case → Domain Service → SymPy Engine
                                           │
                                           ▼
                              Infrastructure (YAML/JSON)
```

### 推导工作流范例

1. `session_start()` - 开始会话
2. `session_record_step()` - 记录每步
3. `math()` - 执行符号操作（微分、积分、求解等）
4. `session_show()` - 显示当前状态
5. `session_complete()` - 存盘

---

## 目录结构

```
symkit-mcp/
├── src/
│   ├── symkit/              # Core Library (DDD)
│   │   ├── domain/           # 纯业务逻辑
│   │   ├── application/      # 用例协调
│   │   └── infrastructure/   # 持久化、外部适配器
│   └── symkit_mcp/          # MCP Server
│       ├── server.py         # 入口
│       └── tools/            # 41 个工具
├── formulas/                 # 公式仓库
│   ├── derivations/          # 推导示例（Markdown）
│   └── fluid_dynamics/       # 已保存公式示例
├── examples/                 # Python 示例
├── tests/                    # 测试
└── pyproject.toml
```

---

## 技术栈

- **Python**: 3.10+
- **SymPy**: 符号计算引擎
- **MCP SDK**: Model Context Protocol
- **uv**: 套件管理
- **Ruff**: Linting
- **pytest**: 测试框架

---

## 相关文档

- [README.md](README.md) - 项目说明
- [CONSTITUTION.md](CONSTITUTION.md) - 开发原则
- [docs/symkit-vs-sympy-mcp.md](docs/symkit-vs-sympy-mcp.md) - 技能指南
