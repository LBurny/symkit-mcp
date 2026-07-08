# 子法：Git 工作流规范

> 父法：CONSTITUTION.md 第三章

## 第 1 条：提交前检查清单

依序运行以下步骤：

| 顺序 | 项目 | 说明 | 可跳过 |
|------|------|------|--------|
| 1 | 运行测试 | `uv run pytest` | ❌ |
| 2 | Lint 检查 | `uv run ruff check src/ tests/` | ❌ |
| 3 | 类型检查 | `uv run mypy src/` | ❌ |
| 4 | README 更新 | 如用户可见行为变更 | ✅ |
| 5 | CHANGELOG 更新 | 如版本或功能变更 | ✅ |
| 6 | ROADMAP 标记 | 如进度推进 | ✅ |

## 第 2 条：Commit Message 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型
- `feat`: 新功能
- `fix`: 修复
- `docs`: 文档
- `refactor`: 重构
- `test`: 测试
- `chore`: 杂项

## 第 3 条：分支策略

| 分支 | 用途 | 保护 |
|------|------|------|
| `main` | 稳定版本 | ✅ |
| `develop` | 开发集成 | ✅ |
| `feature/*` | 功能开发 | ❌ |
| `hotfix/*` | 紧急修复 | ❌ |
