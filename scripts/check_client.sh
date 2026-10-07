#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT=$(cd "$(dirname "$0")/.." && pwd)
TASK_LOG=$(mktemp /tmp/worldforge-client-check.XXXXXX.log)
trap 'rm -f "$TASK_LOG"' EXIT
if bash "$TASK_ROOT/scripts/godot.sh" --headless --quit-after 10 > "$TASK_LOG" 2>&1; then
  cat "$TASK_LOG"
else
  TASK_STATUS=$?
  cat "$TASK_LOG"
  exit "$TASK_STATUS"
fi
# Godot sometimes exits zero even when a dynamically loaded script fails.
if rg -q 'SCRIPT ERROR|^ERROR:' "$TASK_LOG"; then
  exit 1
fi
