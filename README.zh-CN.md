# SymKit

> **LLM 驱动的 Mathematica 式符号计算。**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-green.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-281%20passed-brightgreen.svg)]()
[![Lint](https://img.shields.io/badge/ruff-passing-brightgreen.svg)]()

🌐 [English](README.md) | **简体中文**

## 如果你拥有 Mathematica 的符号引擎，但可以用自然语言驱动它？

Mathematica 给了我们精确的符号数学能力，大语言模型给了我们自然语言推理能力。**SymKit 把两者结合起来。**

它是一个 MCP 服务器，让 AI Agent 通过对话完成逐步符号推导：计算、变换、验证、保存公式，并记录完整来源。

```text
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│  你用 plain English 描述数学问题                                    │
│        ↓                                                           │
│  SymKit 执行、验证并记录每一步                                       │
│        ↓                                                           │
│  你得到的是精确、可复用的公式及其审计链条                              │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## 为什么要用 SymKit？

| 传统 LLM | SymKit |
|---|---|
| ❌ "答案大约是……" | ✅ "精确表达式是……" |
| ❌ "我再算一遍" | ✅ 每一步都被记录并可验证 |
| ❌ "我觉得单位是对的" | ✅ 量纲分析自动检查每个结果 |
| ❌ "这公式从哪来的？" | ✅ 完整来源：基础公式 + 推导步骤 |
| ❌ 计算结果消失在聊天记录里 | ✅ 以可复用的 Markdown + YAML 保存 |

## 它能做什么？

**SymKit 不是公式数据库。** 它是一个**符号推导引擎**，能从已有公式中创造新公式。

```text
已知公式                          新公式
┌─────────────────┐              ┌────────────────────────────┐
│ F = -kx         │              │                            │
│ F = ma          │  ──组合──▶   │  ω = √(k/m)                │
│ d²x/dt² = a     │              │  （简谐振子角频率）          │
└─────────────────┘              └────────────────────────────┘
```

无论是物理、工程、化学、生物还是经济，只要涉及数学关系的组合与变换，SymKit 都能派上用场。

## ⚡ 四大核心能力

| 能力 | 含义 | 工具 |
|---|---|---|
| **推导** | 将基础公式组合为新公式 | `derive`、`intent_execute`、`math` |
| **控制** | 查看、注释、回滚每一步 | `session_*`、`*_step` |
| **验证** | 符号等价与量纲分析双重检查 | `session_verify_*`、`assume*` |
| **交付** | 生成 Python、LaTeX、Markdown、SymPy | `generate_*` |

## 🚀 实际效果

**从第一性原理推导物理定律：**

```text
用户：推导简谐振子的角频率。

SymKit：
  1. 加载 F = -kx  和  F = m·d²x/dt²
  2. 代入 → m·d²x/dt² = -kx
  3. 求解 ODE → x(t) = A·cos(ωt + φ)，ω = √(k/m)
  4. 回代验证：d²x/dt² = -ω²x  ✓
  5. 保存完整推导历史
```

**构建自定义工程模型：**

```text
用户：求 RC 高通滤波器的截止频率。

SymKit：
  1. 加载 Q = CV 和 V = IR
  2. 推导容抗 X_c = 1/(2πfC)
  3. 在截止频率处令 X_c = R
  4. 解出 f → f_c = 1 / (2πRC)  ✓
```

**验证微积分结果：**

```text
用户：计算并验证 ∫(x² + 3x) dx。

→ 结果：x³/3 + 3x²/2 + C
→ 验证：d/dx(x³/3 + 3x²/2) = x² + 3x  ✓
```

## 🛠️ 43 个 MCP 工具，一套连贯工作流

SymKit 提供 **43 个 MCP 工具**，分为 8 个类别。日常通过少数高层工具即可完成复杂推导，高级用户也可以精细控制每一步。

| 类别 | 工具 | 数量 |
|---|---|---|
| **统一数学** | `math` | 1 |
| **会话管理** | `session_start`、`session_show`、`session_rollback`、`session_complete` 等 | 17 |
| **假设管理** | `assume`、`show_assumptions`、`assume_for_step` 等 | 6 |
| **公式搜索** | `formula_search`、`formula_get`、`formula_constants` 等 | 6 |
| **符号注册** | `register_symbol`、`lookup_symbol` 等 | 4 |
| **代码生成** | `generate_python_function`、`generate_latex_derivation` 等 | 4 |
| **推导与编排** | `derive`、`intent_execute`、`list_patterns` | 3 |
| **工具发现** | `tool_categories`、`tool_recommend` | 2 |

仅 `math()` 一个工具就覆盖约 25 种符号运算——微积分、ODE、矩阵、矢量分析、积分变换——并且可以直接把结果写入推导会话。

## 🔍 公式搜索工作流

SymKit 可以从 Wikidata 拉取权威公式，从 SciPy 拉取物理常数，自动规范化 LLM 的查询，并把选中的公式直接加载到推导会话。

**推荐工作流：**

```text
1. 搜索
   formula_search("Navier-Stokes equations", domain="fluid_dynamics")

2. 获取并加载
   formula_get("Q201321", source="wikidata", load_into_session=True)

3. 推导
   math("simplify", "...", session=True)

4. 完成
   session_complete(description="不可压 NS 动量方程")
```

**查询规范化：** 你可以用自然写法查询——`fluid_dynamics`、`fluid mechanics`、`cfd` 都会解析到同一个领域；`Navier–Stokes`（en dash）和 `Navier-Stokes`（hyphen）会匹配同一个 Wikidata 条目。

**MathML 处理：** Wikidata 的搜索预览有时会返回渲染后的 MathML。调用 `formula_get` 获取结果 ID 对应的原版 LaTeX 和 SymPy 可用字符串。

## 🎛️ 每一步都由你掌控

SymKit 中的推导是一串不可变、可验证的步骤。你可以：

- **创建** — `session_record_step`
- **读取** — `session_get_steps`、`session_show`
- **注释** — `session_add_note`
- **回滚** — `session_rollback`
- **验证** — `session_verify_step`、`session_verify_session`

表达式不会原地修改。如果出错，回滚到上一个有效状态再继续。这保证了整个推导过程可复现。

## 🌍 与 MCP 生态协同

SymKit 的设计目标是扩展科学计算栈，而非取代它。它负责推导、验证和来源追溯；原始符号计算与基础公式查询由 SymPy-MCP 承担。

**适合使用 SymKit 的场景：**

- ✅ 从已有公式推导新公式
- ✅ 构建温度/压力/参数修正模型
- ✅ 为任意定量领域创建自定义模型
- ✅ 生成经过验证、可引用的推导成果

**不适合使用 SymKit 的场景：**

- ❌ 查询基础物理公式 → 使用 `sympy-mcp`
- ❌ 查询物理常数 → 使用 `sympy-mcp` 或 `SciPy`
- ❌ 临床评分 → 使用 `medical-calc-mcp`
- ❌ 阅读教科书公式 → 直接查阅参考资料

## 📦 60 秒快速开始

### 环境要求

- **Python 3.12+**
- **uv**（推荐）

```bash
# 安装
uv add symkit-mcp

# 或使用 pip
pip install symkit-mcp
```

### 接入 Claude Desktop / Cherry Studio

同一套 MCP JSON 配置同时兼容 Claude Desktop、Cherry Studio 等 MCP 客户端。

**如果你是通过 PyPI 安装：**

```json
{
  "mcpServers": {
    "symkit": {
      "command": "uvx",
      "args": ["symkit-mcp"]
    }
  }
}
```

**如果你直接从本地源码运行（无需安装到环境）：**

```json
{
  "mcpServers": {
    "symkit": {
      "command": "uv",
      "args": [
        "run",
        "--no-sync",
        "--directory",
        "i:\\Formulation\\example\\nsforge-mcp-sigma",
        "python",
        "-m",
        "symkit_mcp.server"
      ]
    }
  }
}
```

将 `--directory` 替换为你本地 `symkit-mcp` 仓库的绝对路径。`--no-sync` 会跳过每次启动时的依赖同步，依赖变更后手动运行 `uv sync` 即可。

## 🏗️ 架构清晰，易于扩展

```text
symkit-mcp/
├── src/
│   ├── symkit/               # 纯领域逻辑（不依赖 MCP）
│   │   ├── domain/          # 实体、值对象、推导引擎
│   │   ├── application/     # 用例
│   │   └── infrastructure/  # SymPy 引擎、适配器、持久化
│   └── symkit_mcp/          # MCP 服务器层
│       ├── server.py
│       └── tools/           # 43 个 MCP 工具
├── formulas/                # 推导成果仓库
├── tests/                   # 281 个测试
└── pyproject.toml
```

- **领域驱动设计** — 核心逻辑与 MCP 和 SymPy 解耦。
- **可插拔引擎** — 通过协议可替换符号引擎或验证器。
- **基于文件的持久化** — 公式和会话以 Markdown/YAML/JSON 存储，便于阅读和版本控制。

## 🧪 开发

```bash
# 运行完整测试套件
uv run pytest

# Lint 与类型检查
uv run ruff check src/ tests/
uv run mypy src/

# 启动开发服务器
uv run symkit-mcp
```

## 📖 了解更多

- [ARCHITECTURE.md](ARCHITECTURE.md) — DDD 分层与职责
- [docs/symkit-design.md](docs/symkit-design.md) — 深度技术设计文档（英文）
- [docs/symkit-design.zh-CN.md](docs/symkit-design.zh-CN.md) — 深度技术设计文档（中文）
- [docs/symkit-vs-sympy-mcp.md](docs/symkit-vs-sympy-mcp.md) — 与 SymPy-MCP 的能力对比
- [ROADMAP.md](ROADMAP.md) — 路线图

## 🙏 感谢

SymKit 基于 [nsforge-mcp](https://github.com/u9401066/nsforge-mcp) 的成果进一步发展而来。nsforge-mcp 开创了神经符号公式推导的探索方向，其原始中文 README 可参见[此处](https://github.com/u9401066/nsforge-mcp/blob/master/README.zh-TW.md)。

SymKit 与 [sympy-mcp](https://github.com/space-cadet/sympy-mcp) 协同工作，后者提供了 SymKit 所依赖的底层 SymPy 符号计算和基础公式查询能力。

## 📄 许可证

Apache 2.0 — 详见 [LICENSE](LICENSE)。

---

<p align="center">
  <strong>停止只回答数学题。开始推导新知识。</strong>
</p>
