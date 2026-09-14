#!/usr/bin/env bash
# 同 run_task.sh，但注入真实 Lean 安装（Lean 认证卡专用）：
# SYMKIT_DATA_DIR 指向用户安装目录（含就绪戳的 lean-workspace），ELAN_HOME 指向 elan。
# 路径是维护者环境（D:/Code/Mathlib）；没有这套安装时先跑 symkit-lean-setup，
# 或把两个变量改指 lab 自己的安装根。前提: <root>/data/lean-workspace/.symkit-lean-ready 存在。
set -euo pipefail
TASK_FILE="$1"
RUN_ID="$2"
MAX_TURNS="${3:-60}"
LEAN_ROOT="${LEAN_ROOT:-D:/Code/Mathlib}"
WINPWD="$(pwd -W 2>/dev/null || pwd)"
mkdir -p "runs/$RUN_ID"
MCP_JSON="$(pwd)/runs/$RUN_ID/.mcp.json"
cat > "$MCP_JSON" <<EOFX
{
  "mcpServers": {
    "symkit": {
      "command": "$WINPWD/.venv/Scripts/symkit-mcp.exe",
      "args": [],
      "env": {
        "SYMKIT_DATA_DIR": "$LEAN_ROOT/data",
        "ELAN_HOME": "$LEAN_ROOT/elan"
      }
    }
  }
}
EOFX
claude -p "$(cat "$TASK_FILE")" \
  --output-format stream-json --verbose \
  --mcp-config "$MCP_JSON" --strict-mcp-config \
  --permission-mode bypassPermissions \
  --max-turns "$MAX_TURNS" \
  > "runs/$RUN_ID/stream.jsonl" 2> "runs/$RUN_ID/stderr.log"
echo "done -> runs/$RUN_ID/stream.jsonl"