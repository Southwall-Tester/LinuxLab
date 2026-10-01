#!/usr/bin/env python3
"""ORBIT: a local, state-based Linux teaching lab (Python 3.9+)."""
import argparse
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

from lessons import TITLES, SKILLS, REWARDS, REFLECTIONS, HINTS, CARDS, HELP, brief, explain_options

APP = Path(__file__).resolve().parent
VERSION = '1.0.0'
MARKER = 'orbit-linux-lab-v1'


class LabError(Exception):
    pass


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
        raise LabError('路径离开了本局目录：' + str(rel))
    p = root
    for part in Path(rel).parts:
        if part == '..':
            raise LabError('练习路径不能包含 ..')
        p = p / part
        if p.is_symlink():
            raise LabError('请使用普通文件/目录，不使用符号链接：' + str(rel))
    return path


def write(root, rel, text, mode=0o644):
    p = safe_path(root, rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')
    p.chmod(mode)


def content(root, rel):
    p = safe_path(root, rel)
    if not p.is_file() or p.stat().st_size > 65536:
        raise LabError(f'文件缺失、类型不对或过大：{rel}')
    return p.read_text(encoding='utf-8')


def require(condition, message):
    if not condition:
        raise LabError(message)


def cfg(s, final=False, initial=False):
    return (f"STATION={s['station_id']}\n"
            f"MODE={'maintenance' if initial else 'evacuate' if final else 'rescue'}\n"
            f"CHANNEL={'000' if initial else s['final_channel'] if final else s['channel']}\n"
            f"AUTH={'UNSET' if initial else s['final_code'] if final else s['code']}\n")


def parse_cfg(text):
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        require('=' in line, '配置行应为 KEY=value。')
        key, value = (x.strip() for x in line.split('=', 1))
        require(key not in data, f'配置中 {key} 重复，请只保留一次。')
        data[key] = value
    return data


def validate_config(text, s, final=False):
    actual = parse_cfg(text)
    expected = parse_cfg(cfg(s, final=final))
    for key, val in expected.items():
        require(actual.get(key) == val, f'{key} 尚未正确设置；请回看本关要求和最新日志。')
    require(actual.keys() == expected.keys(), '配置只应包含 STATION、MODE、CHANNEL、AUTH 四个字段。')


def crew(s):
    return f"station,name,status\n{s['station_id']},Lin,waiting\n{s['station_id']},Qiao,waiting\n{s['station_id']},Mo,waiting\n"


def route(s):
    return (f"导航已接入 {s['station_id']}。\n"
            'comms.log 按时间追加；以最后一条 READY 为准，HEARTBEAT 不是频率更新。\n'
            'CHANNEL 是频率，CODE 是授权码；请同时记下两者。\n')


def blackbox(s):
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
        '.decoy-cache.tmp': 'KEEP: hidden navigation cache\n',
    }


def generate(root, s):
    root.mkdir()
    sync_guides(root)
    for d in ['airlock', 'work', 'blackbox', 'inbox', 'supplies', 'logs']:
        (root / d).mkdir()
    (root / 'airlock' / ('.beacon-' + s['beacon'])).mkdir()
    write(root, 'airlock/WELCOME.txt', explain_options('定位灯藏在点号开头的名字里。可以用 ls -a 查看。', 'ls-a') + '\n')
    write(root, 'MAP.txt', 'airlock 气闸 / blackbox 原件 / inbox 来件 / supplies 救援舱\nlogs 通信记录 / work 你的工作区。lab 查看任务，lab hint 求助。\n')
    for name, text in blackbox(s).items():
        write(root, 'blackbox/' + name, text)
    write(root, 'inbox/route.pending', route(s))
    for name in cleanup_targets(s):
        write(root, 'inbox/' + name, 'DECOY - expired\n')
    for name, text in cleanup_kept(s).items():
        write(root, 'inbox/' + name, text)
    write(root, 'inbox/crew.csv', crew(s))
    make_tar(root / 'supplies/rescue.tar.gz', {
        'manifest.txt': (f"STATION={s['station_id']}\nSEAL={s['seal']}\n先验证密封，再修复配置。\n", 0o644),
        'relay.conf': (cfg(s, initial=True), 0o644), 'relay.sh': (RELAY, 0o644),
    })
    lines = ['0000 READY CHANNEL=111 CODE=OLD-DO-NOT-USE']
    lines += [f'{i:04} HEARTBEAT link=searching retry={i % 7}' for i in range(1, 181)]
    lines += ['0181 READY CHANNEL=222 CODE=EXPIRED', '0182 WARN old channel closed',
              f"0183 READY CHANNEL={s['channel']} CODE={s['code']}",
              '0184 HEARTBEAT link=waiting', '0185 HEARTBEAT link=waiting']
    write(root, 'logs/comms.log', '\n'.join(lines) + '\n')


