#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT=$(cd "$(dirname "$0")/.." && pwd)
export XDG_DATA_HOME="$TASK_ROOT/.tools/xdg/data"
export XDG_CONFIG_HOME="$TASK_ROOT/.tools/xdg/config"
export XDG_CACHE_HOME="$TASK_ROOT/.tools/xdg/cache"
mkdir -p "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
exec godot --path "$TASK_ROOT" "$@"
