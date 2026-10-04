"""Original Chinese teaching material. No network or third-party packages."""
from cli_messages import LAB_SCOPE, native_help
import scenes
from tasks import requirements

# A single wording source for terminal hints, command cards and feedback.
# Mnemonics are explicitly distinguished from actual long-option names.
OPTION_HELP = {
    'dest-dir': '好习惯：把普通文件放进已有目录时，目标末尾写 /，如 mv file.txt notes/。若 notes 不存在或不是目录，就会报错，避免意外改名；有意改名则写完整文件名，不加 /。它不会创建目录，也不能发现选错了另一个已有目录。',
    'glob-star': '* 是通配符，不是命令参数或英文缩写：匹配同一层文件名中的零个或多个字符，方便按共同规律批量选文件。Bash 先把未加引号的模式展开成文件名，再交给命令；默认不匹配名称开头的点号，也不跨越 /。',
    'glob-preview': '例如先用 ls notes/note-*.txt 查看匹配范围，核对后再用同一模式操作。给整个模式加引号会阻止展开；默认没有匹配时，Bash 会把模式原样传给命令，出现“不存在”时先检查目录和拼写。',
    'mkdir-p': 'mkdir -p：p = parents（父级目录），补齐缺少的父目录，已存在也可继续。默认报错有助于发现路径写错；加 -p 才自动补齐，也可以自己逐层创建。',
    'ls-a': 'ls -a：a = all（全部），包括点号开头的隐藏项。默认省略它们，让日常文件列表更清爽；需要检查配置等隐藏项时再主动展开。隐藏不等于权限保护。',
    'ls-l': 'ls -l：l 可按 long（长格式）记，显示权限、大小等详细信息。平时只看名字更简洁，排查权限或核对文件时再增加细节。',
    'cp-r': 'cp -r：r = recursive（递归），把目录里的子目录和文件一起复制。默认不展开目录，避免一次普通复制意外带走大量内容；需要整棵目录时再明确选择。',
    'cp-a': 'cp -a：a = archive（归档式复制），复制目录并尽量保留权限、时间等属性，适合保留原貌的备份。这里不会生成压缩包，a 也不是 ls 中的 all。',
    'rm-i': 'rm -i：i = interactive（交互），每次删除前询问。默认不逐个询问便于批量操作；需要多一次人工核对时加 -i，减少选错文件就直接删除的机会。',
    'rm-r': 'rm -r：r = recursive（递归），删除目录及其内部内容。默认不删除目录，避免把一个目录名误当成普通文件时连带删掉整棵目录；只有明确需要时才扩大删除范围。',
    'rm-f': 'rm -f：f = force（强制），不询问，且忽略目标不存在的错误，适合已核对范围的自动清理；代价是少了确认机会，不适合拿来盲目消除报错。',
    'tar-t': 'tar -t：对应 --list（列清单），可用 table of contents（目录表）助记。先看包里有什么，不会向工作区写入文件。',
    'tar-x': 'tar -x：对应 extract（提取），取出包内文件；与查看分开，便于明确何时向目标目录写入文件。',
    'tar-c': 'tar -c：c = create（创建），生成新归档；与查看、提取分开，明确此次要生成交付包。',
    'tar-z': 'tar -z：对应 gzip，联系 gzip 中的 z 来记。创建时压缩省空间；读取时明确格式，现代 GNU tar 读普通归档文件通常也能自动识别。',
    'tar-f': 'tar -f：f = file（文件），后跟归档名，分清“操作哪个包”和“包里有哪些文件”；不是 rm 的 force 或 tail 的 follow。',
    'tar-C': 'tar -C：对应 --directory，按 change directory（切换目录）记。默认在当前目录操作；指定后无需先手动切换，就能明确操作位置。',
    'tar-v': 'tar -v：v = verbose（详细输出），列包时还能看权限等信息。默认输出较简洁；需要核对细节时再展开，避免大量信息淹没重点。',
    'tail-n': 'tail -n：n 可按 number（数量）记，长选项是 --lines（行数）；后面数字表示看多少行。默认看末尾 10 行，指定数量后能按需要控制阅读范围。',
    'tail-f': 'tail -f：f = follow（跟随），显示末尾内容后继续等待新增日志。默认看完就退出，方便立刻做下一件事；只有需要持续监看时才让终端等着，Ctrl+C 可停止跟随。',
    'top-b': 'top -b：b = batch（批处理），以普通文本输出，适合复制、保存或交给其他程序。默认交互界面方便实时查看；加 -b 才切换到文本输出方式。',
    'top-n': 'top -n：n 可按 number（次数）记，长选项是 --iterations（刷新轮数）。默认持续刷新，指定 1 就在输出一轮后退出；这里的 n 是轮数，不是 tail 的行数。',
    'vim-edit': 'Vim 的 i、:wq 是编辑器内的按键/命令，不是 Shell 参数：i = insert（插入），w = write（写入保存），q = quit（退出）。分开编辑与保存，可以先修改检查，再决定何时写入文件；Esc 返回普通模式。',
    'vim-quit': 'Vim 的 :q! 中 q = quit（退出）；! 是要求放弃未保存修改的符号，不是英文缩写。普通 :q 会阻止带着未保存修改退出，减少丢失编辑内容的风险；确认不要这些修改时才加 !。',
    'vim-undo': 'Vim 的 u = undo（撤销）；搜索后 n 可按 next（下一个匹配）记。这些是编辑器按键，帮助撤回误改或继续查找，不会默认替你反复改变位置。',
    'chmod-mode': 'chmod 权限写法：u = user（所有者），r = read（读），w = write（写），x 对应 execute（执行）。u+x 只增加所有者执行权限，保留其余权限；700/600 则指定仅所有者可读写执行/可读写。这些不是带横线的选项。',
    'top-keys': 'top 中 q = quit（退出）；P 按 CPU 使用率排序，M 按内存使用率排序，M 可联系 memory（内存）记。这些是界面按键而非命令行参数；按需切换排序，方便找出你关心的进程。',
    'lab-new': 'start.sh --new：new 就是“新建”，是本 Lab 自定义的长选项。默认续玩，避免误丢进度；主动指定才建立新周目，旧周目仍保留。',
}


