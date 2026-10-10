#!/usr/bin/env python3
"""LinuxLab: a local, state-based Linux teaching lab (Python 3.9+)."""
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone

from lessons import SKILLS, REFLECTIONS, HINTS, CARDS, HELP, brief, explain_options
from terminal_notes import render_markdown
from cli_messages import (InputError, LabParser, USAGE, unknown_lab_command,
                          unknown_topic, shell_lookup_error, runtime_error, LAB_SCOPE, native_help)
from knowledge import CONCEPTS, PHASE_CONCEPTS, feedback
import learning
import pliac_bridge
import ai_tutor
import activity
import scenes
import layout
import scene_generator
import tasks
import error_patterns

APP = Path(__file__).resolve().parent
VERSION = '2.0.0'
PRODUCT_NAME = 'LinuxLab'
# Storage identifiers and ORBIT_* variables remain compatible with old rounds.
MARKER = 'orbit-linux-lab-v1'


class LabError(Exception):
    def __init__(self, message, code='unknown', facts=None):
        super().__init__(message)
        self.code = code
        self.facts = facts or []


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def atomic_json(path, data):
    if path.is_symlink():
        raise LabError('存档路径不能是符号链接。')
    temp = path.with_name(path.name + '.' + secrets.token_hex(4) + '.tmp')
    with temp.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def safe_path(root, rel):
    """Check each component, including dangling symlinks, before any lab I/O."""
    root = Path(root)
    path = root / rel
    if root.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise LabError('路径离开了本局目录：' + str(rel), 'path_type')
    p = root
    for part in Path(rel).parts:
        if part == '..':
            raise LabError('练习路径不能包含 ..', 'path_type')
        p = p / part
        if p.is_symlink():
            raise LabError('请使用普通文件/目录，不使用符号链接：' + str(rel), 'path_type')
    return path


