# Roadmap / 路线图

SymKit project roadmap and feature planning.
SymKit 项目路线图与功能规划。

---

## ✅ Completed / 已完成

### v1.0.1 (Current / 当前版本)

- Unified math entry `math()` covering calculus, linear algebra, ODE, Laplace/Fourier transforms, and ~25 other operations.
  统一数学入口 `math()`，覆盖微积分、线性代数、ODE、Laplace/Fourier 变换等 ~25 种操作。
- Step-by-step derivation sessions with start, continue, rollback, complete, record step, and verify step.
  步进式推导会话，支持开始、继续、回滚、完成、记录步骤、验证步骤。
- Symbol assumption management: register, query, conflict detection, and per-step isolation.
  符号假设管理：假设注册、查询、冲突检测、按步骤隔离。
- External formula search: Wikidata, SciPy constants, BioModels.
  外部公式搜索：Wikidata、SciPy 常数、BioModels。
- Symbol registry: domain-specific notation, conflict detection, and per-domain listing.
  符号注册表：管理领域符号、检测冲突、按域列举。
- Code/report generation: Python functions, LaTeX derivation, Markdown reports, SymPy scripts.
  代码/报告生成：Python 函数、LaTeX 推导、Markdown 报告、SymPy 脚本。
- High-level derivation orchestration: `derive`, `intent_execute`, pattern listing, tool recommendations.
  高层推导编排：`derive`、`intent_execute`、模式列表、工具推荐。
- **41 MCP tools** with DDD-layered architecture; the core library can be used independently.
  **41 个 MCP 工具**，DDD 分层架构，核心库可独立使用。
- Python requirement lowered to 3.10+ for broader installation compatibility.
  Python 版本要求已降至 3.10+，提升安装兼容性。

---

## 🚧 In Progress / 进行中

- Documentation cleanup and clearer project positioning (general-purpose formula derivation, not domain-specific).
  文档整理与项目定位清晰化（通用公式推导，非特定领域）。
- Derivation example library expansion: cross-domain cases in physics, engineering, chemistry, biology, etc.
  推导示例库扩展：物理、工程、化学、生物等跨领域案例。
- Tool usage examples and best-practice additions.
  工具使用示例与最佳实践补充。

---

## 📋 Planned / 计划中

### v0.3.0 - Derivation Experience Enhancement / 推导体验增强

- **Auto-verification**: automatically run dimensional checks and boundary-condition validation after each step.
  自动验证：每步完成后自动运行维度检查、边界条件验证。
- **Derivation suggestions**: proactively suggest next steps or related formulas based on the current state.
  推导建议：基于当前步骤主动建议下一步操作或相关公式。
- **Symbol semantic tracking**: distinguish the meaning of symbols with the same name in different contexts.
  符号语义追踪：区分同名符号在不同上下文中的含义。
- **Error-pattern detection**: warnings for dimensional errors, undefined symbols, and assumption conflicts.
  错误模式检测：量纲错误、未定义符号、假设冲突预警。

### v0.4.0 - Ecosystem & Extensions / 生态与扩展

- More external formula-source adapters (e.g., Wolfram Alpha, MathWorld).
  更多外部公式源适配器（如 Wolfram Alpha、MathWorld）。
- Extended export formats for derivation results (Julia, R, MATLAB).
  推导结果导出格式扩展（Julia、R、MATLAB）。
- Formula version control and diff comparison.
  公式版本控制与差异比较。
- Richer cross-domain example library.
  更丰富的跨领域示例库。

### Infrastructure / 基础设施

- GitHub Actions CI/CD (tests, lint, type checks).
  GitHub Actions CI/CD（测试、lint、类型检查）。
- Automated PyPI release.
  发布自动化到 PyPI。
- More complete API documentation and interactive tutorials.
  更完整的 API 文档与交互式教程。

---

## Long-term Goals / 长期目标

- Become the standard derivation layer between the SymPy ecosystem and the MCP protocol.
  成为 SymPy 生态与 MCP 协议之间的标准推导层。
- Support multi-agent collaborative derivation (multi-user / multi-agent sessions).
  支持多 Agent 协作推导（多人/多 Agent 会话）。
- Contribute general capabilities upstream to SymPy.
  向 SymPy 上游贡献通用能力。