def generate_final(root, s):
    safe_path(root, 'finale').mkdir(exist_ok=True)
    make_tar(safe_path(root, 'finale/capsule.tar.gz'), {
        'dispatch/relay.conf.draft': (cfg(s), 0o644),
        'dispatch/discard.tmp': ('This draft must not leave the station.\n', 0o644),
    })
    write(root, 'finale/final.log',
          '0001 FINAL CHANNEL=101 AUTH=OLD\n' +
          ''.join(f'{i:04} WAIT rescue window closed\n' for i in range(2, 70)) +
          f"0070 FINAL CHANNEL={s['final_channel']} AUTH={s['final_code']}\n0071 WINDOW OPEN\n")


def sync_guides(root):
    for name in ['AGENTS.md', 'STUDENT.md', 'notes.md']:
        source = APP / name
        if source.is_file():
            write(root, name, source.read_text(encoding='utf-8'))


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


def prepare(new=False):
    doctor()
    base = Path(os.environ.get('ORBIT_DATA_DIR', '~/.local/share/orbit-lab')).expanduser().resolve()
    require(not str(base).startswith('/mnt/'), '练习数据请放在 WSL Linux 文件系统中，不能放在 /mnt/，以保证 chmod 语义。')
    base.mkdir(parents=True, exist_ok=True)
    pointer = base / 'current.json'
    if pointer.exists() and not new:
        session = Path(read_json(pointer)['session'])
        require(session.parent.resolve() == (base / 'sessions').resolve(), '当前周目索引异常。')
        load_session(session)
        sync_guides(session / 'station')
        return session
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
         'events': [], 'worker': None, 'cleanup_version': 1}
    generate(session / 'station', s)
    snapshot(session, 1)
    atomic_json(session / 'state.json', s)
    atomic_json(pointer, {'session': str(session)})
    return session


def load_session(session):
    require(not session.is_symlink(), '周目目录不能是符号链接。')
    s = read_json(safe_path(session, 'state.json'))
    require(s.get('format') == MARKER, '这不是 ORBIT 的有效存档。')
    require(isinstance(s.get('done'), list) and s['done'] == list(range(1, len(s['done']) + 1))
            and len(s['done']) <= 9, '存档进度异常。')
    safe_path(session, 'station')
    return s


def equal_file(root, path, expected, message=None):
    require(content(root, path) == expected, message or f'{path} 内容与本局原件不符。')


def validate_backup(root, s):
    for name, text in blackbox(s).items():
        equal_file(root, 'blackbox/' + name, text, 'blackbox 原件不完整：' + name)
        equal_file(root, 'work/backup/' + name, text, '备份内容不完整：' + name)


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
    log = safe_path(root, 'logs/pulse.log')
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
    print('探针已启动：station-pulse，最多运行 90 秒。现在运行 top，按 q 返回。')
    print(explain_options('也可以 tail -f logs/pulse.log 观察日志；Ctrl+C 结束跟随。', 'tail-f'))


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
    archive = safe_path(root, 'work/rescue.tar.gz')
    require(archive.is_file(), '还没有 work/rescue.tar.gz。')
    require(archive.stat().st_size < 2_000_000, '归档过大，应仅包含三个交付文件。')
    expected = {'dispatch/relay.conf', 'dispatch/crew.csv', 'dispatch/receipt.txt'}
    seen = set()
    with tarfile.open(archive, 'r:gz') as tar:
        for index, member in enumerate(tar):
            require(index < 16, '归档含过多成员。')
            name = member.name
            require(not name.startswith('/') and '..' not in PurePosixPath(name).parts,
                    '归档不能包含绝对路径或 ..。')
            name = str(PurePosixPath(name))
            if member.isdir():
                require(name == 'dispatch', '归档中多套了目录：' + name)
                continue
            require(member.isfile() and not member.issparse(), '交付成员必须是普通文件，不能是链接或特殊文件。')
            require(name in expected, '归档包含多余文件或路径层级错误：' + name)
            require(name not in seen, '归档中有重复成员：' + name)
            require(member.size <= 65536, '归档成员过大：' + name)
            seen.add(name)
            with tar.extractfile(member) as f:
                text = f.read().decode('utf-8')
            if name.endswith('relay.conf'):
                validate_config(text, s, final=True)
                require(member.mode & 0o7777 == 0o600, '归档内 relay.conf 权限应为 600；修改后重新打包。')
            elif name.endswith('crew.csv'):
                require(text == crew(s), '归档中的 crew.csv 与本局名单不符。')
            else:
                require(text == receipt(s), '归档中的 receipt.txt 与本局启动回执不符。')
    require(seen == expected, '归档缺少：' + ', '.join(sorted(expected - seen)))


