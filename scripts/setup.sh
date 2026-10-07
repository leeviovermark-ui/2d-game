#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$TASK_ROOT"
export PIP_CACHE_DIR="$TASK_ROOT/.tools/pip-cache"
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
test "$(bash scripts/godot.sh --version | cut -d. -f1-3)" = "4.6.3" || {
  echo 'This project requires Godot 4.6.3 (the cloud image provides it).'
  exit 1
}
bash scripts/godot.sh --headless --editor --import --quit
bash scripts/check_client.sh
.venv/bin/python -m unittest discover -v
if test -f .tools/export_templates/4.6.3.stable/web_release.zip; then
  bash scripts/export_web.sh
fi
