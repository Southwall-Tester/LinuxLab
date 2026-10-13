"""Versioned, scene-independent independent assessments using real Linux files.

The manifest is private instructor state. Only catalog metadata, prompt, scope and
required_commands are learner-facing. Grading never executes a learner file and
never extracts a submitted archive. Command observations are enforced by the
assessment coordinator, separately from the artifact checks returned here.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import time

SCHEMA_VERSION = 1
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
MAX_ENTRIES = 512

_FAMILIES = {
    'paths': [('parent', '相对路径的父目录'), ('case', '路径大小写与起点'), ('nested', '多层路径导航')],
    'hidden': [('file', '发现隐藏文件'), ('directory', '发现隐藏目录'), ('contrast', '区分隐藏与普通同名线索')],
    'mkdir': [('parents', '补齐多层父目录'), ('siblings', '已有父目录下创建并列目录'), ('space', '含空格路径的目录创建')],
    'copy': [('new_target', '复制到尚不存在的目标'), ('existing_target', '已有目标中的完整内容复制'), ('selective', '选择性复制与保留属性')],
    'move': [('rename', '文件改名'), ('existing_directory', '移入已有目录'), ('directory_rename', '嵌套目录整体移动并改名')],
    'glob': [('suffix', '后缀筛选与隐藏项保留'), ('single_digit', '单字符范围匹配'), ('zero_width', '星号的零字符匹配')],
    'archive_read': [('nested', '保留归档成员的相对层级'), ('strip', '去掉归档的首层目录'), ('selective', '选择性恢复一个归档成员')],
    'logs': [('latest', '状态消息之后的最新有效记录'), ('filtered', '按设备选择有效记录'), ('timestamp', '乱序日志按时间选择记录')],
    'config': [('duplicate', '消除重复配置键'), ('syntax', '修正配置语法并保留字段'), ('active_file', '区分模板与生效配置')],
    'editing': [('append', 'Vim 插入与保存'), ('replace', 'Vim 定点修改并保存'), ('discard', 'Vim 保存产物与放弃修改语义')],
    'permissions': [('private', '私有文件最小权限'), ('shared', '分组读取与目录穿越权限'), ('executable', '区分脚本与配置权限')],
    'execution': [('direct', '直接运行脚本并确认结果'), ('argument', '传参运行并核对返回产物'), ('working_directory', '工作目录影响执行结果的位置')],
    'process': [('shell_identity', '确认当前终端进程身份'), ('child_identity', '确认后台进程与父进程'), ('child_state', '确认运行状态与进程生命周期')],
    'archive_build': [('contents', '归档内容不额外套目录'), ('wrapper', '交付包保留指定首层目录'), ('snapshot', '源文件修订后更新归档快照')],
    'integrity': [('backup', '制作完整备份并保留原件'), ('restore', '保护损坏现场后恢复副本'), ('compare', '比较内容并恢复正确版本')],
}


def catalog():
    """Return fresh public task records, never private expected answers."""
    return [dict(id=f'{topic}.{family}.v1', topic=topic, title=title,
                 family=family, version=1, duration_seconds=120 if topic != 'process' else 90,
                 slip=.05, guess=.20, objectives=[f'{topic}:core'],
                 kind='assessment',
                 response_kind='observation' if topic in {'paths', 'hidden', 'logs', 'process'} else 'artifact')
            for topic, families in _FAMILIES.items() for family, title in families]


def _digest(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()


def _relative(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('invalid relative path')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {'.', '..'} for part in path.parts) or ':' in value:
        raise ValueError('invalid relative path')
    return path


def _path(root, relative):
    return root.joinpath(*_relative(relative).parts)


def _safe_tree(root):
    """Reject links/special objects and bound traversal before any content read."""
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError('练习目录缺失或不是普通目录')
    count, total = 0, 0
    pending = [root]
    while pending:
        directory = pending.pop()
        for child in directory.iterdir():
            info = child.lstat()
            count += 1
            if count > MAX_ENTRIES:
                raise ValueError('练习目录项目过多')
            if stat.S_ISDIR(info.st_mode):
                pending.append(child)
            elif stat.S_ISREG(info.st_mode):
                total += info.st_size
                if info.st_nlink > 1 or info.st_size > MAX_FILE or total > MAX_TOTAL:
                    raise ValueError('练习文件超出安全大小或包含硬链接')
            else:
                raise ValueError('练习目录含符号链接或不支持的特殊文件')


def _read(root, relative):
    """Use no-follow open-at traversal on Linux to avoid symlink races."""
    parts = _relative(relative).parts
    if os.name == 'posix':
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        directory_fd = os.open(root, flags | os.O_DIRECTORY)
        try:
            for part in parts[:-1]:
                next_fd = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = next_fd
            fd = os.open(parts[-1], flags, dir_fd=directory_fd)
        finally:
            os.close(directory_fd)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1 or info.st_size > MAX_FILE:
                raise ValueError('unsupported file')
            content = handle.read(MAX_FILE + 1)
    else:
        path = _path(root, relative)
        if any(p.is_symlink() for p in [path, *list(path.parents)[:len(parts)]]):
            raise ValueError('unsupported link')
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1 or info.st_size > MAX_FILE:
            raise ValueError('unsupported file')
        content = path.read_bytes()
    if len(content) > MAX_FILE:
        raise ValueError('file too large')
    return content


def _proc(pid):
    """Read only fixed, bounded Linux process metadata (never learner paths)."""
    if not isinstance(pid, int) or pid < 1 or pid > 2 ** 31 - 1:
        raise ValueError('invalid pid')
    proc_root = Path('/proc') / str(pid)
    with (proc_root / 'stat').open('rb') as handle:
        raw = handle.read(4096).decode('utf-8')
    end = raw.rindex(')')
    fields = raw[end + 2:].split()
    with (proc_root / 'cmdline').open('rb') as handle:
        command = handle.read(4096).decode('utf-8').split('\x00')
    return dict(pid=pid, name=raw[raw.index('(') + 1:end], state=fields[0],
                parent=int(fields[1]), started=int(fields[19]), uid=proc_root.stat().st_uid,
                command=[arg for arg in command if arg])


def _archive(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, body in entries.items():
            data = body.encode('utf-8')
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def create(task_id, root: Path, seed: str):
    """Create exactly one task in a new/empty directory; no student execution."""
    selected = next((item for item in catalog() if item['id'] == task_id), None)
    if selected is None:
        raise ValueError('unknown assessment task')
    root = Path(root).absolute()
    if root.is_symlink() or any(part.is_symlink() for part in root.parents):
        raise ValueError('练习目录及父目录不能是符号链接')
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError('短测只能创建在新的空目录')
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    token = _digest(f'{task_id}:{seed}')[:12]
    alternate = _digest(f'other:{task_id}:{seed}')[:12]
    manifest = dict(selected, schema_version=SCHEMA_VERSION, root=str(root),
                    required_commands=[], scope='验证本题明确列出的操作与理解目标；命令观察、帮助使用和系统掌握决策分别记录。',
                    private={'checks': []})
    checks = manifest['private']['checks']

    def write(name, body, mode=0o644):
        path = _path(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body if isinstance(body, bytes) else body.encode('utf-8'))
        path.chmod(mode)

    def check(kind, label, **kwargs):
        checks.append(dict(id=f'c{len(checks) + 1}', kind=kind, label=label, **kwargs))

    def content(name, body, label='要求的文件内容完整且正确'):
        check('content', label, path=name, digest=_digest(body))

    def preserve(name, body):
        write(name, body)
        content(name, body, '指定保留的原件或旁侧文件保持完整')

    def absent(name):
        check('absent', '不应存在的源路径或多余项目已移除', path=name)

    def directory(name):
        check('directory', '要求的目录结构已创建', path=name)

    def answer(value, label='观察结果或理解短答正确'):
        check('answer', label, value=value)

    topic, family = selected['topic'], selected['family']
    if topic == 'paths':
        target, start = {
            'parent': ('base/shared/code.txt', 'base/work'),
            'case': ('Lab/report/code.txt', 'lab/report'),
            'nested': ('tree/target/deep/code.txt', 'tree/start/inner'),
        }[family]
        write(target, token + '\n')
        _path(root, start).mkdir(parents=True, exist_ok=True)
        if family == 'case':
            write('lab/report/code.txt', alternate + '\n')
        relative = os.path.relpath(_path(root, target), _path(root, start)).replace('\\', '/')
        manifest['prompt'] = (f'先进入 {start}；从此处沿相对路径 {relative} 读取 code.txt。'
                              f'然后停留在该文件所在目录提交，短答只填文件中的值。')
        content(target, token + '\n', '观察文件保持原样')
        check('cwd', '提交时工作目录对应目标文件所在目录', path=str(PurePosixPath(target).parent))
        answer(token)
        manifest['required_commands'] = ['cd']
    elif topic == 'hidden':
        target = {'file': '.access', 'directory': '.vault/code.txt', 'contrast': '.record'}[family]
        write(target, token + '\n')
        write('record' if family == 'contrast' else 'visible.txt', alternate + '\n')
        manifest['prompt'] = {
            'file': '枚举本目录的隐藏项目，读取隐藏普通文件的值并提交短答。',
            'directory': '本目录有一个隐藏目录，进入其中读取 code.txt 的值并提交短答。',
            'contrast': '本目录有 record 和它的隐藏对应文件；仅提交隐藏对应文件的值。',
        }[family]
        content(target, token + '\n', '隐藏观察文件保持原样')
        answer(token)
        manifest['required_commands'] = ['ls']
    elif topic == 'mkdir':
        preserve('keep.txt', 'keep-' + token + '\n')
        paths = {'parents': ['course/week1/notes'],
                 'siblings': ['existing/notes', 'existing/reports'],
                 'space': ['project files/day 1/notes']}[family]
        if family == 'siblings':
            preserve('existing/history.txt', 'history\n')
        for name in paths:
            directory(name)
        manifest['prompt'] = '创建这些目录：' + '、'.join(paths) + '。保留已有文件。'
        manifest['required_commands'] = ['mkdir']
    elif topic == 'copy':
        for name, body in [('data.txt', token + '\n'), ('.settings', 'hidden\n'), ('sub/note.txt', 'nested\n')]:
            preserve('source/' + name, body)
            if family != 'selective' or name != 'data.txt':
                content('backup/' + name, body)
        if family == 'existing_target':
            preserve('backup/keep.txt', 'keep\n')
        if family == 'selective':
            _path(root, 'source/.settings').chmod(0o600)
            check('mode', '隐藏配置的权限在副本中保留', path='backup/.settings', mode=0o600)
            absent('backup/data.txt')
            manifest['prompt'] = '只复制 source/.settings 和 source/sub 到 backup，保持原层级与 .settings 的权限。不要复制 data.txt，保留全部原件。'
        else:
            manifest['prompt'] = ('将 source 的全部内容完整复制到 backup，包含隐藏文件和子目录；backup 内直接出现 data.txt，'
                                  '不要额外套 source 目录。保留原件和目标中已有文件。')
        absent('backup/source')
        manifest['required_commands'] = ['cp']
    elif topic == 'move':
        source, destination = {'rename': ('draft.txt', 'final.txt'),
                               'existing_directory': ('draft.txt', 'archive/draft.txt'),
                               'directory_rename': ('draft/nested/data.txt', 'archive/final/nested/data.txt')}[family]
        write(source, token + '\n')
        preserve('archive/keep.txt' if family != 'rename' else 'keep.txt', 'keep\n')
        content(destination, token + '\n')
        absent('draft' if family == 'directory_rename' else source)
        manifest['prompt'] = {'rename': '将 draft.txt 改名为 final.txt，保留内容和 keep.txt。',
                              'existing_directory': '将 draft.txt 移入已有 archive 目录；保留 archive/keep.txt，原位置不再保留 draft.txt。',
                              'directory_rename': '将整个 draft 目录移入 archive 并改名为 final，保持内部层级与内容，保留 archive/keep.txt。'}[family]
        manifest['required_commands'] = ['mv']
    elif topic == 'glob':
        remove, keep, requirement = {
            'suffix': (['a.tmp', 'b.tmp'], ['.hidden.tmp', 'a.tmp.keep', 'save.txt'], '删除当前目录所有非隐藏的 .tmp 后缀文件'),
            'single_digit': (['part-1.txt', 'part-8.txt'], ['part-10.txt', 'part-x.txt', '.part-2.txt'], '删除名称为 part- 加一个数字再加 .txt 的非隐藏文件'),
            'zero_width': (['note-.txt', 'note-a.txt'], ['note.txt', '.note-a.txt', 'note-a.csv'], '删除匹配 note-*.txt 的非隐藏文件，注意 * 也可匹配零个字符'),
        }[family]
        for name in remove:
            write(name, 'remove\n')
            absent(name)
        for name in keep:
            preserve(name, 'keep-' + token + '\n')
        preserve('nested/' + remove[0], 'nested-keep\n')
        manifest['prompt'] = requirement + '；只处理当前目录，保留所有其他文件及 nested 目录内容。先预览匹配范围。'
        manifest['required_commands'] = ['rm']
    elif topic == 'archive_read':
        entries = {'bundle/docs/readme.txt': token + '\n', 'bundle/.config': 'hidden\n', 'bundle/extra.txt': 'extra\n'}
        package = _archive(entries)
        preserve('input.tar.gz', package)
        preserve('restore/keep.txt', 'keep\n')
        if family == 'nested':
            for name, body in entries.items():
                content('restore/' + name, body)
            manifest['prompt'] = '先列出 input.tar.gz 的成员，再解包到已有 restore 中，保留包内 bundle 层级以及 restore/keep.txt。'
        elif family == 'strip':
            for name, body in entries.items():
                content('restore/' + name.removeprefix('bundle/'), body)
            absent('restore/bundle')
            manifest['prompt'] = '将 input.tar.gz 恢复到 restore，去掉包内首层 bundle；restore 下应直接出现 docs、.config、extra.txt。保留 keep.txt。'
        else:
            content('restore/bundle/docs/readme.txt', token + '\n')
            absent('restore/bundle/.config')
            absent('restore/bundle/extra.txt')
            manifest['prompt'] = '从 input.tar.gz 只恢复 bundle/docs/readme.txt 到 restore，并保留该成员的完整层级；不要提取其他成员，保留 keep.txt。'
        manifest['required_commands'] = ['tar']
    elif topic == 'logs':
        records = {
            'latest': f'10:00 READY value={alternate}\n10:01 READY value={token}\n10:02 HEARTBEAT value=none\n',
            'filtered': f'10:00 device=A READY value={token}\n10:01 device=B READY value={alternate}\n10:02 device=A ERROR value=none\n',
            'timestamp': f'10:03 READY value={token}\n10:01 READY value={alternate}\n10:04 HEARTBEAT value=none\n10:02 READY value=older\n',
        }[family]
        preserve('events.log', records)
        manifest['prompt'] = {'latest': '读取 events.log，提交按日志行顺序最后一条 READY 记录的 value；HEARTBEAT 不是 READY。',
                              'filtered': '读取 events.log，提交 device=A 的最新 READY 记录的 value；其他设备及 ERROR 均不满足条件。',
                              'timestamp': 'events.log 的行顺序被打乱。按同一天 HH:MM 时间，提交最新 READY 记录的 value。'}[family]
        answer(token)
    elif topic == 'config':
        desired = f'MODE=training\nTOKEN={token}\nRETRIES=3\n'
        preserve('requirements.txt', desired)
        target = 'active/app.conf' if family == 'active_file' else 'app.conf'
        write(target, {'duplicate': f'MODE=old\nTOKEN={alternate}\nTOKEN={token}\nRETRIES=3\n',
                       'syntax': f'MODE:training\nTOKEN {alternate}\nRETRIES=3\n',
                       'active_file': f'MODE=old\nTOKEN={alternate}\nRETRIES=1\n'}[family])
        if family == 'active_file':
            preserve('templates/app.conf', desired)
        check('config', '生效配置键唯一、语法正确且所有值符合要求', path=target,
              values={'MODE': 'training', 'TOKEN': token, 'RETRIES': '3'})
        manifest['prompt'] = f'按 requirements.txt 修正 {target}。每个键恰好一次、使用 KEY=value、只含指定三个键。保留参考文件' + ('和 templates/app.conf。' if family == 'active_file' else '。')
    elif topic == 'editing':
        initial, expected, question, response = {
            'append': ('heading\n', 'heading\n' + token + '\n', 'Esc 从插入模式返回哪种模式？用英文 normal/insert/command 中的一个词回答。', 'normal'),
            'replace': ('first\nreplace-me\nlast\n', 'first\n' + token + '\nlast\n', '只写入磁盘而不退出 Vim 的命令是什么？回答 :w、:q 或 :q!。', ':w'),
            'discard': ('keep-original\n', 'keep-original\n' + token + '\n', 'Vim 执行 :q! 后，未保存的缓冲区修改被保存还是丢弃？回答 save 或 discard。', 'discard'),
        }[family]
        write('notes.txt', initial)
        preserve('instruction.txt', token + '\n')
        content('notes.txt', expected, 'Vim 任务要求的修改已正确保存到磁盘')
        answer(response, 'Vim 模式或保存语义理解正确')
        action = {'append': '将 instruction.txt 中的值追加为 notes.txt 第二行，保留首行，保存退出。',
                  'replace': '只把 notes.txt 第二行替换为 instruction.txt 中的值，首末行不变，保存退出。',
                  'discard': '将 instruction.txt 的值追加为 notes.txt 第二行，保留首行并保存退出。理解短答考查放弃未保存修改的语义。'}[family]
        manifest['prompt'] = '使用 Vim 编辑：' + action + ' 提交时同时回答：' + question
        manifest['required_commands'] = ['vim']
        manifest['scope'] = '检查 Vim 启动观察、指定磁盘修改和一道模式/保存理解题；中途缓冲区变化和放弃操作不在自动观察范围内。'
    elif topic == 'permissions':
        files = {'private': [('secret.conf', 0o600)],
                 'shared': [('shared/report.txt', 0o640), ('shared', 0o750)],
                 'executable': [('runner.sh', 0o750), ('runner.conf', 0o640)]}[family]
        for name, mode in files:
            if name == 'shared':
                _path(root, name).chmod(0o755)
            else:
                preserve(name, 'data-' + token + '\n')
            check('mode', '文件或目录满足最小权限要求', path=name, mode=mode)
        manifest['prompt'] = {'private': '设置 secret.conf：仅所有者可读写，组和其他人无权限；不改变内容。',
                              'shared': '设置 shared/report.txt：所有者读写、组只读、其他人无权限；shared 目录所有者 rwx、组 r-x、其他人无权限。不改变文件内容。',
                              'executable': '设置 runner.sh：所有者 rwx、组 r-x、其他人无权限；runner.conf：所有者读写、组只读、其他人无权限。保留两者内容。'}[family]
        manifest['required_commands'] = ['chmod']
    elif topic == 'execution':
        script = "#!/bin/sh\nset -eu\n"
        if family == 'argument':
            script += f'[ "${{1:-}}" = "{alternate}" ] || exit 2\n'
            preserve('argument.txt', alternate + '\n')
        script += f"printf '%s\\n' '{token}' > receipt.txt\n"
        target = 'bin/run.sh' if family == 'working_directory' else 'run.sh'
        preserve(target, script)
        check('executable', '脚本已具备所有者执行权限', path=target)
        receipt = 'run/receipt.txt' if family == 'working_directory' else 'receipt.txt'
        content(receipt, token + '\n', '执行产生的回执内容和位置符合要求')
        if family == 'working_directory':
            _path(root, 'run').mkdir()
            absent('receipt.txt')
        manifest['prompt'] = {'direct': '保持 run.sh 内容不变，授予所有者执行权限并直接运行；确认当前目录产生 receipt.txt。',
                              'argument': '保持 run.sh 内容不变，授予所有者执行权限；读取 argument.txt，将其中的值作为唯一参数直接运行脚本，生成 receipt.txt。',
                              'working_directory': '保持 bin/run.sh 内容不变，授予所有者执行权限；进入 run 目录后直接运行 ../bin/run.sh，使回执只出现在 run/receipt.txt。'}[family]
        manifest['required_commands'] = ['run.sh']
    elif topic == 'process':
        if os.name != 'posix' or not Path('/proc/self/stat').exists():
            raise OSError('进程短测需要 Linux / WSL 的 /proc')
        parent = _proc(os.getppid())
        manifest['private']['shell'] = {key: parent[key] for key in ('pid', 'started', 'uid', 'name', 'state')}
        manifest['private']['created_ticks'] = int(time.clock_gettime(
            getattr(time, 'CLOCK_BOOTTIME', time.CLOCK_MONOTONIC)) * os.sysconf('SC_CLK_TCK'))
        if family == 'shell_identity':
            manifest['prompt'] = ('在启动本次短测的同一终端，用 ps 或 top 观察当前 shell，'
                                  '提交两个字段：当前 shell 的 PID 和 COMMAND 名称（空格分隔）。')
        elif family == 'child_identity':
            manifest['prompt'] = ('在同一终端自行启动一个 sleep 120 后台进程，用 ps 观察其身份。'
                                  '提交两个整数：该进程 PID 和 PPID。提交后自行结束该练习进程。')
        else:
            manifest['prompt'] = ('在同一终端自行启动一个 sleep 180 后台进程，用 ps 观察当前状态。'
                                  '提交 PID 和单字母状态（空格分隔）；需是当前仍存活、处于可中断睡眠的练习进程。'
                                  '不要用旧 PID，提交后自行结束该练习进程。')
        check('process', '当前进程身份、归属与本题要求一致', family=family)
        manifest['required_commands'] = ['ps', 'top'] if family == 'shell_identity' else ['ps']
        manifest['scope'] = '只读核对当前 Linux 进程元数据；本模块不启动、终止进程或执行学生代码。'
    elif topic == 'archive_build':
        entries = {'report.txt': token + '\n', '.settings': 'hidden\n', 'sub/data.txt': 'nested\n'}
        for name, body in entries.items():
            preserve('package/' + name, body)
        archive_entries = {('package/' + name if family == 'wrapper' else name): {'digest': _digest(body), 'mode': 0o644}
                           for name, body in entries.items()}
        if family == 'snapshot':
            write('delivery.tar.gz', _archive({'report.txt': alternate + '\n'}))
            _path(root, 'package/.settings').chmod(0o600)
            archive_entries['.settings']['mode'] = 0o600
        check('archive', '交付包成员层级、内容及权限符合要求', path='delivery.tar.gz', entries=archive_entries)
        manifest['prompt'] = {'contents': '将 package 内所有内容（含隐藏项）打成 delivery.tar.gz；包内直接包含 report.txt、.settings、sub/data.txt，不套 package。保留源文件及权限。',
                              'wrapper': '将 package 整个目录打成 delivery.tar.gz；所有文件成员必须位于 package/ 下，包含隐藏项与子目录，保留源文件及权限。',
                              'snapshot': '现有 delivery.tar.gz 已过时；按当前 package 重新生成它，包内直接包含所有内容而不套 package。包含隐藏项，并保留 .settings 当前的 600 权限和其他文件权限。'}[family]
        manifest['required_commands'] = ['tar']
    elif topic == 'integrity':
        if family == 'backup':
            for name, body in [('data.txt', token + '\n'), ('.config', 'hidden\n'), ('sub/note.txt', 'nested\n')]:
                preserve('original/' + name, body)
                content('backup/' + name, body)
            manifest['prompt'] = '完整备份 original 的内容到 backup（backup 内直接出现 data.txt 等），保留原件、隐藏项与子目录。'
        elif family == 'restore':
            preserve('backup/data.txt', token + '\n')
            write('work/data.txt', 'damaged-' + alternate + '\n')
            content('recovery/data.txt', 'damaged-' + alternate + '\n', '恢复前的损坏现场已被保留')
            content('work/data.txt', token + '\n', '工作副本已从备份恢复')
            manifest['prompt'] = '先将 work/data.txt 当前损坏内容保存在 recovery/data.txt，再用 backup/data.txt 恢复工作副本；不得修改备份。'
        else:
            preserve('reference.txt', token + '\n')
            preserve('versions/one.txt', alternate + '\n')
            preserve('versions/two.txt', token + '\n')
            write('work.txt', 'wrong\n')
            content('work.txt', token + '\n')
            manifest['prompt'] = '比较 versions 中两个文件与 reference.txt 的实际内容，将内容一致的版本复制为 work.txt。保留参考与两个版本文件。'
        manifest['required_commands'] = ['cp']
    return manifest


def _check_archive(data, entries):
    if not data.startswith(b'\x1f\x8b'):
        return False
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as zipped:
        unpacked = zipped.read(MAX_TOTAL + 1)
    if len(unpacked) > MAX_TOTAL:
        return False
    found, names = {}, set()
    allowed_dirs = {'.'}
    for name in entries:
        allowed_dirs.update(str(parent) for parent in PurePosixPath(name).parents)
    with tarfile.open(fileobj=io.BytesIO(unpacked), mode='r:') as archive:
        for index, member in enumerate(archive):
            if index >= 128 or member.size > MAX_FILE or member.size < 0:
                return False
            name = member.name
            while name.startswith('./'):
                name = name[2:]
            name = name.rstrip('/') or '.'
            if name in names:
                return False
            names.add(name)
            if member.isdir():
                if name not in allowed_dirs:
                    return False
                continue
            if (not member.isfile() or member.sparse is not None or name not in entries
                    or _relative(name).as_posix() != name):
                return False
            handle = archive.extractfile(member)
            if handle is None:
                return False
            body = handle.read(MAX_FILE + 1)
            found[name] = {'digest': _digest(body), 'mode': stat.S_IMODE(member.mode)}
    return found == entries


def _check_process(manifest, item, answer):
    parts = answer.strip().split()
    if len(parts) != 2 or not parts[0].isdigit():
        return False
    process = _proc(int(parts[0]))
    shell = manifest['private']['shell']
    live_shell = _proc(shell['pid'])
    if (live_shell['started'], live_shell['uid']) != (shell['started'], shell['uid']):
        return False
    if item['family'] == 'shell_identity':
        return process['pid'] == shell['pid'] and parts[1] == process['name']
    command = process['command']
    duration = '120' if item['family'] == 'child_identity' else '180'
    if (len(command) != 2 or Path(command[0]).name != 'sleep' or command[1] != duration
            or process['parent'] != shell['pid'] or process['uid'] != shell['uid']
            or process['started'] < manifest['private']['created_ticks'] - 1
            or process['state'] in {'Z', 'X'}):
        return False
    if item['family'] == 'child_identity':
        return parts[1].isdigit() and int(parts[1]) == process['parent']
    return parts[1] == process['state'] == 'S'


def evaluate(manifest, root: Path, answer='', cwd=None):
    """Read-only artifact results. No answer values are returned in feedback."""
    root = Path(root).absolute()
    if manifest.get('schema_version') != SCHEMA_VERSION or str(root.resolve()) != manifest.get('root'):
        return dict(passed=False, checks=[], feedback='短测环境与任务不一致，请重新打开本次短测。', technical_error=True)
    if manifest.get('topic') == 'process':
        try:
            shell = manifest['private']['shell']
            current = _proc(shell['pid'])
            terminal_available = (os.getppid() == shell['pid'] and current['state'] not in {'Z', 'X'}
                                  and current['started'] == shell['started']
                                  and current['uid'] == shell['uid'])
        except (OSError, ValueError, KeyError):
            terminal_available = False
        if not terminal_available:
            return dict(passed=False, checks=[], technical_error=True,
                        feedback='原短测终端已结束或已切换终端；lab assess abandon 后 lab assess process 在当前终端重开。')
    try:
        _safe_tree(root)
    except (OSError, ValueError):
        return dict(passed=False, checks=[dict(id='workspace_safety', label='练习目录只含限额内的普通文件和目录', passed=False)],
                    feedback='请将练习目录恢复为普通文件和目录，并检查文件数量与大小。', technical_error=False)
    results = []
    for item in manifest['private']['checks']:
        passed = False
        try:
            kind = item['kind']
            if kind == 'content':
                passed = _digest(_read(root, item['path'])) == item['digest']
            elif kind == 'absent':
                passed = not _path(root, item['path']).exists()
            elif kind == 'directory':
                passed = _path(root, item['path']).is_dir()
            elif kind == 'answer':
                passed = str(answer).strip() == item['value']
            elif kind == 'cwd':
                passed = cwd is not None and Path(cwd).resolve() == _path(root, item['path']).resolve()
            elif kind in {'mode', 'executable'}:
                if os.name != 'posix':
                    return dict(passed=False, checks=results, feedback='权限短测需要 Linux / WSL 原生权限。', technical_error=True)
                mode = stat.S_IMODE(_path(root, item['path']).stat().st_mode)
                passed = mode == item['mode'] if kind == 'mode' else bool(mode & stat.S_IXUSR)
            elif kind == 'config':
                lines = _read(root, item['path']).decode('utf-8').splitlines()
                values = {}
                valid = True
                for line in lines:
                    if not re.fullmatch(r'[A-Z_]+=[^=\s]+', line):
                        valid = False
                        break
                    key, value = line.split('=', 1)
                    if key in values:
                        valid = False
                    values[key] = value
                passed = valid and values == item['values']
            elif kind == 'archive':
                passed = _check_archive(_read(root, item['path']), item['entries'])
            elif kind == 'process':
                passed = _check_process(manifest, item, str(answer))
            else:
                return dict(passed=False, checks=results, feedback='任务合同包含未知检查类型。', technical_error=True)
        except (OSError, ValueError, KeyError, UnicodeError, tarfile.TarError, EOFError):
            passed = False
        results.append(dict(id=item['id'], label=item['label'], passed=bool(passed)))
    passed = bool(results) and all(item['passed'] for item in results)
    feedback = '本题产物与理解检查已通过。' if passed else '尚未通过：' + '；'.join(dict.fromkeys(item['label'] for item in results if not item['passed']))
    return dict(passed=passed, checks=results, feedback=feedback, technical_error=False)