def write(root, rel, text, mode=0o644):
    p = safe_path(root, rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')
    p.chmod(mode)


def task_path(root, s, rel):
    return safe_path(root, layout.rel(s, rel))


def task_write(root, s, rel, text, mode=0o644):
    write(root, layout.rel(s, rel), text, mode)


def content(root, rel, code='file', s=None):
    s = s or {}
    p = task_path(root, s, rel)
    if not p.is_file() or p.stat().st_size > 65536:
        facts = []
        if not p.exists() and Path(rel).name.startswith('.'):
            facts.append('hidden_missing')
        if code == 'backup' and activity.scene_facts(root, s)['backup_nested_present']:
            facts.append('nested_backup')
        raise LabError(f'文件缺失、类型不对或过大：{rel}', code, facts)
    return p.read_text(encoding='utf-8')


def require(condition, message, code='unknown'):
    if not condition:
        raise LabError(message, code)


def cfg(s, final=False, initial=False):
    return (f"STATION={s['station_id']}\n"
            f"MODE={tasks.mode(s, final=final, initial=initial)}\n"
            f"CHANNEL={'000' if initial else s['final_channel'] if final else s['channel']}\n"
            f"AUTH={'UNSET' if initial else s['final_code'] if final else s['code']}\n")


def parse_cfg(text):
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        require('=' in line, '配置行应为 KEY=value。', 'config_format')
        key, value = (x.strip() for x in line.split('=', 1))
        require(key not in data, f'配置中 {key} 重复，请只保留一次。', 'config_duplicate')
        data[key] = value
    return data


def validate_config(text, s, final=False):
    actual = parse_cfg(text)
    expected = parse_cfg(cfg(s, final=final))
    for key, val in expected.items():
        require(actual.get(key) == val, f'{key} 尚未正确设置；请回看本关要求和最新日志。', 'config_value')
    require(actual.keys() == expected.keys(), '配置只应包含 STATION、MODE、CHANNEL、AUTH 四个字段。', 'config_keys')


def crew(s):
    return f"station,name,status\n{s['station_id']},Lin,waiting\n{s['station_id']},Qiao,waiting\n{s['station_id']},Mo,waiting\n"


def route(s):
    if s.get('task_schema') != 'linux-nine-v1':
        return (f"导航已接入 {s['station_id']}。\n"
                'comms.log 按时间追加；以最后一条 READY 为准，HEARTBEAT 不是频率更新。\n'
                'CHANNEL 是频率，CODE 是授权码；请同时记下两者。\n')
    return layout.text(s, (f"任务资料标识：{s['station_id']}。\n"
            'comms.log 按时间追加；以最后一条 READY 为准，HEARTBEAT 不是频率更新。\n'
            'CHANNEL 是频道，CODE 是授权码；请同时记下两者。\n'))


def blackbox(s):
    if s.get('material_version') == 2:
        label = s['material_entities']['originals']['label']
        return {'boot.log': f"{s['station_id']} / ORIGINAL / {label}\nDO NOT EDIT\n",
                '.integrity': s['integrity'] + '\n',
                'sensors/pressure.csv': 'sample,value\n0,101\n1,99\n2,98\n'}
    return {'boot.log': f"{s['station_id']} / ORIGINAL / BLACKBOX\nDO NOT EDIT\n",
            '.integrity': s['integrity'] + '\n',
            'sensors/pressure.csv': 'minute,kpa\n0,101\n1,99\n2,98\n'}


RELAY = '''#!/usr/bin/env bash
set -euo pipefail
: "${ORBIT_ENGINE:?请在 bash start.sh 打开的实验终端中运行}"
python3 "$ORBIT_ENGINE" relay
'''


def receipt(s):
    return f"STATION={s['station_id']}\nRELAY=ONLINE\nRECEIPT={s['receipt']}\n"


def manifest(s):
    if s.get('material_version') == 2:
        return (f"STATION={s['station_id']}\nSEAL={s['seal']}\n"
                + s['material_entities']['supplies']['label'] + '：先核对标识，再恢复资料。\n')
    return f"STATION={s['station_id']}\nSEAL={s['seal']}\n先验证密封，再修复配置。\n"


def make_tar(path, files):
    with tarfile.open(path, 'w:gz') as tar:
        for name, (text, mode) in files.items():
            b = text.encode('utf-8')
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(b), mode, 0
            tar.addfile(info, io.BytesIO(b))


def cleanup_targets(s):
    names = ['decoy-a.tmp', 'decoy-b.tmp']
    if s.get('cleanup_version', 0) >= 1:
        names += ['decoy-.tmp', 'decoy-017.tmp', 'decoy-204.tmp', 'decoy-expired.tmp']
    return names


def cleanup_kept(s):
    if s.get('cleanup_version', 0) < 1:
        return {}
    return {
        'decoy-guide.txt': 'KEEP: signal recognition guide\n',
        'sensor.tmp': 'KEEP: live sensor buffer\n',
        '.decoy-cache.tmp': ('KEEP: hidden task cache\n' if s.get('material_version') == 2
                             else 'KEEP: hidden navigation cache\n'),
    }


def generate(root, s):
    root.mkdir()
    sync_guides(root, s)
    for d in ['airlock', 'work', 'blackbox', 'inbox', 'supplies', 'logs']:
        task_path(root, s, d).mkdir()
    task_path(root, s, 'airlock/.beacon-' + s['beacon']).mkdir()
    task_write(root, s, 'airlock/WELCOME.txt', explain_options('定位标记藏在点号开头的名字里。可以用 ls -a 查看。', 'ls-a') + '\n')
    task_write(root, s, 'MAP.txt', layout.text(s, 'airlock 入口 / blackbox 原件 / inbox 待整理资料 / supplies 待解压资料\nlogs 记录 / work 你的工作区。lab 查看任务，lab hint 求助。\n'))
    for name, text in blackbox(s).items():
        task_write(root, s, 'blackbox/' + name, text)
    task_write(root, s, 'inbox/route.pending', route(s))
    for name in cleanup_targets(s):
        task_write(root, s, 'inbox/' + name, 'DECOY - expired\n')
    for name, text in cleanup_kept(s).items():
        task_write(root, s, 'inbox/' + name, text)
    task_write(root, s, 'inbox/crew.csv', crew(s))
    files = {
        'manifest.txt': (manifest(s), 0o644),
        'relay.conf': (cfg(s, initial=True), 0o644), 'relay.sh': (RELAY, 0o644),
    }
    make_tar(task_path(root, s, 'supplies/rescue.tar.gz'), {layout.rel(s, name): value for name, value in files.items()})
    lines = ['0000 READY CHANNEL=111 CODE=OLD-DO-NOT-USE']
    lines += [f'{i:04} HEARTBEAT link=searching retry={i % 7}' for i in range(1, 181)]
    lines += ['0181 READY CHANNEL=222 CODE=EXPIRED', '0182 WARN old channel closed',
              f"0183 READY CHANNEL={s['channel']} CODE={s['code']}",
              '0184 HEARTBEAT link=waiting', '0185 HEARTBEAT link=waiting']
    task_write(root, s, 'logs/comms.log', '\n'.join(lines) + '\n')


def generate_final(root, s):
    task_path(root, s, 'finale').mkdir(exist_ok=True)
    files = {
        'dispatch/relay.conf.draft': (cfg(s), 0o644),
        'dispatch/discard.tmp': ('Exclude this draft from the final delivery.\n' if s.get('material_version') == 2
                                else 'This draft must not leave the station.\n', 0o644),
    }
    make_tar(task_path(root, s, 'finale/capsule.tar.gz'), {layout.rel(s, name): value for name, value in files.items()})
    task_write(root, s, 'finale/final.log',
          '0001 FINAL CHANNEL=101 AUTH=OLD\n' +
          ''.join(f'{i:04} WAIT ' + ('delivery pending\n' if s.get('material_version') == 2
                                     else 'rescue window closed\n') for i in range(2, 70)) +
          f"0070 FINAL CHANNEL={s['final_channel']} AUTH={s['final_code']}\n0071 WINDOW OPEN\n")


def sync_guides(root, s=None):
    # Never copy the repository's maintainer instructions into a learner session.
    write(root, 'AGENTS.md', (APP / 'docs/STUDENT-AGENTS.md').read_text(encoding='utf-8'))
    for name in ['STUDENT.md', 'notes.md', 'docs/LOCAL-AI.md']:
        source = APP / name
        if source.is_file():
            text = source.read_text(encoding='utf-8')
            if name == 'STUDENT.md':
                text = layout.text(s or {}, text)
            write(root, name, text)


def snapshot(session, n):
    root = session / 'station'
    require(not root.is_symlink(), '站点根目录不能是符号链接。')
    for p in root.rglob('*'):
        require(not p.is_symlink(), '检查点不接受符号链接：' + str(p.relative_to(root)))
        require(p.is_file() or p.is_dir(), '检查点仅接受普通文件和目录。')
    target = session / 'checkpoints' / f'phase-{n}'
    target.parent.mkdir(exist_ok=True)
    # A previous interrupted checkpoint is preserved, never deleted.
    if target.exists():
        target.rename(target.with_name(target.name + '-interrupted-' + secrets.token_hex(3)))
    shutil.copytree(root, target)


def doctor():
    require(sys.platform == 'linux', '请在 WSL Ubuntu 或其他 Linux 中运行 bash start.sh。')
    require(sys.version_info >= (3, 9), '需要 Python 3.9 或更新版本。')
    needed = ['bash', 'ls', 'mkdir', 'cp', 'mv', 'rm', 'tar', 'gzip', 'cat', 'tail', 'chmod', 'top', 'vim']
    missing = [x for x in needed if shutil.which(x) is None]
    require(not missing, '缺少命令：' + ', '.join(missing) + '\n请在项目目录运行 bash setup.sh --install，或在 Windows 双击安装环境.cmd。')
    require(Path('/proc/self/stat').exists(), '需要 Linux /proc 文件系统。')


def prepare(new=False, scene='', interactive=False):
    doctor()
    base = Path(os.environ.get('ORBIT_DATA_DIR', '~/.local/share/orbit-lab')).expanduser().resolve()
    require(not str(base).startswith('/mnt/'), '练习数据请放在 WSL Linux 文件系统中，不能放在 /mnt/，以保证 chmod 语义。')
    base.mkdir(parents=True, exist_ok=True)
    pointer = base / 'current.json'
    if pointer.exists() and not new:
        require(not scene, '已有学习周目。配套新情景请使用 bash start.sh --new --scene 主题或JSON文件；直接启动会续学。')
        session = Path(read_json(pointer)['session'])
        require(session.parent.resolve() == (base / 'sessions').resolve(), '当前周目索引异常。')
        s = load_session(session)
        pliac_bridge.attach(s)
        # Preserve an explicit off choice; old rounds without a choice adopt the
        # new local teaching default when the learner next starts this round.
        if 'tracking_enabled' not in s:
            s['tracking_enabled'] = True
            atomic_json(session / 'state.json', s)
        if s['tracking_enabled']:
            write(session, 'tracking.enabled', 'enabled\n', 0o600)
        sync_guides(session / 'station', s)
        atomic_json(session / 'state.json', s)
        pliac_bridge.publish_safely(s)
        return session
    bundle = scene or 'space'
    if interactive and not scene:
        # stdout is reserved for start.sh's session path; the interview stays on stderr.
        print('先选择你感兴趣的主题，再生成本次学习情景。正在联系本地配置的大模型……', file=sys.stderr, flush=True)
        question = scene_generator.ask_interest()
        print(question, file=sys.stderr, flush=True)
        print('你的主题：', end='', file=sys.stderr, flush=True)
        theme = sys.stdin.readline().strip()
        require(bool(theme), '未输入主题，尚未创建学习周目。重新启动后输入主题即可。')
        print('正在生成故事与任务文件命名……', file=sys.stderr, flush=True)
        bundle = scene_generator.create(theme)
        print('已生成：' + bundle['title'] + '。即将开始学习。', file=sys.stderr, flush=True)
    # Validate before making a new session; a failed generation leaves the old round intact.
    scene_state = {}
    scenes.initialize(scene_state, bundle)
    ident = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)
    session = base / 'sessions' / ident
    session.mkdir(parents=True, mode=0o700)
    s = {'format': MARKER, 'version': VERSION, 'id': ident, 'created_at': now(),
         'station_id': 'OR-' + secrets.token_hex(2).upper(),
         'beacon': str(1000 + secrets.randbelow(9000)), 'integrity': secrets.token_hex(12),
         'seal': 'SEAL-' + secrets.token_hex(3).upper(),
         'channel': str(300 + secrets.randbelow(300)), 'code': 'LINK-' + secrets.token_hex(3).upper(),
         'final_channel': str(700 + secrets.randbelow(200)), 'final_code': 'EVAC-' + secrets.token_hex(3).upper(),
         'receipt': secrets.token_hex(8).upper(), 'done': [], 'hints': {}, 'attempts': {},
         'events': [], 'worker': None, 'cleanup_version': 1, 'task_schema': 'linux-nine-v1',
         'tracking_enabled': True}
    s.update(scene_state)
    s.update(course_id=tasks.COURSE_ID, contract_version=tasks.CONTRACT_VERSION,
             contract_hash=tasks.contract_hash())
    pliac_bridge.attach(s)
    if scenes.get(s).get('schema_version') == 2:
        s['material_version'] = 2
        s['material_entities'] = scenes.get(s)['entities']
    generate(session / 'station', s)
    write(session, 'tracking.enabled', 'enabled\n', 0o600)
    snapshot(session, 1)
    atomic_json(session / 'state.json', s)
    atomic_json(pointer, {'session': str(session)})
    pliac_bridge.publish_safely(s)
    return session


