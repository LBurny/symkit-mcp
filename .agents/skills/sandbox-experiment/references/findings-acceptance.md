# 第 5–6 步：缺陷分析修复、验收闭环、收尾

## 第 5 步：缺陷分析修复

### 核验文化（先于修复）

- 操作员 findings 里的每个指控，主控**独立复现后才进缺陷清单**；复现不出或与文档/源码矛盾的，在报告里写"驳回 + 证据"。历史驳回样例：`session_complete` 其实带 `similar_to`；promote 并没有丢 units；"矩阵崩溃是先验存在"实为上一波修复引入。
- 同时核验修复代理的汇报：对照原始产物（测试输出、探针输出），不认转述。
- 缺陷清单格式（放 lab `runs/_analysis/` 或 findings 汇总）：编号 / 来源卡 / 一句话现象 / 复现探针文件 / 根因 / 修法 / 状态（fixed|reported-not-fixed）。

### 修复纪律

1. **TDD**：先把探针行为固化成仓库回归测试（RED），再修（GREEN）。每轮净增测试数十至上百。
2. **修"启发式"先搜全仓副本**：同源缺陷曾在两处实现各犯一次（库 API 路径修了，MCP 用的 `StepVerifier` 漏了）。
3. **改一处语义查所有出口**：`session_show.latex` 与 `session_complete.final_expression` 曾对"最终表达式"给出不同答案，4/5 卡都报。
4. **冻结文件净零行**：`formula.py`、`orchestration.py`、`expression_parser.py` 等顶格文件只能压缩回原行数内改，配套行为用测试锁。跑 `uv run python scripts/check_modularity.py --report` 确认棘轮不破。
5. **跨代理共享枚举/字面量集合 grep 全仓**：给 `OperationType` 加新成员后，`ELIGIBLE_OPERATIONS` 之类关键字面量集合曾漏加，症状是探针计数从 3 变 2——数字漂移是唯一信号。
6. **主控定语义红线**：如"建模公理不得判 failed"、"判定永不改写只上报 discrepancy"——写进派工契约，不留代理自由发挥。
7. **文件所有权互不相交**：并行修复代理的文件集预先写死；共享契约文件（如 lean_types.py）由主控预写；CHANGELOG/README 等公共文档留到最后主控统一改，防并行冲突。

## 第 6 步：验收闭环

修复全部落地后，按序：

```bash
# 1. 仓库四门禁（主控亲自跑）
uv run pytest                 # 全量
uv run ruff check src/ tests/ scripts/
uv run mypy src/ scripts/
uv run python scripts/check_modularity.py --report

# 2. 用最终代码重建 wheel，force-reinstall 进 lab venv（同版本号必须 force）
cd /i/Formulation/example/symkit-mcp-master
uv build --out-dir /i/Formulation/example/symkit-mcp-test-rNN/dist
cd /i/Formulation/example/symkit-mcp-test-rNN
uv pip install --python .venv/Scripts/python.exe --force-reinstall --no-deps dist/symkit_mcp-*.whl

# 3. 探针全绿
.venv/Scripts/python.exe probe/smoke.py
.venv/Scripts/python.exe probe/regress.py   # 退出码 0
.venv/Scripts/python.exe probe/lean_real.py # Lean 卡受影响时

# 4. 失败卡重跑（旧 findings 先备份，run-id 换新）
mv findings findings_rNNa && mkdir findings
RUN_PREFIX=rNN bash run_suite.sh data/<lane> <n> <n>
.venv/Scripts/python.exe analyze.py rNN
```

- **重跑验收卡用新 run-id**（旧 findings 整目录备份到 `findings_rNNa/`）——**新前缀必须避开本轮所有 lane 前缀**：lane 划分常用 `rNNa/rNNb/rNNc`，而"重跑用 rNNb"的示例恰好会与 lane B 撞名（r20 实际事故：`runs/r20b-task-10/stream.jsonl` 原始产物被重跑覆盖，仅 findings 备份幸免）。用不冲突的词（如 `rNNv` / `rNNacc`）。新旧产物可比对，不许覆盖。
- 验收报告写 `runs/_analysis/ACCEPTANCE.md`：探针结果、重跑卡结果、对操作员指控的独立复核结论（哪些坐实、哪些驳回）、遗留 reported-not-fixed 清单及优先级。
- 白盒佐证（支撑 CHANGELOG 量化断言的 sweep 脚本与基线指纹）移到 `runs/_analysis/whitebox/` 留存——一次性 scratch 删掉，可复现的 harness 留下。

### 文档同步（用户可见行为变了就必须做）

- `CHANGELOG.md`：本轮版本条目（缺陷修复按严重度列，量化断言要有 whitebox 佐证）。
- `README.md` / `README.zh-CN.md` / `docs/symkit-design*.md`：工具数、类目数、测试数同步（**5 份对外文档中英同步**）。
- `docs/recommended-system-prompt.md`：本轮若动了工具语义、输入解析、保留名或判定口径，逐条核对该文档里的断言是否仍然成立——它是给真客户端的引导，说错会让客户端按错的方式调工具（如把 `f(x)` 当乘积、把 `E` 当自然常数）。提示词自身要改时保持"文件即提示词"体例（无标题/前言/分隔线）。
- 版本号与发布流程按既有惯例（tag push → OIDC 发 PyPI；`pypi.org/pypi/<pkg>/json` 是 CDN 缓存的，验发布看版本专属 URL）。

## 收尾：知识沉淀与清理

原则：**删重物、留知识**。

- 知识先落地：缺陷清单 + 方法学新教训写进记忆文件；对外结论进 CHANGELOG/文档。
- 然后清理 lab：`runs/*/stream.jsonl`、`.venv/`、`dist/`、`data/` 是重物；`findings/`、`probe/`（含 audit 复现）、`runs/_analysis/`（验收报告 + whitebox）是知识。整轮知识提炼完、下轮不再引用时，整个 lab 目录可删。
- 若本轮开了新的试验卡风格或 harness 改进（如新的护栏话术、参数化前缀），回流进本 skill 的 assets/，让下一轮直接受益。