def explain_options(text, *keys):
    if not keys:
        return text
    notes = '\n'.join('  · ' + OPTION_HELP[key] for key in dict.fromkeys(keys))
    return text + '\n参数与用法说明：\n' + notes

# Compatibility names for integrations that only need the fixed skill sequence.
# Student-facing story titles and rewards come from scenes.get(state).
TITLES = ['定位与目录', '完整备份', '整理文件', '恢复归档', '辨认有效记录',
          '编辑配置', '设置权限与执行', '辨认进程', '综合交付']
SKILLS = ['cd · ls · mkdir', 'cp', 'mv · rm · * 通配符', 'tar · cat', 'cat · tail',
          'vim', 'chmod · ls', 'top', '综合：复制、移动、删除、编辑、权限、归档']
REWARDS = ['位置确认', '备份完成', '整理完成', '归档恢复', '有效记录确认',
           '配置完成', '执行成功', '进程确认', '交付完成']
REFLECTIONS = [
    '以 . 开头的名字默认不被 ls 显示；cd 切换目录；mkdir 创建目录。',
    '复制会保留原件；完整的目录备份应包含隐藏文件和子目录，文件层级也要正确。',
    'mv 可以移动或改名，rm 用于删除；整理文件时，要区分需要转移、丢弃和保留的对象。',
    '归档保存了文件及其内部路径；恢复后的目录层级由解包位置和包内路径共同决定。',
    '日志中可能同时存在有效指令、过期记录和状态消息；应按记录规则判断哪条信息有效。',
    '文本编辑器中的修改需要保存到文件后才会生效；配置还要满足字段名称、值和唯一性要求。',
    '权限分别约束所有者、组用户和其他用户；配置可读与脚本可执行是不同需求。',
    'PID 是进程编号；确认目标时还要核对进程身份和存活状态，不能把旧编号当作永久标识。',
    '交付归档有自己的文件内容、内部路径和权限；修改源文件不会自动更新已有归档。列出成员也不等于验证了文件内容。',
]


def brief(n, s):
    task = requirements(n, s)
    scene = scenes.get(s)
    introduction = scene['introductions'][n - 1]
    parts = [scene['background']] if n == 1 else []
    parts.extend([introduction, task])
    return '\n\n'.join(part for part in parts if part)


