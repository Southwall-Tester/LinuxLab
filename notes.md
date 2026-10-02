# Linux 常用命令参数笔记

按需查表，不必一次背完。实验中输入 `lab notes` 看目录，`lab notes ls` 查某个命令，`lab notes all` 看全文；也可以直接打开本文件阅读。示例使用普通练习文件名，不提供关卡答案。

“英文原词”优先列实际长选项或文档名称；标注“助记”的只是帮助记忆，不代表历史命名来源。以下面向 Bash 和常见 GNU/Linux 工具，个别实现或版本有差异，以本机帮助为准。

## basics — 先读懂命令结构

`命令 [选项] [操作对象]`：例如 `tail -n 5 app.log` 中，`-n` 是选项，`5` 是它需要的行数，`app.log` 是操作对象。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `--help` | help | 多数外部命令显示用法；Bash 内置命令可用 `help cd` | 先看帮助再试 |
| `--version` | version | 多数外部命令显示版本，便于核对行为差异 | Version = 版本 |
| `--` | 无；选项结束标记 | 很多命令用它表示后面都是操作对象，如 `rm -- -draft.txt` | 两横线，把选项和名字隔开 |

短选项通常可以合并：`ls -lah` 等于 `ls -l -a -h`。带值的选项需要跟对位置，例如 `tar -tzf pack.tar.gz` 中的 `-f` 要接包名。大小写有区别，`ls -r` 和 `ls -R` 完全不同。

同一字母不保证同一含义：`ls -a` 是 all，`cp -a` 是 archive；`rm -f` 是 force，`tail -f` 是 follow，`tar -f` 是 file。`-h` 也不总是帮助，例如 `ls -h` 是易读大小。

## ls — 列出文件

**命令名**：`ls` ← **list**（列出），记成“列一下这里有什么”。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-l` | long format | 长格式显示权限、所有者、组、大小、时间等 | Long = 长清单 |
| `-a` | all | 包括点号开头的隐藏项，以及 `.`、`..` | All = 全部展开 |
| `-A` | almost-all | 包括隐藏项，但不列 `.`、`..` | Almost all = 几乎全部 |
| `-h` | human-readable | 配合 `-l` 或 `-s`，用 K、M、G 等易读单位显示大小 | Human = 人类易读；单独加它不会多出大小列 |
| `-t` | time（助记；排序字段默认是修改时间） | 按修改时间从新到旧排序，不是按创建时间 | Time = 最近动过的排前面 |
| `-r` | reverse | 反转当前排序；配合 `-t` 可让最旧的在前 | Reverse = 倒过来 |
| `-R` | recursive | 连同子目录逐层列出；仍遵守隐藏项的显示规则 | 大写 R = 一层层往下看 |
| `-S` | size（助记） | 按文件大小从大到小排序 | Size = 大个头在前 |
| `-d` | directory | 列目录自身的信息，而不是打开它看内部 | Directory = 看目录本人 |
| `-s` | size | 显示文件占用的磁盘块量，可配合 `-h` | 小写 s 显示占用，大写 S 排大小 |

默认列表简洁；需要找隐藏配置才加 `-a`，核对权限和大小才加 `-l`。隐藏不是权限保护。例：`ls -lah` 看详情，`ls -ltr` 把最近修改的放在最后，`ls -ld notes` 查看目录自身权限。目录那一行的大小不是其全部内容的总大小，统计占用用 `du`。

## navigation — cd 与 pwd：你在哪里

**命令名**：`cd` ← **change directory**（切换目录）；`pwd` ← **print working directory**（输出当前工作目录）。一个负责走，一个告诉你现在在哪。

下表既有选项，也有特殊路径写法，注意区别。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `cd ..` | 无；父目录写法 | 回到上一级目录 | 两个点，退一层 |
| `cd -` | 无；特殊操作对象 | 返回上一次所在目录，并显示路径 | 两个位置来回切换 |
| `cd ~` | 无；Bash 的主目录展开 | 回到当前用户的家目录；单独 `cd` 也会回家 | 波浪线代表家 |
| `cd -L` / `pwd -L` | logical | 按逻辑路径处理或显示位置，保留符号链接路径的含义 | Logical = 按你走过的路径理解 |
| `cd -P` / `pwd -P` | physical | 解析符号链接，按实际目录层级处理或显示位置 | Physical = 看实际位置 |

相对路径从当前目录出发，绝对路径从 `/` 出发。找不到目录时先 `pwd`，再 `ls`；重复输入同一条 `cd` 不会改变相对路径的起点。

## mkdir — 创建目录

**命令名**：`mkdir` ← **make directory**（创建目录），可以拆成 mk（make）+ dir（directory）。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-p` | parents | 自动补齐缺少的父目录，目标目录已存在也可继续 | Parents = 先把父级准备好 |
| `-v` | verbose | 输出正在创建的目录 | Verbose = 把过程说出来 |
| `-m 模式` | mode | 指定新目录的权限模式，如 `700`；不影响 `-p` 自动补出的父目录权限 | Mode = 设定访问方式 |