def load_session(session):
    require(not session.is_symlink(), '周目目录不能是符号链接。')
    s = read_json(safe_path(session, 'state.json'))
    require(s.get('format') == MARKER, '这不是 LinuxLab 的有效存档。')
    require(isinstance(s.get('done'), list) and s['done'] == list(range(1, len(s['done']) + 1))
            and len(s['done']) <= 9, '存档进度异常。')
    # Legacy rounds have no contract identifiers. When an identifier was
    # recorded, do not silently resume against a different teaching contract.
    expected_contract = {'course_id': tasks.COURSE_ID,
                         'contract_version': tasks.CONTRACT_VERSION,
                         'contract_hash': tasks.contract_hash()}
    for name, expected in expected_contract.items():
        if name in s:
            require(type(s[name]) is type(expected) and s[name] == expected,
                    f'本局任务合同与当前程序不兼容（{name}）。'
                    '请使用创建本局时对应的程序版本，或由维护者迁移存档；当前现场未修改。',
                    'contract_mismatch')
    safe_path(session, 'station')
    scenes.get(s)
    layout.bindings(s)
    return s


def equal_file(root, path, expected, message=None, code='file', s=None):
    require(content(root, path, code, s) == expected, message or f'{path} 内容与本局原件不符。', code)


def validate_backup(root, s):
    for name, text in blackbox(s).items():
        equal_file(root, 'blackbox/' + name, text, 'blackbox 原件不完整：' + name, 'original', s)
        equal_file(root, 'work/backup/' + name, text, '备份内容不完整：' + name, 'backup', s)


def proc_identity(pid):
    try:
        # Fields after the final ')' start at field 3; starttime is field 22.
        raw = Path(f'/proc/{int(pid)}/stat').read_text()
        rest = raw[raw.rindex(')') + 2:].split()
        return None if rest[0] == 'Z' else rest[19]
    except (OSError, ValueError, IndexError):
        return None


def worker_alive(w):
    if not w or proc_identity(w['pid']) != w['start']:
        return False
    try:
        args = Path(f"/proc/{w['pid']}/cmdline").read_bytes().split(b'\0')
        return b'_worker' in args and w['token'].encode() in args
    except OSError:
        return False


def stop_worker(s):
    w = s.get('worker')
    if worker_alive(w):
        # Linux pidfd pins the process, avoiding PID reuse between check and signal.
        if hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'):
            try:
                fd = os.pidfd_open(w['pid'])
                try:
                    if worker_alive(w):
                        signal.pidfd_send_signal(fd, signal.SIGTERM)
                finally:
                    os.close(fd)
            except ProcessLookupError:
                pass
        # On older kernels the bounded worker exits on its own; never signal an unpinned PID.
    s['worker'] = None


