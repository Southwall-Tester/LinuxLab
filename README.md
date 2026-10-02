# ORBIT · 失联空间站

一个在 **WSL / Linux 真实终端**中游玩的中文 Linux 入门 Lab。你是空间站最后一名值班工程师，需要沿着九个检查点恢复导航、中继与遥测，最终交付救援包，接回三名船员。

核心命令：`cd mkdir ls cp mv rm tar cat tail vim top`，另设完整的 `chmod` 权限关。预计 60～90 分钟，实际时长取决于终端基础；没有经过课堂计时或教学效果验证。

## 环境准备与启动

**Windows 新用户：**完整解压学生 ZIP 包，先双击 **安装环境.cmd**，准备完成后双击 **启动实验.cmd**。只检查、不安装可双击 **检查环境.cmd**。安装向导自动检查 WSL 发行版并补齐缺失软件；首次安装 WSL 可能需要管理员授权、重启和创建 Ubuntu 用户，按提示完成后再次运行即可。详见[安装说明](docs/SETUP.md)。

**已有 WSL/Linux：**进入自己的项目目录运行：

```bash
bash setup.sh --install
bash start.sh
```

推荐 Ubuntu 22.04+ / Debian 12+；需要 Linux 中的 Python 3.9+、Bash、coreutils、tar、gzip、Vim 和 procps（top）。没有 pip/npm 依赖。安装缺失软件可能需要 sudo 和网络，日常实验离线运行，不需要管理员权限。当前作者电脑的项目路径是 `/mnt/c/Users/HP/Desktop/LinuxLab`，其他用户使用自己的解压路径。

进入后直接输入 Linux 命令。第一关会告诉你第一步；输入 `lab` 重看任务。

```text
lab                 当前任务
lab learn           本关命令速查
lab notes [命令]    学习命令名和常用参数；例如 lab notes ls
lab hint            逐级提示，最多三级，不扣分
lab check [答案]    检查成果；只有指定关卡需要答案
lab repair          备份现场，恢复到本关起点
exit                退出，下次启动继续
```

迷路时：`cd "$(lab root)"`。关卡中提到的路径都以这个站点根目录为基准。

启动会自动检查依赖。也可运行 `bash setup.sh --check`（缺 Python 时也能诊断）或 `bash start.sh --doctor`。安装入口在依赖齐全时不下载、不运行 apt；详见[安装说明](docs/SETUP.md)。

## 九关路线

| 关卡 | 要解决的问题 | 主要操作 | 如何判定 |
| --- | --- | --- | --- |
| 01 找到气闸 | 隐藏定位灯在哪里 | cd、ls -a、mkdir -p | 当前目录、隐藏信标、工作目录 |
| 02 保存黑匣子 | 动设备前保护原始记录 | cp -a | 原件和备份，包括隐藏文件与子目录 |
| 03 清理假信号 | 航线改名，按名称规律批量清理 | mv、rm、`*` 通配符 | 完整清理目标，保留名单及相似名称的正常文件 |
| 04 打开救援舱 | 找到封存的恢复文件 | tar -t/-x、cat | 解包层级、内容、随机密封码 |
| 05 最后一条消息 | 旧 READY 会误导你 | cat、tail -n | 识别最新有效消息 |
| 06 修复配置 | 把日志线索写入中继配置 | vim | 四个字段、值、重复字段检查 |
| 07 交还启动权限 | 有文件却不能直接运行 | chmod、ls -l、./脚本 | 真实 POSIX 权限与启动回执 |
| 08 辨认进程 | 哪个探针属于这次实验 | top；可练 tail -f | 本局活进程 PID 与启动身份 |
| 09 最后一次投递 | 新频率、新交付要求 | 前面命令的综合运用 | 归档内部的路径、内容、权限与黑匣子 |

成功后会得到 `rescue.tar.gz`、`ORBIT{...}` 救援凭证和 `report.json`。新局有不同信标、频率与授权码。退出后用 `bash start.sh --new` 开始新周目，旧文件仍保留。

## 文件与运行方式

练习数据默认位于 WSL 的 `~/.local/share/orbit-lab/sessions/`，源码可以留在 Windows 桌面。这样权限关使用 Linux 文件系统的真实权限，不受 `/mnt/c` 挂载选项影响。启动不会改动 `.bashrc`、安装软件或连接评分服务器。

这里使用普通 Bash，支持 Tab 补全、历史、Vim 和原生命令；**不是隔离容器**。请在本局目录里练习。后台探针仅在 `lab load` 时启动，低占用、最多运行 90 秒，通关或退出终端时清理。本关恢复会先把当前站点移到本局 `recovery/`，再复制检查点；按照屏幕提示重新 `cd "$(lab root)"` 即可。

`report.json` 记录检查结果、提示级别、恢复与完成时间；完整 Bash 历史仅留在本局 `history` 中，不发送到网络。判定针对文件结果，不能证明你确实使用了某一命令，也不是防作弊考试系统。

## 教学依据与交付文件

- [学生手册](STUDENT.md)：操作规则、常见问题、命令速查。
- [Linux 命令参数笔记](notes.md)：命令名的英文来源，以及“参数、英文原词、作用说明、记忆联想”四列表；覆盖实验命令和常用拓展工具。实验内用 `lab notes` 查目录、`lab notes ls` 查单个命令；终端会排版标题和表格，窗口较窄时改为逐项说明，按需学习即可。
- [环境与安装](docs/SETUP.md)：首次安装、双击入口、所需软件与故障处理。
- [学生版 AI 助教约定](docs/STUDENT-AGENTS.md)与[使用说明](docs/AI-TUTOR.md)：允许讲解和排错，学生自己操作与提交；发行包和练习目录的 `AGENTS.md` 使用学生版规则。
- [设计与教师说明](docs/DESIGN.md)：视频分集映射、教学节奏、验收和局限。
- [来源核对](research/SOURCES.md)：已核实的内容与尚未核实的范围。
- [验证记录](VALIDATION.md)：本机 WSL 的实际验证结果。
- `dist/orbit-lab-handout.zip`：Windows 学生包，解压后可双击安装/启动。
- `dist/orbit-lab-handout.tar.gz`：Linux 学生包；两者均不含测试通关流程。

`dist/` 是本地生成目录，不随源码提交。维护者在完整源码仓库中进入 WSL/Linux，运行 `python3 tools/package.py` 构建以上学生包，再运行 `python3 tools/verify_handout.py` 验证；发布时把学生包上传为 GitHub Release 附件。普通学生无需执行构建命令。

源码采用单人维护流程：在 `main` 完成一个独立改动、验证后 commit，每轮工作结束 push；正式 Release 单独发布。学生存档与终端历史不进入 Git 仓库。

本项目借鉴 [CS:APP Bomb Lab](https://csapp.cs.cmu.edu/3e/bomblab.pdf) 的分阶段挑战、[Shell Lab](https://csapp.cs.cmu.edu/3e/shlab.pdf) 的由简到繁验证，以及 [CMU Linux Bootcamp](https://www.cs.cmu.edu/afs/cs/academic/class/15213-m22/www/activities/LinuxBootcampHandout.pdf) 的目录探索任务。剧情、程序、关卡与文案为本项目原创实现；不使用 CS:APP 的受限教师代码或题解。
