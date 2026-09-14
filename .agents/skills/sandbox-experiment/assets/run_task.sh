#!/usr/bin/env bash
# 用法: bash run_task.sh tasks/<task>.md <run-id> <data-dir> [max-turns]
# 在本目录（黑箱）下用 Claude Code 无头模式执行一个测试任务。
# 每条 lane 用独立 data-dir（SYMKIT_DATA_DIR 隔离），支持多 lane 并行。
# 产物: runs/<run-id>/stream.jsonl (完整事件流), stderr.log
# 会话 JSON 落在用户 AppData，不理会 CWD；需要留证时手动拷回 runs/<run-id>/。
set -euo pipefail
TASK_FILE="$1"
RUN_ID="$2"
DATA_DIR="$3"
MAX_TURNS="${4:-50}"
WINPWD="$(pwd -W 2>/dev/null || pwd)"
mkdir -p "runs/$RUN_ID" "$DATA_DIR"
MCP_JSON="$(pwd)/runs/$RUN_ID/.mcp.json"
cat > "$MCP_JSON" <<EOF
{
  "mcpServers": {
    "symkit": {
      "command": "$WINPWD/.venv/Scripts/symkit-mcp.exe",
      "args": [],
      "env": {
        "SYMKIT_DATA_DIR": "$WINPWD/$DATA_DIR"
      }
    }
  }
}
EOF
claude -p "$(cat "$TASK_FILE")" \
  --output-format stream-json --verbose \
  --mcp-config "$MCP_JSON" --strict-mcp-config \
  --permission-mode bypassPermissions \
  --max-turns "$MAX_TURNS" \
  > "runs/$RUN_ID/stream.jsonl" 2> "runs/$RUN_ID/stderr.log"
echo "done -> runs/$RUN_ID/stream.jsonl"