def validate(n, session, s, answer):
    root = session / 'station'
    if n == 1:
        require(Path.cwd().resolve() == (root / 'airlock').resolve(), '先 cd 到 station/airlock，再在里面提交。')
        require(safe_path(root, 'work/evidence').is_dir(), '还没有 work/evidence 目录；请用 mkdir 创建。')
        require(answer == s['beacon'], explain_options('信标数字不对；用 ls -a 查看 .beacon- 后面的四位数字。', 'ls-a'))
    elif n == 2:
        validate_backup(root, s)
    elif n == 3:
        equal_file(root, 'work/evidence/route.txt', route(s))
        for path in ['inbox/route.pending'] + ['inbox/' + name for name in cleanup_targets(s)]:
            require(not safe_path(root, path).exists(), '这个文件仍在原位置：' + path)
        equal_file(root, 'inbox/crew.csv', crew(s), '名单 crew.csv 丢失或被改动，请保留原件。')
        for name, text in cleanup_kept(s).items():
            equal_file(root, 'inbox/' + name, text, '需要保留的文件被改动：inbox/' + name)
    elif n == 4:
        require(answer == s['seal'], 'SEAL 不匹配，请读取解出的 manifest.txt。')
        equal_file(root, 'work/recovered/manifest.txt', f"STATION={s['station_id']}\nSEAL={s['seal']}\n先验证密封，再修复配置。\n")
        equal_file(root, 'work/recovered/relay.conf', cfg(s, initial=True))
        equal_file(root, 'work/recovered/relay.sh', RELAY)
    elif n == 5:
        require(answer == s['code'], '不是最新授权码。请读日志最后一条 READY，忽略 HEARTBEAT 和旧 READY。')
    elif n == 6:
        validate_config(content(root, 'work/recovered/relay.conf'), s)
    elif n == 7:
        validate_relay(root, s)
        equal_file(root, 'work/recovered/receipt.txt', receipt(s), '尚未得到正确启动回执。请运行 ./relay.sh。')
    elif n == 8:
        require(worker_alive(s.get('worker')), '本局探针尚未运行或已超时。请先 lab load，再观察 top。')
        require(answer == str(s['worker']['pid']), 'PID 不匹配，请定位 COMMAND 为 station-pulse 的那一行。')
    elif n == 9:
        validate_backup(root, s)
        validate_archive(root, s)


def validate_relay(root, s):
    validate_config(content(root, 'work/recovered/relay.conf'), s)
    equal_file(root, 'work/recovered/relay.sh', RELAY, '启动脚本内容被修改，请使用原脚本。')
    for name, mode in [('relay.conf', 0o600), ('relay.sh', 0o700)]:
        p = safe_path(root, 'work/recovered/' + name)
        require(stat.S_IMODE(p.stat().st_mode) == mode,
                f'{name} 权限应为 {mode:o}，当前是 {stat.S_IMODE(p.stat().st_mode):o}。')


def show_status(s):
    print(f"\n  ORBIT / 失联空间站    {s['station_id']}    {len(s['done'])}/9")
    print('  ' + '━' * 46)
    for i, (title, reward) in enumerate(zip(TITLES, REWARDS), 1):
        label = '●' if i in s['done'] else '▶' if i == len(s['done']) + 1 else '○'
        print(f'  {label} {i:02}  {title}' + (f'  / {reward}' if i in s['done'] else ''))
    print()