def start_worker(session, s):
    if worker_alive(s.get('worker')):
        print('探针已经运行。请在 top 中查找 station-pulse。')
        return
    token = secrets.token_hex(12)
    root = session / 'station'
    log = task_path(root, s, 'logs/pulse.log')
    with log.open('w', encoding='utf-8') as out:
        p = subprocess.Popen([sys.executable, str(APP / 'orbit.py'), '_worker', str(session), token],
                             stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True)
    start = proc_identity(p.pid)
    s['worker'] = {'pid': p.pid, 'start': start, 'token': token}
    # Wait for a short readiness handshake so immediate top sees the assigned name.
    for _ in range(50):
        if 'PROBE ONLINE' in log.read_text(encoding='utf-8'):
            break
        if p.poll() is not None:
            raise LabError('探针未能启动，请查看 logs/pulse.log。')
        time.sleep(0.02)
    print('探针已启动：station-pulse，最多运行 90 秒。请确定它的进程编号 PID。')


def worker(session, token):
    # Name shown by top in its normal COMMAND column. No root privileges.
    ctypes.CDLL(None).prctl(15, b'station-pulse', 0, 0, 0)
    print('PROBE ONLINE / limited to 90 seconds', flush=True)
    deadline = time.monotonic() + 90
    tick = 0
    while time.monotonic() < deadline:
        # A short bounded calculation, then sleep: approximately <= 3% of one core.
        busy_end = time.monotonic() + 0.015
        while time.monotonic() < busy_end:
            hashlib.sha256(token.encode()).digest()
        print(f'{tick:03} TELEMETRY link=online', flush=True)
        tick += 1
        time.sleep(0.6)
    print('PROBE OFFLINE / time limit reached', flush=True)


def validate_archive(root, s):
    archive = task_path(root, s, 'work/rescue.tar.gz')
    require(archive.is_file(), '还没有 work/rescue.tar.gz。', 'archive_missing')
    require(archive.stat().st_size < 2_000_000, '归档过大，应仅包含三个交付文件。', 'archive_layout')
    expected = {layout.rel(s, p) for p in ('dispatch/relay.conf', 'dispatch/crew.csv', 'dispatch/receipt.txt')}
    seen = set()
    with tarfile.open(archive, 'r:gz') as tar:
        for index, member in enumerate(tar):
            require(index < 16, '归档含过多成员。', 'archive_layout')
            name = member.name
            require(not name.startswith('/') and '..' not in PurePosixPath(name).parts,
                    '归档不能包含绝对路径或 ..。', 'archive_layout')
            name = str(PurePosixPath(name))
            if member.isdir():
                require(name == layout.rel(s, 'dispatch'), '归档中多套了目录：' + name, 'archive_layout')
                continue
            require(member.isfile() and not member.issparse(), '交付成员必须是普通文件，不能是链接或特殊文件。', 'archive_layout')
            require(name in expected, '归档包含多余文件或路径层级错误：' + name, 'archive_layout')
            require(name not in seen, '归档中有重复成员：' + name, 'archive_layout')
            require(member.size <= 65536, '归档成员过大：' + name, 'archive_layout')
            seen.add(name)
            with tar.extractfile(member) as f:
                text = f.read().decode('utf-8')
            if name == layout.rel(s, 'dispatch/relay.conf'):
                validate_config(text, s, final=True)
                require(member.mode & 0o7777 == 0o600, '归档内 relay.conf 权限应为 600；修改后重新打包。', 'archive_permissions')
            elif name == layout.rel(s, 'dispatch/crew.csv'):
                require(text == crew(s), '归档中的 crew.csv 与本局名单不符。', 'archive_content')
            else:
                require(text == receipt(s), '归档中的 receipt.txt 与本局启动回执不符。', 'archive_content')
    require(seen == expected, '归档缺少：' + ', '.join(sorted(expected - seen)), 'archive_layout')


def validate(n, session, s, answer):
    root = session / 'station'
    if n == 1:
        require(Path.cwd().resolve() == task_path(root, s, 'airlock').resolve(), '先 cd 到 station/airlock，再在里面提交。', 'location')
        require(task_path(root, s, 'work/evidence').is_dir(), '还没有 work/evidence 目录；请用 mkdir 创建。', 'directory')
        require(answer == s['beacon'], explain_options('信标数字不对；用 ls -a 查看 .beacon- 后面的四位数字。', 'ls-a'), 'beacon')
    elif n == 2:
        validate_backup(root, s)
    elif n == 3:
        equal_file(root, 'work/evidence/route.txt', route(s), code='move', s=s)
        for path in ['inbox/route.pending'] + ['inbox/' + name for name in cleanup_targets(s)]:
            require(not task_path(root, s, path).exists(), '这个文件仍在原位置：' + path,
                    'move' if path.endswith('route.pending') else 'cleanup')
        equal_file(root, 'inbox/crew.csv', crew(s), '名单 crew.csv 丢失或被改动，请保留原件。', 'preserve', s)
        for name, text in cleanup_kept(s).items():
            equal_file(root, 'inbox/' + name, text, '需要保留的文件被改动：inbox/' + name, 'preserve', s)
    elif n == 4:
        require(answer == s['seal'], 'SEAL 不匹配，请读取解出的 manifest.txt。', 'seal')
        equal_file(root, 'work/recovered/manifest.txt', manifest(s), code='extraction', s=s)
        equal_file(root, 'work/recovered/relay.conf', cfg(s, initial=True), code='extraction', s=s)
        equal_file(root, 'work/recovered/relay.sh', RELAY, code='extraction', s=s)
    elif n == 5:
        require(answer == s['code'], '不是最新授权码。请读日志最后一条 READY，忽略 HEARTBEAT 和旧 READY。', 'log_record')
    elif n == 6:
        validate_config(content(root, 'work/recovered/relay.conf', 'config_file', s), s)
    elif n == 7:
        validate_relay(root, s)
        equal_file(root, 'work/recovered/receipt.txt', receipt(s), '尚未得到正确启动回执。请运行 ./relay.sh。', 'receipt', s)
    elif n == 8:
        require(worker_alive(s.get('worker')), '本局探针尚未运行或已超时。请先 lab load，再观察 top。', 'process_absent')
        require(answer == str(s['worker']['pid']), 'PID 不匹配，请定位 COMMAND 为 station-pulse 的那一行。', 'process_identity')
    elif n == 9:
        validate_backup(root, s)
        validate_archive(root, s)


