#!/usr/bin/env bash
# Install only the lab's missing distro packages. No pip, curl installer or profile edits.
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:---install}"
if [[ $# -gt 1 || ( "$MODE" != '--install' && "$MODE" != '--check' ) ]]; then
  printf '用法：bash setup.sh [--install | --check]\n' >&2
  exit 2
fi
if [[ "$(uname -s)" != Linux || ! -r /proc/self/stat ]]; then
  printf '需要真实 Linux 环境。Windows 用户请运行安装环境.cmd，使用 WSL Ubuntu。\n' >&2
  exit 1
fi

missing=()
inspect_dependencies() {
  missing=()
  local program
  for program in python3 bash ls mkdir cp mv rm tar gzip cat tail chmod top vim; do
    if ! command -v "$program" >/dev/null 2>&1; then
      missing+=("$program")
    fi
  done
  if command -v python3 >/dev/null 2>&1; then
    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      missing+=('Python>=3.9')
    fi
  fi
}

inspect_dependencies
if [[ ${#missing[@]} -eq 0 ]]; then
  printf '依赖已就绪；无需下载或安装。\n'
  exec env PYTHONUTF8=1 python3 "$APP_DIR/orbit.py" doctor
fi
printf '需要补齐：%s\n' "${missing[*]}"
if [[ "$MODE" == '--check' ]]; then
  printf 'Ubuntu/Debian：请在当前项目目录运行 bash setup.sh --install\n' >&2
  exit 1
fi

ID=''
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
fi
if [[ "$ID" != ubuntu && "$ID" != debian ]] || ! command -v apt-get >/dev/null 2>&1; then
  printf '自动安装支持 Ubuntu/Debian。其他 Linux 请用本发行版包管理器安装上述依赖，再运行 bash setup.sh --check。\n' >&2
  exit 1
fi
packages=()
for program in "${missing[@]}"; do
  case "$program" in
    python3|'Python>=3.9') package=python3 ;;
    bash) package=bash ;;
    tar) package=tar ;;
    gzip) package=gzip ;;
    top) package=procps ;;
    vim) package=vim ;;
    *) package=coreutils ;;
  esac
  if [[ " ${packages[*]} " != *" $package "* ]]; then
    packages+=("$package")
  fi
done
elevate=()
if (( EUID != 0 )); then
  if ! command -v sudo >/dev/null 2>&1; then
    printf '需要 sudo 或管理员代为安装这些软件包：%s\n' "${packages[*]}" >&2
    exit 1
  fi
  elevate=(sudo)
fi
printf '将通过发行版软件源安装：%s\n' "${packages[*]}"
printf '安装需要联网；如询问密码，请输入 Linux 用户密码，输入时不会显示字符。\n'
if ! "${elevate[@]}" apt-get update; then
  printf '软件源更新失败。请检查网络、软件源或 apt 锁占用，修复后重新运行安装。\n' >&2
  exit 1
fi
if ! "${elevate[@]}" apt-get install -y "${packages[@]}"; then
  printf '安装未完成，环境尚未就绪。请根据上方 apt 错误处理后重试。\n' >&2
  exit 1
fi
inspect_dependencies
if [[ ${#missing[@]} -gt 0 ]]; then
  printf '安装后仍不满足要求：%s\n' "${missing[*]}" >&2
  printf '若系统源中的 Python 低于 3.9，请使用 Ubuntu 22.04+ 或 Debian 12+，无需替换系统 Python。\n' >&2
  exit 1
fi
env PYTHONUTF8=1 python3 "$APP_DIR/orbit.py" doctor
printf '环境准备完成。在本目录运行 bash start.sh 开始实验。\n'
