# SymKit 公式库

`formulas/` 下有两个独立集合，用途和文件格式各不相同。

🌐 [English](README.md) | **简体中文**

## 📁 目录结构

```text
formulas/
├── library/               ← 基础公式库（手动编辑的 YAML）
│   ├── README.md          ← 库条目字段说明
│   ├── fluid_dynamics/    ← 如 reynolds_number、ns_incompressible
│   ├── mechanics/         ← 如 newtons_second_law
│   └── thermodynamics/    ← 如 ideal_gas_law
└── derived/               ← 推导成果（session_complete 自动保存）
    ├── fluid_dynamics/    ← 流体领域的已验证推导
    ├── general/
    └── mechanics/
```

## 📚 `library/` — 基础公式库

可手动编辑的 YAML 条目，供 `formula_search` / `formula_get` MCP 工具
检索。每个文件是一个公式，使用稳定、可读的 id
（`reynolds_number`、`ideal_gas_law` …）。

添加公式的方式：

1. 直接编写 YAML 文件，或
2. 调用 `formula_add` MCP 工具。

字段说明见 [`library/README.md`](library/README.md)。

## 🔨 `derived/` — 推导成果

`session_complete` 的输出：通过 SymKit 验证式符号推导流程创建的新公式。
文件按会话 id（短哈希）命名，按领域分目录存放。

每个 YAML 文件是一条 `DerivationResult` 记录，包含：

| 字段 | 用途 |
| ---- | ---- |
| `id` | 会话 id（哈希） |
| `name` | 推导名称 |
| `expression` | 最终 SymPy 表达式字符串 |
| `derived_from` | 所用基础公式的 id |
| `derivation_steps` | 步骤描述 |
| `verified` / `verification_method` | 验证状态 |
| `assumptions` / `limitations` | 适用范围约束 |
| `domain` / `category` | 分类标签 |

这些文件由 `DerivationRepository` 加载，供 `FormulaRecommender` 使用，
使过去的推导成果可以在未来会话中被推荐。

## ✅ 各类内容归属

| 内容 | 位置 |
| ---- | ---- |
| 教科书 / 基础公式（F=ma、Arrhenius…） | `library/` |
| 物理常数 | SciPy 常数（`formula_search(source="scipy")`） |
| 已验证的推导成果 | `derived/` |

## ❌ 不应放在这里的内容

| 类型 | 替代位置 |
| ---- | ------- |
| SymPy 已有的基础物理 | 直接用 SymPy |
| 标准常数（G、c、h…） | `formula_search(source="scipy")` |
| 临时 / 未验证的推导 | 保留在会话 JSON 中，不持久化到此 |