例：`mkdir -p notes/day1`。默认遇到缺失父目录会报错，有助于发现路径写错；显式加 `-p` 才允许自动补齐。也可以自己逐层创建。

## cp — 复制

**命令名**：`cp` ← **copy**（复制），原件仍保留。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-r` / `-R` | recursive | 复制目录及其子目录、文件 | Recursive = 整棵目录一起带走 |
| `-a` | archive | 递归复制，并尽量保留权限、时间、链接等属性 | Archive = 保留原貌的备份；不会生成压缩包 |
| `-p` | preserve | 尽量保留权限、所有者和时间戳；单用它不会递归复制目录 | Preserve = 保留属性，不是 parents |
| `-i` | interactive | 覆盖目标前询问 | Interactive = 覆盖前问一句 |
| `-u` | update | 源文件较新或目标不存在时才复制 | Update = 有更新才拷贝 |
| `-v` | verbose | 显示复制过程 | Verbose = 看清复制到了哪里 |
| `-t 目录` | target-directory | 明确要求目标是已有目录，如 `cp -t notes note.txt`；目录不存在就报错 | Target = 认准接收文件的目录 |

例：`cp -a photos photos-backup`。目标不存在时会以新名字创建；目标目录已存在时通常会在它里面再放一层源目录。默认不复制目录，避免普通文件复制意外涉及整棵目录；需要时明确选择递归。

**写清目标目录是个好习惯**：把一个普通文件复制进已有目录时，可以写 `cp note.txt notes/`。末尾的 `/` 表明目标应是目录；如果 `notes` 不存在或不是目录，会报错，避免意外复制出一个叫 `notes` 的普通文件。若本来就是复制并改名，则写新文件名，不加 `/`。递归复制目录的目标创建规则不同，不能把这条保护直接套到 `cp -a 源目录 新目录/` 上；需要明确要求目标目录已经存在时，可用 `-t`。

## mv — 移动与改名

**命令名**：`mv` ← **move**（移动）。改名也可以理解成把文件移到同目录下的新名字。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-i` | interactive | 覆盖已有目标前询问 | 先问再覆盖 |
| `-n` | no-clobber | 不覆盖已有目标 | No clobber = 别盖掉旧文件 |
| `-f` | force | 覆盖前不询问；不能绕过文件系统权限 | Force = 省掉询问，不是获得权限 |
| `-v` | verbose | 显示移动或改名过程 | 把过程说出来 |
| `-t 目录` | target-directory | 明确指定目标目录，便于把多个源文件移到同一处 | Target = 目标 |

例：`mv -i draft.txt final.txt`。移动后原位置不再保留文件；`mv` 移动目录不需要 `-r`。交互、跳过、强制覆盖是不同选择，初学时不要把 `-i`、`-n`、`-f` 混在一起。

**好习惯：明确要把文件放进已有目录时，目标路径末尾加 `/`。** 这能把“放进目录”的意图写清楚，减少目录名写错后意外变成改名操作的情况。

假设 `file.txt` 是普通文件，当前目录中还没有 `renames`：

| 写法 | 实际结果 |
| --- | --- |
| `mv file.txt renames` | 把文件改名为 `renames`，不会因为你原本想写目录而报错 |
| `mv file.txt renames/` | 目标不能作为目录使用，报错，原文件仍在原处 |

