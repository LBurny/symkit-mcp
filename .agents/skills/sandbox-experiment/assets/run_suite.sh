#!/usr/bin/env bash
# 用法: RUN_PREFIX=rNN bash run_suite.sh <data-dir> [start] [end] [max-turns]
# 例: RUN_PREFIX=r17 bash run_suite.sh data/pure 1 6     # PURE lane 跑 task-01..06
# run-id 前缀必须每轮换（默认 r16 只是占位），analyze.py 用同一前缀汇总。
# SYSTEM_PROMPT_FILE 等环境变量照常透传给 run_task.sh（注入推荐系统提示词时在此 export）。
set -uo pipefail
cd "$(dirname "$0")"
DATA_DIR="${1:?usage: RUN_PREFIX=rNN run_suite.sh <data-dir> [start] [end] [max-turns]}"
START="${2:-1}"
END="${3:-9}"
MAX_TURNS="${4:-50}"
RUN_PREFIX="${RUN_PREFIX:?set RUN_PREFIX=rNN (unique per round)}"
for n in $(seq -f "%02g" "$START" "$END"); do
  task=$(ls tasks/task-${n}-*.md 2>/dev/null | head -1)
  [ -z "$task" ] && { echo "skip $n (no card)"; continue; }
  run="${RUN_PREFIX}-task-${n}"
  echo "=== $(date +%H:%M:%S) $task -> runs/$run (data: $DATA_DIR) ==="
  bash run_task.sh "$task" "$run" "$DATA_DIR" "$MAX_TURNS" || echo "RUN FAILED: $task"
done
echo "suite done ($DATA_DIR)"