def validate_relay(root, s):
    validate_config(content(root, 'work/recovered/relay.conf', 'config_file', s), s)
    equal_file(root, 'work/recovered/relay.sh', RELAY, '启动脚本内容被修改，请使用原脚本。', 'script', s)
    for name, mode in [('relay.conf', 0o600), ('relay.sh', 0o700)]:
        p = task_path(root, s, 'work/recovered/' + name)
        require(stat.S_IMODE(p.stat().st_mode) == mode,
                f'{name} 权限应为 {mode:o}，当前是 {stat.S_IMODE(p.stat().st_mode):o}。', 'permissions')


def show_status(s):
    scene = scenes.get(s)
    print(f"\n  {PRODUCT_NAME} / {scene['title']}    {s['station_id']}    {len(s['done'])}/9")
    print('  ' + LAB_SCOPE)
    print('  ' + '━' * 46)
    for i, (title, reward) in enumerate(zip(scene['titles'], scene['rewards']), 1):
        label = '●' if i in s['done'] else '▶' if i == len(s['done']) + 1 else '○'
        print(f'  {label} {i:02}  {title}' + (f'  / {reward}' if i in s['done'] else ''))
    print()


def report(session, s):
    out = {'lab': PRODUCT_NAME, 'version': VERSION, 'run_id': s['id'], 'station': s['station_id'],
           'completed': len(s['done']) == 9, 'phases_passed': len(s['done']),
           'created_at': s['created_at'], 'completed_at': s.get('completed_at'),
           'hints': s['hints'], 'attempts': s['attempts'], 'events': s['events'],
           'result': s.get('flag'),
           'archive_sha256': s.get('archive_sha256'),
           'learning': s.get('learning', {}),
           'scene': s.get('scene', 'space'),
           'scene_title': scenes.get(s)['title'], 'task_schema': 'linux-nine-v1',
           'course_id': s.get('course_id', 'linux-foundations'),
           'contract_version': s.get('contract_version'), 'contract_hash': s.get('contract_hash'),
           'shell_observations': s.get('shell_observations', []),
           'validation_scope': '文件结果与当前进程验证；不证明命令使用过程或独立学习成效。'}
    p = safe_path(session, 'report.json')
    atomic_json(p, error_patterns.report_copy(out))
    return p


def save_notebook(session, s):
    path = safe_path(session, 'learning-notebook.md')
    temp = safe_path(session, 'learning-notebook.' + secrets.token_hex(4) + '.tmp')
    try:
        temp.write_text(learning.notebook(s), encoding='utf-8')
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
    return path


def ending(session, s):
    scene = scenes.get(s)
    print('\n  ✦  ' + ('RESCUE COMPLETE' if scene['id'] == 'space' else 'TASK COMPLETE') + '  ✦\n')
    print(scene['ending'])
    print('\n完成凭证：' + s['flag'])
    print('交付物：' + str(task_path(session / 'station', s, 'work/rescue.tar.gz')))
    print('通关报告：' + str(report(session, s)))
    print('个人学习手册：lab notebook；知识点复习：lab review。')
    print(explain_options('输入 exit 退出。想换一组线索重玩：bash start.sh --new。', 'lab-new') + '\n')


def check_observation_key(root, s, phase, answer):
    """Hash only files/properties observed by this phase; never follow links."""
    backup = [(base + '/' + name, 'content')
              for name in blackbox(s) for base in ('blackbox', 'work/backup')]
    # content() uses this existence fact to distinguish a nested-copy error.
    backup.append(('work/backup/blackbox/boot.log', 'file'))
    cleanup = [('inbox/' + name, 'exists')
               for name in ['route.pending'] + cleanup_targets(s)]
    preserved = [('inbox/' + name, 'content')
                 for name in ['crew.csv'] + list(cleanup_kept(s))]
    relevant = {
        1: [('airlock', 'directory'), ('work/evidence', 'directory')],
        2: backup,
        3: [('work/evidence/route.txt', 'content')] + cleanup + preserved,
        4: [('work/recovered/' + name, 'content')
            for name in ('manifest.txt', 'relay.conf', 'relay.sh')],
        5: [],
        6: [('work/recovered/relay.conf', 'content')],
        7: [('work/recovered/relay.conf', 'content_mode'),
            ('work/recovered/relay.sh', 'content_mode'),
            ('work/recovered/receipt.txt', 'content')],
        8: [],
        9: backup + [('work/rescue.tar.gz', 'archive')],
    }
    digest = hashlib.sha256()

    def add(value):
        digest.update(json.dumps(value, ensure_ascii=False).encode() + b'\n')

    add([s['id'], phase, answer if phase in (1, 4, 5, 8) else '',
         str(Path.cwd()) if phase == 1 else '',
         [worker_alive(s.get('worker')), (s.get('worker') or {}).get('pid')]
         if phase == 8 else None])
    root_fd = None

    def observe(logical, kind):
        parts = Path(layout.rel(s, logical)).parts
        if not parts or any(part in ('', '.', '..') for part in parts) or Path(parts[0]).is_absolute():
            raise OSError('Invalid task path')
        current_fd = os.dup(root_fd)
        try:
            for index, part in enumerate(parts):
                try:
                    info = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return ['missing', index]
                if stat.S_ISLNK(info.st_mode):
                    return ['link', index]
                if index < len(parts) - 1:
                    if not stat.S_ISDIR(info.st_mode):
                        return ['parent_not_directory', index]
                    next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=current_fd)
                    os.close(current_fd)
                    current_fd = next_fd
                    continue
                if kind == 'exists':
                    return ['exists']
                if kind == 'directory':
                    return ['directory', stat.S_ISDIR(info.st_mode)]
                if kind == 'file':
                    return ['file', stat.S_ISREG(info.st_mode)]
                if not stat.S_ISREG(info.st_mode):
                    return ['not_regular']
                # Match content() and validate_archive() limits. No directory
                # metadata, unrelated file contents or unrelated modes count.
                limit = 1_999_999 if kind == 'archive' else 65536
                mode = stat.S_IMODE(info.st_mode) if kind == 'content_mode' else None
                if info.st_size > limit:
                    return ['oversize', info.st_size, mode]
                fd = os.open(part, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=current_fd)
                with os.fdopen(fd, 'rb') as stream:
                    before = os.fstat(stream.fileno())
                    if not stat.S_ISREG(before.st_mode):
                        raise OSError('Task file changed during observation')
                    data = stream.read(limit + 1)
                    after = os.fstat(stream.fileno())
                signature = lambda st: (st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns)
                if signature(info) != signature(before) or signature(before) != signature(after):
                    raise OSError('Task file changed during observation')
                return ['content', hashlib.sha256(data).hexdigest(), mode]
        finally:
            os.close(current_fd)

    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for logical, kind in relevant[phase]:
            add([logical, kind, observe(logical, kind)])
    except OSError:
        return None
    finally:
        if root_fd is not None:
            os.close(root_fd)
    return digest.hexdigest()


