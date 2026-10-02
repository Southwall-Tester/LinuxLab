# This configuration is used only by the lab's child Bash.
lab() { python3 "$ORBIT_ENGINE" "$@"; }
export -f lab
command_not_found_handle() {
  if command -v python3 >/dev/null 2>&1; then
    python3 "$ORBIT_ENGINE" --shell-command-not-found "$@"
  else
    printf '终端找不到命令：%s。请检查拼写或依赖安装情况。\n' "$1" >&2
  fi
  return 127
}
HISTFILE="$ORBIT_HOME/history"
HISTSIZE=2000
HISTFILESIZE=2000
shopt -s histappend checkwinsize
PS1='\[\e[38;5;45m\]ORBIT\[\e[0m\] \w\n\$ '
trap 'python3 "$ORBIT_ENGINE" stop --quiet' EXIT
printf '\n真实 Bash 已就绪。输入 lab 查看任务，lab help 查看帮助，exit 存档退出。\n'
printf '练习文件位于 %s/station；这是普通 Shell，命令也能访问其他目录。\n' "$ORBIT_HOME"
lab
