# 第一次安装与环境检查

## 需要什么

| 项目 | 要求 |
| --- | --- |
| Windows 路线 | 推荐 Windows 11 + WSL 2 + Ubuntu；官方简化安装命令也支持 Windows 10 2004 / 内部版本 19041 及以上 |
| Linux 路线 | 推荐 Ubuntu 22.04+ 或 Debian 12+；其他发行版可手动补齐依赖后检查 |
| Python | Linux 中的 Python 3.9+；不使用 Windows 中安装的 Python |
| 终端工具 | Bash、GNU coreutils、tar、gzip、Vim、procps（提供 top） |
| 权限 | 首次安装 WSL 可能需要 Windows 管理员授权；安装 Linux 软件可能需要 sudo |
| 网络 | 安装依赖、默认新周目的兴趣问询/情境生成和 AI 求助需要联网；本地主题、已有周目、Linux 操作与判题可离线运行 |

不需要 VS Code、Docker、Node.js、pip 包或 Codex。默认新周目需要在 `ai.local.json` 配置可用模型服务；服务不限于 OpenAI。若要完全离线开始，按下文指定本地主题。Git Bash、PowerShell 和 CMD 本身不能替代实验需要的 Linux 环境。

## Windows 用户：双击入口

先把 **Windows 学生版 `orbit-lab-student-windows.zip` 完整解压**到一个普通本地目录，再打开里面的 `orbit-lab` 文件夹；不要直接在压缩包中点击脚本。

1. 第一次使用，双击 **安装环境.cmd**。
2. 按屏幕提示完成环境准备。依赖已经齐全时会直接检查通过，不重复安装。
3. 在解压后的 `orbit-lab` 目录复制 `ai.example.json`，将副本命名为 `ai.local.json`；打开副本，填写 `base_url`、`api_key`、`model`，并设置 `enabled: true`。这个方式不需要 Windows 安装 Python，注意不要保存成 `.json.txt`。详见[本地 AI 配置](LOCAL-AI.md)。
4. 保存配置后，双击 **启动实验.cmd**，回答兴趣问题并生成本局情境。学生包不附带维护者的密钥。

离线开始时，在解压后的 `orbit-lab` 目录打开 PowerShell，运行以下命令；把 `Ubuntu` 换成你实际安装的发行版名称：

```powershell
wsl -d Ubuntu --cd "$PWD" -- bash ./start.sh --new --scene space
```

只想检查而不安装，双击 **检查环境.cmd**。

这是一键启动的安装向导，不是所有机器上都能无人值守完成：

- **没有 Ubuntu/Debian**：向导调用微软的 `wsl --install -d Ubuntu --no-launch`，需要时弹出管理员授权。下载完成后按提示重启（如需要）、从开始菜单打开 Ubuntu 并创建 Linux 用户，再次运行“安装环境”继续。不会自动重启或删除现有发行版。
- **已有 Ubuntu/Debian，但缺命令**：只对缺失依赖调用该发行版的 `apt-get update`、`apt-get install -y`。若提示密码，输入 Ubuntu/Linux 用户密码；输入时不显示字符属于正常行为。
- **环境完整**：只运行检查，不执行 apt、不下载内容。
- **找不到 wsl.exe**：先按下方官方步骤安装 WSL；脚本会明确报告尚未就绪，不会假装完成。

入口按 Ubuntu、Ubuntu-*、Debian 的顺序选择已安装发行版，并显示实际名称；不修改 WSL 的默认发行版。多个 Ubuntu-* 时使用列表中的第一个，安装和启动采用相同规则。要用指定发行版，可在本项目目录的 PowerShell 中运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows.ps1 -Mode Setup -Distro Ubuntu-24.04
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows.ps1 -Mode Start -Distro Ubuntu-24.04
```

`-Mode Check` 只检查。`ExecutionPolicy Bypass` 只作用于这次脚本进程，不会更改全局执行策略；组织策略仍可能阻止脚本，需要联系管理员。

## 手动安装 WSL

在**管理员 PowerShell**中运行：

```powershell
wsl --install -d Ubuntu
```

按系统要求重启，然后打开 Ubuntu 完成用户名和密码设置。完成后重新运行 `安装环境.cmd`。如果商店下载或网络失败，请先修复网络，或参照微软文档中的安装选项；不要为此注销已有发行版。

依据：[微软 WSL 安装说明](https://learn.microsoft.com/en-us/windows/wsl/install)、[WSL 命令参考](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)、[首次创建 Linux 用户](https://learn.microsoft.com/en-us/windows/wsl/setup/environment)。

## 已有 Linux / WSL 终端

进入**解压后的项目目录**，执行：

```bash
bash setup.sh --install
python3 orbit.py ai init
# 编辑 ai.local.json，填写模型服务配置并设 enabled 为 true。
bash start.sh
```

无需联网生成主题时，安装依赖后改用 `bash start.sh --new --scene space`。已有周目直接用 `bash start.sh` 续学。

只检查：

```bash
bash setup.sh --check
```

当前作者电脑上的项目目录是 `/mnt/c/Users/HP/Desktop/LinuxLab`；其他电脑要换成自己的目录，不能照抄这个用户名和路径。

手动安装的 Ubuntu/Debian 等价命令如下。完整列表仅供手动安装使用，自动脚本只安装缺失项对应的软件包：

```bash
sudo apt-get update
sudo apt-get install -y python3 bash coreutils tar gzip vim procps
bash start.sh --doctor
```

## 常见故障

- **WSL 提示虚拟化/可选组件未启用或要求重启**：按 Windows 提示完成；BIOS 虚拟化、组织权限限制不能由本 Lab 静默修复。查看微软安装文档。
- **第一次运行出现用户创建提示**：完成 Ubuntu 初始化，使用普通 Linux 用户运行实验。无需 `sudo bash start.sh`。
- **apt 锁被占用**：等待其他软件安装结束后重试；不要删除锁文件。
- **下载失败**：检查网络和 Ubuntu 软件源，修复后重新运行安装入口。失败时脚本返回非零退出码。
- **Python 仍低于 3.9**：旧发行版的默认软件源可能只提供旧版本，建议使用 Ubuntu 22.04+ / Debian 12+，不要手动替换系统 Python。
- **Windows 路径无法进入**：确认压缩包完整解压到本机磁盘目录，WSL 为支持 `--cd` 的版本；可直接从 Ubuntu 终端进入项目目录运行。
- **权限关异常**：源文件可以放在 Windows 磁盘，练习数据默认在 Linux 家目录；不要把 `ORBIT_DATA_DIR` 指向 `/mnt/c`。

安装入口不创建或重置周目。正常启动自动续玩；重新开始用 `bash start.sh --new`。
