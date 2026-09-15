---
name: sandbox-experiment
description: symkit-mcp 黑箱沙箱试验全流程（八轮实战沉淀）：搭建隔离 lab 实验台 → 写试验卡 → 无头 Claude 多 lane 运行 → 确定性探针复现 → 缺陷分析修复 → 验收闭环。只要用户提到沙箱试验/沙箱轮/黑箱测试/实验台/lab/试验卡/复现探针/验收，或想黑箱验证 symkit-mcp 某个版本或某批修复——即使没说"沙箱"二字（例如"跑一轮试试""搭个实验台""这版修好了再验一遍""复现这个缺陷"）——都使用本 skill。
---

# symkit-mcp 沙箱试验（黑箱轮）操作手册

黑箱原则：symkit-mcp 只通过它的 MCP 工具接口被评测。操作员（无头 Claude）和探针（stdio MCP client）从不读源码；源码侧的工作（根因、修复）由主控和修复代理在仓库里做。观察到的摩擦驱动框架改进——1.5.0→1.7.0 的八轮实战都是这条闭环跑出来的。

## 六步闭环

| 步骤 | 关键产物 | 详参 |
|---|---|---|
| 0. 决策：轮型 / 目标 wheel / lane 划分 | 卡片清单 | [lab-setup.md](references/lab-setup.md) |
| 1. 搭实验台 | `symkit-mcp-test-rNN/`（venv + wheel + smoke 全绿） | [lab-setup.md](references/lab-setup.md) |
| 2. 写试验卡 | `tasks/task-NN-*.md` | [lab-setup.md](references/lab-setup.md) |
| 3. 跑卡 | `runs/<run-id>/stream.jsonl` + `findings/task-NN.md` | [probes.md](references/probes.md) |
| 4. 探针复现 | `probe/audit*.py`：每个缺陷坐实或驳回 | [probes.md](references/probes.md) |
| 5. 缺陷分析修复 | 仓库内 TDD 修复 + 回归测试 | [findings-acceptance.md](references/findings-acceptance.md) |
| 6. 验收闭环 | 重装 wheel + 探针/失败卡重跑 + 四门禁 + 文档同步 | [findings-acceptance.md](references/findings-acceptance.md) |

lab 目录布局（模板见 [assets/](assets/)）：

```
symkit-mcp-test-rNN/
├── .venv/                  # lab 自己的解释器（wheel 装在这里）
├── dist/                   # 本轮被测 wheel
├── data/<lane>/            # 每条 lane 独立 SYMKIT_DATA_DIR
├── .mcp.json → runs/<run-id>/.mcp.json   # run_task.sh 每 run 生成，勿手写
├── tasks/task-NN-*.md      # 试验卡
├── runs/<run-id>/          # stream.jsonl / stderr.log / 拷回的会话 JSON
├── findings/task-NN.md     # 操作员逐卡报告
├── findings_rNNa/          # 重跑验收时备份的旧 findings
├── probe/                  # smoke.py / regress.py / audit*.py / lean_real.py
├── analyze.py              # stream.jsonl 汇总表
├── run_task.sh / run_suite.sh / run_task_lean.sh
└── runs/_analysis/         # ACCEPTANCE.md / suite-summary.json / 白盒证据
```

## 角色分工

- **主控**（你）：定轮型与卡片、跑探针坐实根因后再派工、写死接口契约与互不相交的文件所有权、验收时亲自审 diff + 跑全量门禁。设计决策（根因、修法方向、语义红线）主控做完，代理只实现。
- **操作员**（无头 Claude，每 lane 一个）：只拿试验卡黑箱操作，产物写 findings/。
- **修复代理**：单 Wave 内 TDD 实现，聚焦测试（`--no-cov -p no:cacheprovider`），越界需求停下报告。
- **并行上限 3 条 lane / 3 个子代理**；子代理 Bash 上限 600 秒 → 必须 run_in_background + 轮询。

## 硬规则（八轮踩坑换来的，先读）

