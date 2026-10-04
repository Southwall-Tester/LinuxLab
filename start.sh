#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  printf '缺少 Python 3。请在项目目录运行 bash setup.sh --install，或在 Windows 双击安装环境.cmd。\n' >&2
  exit 1
fi
export PYTHONUTF8=1
export ORBIT_ENGINE="$APP_DIR/linuxlab.py"
if [[ "${1:-}" == "--doctor" ]]; then
  exec python3 "$ORBIT_ENGINE" doctor
fi
ORBIT_HOME="$(python3 "$ORBIT_ENGINE" prepare --interactive "$@")"
export ORBIT_HOME
cd -- "$ORBIT_HOME/station"
exec bash --noprofile --rcfile "$APP_DIR/shellrc.sh" -i