def report(session, s):
    out = {'lab': 'ORBIT', 'version': VERSION, 'run_id': s['id'], 'station': s['station_id'],
           'completed': len(s['done']) == 9, 'phases_passed': len(s['done']),
           'created_at': s['created_at'], 'completed_at': s.get('completed_at'),
           'hints': s['hints'], 'attempts': s['attempts'], 'events': s['events'],
           'result': s.get('flag'),
           'archive_sha256': s.get('archive_sha256'),
           'validation_scope': '文件结果与当前进程验证；不证明命令使用过程或独立学习成效。'}
    p = safe_path(session, 'report.json')
    atomic_json(p, out)
    return p


def ending(session, s):
    print('\n  ✦  RESCUE COMPLETE  ✦\n')
    print('地面站：“交付包已验证。三名船员已接入返航轨道。”')
    print('你从一个隐藏目录出发，保住黑匣子，恢复中继，送出了最后一份救援包。')
    print('\n救援凭证：' + s['flag'])
    print('交付物：' + str(session / 'station/work/rescue.tar.gz'))
    print('通关报告：' + str(report(session, s)))
    print(explain_options('输入 exit 退出。想换一组线索重玩：bash start.sh --new。', 'lab-new') + '\n')


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
        print(f'\n[通过 {n:02}/09] {REWARDS[n-1]}')
        print('本关知识：' + REFLECTIONS[n-1])
        if n == 9:
            s['completed_at'] = now()
            archive = session / 'station/work/rescue.tar.gz'
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            s['flag'] = 'ORBIT{' + s['station_id'] + '-' + digest[:16].upper() + '}'
            s['archive_sha256'] = digest
            ending(session, s)
        else:
            print(f'\n下一关 {n+1:02} / {TITLES[n]}\n' + brief(n+1, s))
        return 0
    except (LabError, OSError, UnicodeError, tarfile.TarError, EOFError) as e:
        s['events'].append({'at': now(), 'phase': n, 'result': 'retry', 'reason': str(e)})
        print('\n[尚未通过] ' + str(e))
        print('进度未回退。lab hint 获取提示；lab learn 查命令；误操作可 lab repair。')
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
    sync_guides(root)
    s['events'].append({'at': now(), 'phase': n, 'result': 'repair'})
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
    if topic == 'all':
        print(text)
    elif topic:
        require(topic in sections, '没有这个笔记主题；输入 lab notes 查看目录。')
        print(sections[topic][1])
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
                print('\n提示：lab learn 查看用法；lab hint 逐级求助；lab notes 查看命令参数笔记。')
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
        print(f'提示 {level}/3（不扣分）：\n' + HINTS[n-1][level-1])
    elif cmd == 'learn':
        require(n <= 9, '已经通关，可用 lab notes 查命令笔记，或阅读 STUDENT.md。')
        print(CARDS[n-1])
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
        write(session / 'station', 'work/recovered/receipt.txt', receipt(s), 0o600)
        print('RELAY ONLINE：启动成功，receipt.txt 已写入。现在 lab check。')
    elif cmd == 'repair':
        repair(session, s)
    elif cmd == 'report':
        print(f"本局完成 {len(s['done'])}/9 关；检查次数 {sum(s['attempts'].values())}；不设扣分。")
        print('报告：' + str(report(session, s)))
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '_worker':
        worker(Path(sys.argv[2]), sys.argv[3])
        return 0
    parser = argparse.ArgumentParser(description='ORBIT Linux 学习实验')
    sub = parser.add_subparsers(dest='command')
    p = sub.add_parser('prepare'); p.add_argument('--new', action='store_true')
    sub.add_parser('doctor')
    for name in ['mission', 'status', 'help', 'root', 'learn', 'load', 'relay', 'repair', 'report']:
        sub.add_parser(name)
    p = sub.add_parser('check'); p.add_argument('answer', nargs='?', default='')
    p = sub.add_parser('hint'); p.add_argument('level', nargs='?', type=int, choices=[1, 2, 3])
    p = sub.add_parser('notes'); p.add_argument('topic', nargs='?', default='')
    p = sub.add_parser('stop'); p.add_argument('--quiet', action='store_true')
    args = parser.parse_args()
    args.command = args.command or 'mission'
    if args.command == 'prepare':
        print(prepare(args.new)); return 0
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
        finally:
            atomic_json(session / 'state.json', s)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (LabError, OSError, ValueError, tarfile.TarError) as exc:
        print('[ORBIT] ' + str(exc), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\n已取消；已通过的关卡会保留。', file=sys.stderr)
        sys.exit(130)
