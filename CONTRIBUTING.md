# 贡献指南

感谢你有兴趣为此项目做出贡献！

## 如何贡献

### 回报问题 (Bug Report)

1. 先搜索现有 Issues，确认问题未被回报
2. 使用 Issue 模板提交问题
3. 提供清晰的重现步骤

### 功能建议 (Feature Request)

1. 先搜索现有 Issues
2. 描述功能的使用场景
3. 说明期望的行为

### 提交代码 (Pull Request)

#### 开发流程

1. Fork 此项目
2. 创建功能分支：`git checkout -b feature/your-feature`
3. 遵循项目架构（参见 `CONSTITUTION.md`）
4. 提交变更：`git commit -m 'feat: add your feature'`
5. 推送分支：`git push origin feature/your-feature`
6. 创建 Pull Request

#### Commit 消息格式

遵循 Conventional Commits：

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型：
- `feat`: 新功能
- `fix`: 修复
- `docs`: 文档
- `refactor`: 重构
- `test`: 测试
- `chore`: 杂项

#### 代码规范

- 遵循 DDD 架构（参见 `.github/bylaws/ddd-architecture.md`）
- DAL 必须独立
- 提交前更新相关文档

### 审查流程

1. 自动化检查通过
2. 至少一位维护者审查
3. 所有讨论已解决
4. 文档已更新

## 行为准则

请参阅 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## 问题？

如有任何问题，欢迎开 Issue 讨论！
