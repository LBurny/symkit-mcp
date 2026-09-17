# SymKit

面向 AI Agent 的逐步符号数学：在 SymPy 之上推导、验证、认证公式，并保留完整来源。

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-1656%20passed-brightgreen.svg)]()

[English](README.md) | **简体中文**

## SymKit 是什么？

一个 [MCP](https://modelcontextprotocol.io/) 服务器，让 AI Agent 通过对话完成精确的符号数学。基于 SymPy 构建：把已知公式组合成新公式，记录每个推导步骤，并对每个结果做符号等价与量纲双重验证——而不是让计算停留在大模型无法复核的叙述里。

| 只有 LLM | 配合 SymKit |
|---|---|
| ❌ "答案大约是……" | ✅ "精确表达式是……" |
| ❌ 靠重新算一遍来复查 | ✅ 每一步都被记录、可独立验证 |
| ❌ "我觉得单位是对的" | ✅ 量纲分析自动检查每个结果 |
| ❌ "这公式从哪来的？" | ✅ 完整来源：基础公式 + 推导步骤 |

适用于物理、工程、化学、生物、经济——任何需要组合与变换数学关系的领域。

## 核心能力

| 能力 | 含义 | 主要工具 |
|---|---|---|
| 推导 | 将基础公式组合为新公式 | `derive`、`intent_execute`、`math` |
| 控制 | 查看、注释、回滚每一步 | `session_*` |
| 验证 | 符号等价 + 量纲分析 | `session_verify_*`、`assume` |
| 交付 | 导出 Python、LaTeX、Markdown、SymPy 脚本 | `generate_output` |

示例——从 `F = -kx` 和 `F = m·a` 推导简谐振子的角频率：

```text
1. 加载两个基础公式并代入 → m·d²x/dt² = -kx
2. 求解 ODE → x(t) = A·cos(ωt + φ)，ω = √(k/m)
3. 回代验证：d²x/dt² = -ω²x  ✓
4. 保存结果及完整推导历史
```

## 工具

47 个 MCP 工具，分 10 个类别。多数工作通过少数高层工具完成；高级用户可以精细控制每一步。

| 类别 | 数量 | 代表工具 |
|---|---|---|
| 统一数学 | 1 | `math` — 33 种符号运算：微积分、ODE、矩阵、矢量分析、积分变换、量纲分析 |
| 会话管理 | 15 | `session_start`、`session_record_step`、`session_rollback`、`session_complete` |
| 验证 | 5 | `session_verify_step`、`session_verify_session`、`session_certify`、`lean_status` |
| 假设管理 | 7 | `assume`、`unassume`、`check_assumption_conflicts` |
| 公式库 | 8 | `formula_search`、`formula_get`、`formula_add`、`formula_promote` |
| 符号语义 | 4 | `register_symbol`、`lookup_symbol`、`check_symbol_conflicts` |
| 输出 | 1 | `generate_output`（`markdown_report` / `latex` / `python` / `sympy_script`） |
| 高层编排 | 3 | `derive`、`intent_execute`、`list_patterns` |
| 元工具 | 2 | `tool_categories`、`tool_recommend` |
| 代码执行 | 1 | `python_exec` — 隔离子进程中运行一次性 Python/sympy 代码 |

## 推导会话

推导是一串不可变、可验证的步骤。表达式不会被原地修改——出错时 `session_rollback` 回到上一个有效状态再继续，保证整个推导可复现。每一步都保存输入、输出、注释、假设与实际执行的 SymPy 命令，以 JSON 持久化在数据目录下。

## 公式库

公式以 YAML 文件存储，由持久化 SQLite FTS5 索引支撑检索——确定、离线、即时。条目按 tier 分层排序：

| tier | 来源 | 加成 |
|---|---|---|
| `seed` | 随包分发的只读公式（雷诺数、Navier–Stokes 等） | +0.10 |
| `curated` | `formula_add`，或经 `formula_promote` 晋升 | +0.15 |
| `staging` | `session_complete(auto_save=True)` 写入的会话产物 | +0.00 |

```text
formula_search("Navier-Stokes", domain="fluid_dynamics")
formula_get("ns_incompressible", load_into_session=True)
math("simplify", "...", session=True)
session_complete(description="不可压 NS 动量方程")
```

检索覆盖名称、别名（支持中文：搜 `雷诺数` 命中 Reynolds number）、标签、领域、描述及表达式文本。会话产物以确定性 id 写入 `staging` 并自动去重；用 `formula_promote` 晋升要留存的条目，用 `formula_stats` 查看分层统计，手工编辑 YAML 后用 `formula_reindex` 重建索引。索引（`<数据目录>/formulas/index.sqlite3`）只是缓存，随时可删。可选外部来源（`source="wikidata" | "scipy" | "biomodels"`）离线时优雅降级。

## Lean 4 内核认证（可选）

`session_certify()` 用 Lean 4 + Mathlib 内核复核当前会话中符合条件的代数等式步骤（有理式片段内的 `simplify` / `expand` / `factor` / `combine`），经 `ring` / `field_simp` 证明。结果写入各步骤的 `details.lean`；既有验证判定从不被修改，`unproven` 只表示自动化未能闭合目标，不代表步骤有误。输入与输出逐字相同的步骤（`x = x`、`0 = 0`）记为 `trivial` 并**不计入** `proven`：内核虽瞬时通过，但并未验证任何代数。不引入任何额外 Python 依赖。

不确定后端是否装好时，先调 `lean_status()`——它只读、不会运行 Lean、也不下载，会报告解析到的 toolchain / Mathlib / 工作区路径、各路径来自哪个变量、缺哪一层、以及确切的下一步命令。不要自己去翻目录或跑 `lake --version`：某个目录不存在并不构成证据，而 Mathlib 位于 `<数据目录>/lean-workspace/.lake/packages/mathlib`。

### 配置

```bash
# 一次性安装 elan + Lean 4 + 预编译 Mathlib（约 1–2 GB 下载，需联网）
symkit-lean-setup --yes

# 可选：固定 Lean 版本而非 stable
symkit-lean-setup --yes --toolchain v4.24.0
```

配置要点：

- **数据目录**：Lean 工作区安装在 `<数据目录>/lean-workspace`。运行安装脚本（及服务器）前设置 `SYMKIT_DATA_DIR` 可改变位置。
- **工具链位置**：`lake` 按 `ELAN_HOME/bin` → `PATH` → `~/.elan/bin` 的顺序查找。已有 elan 安装时，把 `ELAN_HOME` 指向它即可复用——它的优先级最高，`PATH` 上的默认 `~/.elan/bin/lake` 不会将其遮蔽。认证前还会校验所选 `lake` 是否已持有工作区钉住的 Lean 版本；否则返回 `lean_available: false` 并给出明确原因，而不是触发一次新的工具链下载。
- **代理**：若下载在代理环境停滞或失败，先导出 `HTTP_PROXY` / `HTTPS_PROXY` 再运行安装——elan 安装器不读取 Windows 系统代理设置。
- **就绪检查**：工具链与 `.symkit-lean-ready` 标记就位后，再次调用 `session_certify()` 会报告 `lean_available: true`。

使用限制：`session_certify()` 需要活跃会话；含变量作分母的步骤需显式声明分母非零。可在认证时直接传入 `session_certify(assumptions={"x": {"nonzero": True}})`（或 `assumptions="x nonzero"`），也可事先用 `assume({"x": "nonzero"})` 注册。未安装工具链时，SymKit 的其余行为完全不变。

## 安装

环境要求：Python 3.10+、任意 MCP 兼容客户端（Claude Desktop、Claude Code、Cherry Studio 等）、uv 或 pip。

### 方式 A —— uv（推荐）

```bash
uv tool install symkit-mcp
symkit-mcp --version
```

`uvx symkit-mcp` 免安装即时运行最新发布版。

### 方式 B —— pip

```bash
pip install symkit-mcp
```

（需要隔离环境可用 `pipx install symkit-mcp`。）

### 方式 C —— 从源码

```bash
git clone https://github.com/LBurny/symkit-mcp.git
cd symkit-mcp
uv sync --all-extras
uv run symkit-mcp
```

### 数据目录

运行时数据按用户存放（经 `platformdirs` 解析）：Linux 为 `~/.local/share/symkit/`，Windows 为 `%LOCALAPPDATA%\symkit`，macOS 为 `~/Library/Application Support/symkit`。设置 `SYMKIT_DATA_DIR` 可覆盖——例如通过 MCP 服务器的 `env` 配置块按项目隔离会话与公式库。种子公式只读打包在包内；`formula_add` 添加的用户公式进入可写覆盖层并按 id 覆盖种子；会话派生公式写入 `<数据目录>/formulas/derived/`。

### 接入客户端

在客户端配置中加入 `mcpServers` 条目（Claude Desktop 为 `claude_desktop_config.json`；Cherry Studio 为设置面板）。

已安装且在 PATH 中（uv tool / pip / pipx）：

```json
{ "mcpServers": { "symkit": { "command": "symkit-mcp", "args": [] } } }
```

免安装（uvx 拉取并缓存最新发布版）：

```json
{ "mcpServers": { "symkit": { "command": "uvx", "args": ["symkit-mcp"] } } }
```

从源码检出目录运行：

```json
{
  "mcpServers": {
    "symkit": {
      "command": "uv",
      "args": ["run", "--no-sync", "--directory", "<本地路径>",
               "python", "-m", "symkit_mcp.server"]
    }
  }
}
```

> Windows：若客户端报 "command not found"，改用绝对路径，如 `"C:/Users/you/AppData/Local/uv/tools/symkit-mcp/Scripts/symkit-mcp.exe"`。

## 架构

```text
src/
├── symkit/               # 核心领域库（不依赖 MCP）
│   ├── domain/           # 实体、推导引擎、验证器契约
│   ├── application/      # 用例
│   └── infrastructure/   # SymPy 引擎、Lean 检查器、持久化、适配器
└── symkit_mcp/           # MCP 服务器层（FastMCP）+ 47 个工具
formulas/                 # 种子公式库（源码树）
tests/                    # 1656 个测试
```

领域驱动设计：核心逻辑与 MCP、SymPy 解耦；引擎经协议可插拔；公式与会话以可读的 YAML/JSON 持久化。

## 开发

```bash
uv run pytest          # 完整测试套件
uv run ruff check src/ tests/
uv run mypy src/
uv run symkit-mcp      # 开发服务器
```

## 了解更多

- [ARCHITECTURE.md](ARCHITECTURE.md) — DDD 分层与工具清单
- [docs/symkit-design.zh-CN.md](docs/symkit-design.zh-CN.md)（[英文](docs/symkit-design.md)）— 深度技术设计
- [推荐系统提示词](docs/recommended-system-prompt.md) — 交给智能体、驱动其走工具链推导的提示词
- [ROADMAP.md](ROADMAP.md) — 路线图
- [公式库字段说明](formulas/README.zh-CN.md) — YAML 条目格式

## 感谢

SymKit 基于 [nsforge-mcp](https://github.com/u9401066/nsforge-mcp) 的成果发展而来，后者开创了神经符号公式推导的探索方向；也可与 [sympy-mcp](https://github.com/sdiehl/sympy-mcp)（通用 SymPy MCP 服务）搭配使用。

## 许可证

[Apache 2.0](LICENSE)。