如果 `renames` 已经是目录，第二种写法会把文件移成 `renames/file.txt`。末尾 `/` 是路径写法，不是命令选项，也不会帮你创建目录。

记住两种意图：**放进目录，目标写 `notes/`；移动并改名，目标写 `notes/new-name.txt`。** 上述例子针对普通文件；不要机械地给所有源路径或文件名都加 `/`。如果错写的目标恰好也是一个已有目录，斜杠无法判断它是不是你想去的地方，仍要核对路径；它也不防止覆盖目录内的同名文件，覆盖前询问用 `-i`。

## rm — 删除

**命令名**：`rm` ← **remove**（移除），从原位置删除文件。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-i` | interactive | 每个文件删除前都询问 | 小写 i = 逐个确认 |
| `-I` | interactive（对应一次确认的形式） | 删除超过三个文件或递归删除时，整体询问一次 | 大写 I = 批量前问一次 |
| `-r` / `-R` | recursive | 删除目录及其内部内容 | Recursive = 范围扩展到子目录 |
| `-d` | dir | 可以删除空目录 | Directory = 空目录也能处理 |
| `-f` | force | 不询问，忽略目标不存在的错误 | Force = 少确认；不能绕过权限 |
| `-v` | verbose | 输出删除记录 | Verbose = 看清删了什么 |

默认不删除目录，降低误把目录当成普通文件而整棵删掉的风险。例：`rm -i scratch.txt`。删除不会自动送进桌面回收站；用通配符时，先用 `ls` 核对同一模式的匹配范围。本 Lab 不需要组合 `-rf`。

## cat — 显示文本

**命令名**：`cat` ← **concatenate**（连接、串接）。它可以把多个文件内容顺次输出，如 `cat part1.txt part2.txt`；只给一个文件时，就常用来看内容。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-n` | number | 给所有输出行编号 | Number = 行号 |
| `-b` | number-nonblank | 只给非空行编号，优先于 `-n` | b 联系 blank，空行不计数（助记） |
| `-s` | squeeze-blank | 把连续空行缩成一行 | Squeeze = 挤掉多余空白 |
| `-E` | show-ends | 在每行末尾显示 `$` 标记 | Ends = 看见行尾 |
| `-T` | show-tabs | 把 Tab 显示为 `^I` | Tabs = 看见制表符 |
| `-A` | show-all | 合并显示行尾、Tab 和其他不可打印字符 | All = 把看不见的字符标出来 |

例：`cat -n note.txt` 看行号，`cat -A example.conf` 排查隐藏字符。选项改变的是显示方式，不会修改文件；大日志可以用 `head`、`tail` 或 `grep` 缩小阅读范围。

## head — 看文件开头

**命令名**：**head** 就是英文“头部”，不是缩写，表示看文件前面。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-n 数字` | lines；number 为助记 | 显示开头指定行数，默认 10 行 | n = 数多少行 |
| `-c 数字` | bytes；可用 character 助记 | 显示开头指定字节数，不是中文字数 | c 帮助记字节计数，中文可能占多个字节 |
| `-q` | quiet | 多文件输入时省略文件名标题 | Quiet = 安静一点 |
| `-v` | verbose | 即使只有一个文件也显示文件名标题 | Verbose = 多说文件名 |

例：`head -n 5 app.log`。选择行数可以先看结构，不必把整份文件刷满屏幕。

## tail — 看末尾与跟随日志

**命令名**：**tail** 就是英文“尾部”，不是缩写，表示看文件后面；日志的新内容通常追加在末尾。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-n 数字` | lines；number 为助记 | 显示最后指定行数，默认 10 行；`-n +5` 从第 5 行开始显示到末尾 | n = 控制行数；加号表示起点 |
| `-c 数字` | bytes；可用 character 助记 | 显示末尾指定字节数 | 字节计数，不是中文字数 |
| `-f` | follow | 显示末尾后继续等待新内容 | Follow = 跟着日志走 |
| `-F` | follow=name + retry | 按文件名跟随，并在文件暂时消失时重试，适合日志轮换 | 大写 F = 文件换了还继续找 |
| `-q` | quiet | 多文件输入时省略文件名标题 | Quiet = 少标题 |