HINTS = [
    ['先观察隐藏项目；普通目录列表可能省略它们。',
     'ls -a 会包含点号开头的名称，注意区分文件与目录。',
     '观察骨架：ls -a <待观察目录>。目录与信标值由你观察确定。'],
    ['先比较原件与目标备份的直接子项。',
     '完整复制要包含隐藏项和子目录；目标已存在时注意是否多套一层。',
     '观察骨架：ls -la <备份目录>。核对直接子项是否与原件对应。'],
    ['先观察名称规则与必须保留的对象。',
     '用 * 表达中间变化的部分，先预览匹配范围。',
     '观察骨架：ls <你写出的匹配模式>。本步只观察，不删除。'],
    ['先确认包内保存了哪些路径。',
     'tar 的 -t 列成员清单；列清单与提取文件是两个操作。',
     '观察骨架：tar -tzf <归档文件>。对照成员路径判断解包位置。'],
    ['先区分有效业务记录和状态消息。',
     'tail -n 观察末尾若干行；末尾一行未必符合任务的记录类型。',
     '观察骨架：tail -n <行数> <日志文件>。按任务规则辨认记录。'],
    ['先核对磁盘中保存的配置。',
     '配置要分别检查 KEY=value 格式、字段唯一性和取值来源。',
     '观察骨架：cat <配置文件>。逐行核对，暂时不要猜测字段值。'],
    ['先区分配置与脚本的权限需求。',
     'ls -l 能查看所有者、组与其他人的权限。',
     '观察骨架：ls -l <待检查文件>。逐组解释权限位再对照要求。'],
    ['先确认目标进程仍在运行。',
     'top 的 PID 与 COMMAND 是不同列，进程结束后旧编号失效。',
     '观察骨架：top。核对身份和当前编号，按 q 返回终端。'],
    ['先检查交付包内的成员结构。',
     '归档是快照；修改外部文件后，旧包不会自动更新。',
     '观察骨架：tar -tvzf <交付包>。核对成员路径、类型与权限。'],
]

CARDS = [
    'cd 目录：进入目录；cd ..：上一级；pwd：显示当前路径。\nls：查看；ls -a：包括隐藏项目；ls -l：详细信息。\nmkdir -p notes/day1：创建多层目录。绝对路径从 / 开始，相对路径从当前目录开始。',
    'cp a.txt b.txt：复制文件。cp -a folder snapshot：完整复制目录并保留属性。\n目标目录已存在时，源目录会被放到它里面。名称以 . 开头也是普通目录成员。',
    'mv old.txt new.txt：改名；mv new.txt notes/：移动。\nrm scratch.tmp：删除指定文件；rm -i scratch.tmp：先询问。\nnote-*.txt 能匹配 note-.txt 和 note-day1.txt，不匹配 note-day1.csv。\n本关不需要 -r 或 -f。执行前用 ls 确认对象。',
    'tar -tzf pack.tar.gz：只列内容。\ntar -xzf pack.tar.gz -C target：解到已存在的 target。\ntar -czf pack.tar.gz folder：打包压缩 folder。t/x/c 选一；z=gzip，f 后跟归档文件名。\ncat note.txt：显示短文本。',
    'cat file：全部显示。tail -n 5 file：最后五行。\ntail -f file：持续看追加内容；Ctrl+C 停止跟随。\n本关的日志是静态谜题；第八关 lab load 后可对 logs/pulse.log 练 tail -f。',
    'vim file：打开。普通模式用方向键移动；i 进入插入模式。\nEsc 回普通模式；:wq 回车保存退出；:q! 回车放弃修改。\n普通模式 u 撤销，/词 回车搜索，n 下一个匹配。第一次练习只用方向键和 i 即可。',
    'chmod 700 script：所有者 rwx，其余无权限。chmod 600 config：所有者 rw。\nchmod u+x script：给所有者增加执行权限。ls -l 查看结果。\n./script 表示执行当前目录下的程序。不要用 sudo；自己的文件可自行更改权限。',
    'top：持续刷新进程列表；q 退出；P 按 CPU 排序；M 按内存排序。\ntop -b -n 1：输出一次快照。PID 是进程编号，COMMAND 是进程名称。\n练习探针会自动退出，不需要 kill，也不使用真实满载压力测试。',
    '复用前面的命令。tar 记录的是你提供的成员路径；在 work 中打包 dispatch，\n就能得到 dispatch/...，而不是 work/dispatch/...。\ntar -tvzf rescue.tar.gz 同时查看成员名称、类型和权限。',
]

