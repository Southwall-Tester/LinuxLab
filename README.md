# LinuxLab · 情境式实践

当前版本：**2.0.0**。已发布的学生包下载见 [GitHub Releases](https://github.com/Southwall-Tester/LinuxLab/releases/latest)。

一个在 **WSL / Linux 真实终端**中进行情境式实践的中文 Linux 入门 Lab。首次进入时，大模型先问你喜欢什么主题，再为固定的学习任务创作故事与对象名称；本地程序根据任务合同生成文件、组合题面，完成校验与语义复核后进入 Bash。题材可以自由描述，Linux 知识点和检查要求保持一致。

核心命令：`cd mkdir ls cp mv rm tar cat tail vim top`，另设完整的 `chmod` 权限关。预计 60～90 分钟，实际时长取决于终端基础；没有经过课堂计时或教学效果验证。

## 环境准备与启动

**Windows 新用户：**完整解压学生 ZIP 包，先双击 **安装环境.cmd**。环境准备完成后，按下文配置本地 API，再双击 **启动实验.cmd**；离线开始请使用下文指定主题的启动命令。只检查、不安装可双击 **检查环境.cmd**。安装向导自动检查 WSL 发行版并补齐缺失软件；首次安装 WSL 可能需要管理员授权、重启和创建 Ubuntu 用户，按提示完成后再次运行即可。详见[安装说明](docs/SETUP.md)。

**已有 WSL/Linux：**进入自己的项目目录运行：

```bash
bash setup.sh --install
python3 linuxlab.py ai init
# 编辑生成的 ai.local.json，填写服务地址、密钥、模型并启用后再启动。
bash start.sh
```

推荐 Ubuntu 22.04+ / Debian 12+；需要 Linux 中的 Python 3.9+、Bash、coreutils、tar、gzip、Vim 和 procps（top）。没有 pip/npm 依赖。安装缺失软件可能需要 sudo 和网络；进入练习后的 Linux 操作、本地提示和判题离线可用，不需要管理员权限。请使用自己的解压路径。

**首次或新周目：先问兴趣，再生成情境。** 默认 `bash start.sh` 在没有旧周目时调用本地配置的模型，显示一个兴趣问题；你回答主题后，模型为九项任务生成动机、进展与主题对象名称。本地程序编译实际文件名并检查结构，再通过独立请求复核语义；合格后冻结本局实例，建立文件并进入真实 Bash。失败时最多带诊断重新生成一次，仍不合格则中止，保留旧周目。已有周目直接续学，不重新提问，也不因启动续学发送模型请求。`bash start.sh --new` 会重新询问主题，旧周目保留。

先在程序目录创建本地 API 文件：WSL/Linux 用 `python3 linuxlab.py ai init`；Windows 可直接复制 `ai.example.json` 为 `ai.local.json`，不需要另装 Windows Python。打开该文件，填写 `base_url`、`api_key`、`model` 并设置 `enabled: true`，再启动实验。密钥留在本地文件，不填到命令行。未配置或模型请求失败时会说明原因，不把默认主题冒充为生成结果。详见[配置说明](docs/LOCAL-AI.md)。

需要离线开始时，显式指定本地主题：

```bash
bash start.sh --new --scene space
bash start.sh --new --scene ./my-scene.json
```

`space`、`ocean`、`museum`、`anime` 是四个离线示例，分别为失联空间站、深海观测站、数字档案馆和原创星绘学园，**不是可生成题材的白名单**。使用本地 JSON 时也不会请求模型。进入后直接输入 Linux 命令；第一关会告诉你第一步，输入 `lab` 重看当前故事、目标与实际文件路径。

**使用范围：`lab` 及其子命令（包括 `lab notes`、`lab tutor`、`lab notebook`、`lab review`、`lab tracking`）由本平台实验终端提供，不是 Linux 通用命令；换到其他环境不能默认使用。**

`lab notes` 保留为中文补充知识入口，解释命令名的英文来源、参数原词、用法和记忆联想。同时鼓励查阅工具自带的帮助，例如 `cp --help`、`man cp`，Bash 内置命令用 `help cd`，Vim 编辑器内用 `:help`。这些帮助入口取决于具体工具和环境；`man` 需要本机安装工具及对应手册页。

```text
lab                 当前任务
lab learn           本关命令速查
lab notes [命令]    学习命令名和常用参数；例如 lab notes ls
lab hint            逐级提示，最多三级，不扣分
lab check [答案]    检查成果；只有指定关卡需要答案
lab repair          备份现场，恢复到本关起点
lab tutor           针对当前问题逐级求助；--offline 使用本地讲解
lab notebook        查看个人学习手册
lab review          查看已遇到知识点的复习清单
lab ai init         创建本地 API 配置文件，用于兴趣问询、情境生成与 AI 讲解
lab scene           查看情境与切换方式
exit                退出，下次启动继续
```

迷路时：`cd "$(lab root)"`。关卡中提到的路径都以这个站点根目录为基准。

启动会自动检查依赖。也可运行 `bash setup.sh --check`（缺 Python 时也能诊断）或 `bash start.sh --doctor`。安装入口在依赖齐全时不下载、不运行 apt；详见[安装说明](docs/SETUP.md)。

## 九关路线

| 关卡 | 要解决的问题 | 主要操作 | 如何判定 |
| --- | --- | --- | --- |
| 01 路径与隐藏项 | 观察隐藏标记并准备资料目录 | cd、ls -a、mkdir -p | 当前目录、隐藏标记、工作目录 |
| 02 完整备份 | 保护原始记录 | cp -a | 原件和备份，包括隐藏文件与子目录 |
| 03 整理文件 | 移动改名，按名称规律批量清理 | mv、rm、`*` 通配符 | 完整清理目标，保留名称相似的正常文件 |
| 04 恢复资料 | 读取并恢复归档文件 | tar -t/-x、cat | 解包层级、内容、随机密封码 |
| 05 理解日志 | 辨认有效记录 | cat、tail -n | 识别最新有效消息 |
| 06 编辑配置 | 将已确认的信息写入配置 | vim | 四个字段、值、重复字段检查 |
| 07 权限与启动 | 配置访问权限并执行脚本 | chmod、ls -l、./脚本 | 真实 POSIX 权限与启动回执 |
| 08 辨认进程 | 识别本次实验的探针 | top；可练 tail -f | 本局活进程 PID 与启动身份 |
| 09 综合交付 | 整理新一轮资料并交付 | 前面命令的综合运用 | 归档内部路径、内容、权限与原件备份 |

上表是固定的教学任务，终端中的故事标题随主题变化。通关后显示本局交付包、`LINUXLAB{...}` 完成凭证和 `report.json` 的实际路径；每份存档中已生成的凭证不重新计算。新周目有不同的现场数据；不要把源码文档中的示例文件名当作所有主题都相同的名称。

## 情境与任务如何分开

本地任务合同定义九项任务的稳定标识、学习目标、知识点、可观测证据和依赖。模型只创作故事、12 类任务对象的语义名称与 ASCII 词干，以及对应任务的动机和进展。本地编译器据此产生 34 个文件与目录名称、材料和题面；文件拓扑、隐藏属性、扩展名、权限和判题要求由程序控制。

生成后先进行结构检查，再以另一次模型请求检查题材是否贴合、任务动机是否合理、有无新增要求。模型复核仍可能漏判，不能保证语义绝对正确。通过后保存完整实例、任务合同版本和哈希；续学读取已冻结的实例，不重新生成。模型质量、普通环境中的技能迁移和实际教学效果需分别验证，研究依据与本项目推论见[设计说明](docs/DESIGN.md)。

为保持教学结构，根目录 `station`、隐藏标记 `.beacon-*`、清理模式 `decoy-*.tmp`、探针进程名 `station-pulse` 和配置字段保留。新生成实例的配置状态使用中性值 `active`、`deliver`；旧周目和旧离线情境继续兼容原有 `rescue`、`evacuate`，以本局任务显示的要求为准。

在实验里，`lab scene --generate "你喜欢的任意主题" --output ./my-scene.json` 可生成并导出场景包；不指定输出路径时程序显示自动保存的位置。生成通过结构检查与语义复核后才导出文件，不改当前周目。用 `lab scene ./my-scene.json` 或 `lab scene museum` 切换已有周目的完整叙事时，文件名与学习进度继续沿用；要使用新主题的配套文件名，应退出后在项目目录用 `bash start.sh --new --scene 场景名或JSON文件` 新建周目。

## 文件与运行方式

练习数据默认位于 WSL 的 `~/.local/share/orbit-lab/sessions/`，源码可以留在 Windows 桌面。这样权限关使用 Linux 文件系统的真实权限，不受 `/mnt/c` 挂载选项影响。启动不会改动 `.bashrc`、安装软件或连接评分服务器。

命令入口为 `linuxlab.py`，内部引擎为 `orbit.py`；运行配置使用 `ORBIT_*` 环境变量，存档使用上述默认数据目录。已有脚本也可通过 `orbit.py` 入口运行。

这里使用普通 Bash，支持 Tab 补全、历史、Vim 和原生命令；**不是隔离容器**。请在本局目录里练习。后台探针仅在 `lab load` 时启动，低占用、最多运行 90 秒，通关或退出终端时清理。本关恢复会先把当前站点移到本局 `recovery/`，再复制检查点；按照屏幕提示重新 `cd "$(lab root)"` 即可。

`report.json` 记录检查结果、知识点诊断、具体输入问题及提示和复习记录。`learning-notebook.md` 是随练习更新的个人学习手册。实验终端保留内存中的上下键历史，不再新增磁盘原始命令历史；既有 `history` 文件不读取、不追加、不删除。判定针对文件结果，不是防作弊考试系统。

九关错误分别关联路径、隐藏项、复制、移动、通配符、归档、日志、配置、编辑、权限和进程等知识点。反馈区分观察结果与可能原因；通过检查不换算成掌握百分比。`lab hint` 和实验判题离线可用。

联网入口包括新周目的兴趣问询、情境生成及独立语义复核，显式 `lab scene --generate` 的生成与复核，以及未加 `--offline` 的 `lab tutor`。新周目默认开启有限的本地操作记录，入口显示范围，可用 `lab tracking off` 关闭；续学保留已关闭的选择。记录不会逐条自动上传，主动求助时才发送筛选后的学习摘要。求助失败时回到本地解释，情境生成失败时不创建替代周目。密钥文件不进入 Git 或学生包。

`lab activity` 和 `lab notebook` 可查看经过筛选的命令拼写、选项及实验内路径问题，区分失败输入次数、连续尝试段和候选修正后成功。相同现场与相同提交的连续 `lab check` 合并为同一诊断问题，不反复增加知识点关联失败。AI 诊断引用具体记录编号，并标为待验证解释；统计与模型推测均不等于知识掌握程度。具体范围见[本地 AI 配置与学习记录](docs/LOCAL-AI.md)。

## 教学依据与交付文件

- [学生手册](STUDENT.md)：操作规则、常见问题、命令速查。
- [Linux 命令参数笔记](notes.md)：命令名的英文来源，以及“参数、英文原词、作用说明、记忆联想”四列表；覆盖实验命令和常用拓展工具。实验内用 `lab notes` 查目录、`lab notes ls` 查单个命令；终端会排版标题和表格，窗口较窄时改为逐项说明，按需学习即可。
- [环境与安装](docs/SETUP.md)：首次安装、双击入口、所需软件与故障处理。
- [学生版 AI 助教约定](docs/STUDENT-AGENTS.md)与[使用说明](docs/AI-TUTOR.md)：允许讲解和排错，学生自己操作与提交；发行包和练习目录的 `AGENTS.md` 使用学生版规则。
- [设计与教师说明](docs/DESIGN.md)：视频分集映射、教学节奏、验收和局限。
- [来源核对](research/SOURCES.md)：已核实的内容与尚未核实的范围。
- [验证记录](VALIDATION.md)：本机 WSL 的实际验证结果。
- **Windows 学生版**：`dist/linuxlab-student-windows.zip`，解压后进入 `linuxlab` 文件夹，可双击安装/启动。
- **Linux / WSL 学生版**：`dist/linuxlab-student-linux-wsl.tar.gz`，解压根目录同为 `linuxlab`；两者均不含测试通关流程，按使用环境选一个即可。

`dist/` 是本地生成目录，不随源码提交。维护者在完整源码仓库中进入 WSL/Linux，运行 `python3 tools/package.py` 构建以上学生包，再运行 `python3 tools/verify_handout.py` 验证；发布时把学生包上传为 GitHub Release 附件。普通学生无需执行构建命令。

源码采用单人维护流程：在 `main` 完成一个独立改动、验证后 commit，每轮工作结束 push；正式 Release 单独发布。学生存档与终端历史不进入 Git 仓库。

本项目借鉴 [CS:APP Bomb Lab](https://csapp.cs.cmu.edu/3e/bomblab.pdf) 的分阶段挑战、[Shell Lab](https://csapp.cs.cmu.edu/3e/shlab.pdf) 的由简到繁验证，以及 [CMU Linux Bootcamp](https://www.cs.cmu.edu/afs/cs/academic/class/15213-m22/www/activities/LinuxBootcampHandout.pdf) 的目录探索任务。剧情、程序、关卡与文案为本项目原创实现；不使用 CS:APP 的受限教师代码或题解。