例：`tail -n 20 app.log`，`tail -f app.log`。默认看完就退出，只有需要持续监看才加 `-f`；Ctrl+C 停止跟随，不删除日志。

## tar — 打包、查看与解包

**命令名**：`tar` ← **tape archiver**（磁带归档工具），源于早期把文件归档到磁带的用途；现在也常用于普通归档文件。可以记成 t（tape）+ ar（archiver）。[GNU tar 名称说明](https://www.gnu.org/software/tar/manual/tar.html#What-tar-Does)

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-c` | create | 创建归档 | Create = 新建包 |
| `-t` | list；table of contents 为助记 | 列出包内清单，不解包 | Table of contents = 目录表 |
| `-x` | extract | 提取归档中的文件 | eXtract = 取出来 |
| `-f 包名` | file | 指定读写的归档文件 | File = 操作哪个包 |
| `-z` | gzip | 使用 gzip 压缩或解压 | 联系 gzip 中的 z，不硬套首字母 |
| `-v` | verbose | 输出处理的文件；与 `-t` 合用可看权限等细节 | Verbose = 展开细节 |
| `-C 目录` | directory；change directory 为助记 | 在指定位置处理后续文件名，或解包到该位置 | 大写 C = 换个目录操作 |
| `--exclude=模式` | exclude | 创建归档时排除匹配的路径 | Exclude = 排除不想带走的内容 |

`-c`、`-t`、`-x` 选一个动作；`-f` 后接包名。例如 `tar -tzf pack.tar.gz` 先看清单，`tar -xzf pack.tar.gz -C target` 解到已存在的目录，`tar -czf pack.tar.gz notes` 打包。现代 GNU tar 读取普通 gzip 归档文件通常能自动识别压缩格式，`-z` 并非所有读取场景都必须写。

创建时可用 `tar --exclude='*.tmp' -czf pack.tar.gz notes`；这里给模式加引号，是让 tar 自己按模式排除，而不是让 Bash 先展开它。修改源文件不会自动更新旧包，需要重新创建归档。

## chmod — 更改权限

**命令名**：`chmod` ← **change mode**（更改模式），这里主要指文件的权限模式；ch（change）+ mod（mode）。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-R` | recursive | 对目录及其内部文件递归改权限 | Recursive = 改动范围深入每层 |
| `-v` | verbose | 为处理的每个对象输出说明 | Verbose = 都说一遍 |
| `-c` | changes | 只报告实际发生变化的对象 | Changes = 只看改了的 |
| `--reference=文件` | reference | 使用参考文件的权限模式 | Reference = 照着它设 |

权限表达式是操作参数，不是上述选项：u = user（所有者），g = group（组），o = others（其他人），a = all（三类）；r = read（读），w = write（写），x 对应 execute（执行）。`+` 增加，`-` 移除，`=` 指定。

例：`chmod u+x script.sh` 只补所有者执行权限；`chmod 600 example.conf` 设置仅所有者可读写。数值中读=4、写=2、执行=1，三位分别对应所有者、组、其他人，因此 700 表示仅所有者可读写执行。目录的 x 表示可进入或穿过该目录；把目录递归设成 600 会让正常进入受阻，不能把文件权限照搬给整棵目录。

## top — 观察进程

**命令名**：按英文 **top**（顶部、排在前面的）理解，联想“观察排在前面的活跃进程”。这是记忆联想，不把它硬展开成某个首字母缩写；排序可以切换。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-b` | batch | 以批处理文本方式输出，适合保存或供程序读取 | Batch = 不用交互界面 |
| `-n 次数` | iterations；number 为助记 | 达到指定刷新轮数后退出 | n = 数刷新次数，不是行数 |
| `-d 秒数` | delay | 设置刷新间隔，可用小数 | Delay = 隔多久看一次 |
| `-p PID` | pid（process ID） | 只观察指定进程编号；多个编号可用逗号隔开 | PID = 看指定进程 |
| `-u 用户` | filter-only-euser；user 为助记 | 按有效用户筛选进程 | User = 看谁的进程 |
| `-w 宽度` | width | 设置显示宽度，便于批处理输出容纳较长内容 | Width = 横向宽一点 |

例：`top -b -n 1` 输出一轮后退出；只加 `-b` 仍可能持续刷新。交互界面中 q = quit（退出），P 按 CPU 使用率排序，M 按内存使用率排序（memory 助记）；这些是按键，不是命令行参数。[procps top 手册](https://man7.org/linux/man-pages/man1/top.1.html)

## grep — 在文本里找内容（拓展）

**命令名**：源于编辑器命令 **g/re/p**，可拆成 **global / regular expression / print**（全局 / 正则表达式 / 输出）：查找并输出匹配的行。这里 print 指输出到终端，不是调用打印机。[GNU grep 名称说明](https://www.gnu.org/software/grep/manual/grep.html#Introduction)

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-n` | line-number | 显示匹配行的行号 | Number = 定位到哪一行 |
| `-i` | ignore-case | 忽略大小写 | Ignore = 不计较大小写 |
| `-v` | invert-match | 选择不匹配的行 | inVert = 反过来选；不是 verbose |
| `-r` | recursive | 递归搜索目录内文件 | Recursive = 一层层找 |
| `-l` | files-with-matches；list 为助记 | 只输出有匹配的文件名 | List = 哪些文件里有 |
| `-F` | fixed-strings | 把模式当普通字符串，不按正则表达式解释 | Fixed = 按字面找 |
| `-E` | extended-regexp | 使用扩展正则表达式 | Extended = 扩展匹配语法 |
| `-C 行数` | context | 同时显示匹配行前后指定行数 | Context = 带上下文 |

例：`grep -nF 'ERROR' app.log`。默认输出匹配的文本行，`-n` 帮你定位，`-F` 适合先按字面查找。grep 的正则表达式与 Bash 文件名通配符不是同一套规则，不能把两者的 `*` 直接混用。

## find — 按条件查找文件（拓展）

**命令名**：**find** 就是英文“查找”，不是缩写。记成“按名字、类型、时间等条件去找文件”。

这里的 `-name`、`-type` 等是 find 的选项或条件表达式，虽然只有一条横线，后面也是完整单词，不要拆成多个短选项。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-name '模式'` | name | 按文件名模式匹配，区分大小写 | Name = 名字符合什么规律 |
| `-iname '模式'` | insensitive name（助记） | 按文件名模式匹配，不区分大小写 | i = insensitive，不计较大小写 |
| `-type f` / `-type d` | type；file / directory | 只找普通文件 / 目录 | Type = 类型；f 文件，d 目录 |
| `-maxdepth 数字` | maximum depth | 限制遍历深度；起点是第 0 层 | Max depth = 最多往下几层 |
| `-mtime -1` | modification time | 查找距今不足 24 小时修改过的对象；时间按 24 小时段计算，不是“今天零点后” | mtime = 内容修改时间 |
| `-size +10M` | size | 查找大于 10 MiB 的对象，按该单位向上取整比较 | 加号 = 超过这个大小 |

例：`find notes -maxdepth 2 -type f -name '*.txt'`。模式加引号，是把模式交给 find 自己匹配。find 的 `-name '*.txt'` 可以匹配点号开头的名字，不能照搬 Bash 默认忽略隐藏项的规则。

## du — 统计文件与目录占用（拓展）

**命令名**：`du` ← **disk usage**（磁盘使用量），关心“这些文件占了多少”。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-h` | human-readable | 用 K、M、G 等易读单位显示 | Human = 人类易读 |
| `-s` | summarize | 每个指定对象只输出总计 | Summary = 看总数 |
| `-a` | all | 连同文件逐项输出，不只列目录 | All = 每项都看 |
| `-d 深度` | max-depth；depth 为助记 | 限制输出的目录深度，仍统计其下内容 | Depth = 只展开几层 |
| `--apparent-size` | apparent size | 统计逻辑大小，而不是实际磁盘占用 | Apparent = 文件看起来有多大 |

例：`du -sh notes` 看目录总占用，`du -h -d 1 notes` 看一层分类。文件逻辑大小与磁盘实际占用可能不同，所以结果不一定等于把 `ls -l` 的大小直接相加。

## df — 查看文件系统剩余空间（拓展）

**命令名**：`df` ← **disk free**（磁盘空闲空间），关心“这个文件系统还剩多少”，也会显示总量和已用量。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-h` | human-readable | 使用按 1024 换算的易读单位 | Human = 容易看大小 |
| `-H` | si；可用十进制单位助记 | 使用按 1000 换算的单位 | 大写 H 与小写 h 的换算不同 |
| `-T` | print-type | 显示文件系统类型 | Type = 看是什么文件系统 |
| `-i` | inodes | 看 inode 使用量，而非数据块容量 | Inode = 文件记录的容量 |

例：`df -h .` 看当前路径所在文件系统的空间；`du -sh notes` 看某个目录占多少空间。二者回答的问题不同。

## vim — 打开文件与常用按键

**命令名**：`Vim` ← **Vi IMproved**（改进的 Vi 编辑器），V 来自 Vi，IM 来自 Improved。[Vim 官方帮助](https://vimhelp.org/)

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-R` | read-only | 以只读模式打开，避免随手写回；不是系统权限保护 | Read-only = 先只看 |
| `+行号` | 无；启动位置写法 | 打开后定位到指定行，如 `vim +12 note.txt` | 加个位置，直达某行 |

下面这些在 Vim 内使用，不是在 Shell 命令后添加的选项。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `i` | insert | 从普通模式进入插入模式 | Insert = 开始输入文字 |
| `Esc` | escape | 返回普通模式 | 退出输入状态 |
| `:w` / `:q` / `:wq` | write / quit | 保存 / 退出 / 保存并退出，输入后回车 | 先写入，再退出 |
| `:q!` | quit；`!` 不是缩写 | 放弃当前缓冲区未保存的修改后退出 | 感叹号 = 确认不要这些修改 |
| `u` | undo | 普通模式撤销上次改动 | Undo = 撤回 |
| `/词` / `n` | search；next 为助记 | 搜索并回车，n 跳到同方向的下一个匹配 | Next = 接着找 |

普通 `:q` 会阻止丢失未保存的修改；要保存用 `:wq`，确认不需要本次编辑才用 `:q!`。[Vim 编辑说明](https://vimhelp.org/editing.txt.html)

## glob — 通配符补充

`*` 匹配同一层文件名中的零个或多个字符，`?` 匹配一个字符，`[abc]` 匹配方括号中的任一字符。它们不是命令参数，也没有需要硬背的英文缩写。

例如 `ls notes/note-*.txt`：Bash 先展开未加引号的模式，再把匹配的文件名交给 ls。默认不匹配名字开头的点号、不跨越 `/`；没有匹配时通常会原样传给命令。先查看匹配范围，再把同一模式用于复制或删除。

引用方式由“谁负责匹配”决定：`ls notes/*.txt` 让 Bash 展开；`find notes -name '*.txt'` 把模式交给 find；`grep -F '*' note.txt` 则查找字面上的星号。

## sources — 核对方式与参考

编写时核对了本机 WSL 命令帮助；Bash 内置命令用 `help cd`、`help pwd`，外部命令用 `命令 --help`，复杂条件可查本机手册。GNU 网页直接打开曾超时，另从官方手册搜索结果核对了 tar、grep 的名称来源；其余 GNU 链接作为后续参考入口，不声称此次完整读取了全部手册。

- [GNU coreutils 手册](https://www.gnu.org/software/coreutils/manual/coreutils.html)：ls、mkdir、cp、mv、rm、cat、head、tail、chmod、du、df。
- [GNU tar 手册](https://www.gnu.org/software/tar/manual/tar.html)：归档选项。
- [GNU grep 手册](https://www.gnu.org/software/grep/manual/grep.html)、[GNU findutils 手册](https://www.gnu.org/software/findutils/manual/html_mono/find.html)：搜索条件。
- [Bash 手册](https://www.gnu.org/software/bash/manual/bash.html)：目录操作与文件名展开。
- [procps top 手册](https://man7.org/linux/man-pages/man1/top.1.html)、[Vim 帮助](https://vimhelp.org/)：进程工具与编辑器。

本笔记介绍常用行为，不是全部选项清单。拓展工具不属于 Lab 新增必装依赖，也不要求在通关前全部掌握。
