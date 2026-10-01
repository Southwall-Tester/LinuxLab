# 来源核对

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
