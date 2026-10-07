#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$TASK_ROOT"
mkdir -p build/web
bash scripts/godot.sh --headless --editor --import --quit
bash scripts/godot.sh --headless --export-release Web build/web/index.html