# Keep explanations beside every separately displayed hint/card, including direct
# requests for hint 3. Do not append solution options to default mission briefs.
HINT_OPTION_KEYS = [
    [('ls-a',), ('mkdir-p',), ('ls-a', 'mkdir-p')],
    [(), ('cp-a',), ('cp-a',)],
    [(), ('glob-star', 'glob-preview'), ('glob-star', 'glob-preview')],
    [('tar-t', 'tar-x', 'tar-z', 'tar-f'), ('tar-C',),
     ('mkdir-p', 'tar-t', 'tar-x', 'tar-z', 'tar-f', 'tar-C')],
    [(), ('tail-n',), ()],
    [('tail-n',), ('vim-edit', 'vim-quit'), ('vim-edit',)],
    [('ls-l',), ('chmod-mode',), ('chmod-mode',)],
    [('top-keys',), ('top-b', 'top-n'), ()],
    [(), ('tar-t', 'tar-z', 'tar-f'),
     ('tar-x', 'tar-z', 'tar-f', 'tar-C', 'tail-n', 'chmod-mode', 'tar-c', 'tar-t')],
]
CARD_OPTION_KEYS = [
    ('ls-a', 'ls-l', 'mkdir-p'), ('cp-a',), ('dest-dir', 'glob-star', 'glob-preview', 'rm-i', 'rm-r', 'rm-f'),
    ('tar-t', 'tar-x', 'tar-c', 'tar-z', 'tar-f', 'tar-C'),
    ('tail-n', 'tail-f'), ('vim-edit', 'vim-quit', 'vim-undo'),
    ('chmod-mode', 'ls-l'), ('top-keys', 'top-b', 'top-n'),
    ('tar-t', 'tar-v', 'tar-z', 'tar-f'),
]
REFLECTION_OPTION_KEYS = [
    ('ls-a', 'mkdir-p'), ('cp-r', 'cp-a'), ('dest-dir', 'glob-star', 'glob-preview', 'rm-i'), ('tar-t', 'tar-x', 'tar-C'),
    ('tail-n',), ('vim-edit',), ('chmod-mode',), ('top-keys',),
    ('tar-t', 'tar-v', 'tar-z', 'tar-f'),
]
HINTS = [[explain_options(text, *keys) for text, keys in zip(hints, keysets)]
         for hints, keysets in zip(HINTS, HINT_OPTION_KEYS)]
CARDS = [explain_options(text, *keys) for text, keys in zip(CARDS, CARD_OPTION_KEYS)]
REFLECTIONS = [explain_options(text, *keys)
               for text, keys in zip(REFLECTIONS, REFLECTION_OPTION_KEYS)]

HELP = LAB_SCOPE + '\n\n鼓励查阅原生帮助：' + native_help() + '''。
man 需要本机安装工具和相应手册页；工具参数以本机版本为准。

以下均为本平台辅助功能：
lab                  查看当前任务和进度
lab check [答案]     检查当前关；失败会指出具体缺项，可以重试
lab hint [1|2|3]    逐级提示：方向 → 方法 → 命令骨架（每关单独记录）
lab learn           当前关的命令速查
lab notes [命令]    命令名与参数笔记目录；例如 lab notes ls；all 查看全文
lab status          查看九关任务和通关记录
lab root            显示实验根目录；迷路可用 cd "$(lab root)"
lab load            第八关启动一个限时练习进程
lab stop            停止本局练习进程
lab repair          备份整个现场，并恢复到当前关开始时的文件状态
lab report          查看/导出本局报告
lab concepts        查看本关知识点及其标识
lab tutor ["问题"]  针对最近失败逐级求助；--offline 离线；--topic 指定本关知识点
lab notebook        查看按本局经历整理的学习手册
lab review          查看复习清单；lab review 知识点 看题，再加 A/B/C 作答
lab ai init         创建本地 API 配置；lab ai status 只检查格式，不发送请求
lab tracking on/off  开关本地操作记录（默认关闭，记录命令语义、有限状态与退出码）
lab activity         查看最近操作记录；不记录参数、输出或按键
lab scene            查看可选情境和当前选择
lab scene 名称/本地JSON文件  切换完整叙事；现有周目的文件名保持，避免移动学生文件
lab scene --generate "任意主题" [--output 路径]  按新主题另行生成可复用的本地情境 JSON
exit                保存退出；再次 bash start.sh 自动续玩
新周目：退出后 bash start.sh --new；new 是“新建”，显式指定才新开一局，默认续玩；旧文件保留
首次进入或新周目：先回答想学的主题，由已配置的模型生成情境与题面，再开始练习；续玩不重问
离线选择：bash start.sh --new --scene 名称/JSON文件，按已有情境及其文件命名启动新周目

各任务中的实验根目录名称指本局根目录，不是要求你反复创建同名目录。
每关完成后自动保存检查点。hint 不扣分，失败不回档；没有倒计时和爆炸惩罚。
记录检查、提示、复习与时间；不截取终端输出。Bash 历史仅存在本局目录。
lab 是本实验的辅助命令；ls、cp、vim 等保持原生 Linux 行为。
新周目的主题生成、lab scene --generate 和启用 API 的 lab tutor 会使用本地 API 配置联网；不上传存档或终端历史。
真实 Shell 不是隔离容器，请在练习目录内操作。'''
