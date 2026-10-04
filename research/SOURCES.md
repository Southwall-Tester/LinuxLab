# 来源核对

## 原生帮助与平台边界（2026-10-04）

对照本机 WSL 的 `help help`、`ls --help`、`man -w cp`、`man -w bash` 核对帮助入口；Bash 内置 `help` 的说明见 [GNU Bash 官方手册](https://www.gnu.org/software/bash/manual/html_node/Bash-Builtins.html)，GNU 工具选项见 [GNU Coreutils 手册](https://www.gnu.org/software/coreutils/manual/coreutils.html)。原生帮助的实际可用性取决于工具、Shell 和手册页安装情况。`lab notes` 等是本平台的中文补充与教学功能，不宣称其在其他环境通用。

## 本地可选 AI 接口（2026-10-04）

接口格式参考 [DeepSeek Chat Completions 官方文档](https://api-docs.deepseek.com/api/create-chat-completion/)：以 JSON messages 发起对话补全，使用 Bearer 认证。实现接受用户本地配置的兼容服务，实际服务与模型可用性由用户配置决定。本机模拟服务用于验证协议与失败处理，真实服务试验结果另见 [VALIDATION.md](../VALIDATION.md)；配置检查或服务连通均不能证明生成式讲解的教学效果。

知识点关联、操作证据规则和 1/7/30 天复习安排是本项目的工程设计，不是已证实的认知诊断模型或经实测的遗忘曲线。

## 兴趣情境、任务变式与生成质量（2026-10-04）

本次直接查阅下列论文正文及项目官方文档。论文发现不直接等同于本项目的实现效果；每项列出适用范围，避免只选有利证据。

| 原始来源 | 实际发现或机制 | 限制及本项目用途 |
| --- | --- | --- |
| Walkington（2013），[Using Adaptive Learning Technologies to Personalize Instruction to Student Interests: The Impact of Relevant Contexts on Performance and Learning Outcomes](https://www.researchgate.net/publication/263936546_Using_Adaptive_Learning_Technologies_to_Personalize_Instruction_to_Student_Interests_The_Impact_of_Relevant_Contexts_on_Performance_and_Learning_Outcomes)，DOI 10.1037/a0031882，作者公开全文 | 145名九年级学生的随机分组研究中，兴趣匹配组在较难的代数列式任务上更准确、高效，后续非个性化单元仍观察到优势 | 不是Linux或任意LLM剧情实验；兴趣等中介机制未直接测量。支持研究有意义的情境关系，不证明换词有效 |
| Harp 与 Mayer（1998），[How Seductive Details Do Their Damage: A Theory of Cognitive Interest in Science Learning](https://www.researchgate.net/publication/232595492_How_Seductive_Details_Do_Their_Damage_A_Theory_of_Cognitive_Interest_in_Science_Learning)，作者公开全文 | 四项实验中，有趣但与核心解释无关的材料降低主要内容回忆与问题解决迁移 | 使用单篇科学教材、限时阅读和低先备知识成人，不能概括为一切故事有害。提示删去与操作目的无关的剧情 |
| Gentner、Loewenstein 与 Thompson（2003），[Learning and Transfer: A General Role for Analogical Encoding](https://groups.psych.northwestern.edu/gentner/papers/GentnerLoewensteinThompson03.pdf)，作者实验室PDF | 谈判学习实验中，显式比较案例促进共同结构提取与迁移；第二项实验迁移比例48%对19% | 任务为谈判，非终端操作。用于提出跨情境结构比较的后续验证，不宣称本Lab已有同样收益 |
| [PrairieLearn：server.py与题目生命周期](https://docs.prairielearn.com/question/server/)，官方文档 | 区分generate、render、parse、grade等阶段，以params和correct_answers维护变式数据 | 工程文档而非教学效果研究。借鉴生成、渲染、评分职责分离，不照搬其可自定义判分代码的全部能力 |
| [STACK：Deploying](https://docs.stack-assessment.org/en/STACK_question_admin/Deploying/)，官方文档 | 建议先生成、测试再部署变式，记录实例种子；进行中的测验不应改变随机生成逻辑 | 文档明确测试受覆盖范围限制，变式公平性需实际使用数据。支持先检查和冻结实例，不保证各主题难度等值 |
| Yadav、Tseng 与 Ni（2023），[Contextualizing Problems to Student Interests at Scale in Intelligent Tutoring System Using Large Language Models](https://arxiv.org/abs/2306.00190)，原始论文 | CTAT原型用GPT-4改写情境，提示约束保留数值、原问题意图，并提供作者预览编辑 | 属提示工程与工具探索；学习效果系统研究列为未来工作，涉及图形的问题仍有局限。不能当作已完成的教学实验证据 |
| Logacheva等（ICER 2024），[Evaluating Contextually Personalized Programming Exercises Created with Generative AI](https://arxiv.org/abs/2407.11994)，原始论文 | 对283道生成编程题评估：96.1%匹配主题，87.6%匹配概念，54.4%难度合适；学生偏好选择主题 | 单机构自定进度选修课，64%属浅层个性化；质量、主观反馈和使用行为不是迁移增益的因果验证。提示分别检查主题、概念和难度 |

本项目的工程推论：用稳定任务合同保护目标和可观测证据；模型只填语义对象和任务动机；本地编译控制结构与判题；生成后做结构检查和独立语义复核，失败只允许一次带诊断重生成；通过后冻结实例及合同版本/hash。这一整套流程并非上述来源已验证的方法，模型复核也可能漏判。论文中的兴趣、满意度、当前作答表现和技能迁移不能互换，真实学生效果仍需另行研究。

## 操作错误、重复困难与模型诊断（2026-10-04）

下列原始论文已核对方法与结果正文。评价对象分别是反馈感受、行为模式、编译过程和模型输出，不能统一称为学习效果实验。

| 原始研究 | 方法、样本与发现 | 局限与工程借鉴 |
| --- | --- | --- |
| Švábenský等（2024；在线2023），[Automated feedback for participants of hands-on cybersecurity training](https://link.springer.com/article/10.1007/s10639-023-12265-8) | Shell日志按七类错误和命令频次分析；58人参加、45份问卷 | 误报漏报使错误分析评价较差；未测学习增益。借鉴具体错误聚合，同时验证分类准确性。见§3.6.4、§4–5 |
| Švábenský等（2022），[Student assessment in cybersecurity training automated by pattern mining and clustering](https://arxiv.org/pdf/2307.10260) | 113人、18场训练、8834条命令；序列挖掘与聚类发现反复改参数等模式 | 模式原因依赖上下文；无反馈干预效果实验。借鉴操作序列，不把重复或停顿直接视为知识缺陷。见§4–5；预印本上传于2023年 |
| Jadud（2006），[Methods and Tools for Exploring Novice Compilation Behaviour](https://jadud.com/dl/pdf/2006-icer-jadud.pdf)，作者全文 | 两年Java/BlueJ编译快照研究；EQ统计筛选为96人，以相邻编译事件刻画连续语法错误 | 非Linux，亦非掌握率或教学干预实验。借鉴会话内错误与修正过程，不能把每次重试当独立复发。见§1、§4–5 |
| Reddig等（2025），[Generating In-Context, Personalized Feedback for Intelligent Tutors with Large Language Models](https://link.springer.com/article/10.1007/s40593-025-00505-6) | 6926次代数交互中分析1303条被标错输入（含实际正确者）；提供界面、答案及技能上下文，GPT-4诊断准确率87.8% | 约35%提示为泛化、泄答或错误；另约35%是模拟学生自动评估通过率，均非真人学习增益。借鉴上下文诊断，保留校验与不确定性。见Study 1–3及Discussion |

本项目的设计选择：将学习记录默认开启，是为了让连续诊断具有操作依据，不是上述论文已证明的最优设置。记录范围、关闭入口和数据去向应明确说明；记录的事实与模型提出的候选原因分开，不把表象模式、非零退出码或一次模型判断当作知识掌握结论。

重复错误的统计应区分同一次问题中的连续尝试和独立复发：前者记录尝试次数与修正过程，后者需要已解决后再次发生或另一次独立使用中的证据。十次连续重试不能直接表述为“忘记了十次”；未获得修正或独立使用证据时保留不确定性。错误分类准确性、反馈可用性、同类错误是否减少和迁移效果需要分别验证。

核对日期：2026-09-30。以下区分直接读取的事实与本项目自己的设计选择。

## 指定视频

- [B 站视频 BV1GwMEzVEbQ](https://www.bilibili.com/video/BV1GwMEzVEbQ/)
- [B 站公开视频信息接口](https://api.bilibili.com/x/web-interface/view?bvid=BV1GwMEzVEbQ)
- 本地元数据：[video-metadata.json](video-metadata.json)。直接读取到标题、7 个分集名称、各自时长；字幕列表为空。
- P7 首帧的课程脑图明确显示性能监控中的 `top`；P6 的 150 秒抽样画面明确显示 `chmod`、数字权限及 r/w/x。
- 总时长 3293 秒。以分集主题、上述画面为课程范围依据，没有完整转写全部音频，也没有验证每个讲解案例和命令参数。核心题目与参数安排由本项目重新设计。

## CS:APP 与 CMU 官方资料

1. [CS:APP Lab 总览](https://csapp.cs.cmu.edu/3e/labs.html)：确认各 Lab 的教学目标和独立 handout 的分发方式。
2. [Bomb Lab handout](https://csapp.cs.cmu.edu/3e/bomblab.pdf)：确认阶段式拆解、反馈、难度递增与已完成答案复用。
3. [Shell Lab handout](https://csapp.cs.cmu.edu/3e/shlab.pdf)：第 4～6 页介绍参考行为、驱动及由简单到复杂的 trace；据此安排前期单项任务与最终综合验收。
4. [CMU Linux Bootcamp handout](https://www.cs.cmu.edu/afs/cs/academic/class/15213-m22/www/activities/LinuxBootcampHandout.pdf)：直接以 Shell、Vim、故事和目录探索组成分阶段任务，与本请求最贴近。

本项目借鉴教学结构；未复制这些项目的受限源代码、题解、角色或关卡。资料并不能证明本实验已经达到相同趣味性或教学效果，仍需要真实学生试玩。

## 参数说明核对（2026-10-01）

九关中的参数说明对照本机 WSL 的 `mkdir`、`ls`、`cp`、`rm`、`tar`、`tail`、`top` 的 `--help` 输出核对；Vim 对照 [插入模式说明](https://vimhelp.org/insert.txt.html) 和 [文件编辑说明](https://vimhelp.org/editing.txt.html)，top 另参考 [procps 手册](https://man7.org/linux/man-pages/man1/top.1.html)。GNU 网页正文此次访问超时，未把未读到的网页当作已验证依据。

说明区分实际选项名称和助记法：例如 tar 的 `-t` 对应 `--list`，table of contents 仅作助记；`-z` 对应 gzip，不虚构首字母全称。对默认行为的好处采用面向新手的使用场景解释，不声称考证了命令作者的历史设计动机。