1. **卡片里的产物路径是本 lab 的绝对路径**。克隆/复用旧 lab 素材时先全量重指向——曾发生操作员把报告写进旧 lab、还把整个目录改了名。
2. **纪律检查只防"读源码目录"，不防"写沙箱外"**。"禁写沙箱外"必须在卡片里明令（模板已含）。
3. **`math` 的成功响应不含验证结论**。判定必须看 `session_verify_step` / `session_verify_session` 的 verdict。
4. **诊断缺陷必须打真实 MCP 服务器进程**（stdio 探针）。禁止从仓库 cwd 直接 import 包诊断——组合根只见 data dir 内公式，会得出假缺陷。
5. **探针脚本里一个 early `return` 会让后续探针整组静默跳过**，而跑探针的代理会把没跑的报成 PASS——逐条对照原始输出核验。
6. **不认操作员/子代理的口头汇报**。验收逐条对照 stream.jsonl / 会话 JSON 原始产物；历史上多次驳回假指控。
7. **同版本号 wheel 重装必须 `--force-reinstall --no-deps`**。
8. **analyze.py / run_suite.sh 的 run-id 前缀每轮不同**。assets 已参数化（`RUN_PREFIX` 环境变量 / argv），建 lab 时设好。
9. **卡死的运行杀整棵进程树**：`taskkill /PID <pid> /T /F`。真干活的是 CPU 最高的最内层 python.exe（stub .exe → venv python → anaconda python 三层链）；Agent 被取消后 claude.exe 孤儿树会存活。
10. **回归类检查不交给模糊需求卡**——模糊卡管 UX/发现性，确定性断言走主控亲写预期值的 regress 探针。
11. **大计算护栏写进卡**：大 n 禁显式分数链、单表达式 ≤200 显式加项（曾因 lcm(1..10⁶) 单卡跑 32 分钟 / 4.5GB）。
12. **改一处语义要查全部出口**（如"最终表达式"有 session_show 与 session_complete 两处）和**全部同源副本**（一个启发式可能在多处实现）。
13. **推荐系统提示词是被交付面，不是背景资料**。给真客户端的规范引导在仓库 `docs/recommended-system-prompt.md`（体例即提示词本身：无标题、无前言、无分隔线）。跑卡时用 `SYSTEM_PROMPT_FILE=<lab 内副本绝对路径> bash run_suite.sh ...`，它经 `--append-system-prompt-file` 整份追加到 harness 默认提示之后——追加而非替换，替换会连带丢掉 harness 自己的工具说明。不设这个变量，操作员跑的是 harness 默认提示词，测不到交付给用户的引导。该文档里每条断言（`f(x)` 解析为未定义函数、`E`/`I` 保留为普通符号、`pi`/`oo` 才是常量、会话链与 `assume` 口径）都能被黑箱证伪：同一张卡注入与不注入各跑一次，两次都错是引擎缺陷，只有不注入时错则是提示词没交代清。

## 各步要点（细节在 references）

**第 1–2 步（搭台 + 写卡）**：master 构建本轮 wheel（`uv build --out-dir <lab>/dist`，不受运行中 exe 锁影响）→ lab 建独立 venv 装 wheel（官方索引，阿里镜像滞后）→ `probe/smoke.py` 确认服务器可用 + 工具数吻合再花钱。试验卡用原始用户口径写需求，纪律段落照模板，重计算卡加护栏。→ [lab-setup.md](references/lab-setup.md)

**第 3–4 步（跑卡 + 探针）**：`run_task.sh <task> <run-id> <data-dir> [turns]` 单卡；`RUN_PREFIX=<rr> bash run_suite.sh <data-dir> <start> <end>` 按 lane 串行，≤3 lane 并行各用独立 data-dir。客户端引导经 `SYSTEM_PROMPT_FILE` 注入（硬规则 13），不设即 harness 默认提示词。跑完 `analyze.py` 出汇总表（注意客户端噪声虚增计数）。缺陷用 stdio 探针 `probe/audit*.py` 坐实，先重放操作员指控再定根因。→ [probes.md](references/probes.md)

**第 5–6 步（修复 + 验收）**：每个 agent 指控先独立复现（历史驳回率不低），TDD 修复；冻结文件净零行改动。修完重建 wheel force-reinstall 进 lab venv，探针全绿 + 失败卡换新 run-id 重跑（旧 findings 先备份），主控跑四门禁（pytest / ruff / mypy / modularity），CHANGELOG / README / docs 计数 / 记忆同步。→ [findings-acceptance.md](references/findings-acceptance.md)

**收尾**：知识沉淀（缺陷清单 + 方法学教训进记忆/文档），重物清理（runs/stream.jsonl、.venv、dist、data 可删；findings / 探针 / 验收报告保留或提炼后整 lab 删除）。