def check(session, s, answer):
    n = len(s['done']) + 1
    if n > 9:
        ending(session, s)
        return 0
    k = str(n)
    s['attempts'][k] = s['attempts'].get(k, 0) + 1
    try:
        validate(n, session, s, answer)
        if n == 8:
            stop_worker(s)
            generate_final(session / 'station', s)
        if n < 9:
            snapshot(session, n + 1)
        s['done'].append(n)
        s['events'].append({'at': now(), 'phase': n, 'result': 'passed'})
        learning.record_check(s, n, True)
        print(f'\n[通过 {n:02}/09] ' + scenes.get(s)['rewards'][n-1])
        print('本关知识：' + REFLECTIONS[n-1])
        if n == 9:
            s['completed_at'] = now()
            archive = task_path(session / 'station', s, 'work/rescue.tar.gz')
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            s['flag'] = 'LINUXLAB{' + s['station_id'] + '-' + digest[:16].upper() + '}'
            s['archive_sha256'] = digest
            ending(session, s)
        else:
            print(f'\n下一关 {n+1:02} / ' + scenes.get(s)['titles'][n] + '\n' + brief(n+1, s))
        return 0
    except (LabError, OSError, UnicodeError, tarfile.TarError, EOFError) as e:
        s['events'].append({'at': now(), 'phase': n, 'result': 'retry', 'reason': str(e)})
        code = getattr(e, 'code', 'unknown')
        if isinstance(e, PermissionError):
            code = 'access'
        elif isinstance(e, (tarfile.TarError, EOFError)):
            code = 'archive_format'
        elif isinstance(e, UnicodeError):
            code = 'encoding'
        elif isinstance(e, (NotADirectoryError, IsADirectoryError)):
            code = 'path_type'
        elif isinstance(e, FileNotFoundError):
            code = 'file'
        item = learning.record_check(s, n, False, code, facts=getattr(e, 'facts', []),
                                     observation_key=check_observation_key(session / 'station', s, n, answer))
        print('\n[尚未通过] ' + layout.text(s, runtime_error(e)))
        print(feedback(item))
        if item.get('repeat_checks'):
            print(f'相同现场的重复检查：追加 {item["repeat_checks"]} 次，仍归入同一问题。')
        print('也可查原生帮助：' + native_help(CONCEPTS[item['concepts'][0]]['note']))
        print('进度未回退。lab hint 获取提示；lab learn 查命令；误操作可 lab repair。')
        print('针对这次问题：lab tutor；复习记录：lab notebook。')
        return 1


