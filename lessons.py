"""Original Chinese teaching material. No network or third-party packages."""

# A single wording source for terminal hints, command cards and feedback.
# Mnemonics are explicitly distinguished from actual long-option names.
OPTION_HELP = {
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

TITLES = ['找到气闸', '保存黑匣子', '清理假信号', '打开救援舱', '读懂最后一条消息',
          '修复中继配置', '交还启动权限', '辨认正在运行的进程', '最后一次投递']
SKILLS = ['cd · ls · mkdir', 'cp', 'mv · rm · * 通配符', 'tar · cat', 'cat · tail',
          'vim', 'chmod · ls', 'top', '综合：复制、移动、删除、编辑、权限、归档']
REWARDS = ['位置锁定', '黑匣子保全', '导航恢复', '救援舱解封', '通信频率确认',
           '中继配置恢复', '中继启动', '遥测恢复', '全员获救']
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
    station = s['station_id']
    cleanup_goal = (
        '导航队列混入了一批假信号，真正的航线也被错误命名。\n'
        '清理规则：只删除 inbox 中名称以 decoy- 开头、以 .tmp 结尾的所有普通文件。\n'
        '除下述需要移动的航线外，保留其他文件及其内容，包括名单、识别指南、传感器缓存和隐藏缓存。\n'
        '这次练习按名称规律批量选择文件：尝试用 * 表达规则，操作前先查看匹配范围。'
        if s.get('cleanup_version', 0) >= 1 else
        '导航队列混入了两份假信号，真正的航线也被错误命名。\n'
        '只删除 inbox 中的 decoy-a.tmp 和 decoy-b.tmp，保留 crew.csv。\n'
        '也可以尝试用 * 按共同名称规律选择这两个文件，操作前先查看匹配范围。')
    tasks = [
        f'''你在失联空间站 {station} 醒来。气闸 airlock 内的定位终端还在闪烁。
终端传来提示：“先找到气闸里的隐藏信标。接下来收到的航线等线索，需要统一
保存在工作区 work 的 evidence 目录里，方便后续修复时查阅。本关先准备好这个
目录，收到线索后再放进去。
本次定位必须在气闸内现场确认。准备好后，请回到 airlock，再提交检查。”

空间站根目录是 station。本关需要完成三件事：
1. 进入 airlock，找出隐藏的 .beacon-XXXX 信标，记下四位数字。
2. 在 station/work 下创建 evidence 目录，作为后续航线等线索的存放处；本关先建好空目录即可。
3. 如果离开了气闸，必须先回到 station/airlock，再运行 lab check 提交。
第一步可以试试 ls，接下来由你探索。
提交位置：station/airlock（不能在 work 或 evidence 里提交本关）。
提交命令：lab check 四位数字（请把“四位数字”替换成你发现的数字）。
检查会同时确认：信标数字正确、work/evidence 已建立、你当前位于 airlock。''',
        '''救援终端：“接下来会动设备。先保存黑匣子，别让原始记录消失。”
目标：完整复制 station/blackbox 目录为 station/work/backup。
包括隐藏的校验文件和子目录；blackbox 原件不能丢失或被改动。
注意最终层级是 work/backup/boot.log，不是 work/backup/blackbox/boot.log。
提交：lab check。现在不需要再输入信标数字。''',
        f'''{cleanup_goal}
目标：把 station/inbox/route.pending 移动并改名为 station/work/evidence/route.txt；
移动后原位置不应再有 route.pending。
提交：lab check。''',
        '''你收到密封救援舱 supplies/rescue.tar.gz。里面有恢复中继所需的文件。
目标：舱内文件完整恢复到 station/work/recovered，保持原始内容，不能多套一层目录。
清单 manifest.txt 记录了本舱的密封码 SEAL，需要你找到它以确认救援舱身份。
提交：lab check 密封码。''',
        '''通信记录中混杂着旧指令和状态消息，过期授权无法恢复中继。
目标：确定当前有效的授权码 CODE，并记下配套的频道 CHANNEL，供后续修复使用。
手头资料：station/work/evidence/route.txt 和 station/logs/comms.log。
提交：lab check 当前有效的授权码。''',
        f'''中继配置 work/recovered/relay.conf 仍停留在维护状态。
目标：配置中的 MODE=rescue，CHANNEL 和 AUTH 分别对应上一关确认的频道与授权码。
STATION={station} 必须保留；配置只包含这四个字段，每个字段各出现一次。
提交：lab check。以保存后的配置为准。''',
        '''配置正确，但启动脚本被撤掉了执行权限。
目标：work/recovered/relay.sh 仅允许所有者读、写、执行；
同目录的 relay.conf 仅允许所有者读、写。两者都不允许组用户和其他用户访问，也不设置特殊权限位。
通过该脚本启动中继，取得它生成的 receipt.txt 回执；保留脚本原始内容。
提交：lab check。只改权限、没有启动成功还不能通过。''',
        '''中继上线了，但你还要从正在运行的进程中认出遥测探针。
先运行 lab load，它会启动最多 90 秒、低占用的练习进程 station-pulse。
目标：从系统中辨认出本局正在运行的 station-pulse，确定它的进程编号 PID。
提交：lab check 这个PID。必须是本局仍然存活的探针，旧 PID 无效。
若已超时，可以重新 lab load。''',
        f'''最终救援窗口已开启。这次只给交付要求，由你决定命令顺序。
可用资料：finale/capsule.tar.gz 中的配置草稿、finale/final.log 中的救援通信记录，
以及 inbox/crew.csv 名单和 work/recovered/receipt.txt 中继回执。

交付物：work/rescue.tar.gz。包内恰有以下三个普通文件（可包含 dispatch 目录条目）：
  dispatch/relay.conf —— MODE=evacuate，STATION={station}；CHANNEL 和 AUTH
  对应最新 FINAL 指令。仅所有者可读写，其余用户无权限，不设置特殊权限位。
  dispatch/crew.csv —— 本局完整船员名单。
  dispatch/receipt.txt —— 本局有效中继回执。
配置只包含上述四个字段，每个字段各出现一次。归档不能夹带草稿或其他文件。
保留 work/backup 黑匣子备份。提交：lab check。
成功后将生成救援凭证和可分享的 JSON 通关报告。''',
    ]
    return tasks[n-1]


HINTS = [
    ['隐藏文件可以用 ls -a 查看；.. 表示上一级。lab root 显示站点根目录。',
     '在 airlock 里，../work/evidence 指向隔壁 work 中的 evidence；mkdir -p 可以补齐父目录。',
     '从站点根目录：cd airlock；ls -a；mkdir -p ../work/evidence；lab check 你看到的数字。'],
    ['先 cd 到站点根目录。目录复制需要递归；不要把文件移动走。',
     'cp -a 源目录 目标目录 可保留整个目录，包括隐藏文件。目标不存在时会以新名称创建。',
     '从站点根目录：cp -a blackbox work/backup；然后 lab check。若 backup 已存在，先检查是否多套了目录。'],
    ['先观察 inbox 的文件名：哪些同时符合任务指定的开头和结尾？相似名称不一定都要删除。',
     '保留固定的开头和结尾，中间变化的部分用 * 代替；它也能匹配空字符串。先用 ls 查看自己写的模式是否只选中了目标。mv 的第二个参数可同时给出新目录和新文件名。',
     '从站点根目录先运行 ls inbox/decoy-*.tmp，核对范围；确认后可用 rm inbox/decoy-*.tmp。航线移动：mv inbox/route.pending work/evidence/route.txt；完成后 lab check。'],
    ['tar -tzf 查看 gzip 归档；tar -xzf 解开。先创建目标目录。',
     '使用 -C work/recovered 指定解压位置，再 cat work/recovered/manifest.txt。',
     '从站点根目录：mkdir -p work/recovered；tar -tzf supplies/rescue.tar.gz；tar -xzf supplies/rescue.tar.gz -C work/recovered；cat work/recovered/manifest.txt；lab check 读到的SEAL。'],
    ['不要逐行翻完整份日志。文件末尾才是最新记录。',
     '先 cat work/evidence/route.txt，再 tail -n 5 logs/comms.log。忽略后面的 HEARTBEAT。',
     '最后一条 READY 同时给出 CHANNEL 和 CODE。把 CODE 作为 lab check 的唯一参数；这两个值也会用于第六关。'],
    ['配置是 KEY=value 文本，等号两边无需空格。先回看 tail -n 5 logs/comms.log。',
     'vim work/recovered/relay.conf；方向键移动，i 插入，Esc 返回普通模式。:q! 可以放弃本次未保存修改。',
     '把 MODE 的 maintenance 改成 rescue，把 CHANNEL 和 AUTH 改为最后 READY 的值。保留 STATION；Esc → :wq → 回车 → lab check。'],
    ['ls -l 的权限列从左至右表示类型、所有者、组和其他人的权限。',
     '700 = 所有者 rwx、其余无权限；600 = 所有者 rw、其余无权限。执行时使用 ./relay.sh。',
     '从站点根目录：cd work/recovered；chmod 700 relay.sh；chmod 600 relay.conf；./relay.sh；lab check。'],
    ['lab load 后再运行 top。top 中 q 退出，P 按 CPU 排序。占用数值会波动。',
     '单次快照可用 top -b -n 1。COMMAND 列找 station-pulse，左侧第一列是 PID。',
     '进程已退出就重新 lab load；使用新一行的 PID 执行 lab check。不要提交文档中的示例数字。'],
    ['先列归档，再解到 work。新频率来自 finale/final.log，不能沿用上一关的 AUTH。',
     '生成归档时可以先 cd work；这样 tar 内成员会以 dispatch/ 开头。tar -tzf 可检查路径。',
     '从站点根目录：tar -xzf finale/capsule.tar.gz -C work；mv work/dispatch/relay.conf.draft work/dispatch/relay.conf；rm work/dispatch/discard.tmp；tail -n 4 finale/final.log；vim work/dispatch/relay.conf；chmod 600 work/dispatch/relay.conf；cp inbox/crew.csv work/recovered/receipt.txt work/dispatch/；cd work；tar -czf rescue.tar.gz dispatch；tar -tzf rescue.tar.gz；lab check。'],
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
    ('ls-a', 'ls-l', 'mkdir-p'), ('cp-a',), ('glob-star', 'glob-preview', 'rm-i', 'rm-r', 'rm-f'),
    ('tar-t', 'tar-x', 'tar-c', 'tar-z', 'tar-f', 'tar-C'),
    ('tail-n', 'tail-f'), ('vim-edit', 'vim-quit', 'vim-undo'),
    ('chmod-mode', 'ls-l'), ('top-keys', 'top-b', 'top-n'),
    ('tar-t', 'tar-v', 'tar-z', 'tar-f'),
]
REFLECTION_OPTION_KEYS = [
    ('ls-a', 'mkdir-p'), ('cp-r', 'cp-a'), ('glob-star', 'glob-preview', 'rm-i'), ('tar-t', 'tar-x', 'tar-C'),
    ('tail-n',), ('vim-edit',), ('chmod-mode',), ('top-keys',),
    ('tar-t', 'tar-v', 'tar-z', 'tar-f'),
]
HINTS = [[explain_options(text, *keys) for text, keys in zip(hints, keysets)]
         for hints, keysets in zip(HINTS, HINT_OPTION_KEYS)]
CARDS = [explain_options(text, *keys) for text, keys in zip(CARDS, CARD_OPTION_KEYS)]
REFLECTIONS = [explain_options(text, *keys)
               for text, keys in zip(REFLECTIONS, REFLECTION_OPTION_KEYS)]

HELP = '''lab                  查看当前任务和进度
lab check [答案]     检查当前关；失败会指出具体缺项，可以重试
lab hint [1|2|3]    逐级提示：方向 → 方法 → 命令骨架（每关单独记录）
lab learn           当前关的命令速查
lab notes [命令]    命令名与参数笔记目录；例如 lab notes ls；all 查看全文
lab status          查看九个系统和通关记录
lab root            显示站点根目录；迷路可用 cd "$(lab root)"
lab load            第八关启动一个限时练习进程
lab stop            停止本局练习进程
lab repair          备份整个现场，并恢复到当前关开始时的文件状态
lab report          查看/导出本局报告
exit                保存退出；再次 bash start.sh 自动续玩
新周目：退出后 bash start.sh --new；new 是“新建”，显式指定才新开一局，默认续玩；旧文件保留

各任务中的 station/... 均指站点根目录内的路径，不是要求你反复创建 station。
每关完成后自动保存检查点。hint 不扣分，失败不回档；没有倒计时和爆炸惩罚。
只记录检查、提示、开始/完成时间；不截取终端输出。Bash 历史仅存在本局目录。
真实 Shell 不是隔离容器，请在练习目录内操作。'''
