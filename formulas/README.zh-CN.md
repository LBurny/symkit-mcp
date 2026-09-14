# SymKit 公式库

[English](README.md) | **简体中文**

本仓库的 `formulas/` 是随包种子公式的源码树。运行时检索走按用户划分的数据目录（`SYMKIT_DATA_DIR` 或 platformdirs 默认值）：种子公式只读打包在包内，`formula_add` 添加的用户公式进入可写覆盖层并按 id 覆盖种子，会话产物写入其中的 `derived/`。

## 目录结构

```text
formulas/
├── library/            ← 基础公式（手动编辑的 YAML，一个文件一条公式）
│   ├── README.md       ← 库条目字段说明
│   ├── fluid_dynamics/ ← 如 reynolds_number、ns_incompressible
│   ├── mechanics/      ← 如 newtons_second_law
│   └── thermodynamics/ ← 如 ideal_gas_law
└── derived/            ← 会话产物（session_complete 自动保存）
```

## `library/` — 基础公式

供 `formula_search` / `formula_get` 检索的 YAML 条目，每条使用稳定、可读的
id（`reynolds_number`、`ideal_gas_law` …）。添加公式可直接编写 YAML 文件，
或调用 `formula_add` 工具。字段说明见
[`library/README.md`](library/README.md)。

## `derived/` — 推导成果

`session_complete(auto_save=True)` 的输出：经验证式推导流程创建的新公式，
按确定性 staging id 命名并按领域分目录存放。每个文件是一条
`DerivationResult` 记录：

| 字段 | 用途 |
| ---- | ---- |
| `id` / `name` | 会话 id（哈希）与推导名称 |
| `expression` | 最终 SymPy 表达式字符串 |
| `derived_from` | 所用基础公式的 id |
| `derivation_steps` | 步骤描述 |
| `verified` / `verification_method` | 验证状态 |
| `assumptions` / `limitations` | 适用范围约束 |
| `domain` / `category` | 分类标签 |

这些文件由 `DerivationRepository` 加载，供 `FormulaRecommender` 使用，使过去的推导成果可在未来会话中被推荐。

## 各类内容归属

| 内容 | 位置 |
| ---- | ---- |
| 教科书 / 基础公式（F=ma、Arrhenius …） | `library/` |
| 已验证的推导成果 | `derived/` |
| 标准物理常数（G、c、h …） | 不放这里 —— `formula_search(source="scipy")` |
| SymPy 已有的基础物理 | 不放这里 —— 直接用 SymPy |
| 临时 / 未验证的推导 | 不持久化 —— 保留在会话 JSON 中 |