def repair(session, s):
    n = len(s['done']) + 1
    require(n <= 9, '已经通关；保留本局交付物，退出后使用 bash start.sh --new 开启新局；new 表示新建，旧局保留。')
    stop_worker(s)
    root = safe_path(session, 'station')
    checkpoint = safe_path(session, f'checkpoints/phase-{n}')
    require(checkpoint.is_dir(), '当前关检查点缺失，无法恢复。可退出后用 bash start.sh --new 开启新局；new 表示新建，旧局保留。')
    for p in checkpoint.rglob('*'):
        require(not p.is_symlink(), '检查点含符号链接，不能恢复。')
    recovery = safe_path(session, 'recovery')
    recovery.mkdir(exist_ok=True)
    target = recovery / ('before-repair-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
    if root.exists():
        root.rename(target)
    shutil.copytree(checkpoint, root)
    sync_guides(root, s)
    s['events'].append({'at': now(), 'phase': n, 'result': 'repair',
                         'operation_cursor': s.get('shell_sequence', 0)})
    if 'learning' in s:
        s['learning']['active_issue'] = None
        for pattern in s['learning'].get('input_errors', {}).get('patterns', {}).values():
            if pattern['phase'] == n:
                pattern['active'] = False  # Repair ends an episode, not evidence of learning.
    print('已保存原现场：' + str(target))
    print('已恢复到本关开始时。请立即输入 cd "$(lab root)" 回到新现场，然后 lab。')


def show_notes(topic):
    path = APP / 'notes.md'
    text = path.read_text(encoding='utf-8')
    sections = {}
    for part in text.split('\n## ')[1:]:
        title = part.split('\n', 1)[0]
        sections[title.split()[0]] = (title, '## ' + part.rstrip())
    topic = {'cd': 'navigation', 'pwd': 'navigation', '*': 'glob'}.get(topic, topic)
    print(LAB_SCOPE)
    print('中文笔记帮助理解，也鼓励查本机原生帮助：' + native_help(topic) + '\n')
    if topic == 'all':
        print(render_markdown(text))
    elif topic:
        if topic not in sections:
            raise InputError(unknown_topic(topic, list(sections) + ['cd', 'pwd', 'all']))
        print(render_markdown(sections[topic][1]))
    else:
        print('Linux 常用命令参数笔记（notes.md）')
        print('先认识命令名，再查“参数 / 英文原词 / 作用说明 / 记忆联想”。\n')
        for key, (title, _) in sections.items():
            print('  lab notes ' + key + '  —  ' + title.partition(' — ')[2])
        print('\n例如 lab notes ls；lab notes cd 或 lab notes pwd 可查目录操作。')
        print('lab notes all 显示全文；笔记文件：' + str(path))


def run_command(args, session, s):
    cmd = args.command
    n = len(s['done']) + 1
    if cmd in ['mission', 'status']:
        show_status(s)
        if cmd == 'mission':
            if n <= 9:
                print('本关工具：' + SKILLS[n-1] + '\n\n' + brief(n, s))
                print('\n提示：lab hint 逐级求助；lab tutor 针对问题讲解；lab notebook 查看学习手册。')
            else:
                ending(session, s)
    elif cmd == 'help':
        print(HELP)
    elif cmd == 'notes':
        show_notes(args.topic)
    elif cmd == 'root':
        print(session / 'station')
    elif cmd == 'check':
        return check(session, s, args.answer)
    elif cmd == 'hint':
        require(n <= 9, '已经完成全部关卡。')
        key = str(n)
        level = args.level or min(s['hints'].get(key, 0) + 1, 3)
        s['hints'][key] = max(s['hints'].get(key, 0), level)
        s['events'].append({'at': now(), 'phase': n, 'result': 'hint', 'level': level})
        item = learning.active_issue(s, n)
        hint = (CONCEPTS[item['concepts'][0]]['hints'][level-1]
                if item['code'] != 'unknown' else HINTS[n-1][level-1])
        print(f'提示 {level}/3（不扣分）：\n' + hint)
    elif cmd == 'tutor':
        require(n <= 9, '已经完成全部关卡。用 lab notebook 复盘，或 lab review 复习知识点。')
        if args.topic:
            require(args.topic in PHASE_CONCEPTS[n], '该知识点不属于当前关；用 lab concepts 查看本关知识点。')
        item, level = learning.tutor_context(s, n, args.level, args.topic)
        if args.topic:
            item = dict(item, concepts=[args.topic])
        topic = CONCEPTS[item['concepts'][0]]
        for key in item['concepts']:
            learning.touch_topic(s, key, now())
        print('本平台助教功能（不是 Linux 通用命令）')
        print(f'助教提示 {level}/3 · {topic["title"]}')
        if item.get('input_error'):
            print('本地观察：' + item['observation'])
            print('依据：' + '；'.join(item['evidence']))
        explanation, source = topic['explanation'], 'local'
        hypotheses = []
        if not args.offline:
            try:
                context = error_patterns.context(s, n)
                if context['evidence']:
                    result = ai_tutor.diagnose(s, item, level, args.question, context)
                    explanation, hypotheses = result['explanation'], result['hypotheses']
                else:
                    explanation = ai_tutor.explain(s, item, level, args.question)
                source = 'ai'
            except ai_tutor.AIError as e:
                print(str(e))
        print(('AI 概念解释：' if source == 'ai' else '本地概念解释：') + explanation)
        for hypothesis in hypotheses:
            print('AI 待验证解释：' + hypothesis['reason'])
            print('引用记录：' + '、'.join(hypothesis['evidence_ids']))
            print('验证目标：' + hypothesis['verify'])
        print('下一步：' + topic['hints'][level-1])
        print('预期观察：用现场结果确认原因；操作与提交由你完成。')
        print('原生帮助：' + native_help(topic['note']))
        print(f'本平台中文补充说明：lab notes {topic["note"]}。')
        s['events'].append({'at': now(), 'phase': n, 'result': 'tutor', 'level': level,
                            'concept': item['concepts'][0], 'source': source})
    elif cmd == 'concepts':
        if n <= 9:
            for key in PHASE_CONCEPTS[n]:
                print(key + ' · ' + CONCEPTS[key]['title'])
            print('针对一个知识点求助：lab tutor --topic 知识点；离线可加 --offline。')
        else:
            print('全部关卡已完成；lab review 查看本局知识点记录。')
    elif cmd == 'tracking':
        if args.mode != 'status':
            enabled = args.mode == 'on'
            marker = safe_path(session, 'tracking.enabled')
            if enabled:
                write(session, 'tracking.enabled', 'enabled\n', 0o600)
            elif marker.exists():
                marker.unlink()
            s['tracking_enabled'] = enabled
        print('本平台操作记录：' + ('已开启' if s.get('tracking_enabled') else '已关闭'))
        print('新周目默认开启；仅记录本实验内的有限操作特征及经过筛选的错误命令词、选项和路径片段。')
        print('不保存完整命令、原生输出、按键或停顿；本地记录不会逐条自动上传。lab tracking off 可关闭。')
    elif cmd == 'activity':
        print(activity.display(s))
    elif cmd == 'scene':
        print(scenes.choose(s, args.name))
    elif cmd == 'notebook':
        print('本平台个人学习手册；生成的文件也可用 cat 或 less 加文件路径阅读。')
        print(render_markdown(learning.notebook(s)))
        print('手册文件：' + str(save_notebook(session, s)))
    elif cmd == 'review':
        print('本平台复习功能（不是 Linux 通用命令）')
        print(learning.review(s, args.topic, args.answer))
    elif cmd == 'learn':
        require(n <= 9, '已经通关，可用 lab notes 查命令笔记，或阅读 STUDENT.md。')
        print(layout.text(s, CARDS[n-1]))
        print('\n也鼓励查阅原生帮助：' + native_help(CONCEPTS[PHASE_CONCEPTS[n][0]]['note']))
        print('\n更多常用参数及命令名含义：lab notes（例如 lab notes ls），也可阅读 notes.md。')
    elif cmd == 'load':
        require(n == 8, '遥测探针在第八关开放。')
        start_worker(session, s)
    elif cmd == 'stop':
        stop_worker(s)
        if not args.quiet:
            print('本局探针已停止；旧内核不支持 pidfd 时，探针将按 90 秒上限自行退出。')
    elif cmd == 'relay':
        require(n == 7, '请在第七关执行中继启动任务。')
        validate_relay(session / 'station', s)
        task_write(session / 'station', s, 'work/recovered/receipt.txt', receipt(s), 0o600)
        print(layout.text(s, 'RELAY ONLINE：启动成功，receipt.txt 已写入。现在 lab check。'))
    elif cmd == 'repair':
        repair(session, s)
    elif cmd == 'report':
        print(f"本局完成 {len(s['done'])}/9 关；检查次数 {sum(s['attempts'].values())}；不设扣分。")
        print('报告：' + str(report(session, s)))
        print('学习手册：' + str(save_notebook(session, s)))
    return 0


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == '--observe-shell':
        # Internal prompt hook; errors must not interfere with the learner's shell.
        try:
            import fcntl
            session = Path(os.environ['ORBIT_HOME'])
            require(session.is_absolute(), '无效周目路径。')
            require(len(argv) == 3 and 0 <= int(argv[1]) <= 255 and argv[2] in ('0', '1'), '无效观察参数。')
            line = sys.stdin.read(8192)
            with safe_path(session, 'state.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                s = load_session(session)
                cwd = Path(os.environ.get('ORBIT_OBSERVED_CWD', str(Path.cwd())))
                activity.record(s, session, line, int(argv[1]), cwd, argv[2] == '1',
                                os.environ.get('ORBIT_OBSERVED_COMMAND_KIND'))
                atomic_json(session / 'state.json', s)
                pliac_bridge.publish_safely(s)
        except (LabError, OSError, ValueError, KeyError):
            pass
        return 0
    if argv and argv[0] == '--shell-command-not-found':
        require(len(argv) >= 2, '输入 lab help 查看实验命令。')
        print('[命令未找到] ' + shell_lookup_error(argv[1], argv[2:]), file=sys.stderr)
        return 127
    if argv and argv[0] == '_worker':
        require(len(argv) == 3, '练习探针请通过 lab load 启动。')
        worker(Path(argv[1]), argv[2])
        return 0
    if argv in (['-h'], ['--help']):
        print(HELP)
        return 0
    if argv and argv[0] not in USAGE and not argv[0].startswith('-'):
        raise InputError(unknown_lab_command(argv[0], argv[1:]))
    if len(argv) == 2 and argv[0] in USAGE and argv[1] in ('-h', '--help'):
        print('用法：' + USAGE[argv[0]])
        return 0
    parser = LabParser(prog='lab', description='LinuxLab 情境式 Linux 学习实验')
    parser.command_name = argv[0] if argv else ''
    sub = parser.add_subparsers(dest='command')
    p = sub.add_parser('prepare'); p.add_argument('--new', action='store_true')
    p.add_argument('--scene', default=''); p.add_argument('--interactive', action='store_true')
    sub.add_parser('doctor')
    for name in ['mission', 'status', 'help', 'root', 'learn', 'load', 'relay', 'repair', 'report', 'concepts', 'notebook', 'activity']:
        sub.add_parser(name)
    p = sub.add_parser('check'); p.add_argument('answer', nargs='?', default='')
    p = sub.add_parser('hint'); p.add_argument('level', nargs='?', type=int, choices=[1, 2, 3])
    p = sub.add_parser('notes'); p.add_argument('topic', nargs='?', default='')
    p = sub.add_parser('ai'); p.add_argument('action', nargs='?', choices=['init', 'status'], default='status')
    p = sub.add_parser('tracking'); p.add_argument('mode', nargs='?', choices=['on', 'off', 'status'], default='status')
    p = sub.add_parser('scene'); p.add_argument('name', nargs='?', default='')
    p.add_argument('--generate', metavar='主题'); p.add_argument('--output', metavar='JSON文件')
    p = sub.add_parser('tutor')
    p.add_argument('question', nargs='?', default='')
    p.add_argument('--level', type=int, choices=[1, 2, 3])
    p.add_argument('--topic', default='')
    p.add_argument('--offline', action='store_true')
    p = sub.add_parser('review')
    p.add_argument('topic', nargs='?', default=''); p.add_argument('answer', nargs='?', default='')
    p = sub.add_parser('stop'); p.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)
    args.command = args.command or 'mission'
    if args.command == 'ai':
        print(ai_tutor.init_config() if args.action == 'init' else ai_tutor.status()); return 0
    if args.command == 'prepare':
        print(prepare(args.new, args.scene, args.interactive)); return 0
    if args.command == 'scene' and (args.generate is not None or args.output is not None):
        require(args.generate is not None and not args.name, '生成情景请用 lab scene --generate "主题" [--output 文件.json]。')
        print(scene_generator.generate(args.generate, args.output)); return 0
    if args.command == 'doctor':
        doctor(); print('环境检查通过：Linux、Python 3.9+、Bash、Vim、top、GNU 基础命令就绪。'); return 0
    require(bool(os.environ.get('ORBIT_HOME')), '请先运行 bash start.sh 进入实验终端。')
    session = Path(os.environ['ORBIT_HOME'])
    require(session.is_absolute(), '周目路径必须为绝对路径。')
    # Serialize checks, hints, repair and worker lifecycle across terminals.
    import fcntl
    with safe_path(session, 'state.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        s = load_session(session)
        try:
            return run_command(args, session, s)
        except (LabError, OSError, ValueError, tarfile.TarError) as e:
            print('[LinuxLab] ' + layout.text(s, runtime_error(e)), file=sys.stderr)
            return 1
        finally:
            atomic_json(session / 'state.json', s)
            pliac_bridge.publish_safely(s)
            if 'learning' in s:
                try:
                    save_notebook(session, s)
                except (LabError, OSError) as e:
                    print('学习记录已保存，手册暂时无法更新：' + runtime_error(e), file=sys.stderr)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (LabError, OSError, ValueError, tarfile.TarError) as exc:
        print('[LinuxLab] ' + runtime_error(exc), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\n已取消；已通过的关卡会保留。', file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f'[LinuxLab] 程序出现内部异常（{type(exc).__name__}），本次操作未正常完成。'
              '请保留现场，并把这条提示反馈给维护者。', file=sys.stderr)
        if os.environ.get('ORBIT_DEBUG') == '1':
            import traceback
            traceback.print_exc()
        sys.exit(1)
