# 第 0–2 步：决策、搭实验台、写试验卡

## 第 0 步：决策

开跑之前主控定四件事：

1. **轮型**（决定卡片风格与探针重点；卡数和 lane 结构是独立决策——大轮（≈20 卡）把多种轮型混编进 lane，先例 r16：A 纯公式 6 卡 / B 理论 7 卡 / C 验证+Lean+对抗 7 卡）：
   - **纯公式轮**——只做符号推导，不带物理情境，压变换/级数/特殊函数/矩阵面。
   - **理论建模轮**——带物理情境的模糊需求句（vdW 临界点、RLC 阶跃、Lotka-Volterra…），压 UX/发现性。
   - **验证深水区轮**——压验证器判定语义、量纲、Lean 认证。
   - **对抗轮**——卡片里故意埋错（错符号、错条件），看验证器能否拦截。
   - **验证轮**——被测的是一批确定性修复契约（进程/环境/报告语义、判定口径）。模糊卡压不出结论，主体是主控亲写预期值的探针（见 [probes.md](probes.md) 的验证轮段与 `assets/probe_lean_regress.py`），操作员卡只留 1–2 张压 UX 发现性。先例：lab `symkit-mcp-test-lean`。
2. **目标 wheel**：
   - **HEAD 构建**（测未发布修复）：master 里 `uv build --out-dir <lab>/dist`。`uv build` 不受运行中服务器锁 `.venv\Scripts\symkit-mcp.exe` 影响（`uv run` 会，`uv build` 不会）。
   - **已发布版**（测 PyPI 版本）：装 `symkit-mcp==X.Y.Z` 时必须 `--default-index https://pypi.org/simple`——本机默认 pip 索引是阿里镜像，滞后官方数小时。
3. **lane 划分**：每 lane 5–7 卡串行，**并行 ≤3 条 lane**，每 lane 独立 `SYMKIT_DATA_DIR`（`data/pure`、`data/theory`、…）。Lean 认证卡例外：`run_task_lean.sh` 的 `SYMKIT_DATA_DIR` 指向 Lean 安装根（认证要访问 lean-workspace），不走 lab data-dir 隔离——刻意设计；该 lane 其余普通卡仍走 `run_task.sh` + lab data-dir。
4. **卡片清单**：主控亲写；确定哪张卡走 Lean lane（需真实 Lean 安装）。

## 第 1 步：搭实验台

在 `I:\Formulation\example\` 下建独立 lab（名字 `symkit-mcp-test-rNN` 或 `symkit-mcp-test-<主题>`）。命令序列（Git Bash，`uv` 不需要激活 venv）：

```bash
# 1. master 构建本轮 wheel（HEAD 轮；发布轮跳过）
cd /i/Formulation/example/symkit-mcp-master
uv build --out-dir /i/Formulation/example/symkit-mcp-test-rNN/dist

# 2. lab 建独立 venv 并装 wheel
cd /i/Formulation/example/symkit-mcp-test-rNN
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe --default-index https://pypi.org/simple "mcp<2" dist/symkit_mcp-*.whl
# 同版本号重装（验收轮）必须加 --force-reinstall --no-deps

# 3. 从 skill assets 拷入 harness，设定 run-id 前缀
cp <skill>/assets/{run_task.sh,run_suite.sh,run_task_lean.sh,analyze.py} .
mkdir -p probe tasks findings runs
cp <skill>/assets/probe_smoke.py probe/smoke.py
cp <skill>/assets/probe_lean_real.py probe/lean_real.py   # 有 Lean 认证卡时
export RUN_PREFIX=rNN   # run_suite.sh 用；analyze.py 用 argv

# 4. 花 AI 费用之前先确认服务器可用
.venv/Scripts/python.exe probe/smoke.py   # 期望: 工具数与当前版本一致 + session_certify present
```

- **HEAD 轮测的是当前工作区**（含未提交修复）——wheel 版本号仍是上一发布版（如 1.7.0）属正常，沙箱轮不做版本号 bump；因此重装一律 `--force-reinstall`（硬规则 7）。smoke 的工具数期望值以当前源码为准（1.7.0 = 45 仅为参照），lab README 里写清 wheel 实际版本与来源（工作区 HEAD 还是干净 tag）。
- `mcp<2` 是历史教训钉住的（pin 原因见 run-001 findings 记忆）。lab venv 装 symkit-mcp 时会带上 mcp，探针脚本用它的 client 端。
- `.mcp.json` **不要手写**——`run_task.sh` 每次运行在 `runs/<run-id>/.mcp.json` 生成，注入该 run 的 `SYMKIT_DATA_DIR`。`SYMKIT_DATA_DIR` 必须在服务器进程启动前生效（组合根 lru_cache）。
- `run_task_lean.sh` 硬编码维护者环境（`SYMKIT_DATA_DIR=D:/Code/Mathlib/data`、`ELAN_HOME=D:/Code/Mathlib/elan`）；没有这套安装就跳过 Lean lane，或先在 lab 里跑 `symkit-lean-setup` 并把两个变量改指 lab。
- lab 里写个 `README.md`：本轮目标、被测 wheel 版本/来源、lane 划分、卡片清单。
- stderr 里的 `unrecognized_model` 是无害的标题生成警告。

**克隆旧 lab 检查单**（如果复用旧 lab 而不是 assets）：tasks/ 里所有绝对路径重指向新 lab；probe 里 `EXE`/`DATA` 指向新 lab；analyze.py / run_suite.sh 的 run-id 前缀换掉。历史事故：漏改路径导致操作员写进旧 lab 并改名目录。

## 第 2 步：写试验卡

模板：[assets/task-template.md](../assets/task-template.md)。核心规则：

1. **需求用原始用户口径**：一到两句用户会说的话。模糊卡不列公式、不给可验证锚点、不指定步数——这是压"引擎在真实使用方式下的表现"。针对性验证卡可以展开 (a)(b)(c) 并加"特别观察"（历史缺陷复查，要求原样摘录）。
2. **纪律段落照模板逐字写**：禁读源码目录、禁读其他 lane 的 findings/runs、禁写沙箱外、所有符号数学必须走 MCP 工具禁止心算、同报错重试 ≤2。
3. **产物要求明确**：会话名（kebab-case）、每步完整 JSON 摘录（含 details/warning）、异常情形给原文、缺陷分类口径（CRASH/WRONG/SILENT/UX/OK）、报告写到 `<LAB绝对路径>\findings\task-NN.md`。
4. **长程回归卡保持逐字节一致**（传统：Spalart–Allmaras 五子目标卡 task-02），跨轮对比才有效。
5. **重计算卡加护栏**：大 n 禁显式分数链、单表达式 ≤200 显式加项、数值求和给上限（教训：n=10⁶ 调和数逐项分数链让 lcm 失控，单卡 32 分钟 4.5GB）。
6. **回归类检查不进模糊卡**——模糊卡会自由发挥甚至照录假 PASS；确定性断言一律进 regress 探针。
7. 卡片路径**必须是本 lab 绝对路径**。

卡片数量参考：综合轮 15–20 张（3 lane），专项轮 5–6 张。单卡预算 max-turns 50（Lean 卡 60），实际 2–8 分钟/卡，历史综合轮总成本 $10–60。