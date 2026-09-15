# 第 3–4 步：跑卡、汇总、探针复现

## 第 3 步：跑卡

```bash
# 单卡
bash run_task.sh tasks/task-16-*.md r16-task-16 data/verify 50

# 整条 lane 串行（RUN_PREFIX 决定 run-id 前缀）
RUN_PREFIX=r16 bash run_suite.sh data/pure 1 6        # task-01..06 → runs/r16-task-01..06

# Lean lane（走真实 Lean 安装，独立脚本）
bash run_task_lean.sh tasks/task-15-*.md r16-task-15 60
```

- `run_task.sh <task> <run-id> <data-dir> [max-turns]`：无头 Claude（`claude -p`，stream-json、`--strict-mcp-config`、bypassPermissions），`.mcp.json` 按 run 生成并注入该 lane 的 `SYMKIT_DATA_DIR`。
- 多 lane 并行：开多个终端各跑一条 `run_suite.sh`，data-dir 互不相同。**并行 ≤3**。
- **系统提示词注入**：`SYSTEM_PROMPT_FILE=<lab 内副本>` 对单卡、lane、Lean 三个 runner 都生效（`run_suite.sh` 靠环境变量透传）。A/B 用法：同一张卡注入与不注入各跑一次（run-id 加 `-p` / `-nop` 后缀），两次都错才是引擎缺陷，只有不注入时错说明是提示词没交代清——归因结论回写 `docs/recommended-system-prompt.md`（硬规则 13）。
- 产物：`runs/<run-id>/stream.jsonl`（完整事件流）、`stderr.log`。**会话 JSON 落在用户 AppData，不理会 CWD**——需要留证时从 `%LOCALAPPDATA%\symkit\symkit\derivation_sessions\` 拷回 `runs/<run-id>/`。
- 监控：`wc -l runs/*/stream.jsonl` 看进度；单卡超 10 分钟查 CPU——卡死的真身是最内层 python.exe（stub .exe → venv python → anaconda python 三层链里 CPU 最高的那个）。杀树：`taskkill /PID <pid> /T /F`；Agent 被取消后 `claude.exe` 孤儿树会存活，也要杀。
- **`claude` 的进程名是 `node.exe`**（npx shim），`tasklist | grep -i claude` 在三条 lane 全忙时也会返回 0——别据此判断"跑完了"。判断卡死看 `stream.jsonl` 尾部的 `tool_progress` 心跳（`"elapsed_time_seconds"`）：单个 `math` 调用涨到几百秒就是楔死（r17：order=4 的 diff 卡了 15 分钟，`tasklist` 里只看得到 node.exe 与 python.exe）。孤儿 MCP 服务器会锁 lab 的 `.venv/Scripts/symkit-mcp.exe`，`uv pip install --force-reinstall` 报 `os error 32` 时先按可执行路径筛进程并杀掉。
- 超长单卡的处理不是干等：先评估是否触发了卡片护栏遗漏（如显式分数链），kill 后给卡加护栏换 run-id 重跑。
- **验收重跑自己的卡本身就是缺陷来源**：r17 的 P0 楔死是重跑 task-01 时才出现的（同一表达式 `session=False` 0.06s、`session=True` 无限），任何探针都没覆盖到——验收轮必须真的重跑受影响的卡，不能只跑确定性探针。

### 汇总（analyze.py）

```bash
.venv/Scripts/python.exe analyze.py r16        # argv = run-id 前缀
```

输出表：每 run 的 verdict（SUCCESS/ERROR/INCOMPLETE/NO-STREAM）、turns、MCP vs non-MCP 调用数、err、`success:false` 计数、纪律（FORBIDDEN 目录字符串命中）、成本；外加 tool_use 明细与 result 尾巴，JSON 落 `runs/_analysis/suite-summary.json`。

**读数注意（历史虚增教训）**：
- 客户端侧 Read/Edit 错误会被计进 mcp_errors（tool_result is_error 不分 MCP/非 MCP）；
- Read 回显里包含 `"success": false` 子串会重复计数；
- 纪律检查匹配 FORBIDDEN 字符串（`symkit-mcp-master`/`nsforge-mcp-sigma`）出现在**任何**工具入参中——读到 VIOLATION 先看 payload 是真读了源码还是无害引用。
数字异常时回到 stream.jsonl 人工剔除客户端噪声，别直接进报告。

## 第 4 步：探针复现

探针是 stdio MCP client 脚本（`mcp.client.stdio` 驱动 lab venv 里的 `symkit-mcp.exe`），输出存 `probe/*-out.txt`。三类：

1. **smoke**（[assets/probe_smoke.py](../assets/probe_smoke.py)）：建 lab 后、花钱前必跑。列工具数、关键工具在位。
2. **regress**：确定性断言 lane，**主控亲写预期值**，每轮针对本轮风险面重写（历史缺陷回归、判定语义、治理、certify 降级路径、探针退出码）。15 条左右。不交给模糊卡，也不让子代理改预期值——只跑 + 照录。
3. **audit\***：单个缺陷的复现脚本（audit.py、audit2.py…递增），一个缺陷一个最小复现，附对照实验。

**验证轮专用**（被测的是确定性契约，如一轮修复的进程/环境/报告语义）：模糊卡压不出结论，改用两层——
（a）主控亲写预期值的确定性探针（模板 [assets/probe_lean_regress.py](../assets/probe_lean_regress.py)：每个 check 独立、异常记为 FAIL 不中断后续，覆盖 trivial 分桶 / certify 时 assumptions / toolchain 守卫 / 健康安装仍认证）；
（b）1–2 张无头操作员卡压 UX 发现性与"报告里到底证明了什么"（先例：lab `symkit-mcp-test-lean` 的 task-01/02）。
对"MCP 输出看不出来"的契约（如超时是否留孤儿进程），黑箱只验可见摘要（`summary.unproven==1` + `detail=="timeout"`），进程级断言放到 lab venv 内直调 shipped helper（`import symkit.infrastructure.lean_process`）——**用 wheel 里的代码，不是仓库 cwd**，两层合起来才既可信又便宜。

写探针的要点（范例见 [assets/probe_lean_real.py](../assets/probe_lean_real.py) 的 call/main 结构）：

- 用 `StdioServerParameters` + `ClientSession`，`env` 里显式注入 `SYMKIT_DATA_DIR`（要打外部安装时再注入 `ELAN_HOME`）。
- 支持 `SYMKIT_MCP_EXE` 环境变量覆写 exe 路径，让未发布构建走真实 stdio 接口。
- `math` 的成功响应**不含 verdict**——判定看 `session_verify_step {step_number}` 或 `session_verify_session`。
- 步骤级真相在 `data/derivation_sessions/session_<id>.json`（`operation` / `output_expression` / `input_srepr` / `verification_result`），操作员可直接读来核对工具改名、笔记继承这类元数据行为。
- 仓库里有 `scripts/lean_oracle.py`：对持久化会话批量重跑 Lean 认证，疑似验证器假阴性上 exit 1——黑箱轮用它审计 StepVerifier。

### 诊断铁律

1. **打真实服务器进程**。从仓库 cwd 直接 `import symkit` 诊断是假象：组合根只见 data dir 内公式，种子走 wheel 包资源由服务器进程解析——`catalog.get(...)=None`、数量偏少都是诊断假缺陷。
2. **对照实验确认触发条件**：换简单符号、去掉假设、换键拼法各跑一遍，才能说清缺陷边界（例：复合键代换假阴性只在"两路径解析不一致"的字面量上触发）。
3. **先重放 agent 指控**：按提示写法直接跑一遍——历史上"ics 语法不可用"照文档写法直接成功，是归因错误。
4. **early return 会静默跳过后续探针**：脚本里每个分支都要么继续跑要么 exit 非 0；跑探针的人（含子代理）汇报 PASS 前逐条对照原始输出。
5. **操作员自述只当线索**：其"纯黑箱/未执行 shell"的自称可能与 stream 里的 Bash 调用矛盾——核验看 stream.jsonl，不看自述。
6. Lean 通道的降级路径也是探针对象：无 Lean 环境时 `lean_available: false` + 安装指引、其余 44 工具照常。
7. **定位"挂住的调用"按 heartbeat 的 `parent_tool_use_id` 反查**，不要取 stream 里最后一个 `tool_use`——tool_use 块在调用返回前就落盘，两者常常不是同一个调用。r18 有一次按"最后一个"归因，写出来的探针（对那个表达式 6 种变体全 0.03–0.9 s）当场把自己的结论驳回。
8. **单会话内无法给"不返回的调用"设时限**：楔死类契约写成 per-case 子进程 + 硬 cap + 两侧对照的独立探针（`audit3`/`audit6`/`audit11` 模板），不要放进 regress 电池——asyncio 层没有超时，电池会被永久挂住，kill 子进程还可能留下孤儿服务器占满 CPU。