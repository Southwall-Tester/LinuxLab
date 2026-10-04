"""Bounded local Bash observations, including safe error fragments."""
import hashlib
import re
import shlex
from pathlib import Path

from learning import stamp
import layout
import error_patterns
import input_diagnostics

COMMANDS = {'ls', 'pwd', 'cd', 'mkdir', 'cp', 'mv', 'rm', 'tar', 'cat', 'tail',
            'head', 'vim', 'chmod', 'top', 'grep', 'find'}
FLAGS = {'-a', '-r', '-R', '-p', '-l', '-la', '-al', '-f', '-n', '-i', '-v',
         '-t', '-x', '-c', '-z', '-C', '-A', '--all', '--almost-all',
         '--recursive', '--archive', '--parents'}
ROLES = {'blackbox': 'original', 'work/backup': 'backup',
         'work/recovered': 'recovered', 'work/dispatch': 'delivery',
         'work/rescue.tar.gz': 'archive', 'work/evidence': 'evidence',
         'inbox': 'inbox', 'airlock': 'entry', 'logs': 'logs',
         'supplies': 'supplies', 'finale': 'finale'}


def _command_semantics_available(kind):
    # None keeps the older direct-call interface used by local fixtures. The
    # live prompt hook supplies a kind; unrecognized metadata is never trusted.
    return kind is None or kind in ('file', 'builtin', 'missing')


def role(path, cwd, root, s=None):
    # Path.resolve follows links only for role classification; never opens their targets.
    # Remove a simple trailing glob to identify its parent role.
    path = path.split('*', 1)[0] if '*' in path else path
    try:
        relative = (Path(cwd) / path).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError, RuntimeError):
        return 'outside'
    roles = {layout.rel(s or {}, prefix): name for prefix, name in ROLES.items()}
    for prefix, name in sorted(roles.items(), key=lambda item: len(item[0]), reverse=True):
        if relative == prefix or relative.startswith(prefix + '/'):
            return name
    return 'other'


def scene_facts(root, s=None):
    """Small allowlisted observation, not a grader; never follows symlinks."""
    def ordinary(rel):
        p = root
        for part in Path(layout.rel(s or {}, rel)).parts:
            p = p / part
            if p.is_symlink():
                return False
        return p.is_file()
    return {'backup_hidden_present': ordinary('work/backup/.integrity'),
            'backup_nested_present': ordinary('work/backup/blackbox/boot.log')}


def config_fingerprint(root, s=None):
    p = root
    for part in Path(layout.rel(s or {}, 'work/recovered/relay.conf')).parts:
        p = p / part
        if p.is_symlink():
            return None
    if p.is_file() and p.stat().st_size <= 65536:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    return None


def record(s, session, line, exit_code, cwd, dotglob=False, command_kind=None):
    if not s.get('tracking_enabled') or not Path(cwd).resolve().is_relative_to((session / 'station').resolve()):
        return
    # history 1 prefixes an index; only tokenize, never execute or retain this text.
    line = re.sub(r'^\s*\d+\s+\*?\s*', '', line, count=1)
    try:
        words = shlex.split(line, comments=True)
    except ValueError:
        words = []
    if not words or words[0] == 'exit' or (words[0] == 'lab' and exit_code == 0):
        return
    complex_line = any(c in line for c in (';', '|', '&', '\n', '$', '`', '(', ')', '<', '>'))
    semantic_input = (_command_semantics_available(command_kind)
                      and not any(word in ('--help', '--version') for word in words[1:]))
    if complex_line:
        command = '组合命令'
    elif not semantic_input:
        command = '未解释的命令'
    else:
        command = words[0] if words[0] in COMMANDS else '其他命令'
    root = session / 'station'
    flags, operands, raw_operands = [], [], []
    known_options = semantic_input
    if command in COMMANDS:
        after_separator = False
        for word in words[1:]:
            if word == '--':
                after_separator = True
            elif not after_separator and word.startswith('-'):
                if word in FLAGS or (command == 'tar' and re.fullmatch(r'-[ctxzfv]+', word)):
                    flags.append(word)
                else:
                    known_options = False
            else:
                operands.append(role(word, cwd, root, s))
                raw_operands.append(word)
    event = {'at': stamp(), 'phase': min(len(s['done']) + 1, 9),
             'command': command, 'exit_code': exit_code, 'flags': flags,
             'operand_roles': operands, 'known_options': known_options, 'facts': scene_facts(root, s)}
    if command_kind is not None:
        event['command_kind'] = (command_kind if command_kind in
                                ('alias', 'function', 'keyword', 'file', 'builtin', 'missing') else 'unknown')
    # Conservative: quoted/mixed syntax remains unknown, as do complex commands.
    event['plain_star_excludes_hidden'] = (command == 'cp' and not dotglob
        and '*' in line and not any(c in line for c in ('"', "'", '{', '}', '?', '[', ']'))
        and any(Path(word).name.startswith('*') and role(word, cwd, root, s) == 'original'
                for word in raw_operands[:-1]))
    fingerprint = config_fingerprint(root, s)
    previous = s.get('last_observed_config')
    event['config_changed_since_observation'] = (fingerprint is not None and previous is not None
                                                  and fingerprint != previous)
    s['last_observed_config'] = fingerprint
    s['shell_sequence'] = s.get('shell_sequence', 0) + 1
    event['sequence'] = s['shell_sequence']
    events = s.setdefault('shell_observations', [])
    events.append(event)
    del events[:-2000]
    # Actual submitted simple inputs only. Never re-execute commands, and never
    # turn an unparsed compound line or a nonzero status alone into a diagnosis.
    if (not complex_line and semantic_input
            and not any(c in line for c in ('*', '?', '[', ']', '{', '}', '~'))):
        items = input_diagnostics.detect(s, root, Path(cwd), words, exit_code)
        location = Path(cwd).resolve().relative_to(root.resolve()).as_posix()
        error_patterns.record(s, items, words, exit_code, location, event['phase'], event['at'])


def display(s):
    lines = ['本地操作记录（最近 10 条）：']
    for item in s.get('shell_observations', [])[-10:]:
        lines.append(f'{item["at"]} · 第 {item["phase"]} 关 · {item["command"]} · 退出码 {item["exit_code"]}')
        if item.get('flags') or item.get('operand_roles'):
            lines.append('  选项：' + ', '.join(item.get('flags', [])) + '；对象角色：' + ', '.join(item.get('operand_roles', [])))
    if not s.get('shell_observations'):
        lines.append('暂无记录。lab tracking on 可开启，lab tracking off 可关闭。')
    lines.extend(['', *error_patterns.lines(s)])
    lines.append('保留有限操作特征，以及筛选后的错误命令词、选项或实验内路径片段；不保存完整命令。')
    lines.append('不记录输出、按键、删除或停顿；退出码不是知识掌握结论。')
    return '\n'.join(lines)


def evidence_for(s, phase, item, facts):
    """Correlate actual bounded observations; never infer a particular editor action."""
    observations = s.get('shell_observations', [])
    # Only consider this phase's operations after the last check/repair.
    boundary = next((e.get('operation_cursor', 0) for e in reversed(s['events'][:-1])
                     if e.get('phase') == phase and e.get('result') in ('passed', 'retry', 'repair')), 0)
    recent = [e for e in observations[-20:] if e['phase'] == phase and e.get('sequence', 0) > boundary]
    evidence = []
    for event in reversed(recent):
        if not _command_semantics_available(event.get('command_kind')):
            continue
        if item['code'] == 'backup' and event['command'] == 'cp':
            roles = event.get('operand_roles', [])
            if 'original' in roles and 'backup' in roles:
                if 'hidden_missing' in facts and event.get('plain_star_excludes_hidden'):
                    evidence.append('记录到原件到备份的 cp 输入使用了不含隐藏项的星号模式；随后检查发现隐藏项缺失。')
                    item['concepts'] = ['hidden', 'copy', 'glob', 'integrity']
                    item['possible_causes'] = ['本次通配符选择范围与缺失现象一致，优先核对隐藏项；仍需排除其他后续改动']
                elif 'nested_backup' in facts and event.get('facts', {}).get('backup_nested_present'):
                    evidence.append('复制操作后的目录观察和本次检查均发现备份多套了一层目录。')
                    item['possible_causes'] = ['目标目录已经存在时，复制整个目录可能产生嵌套；请核对源与目标语义']
            break
        if item['code'].startswith('config_') and event['command'] == 'vim':
            if 'recovered' in event.get('operand_roles', []):
                if event.get('config_changed_since_observation'):
                    evidence.append('观察到 Vim 命令结束后磁盘配置内容发生变化，但本次字段检查仍不满足。')
                else:
                    evidence.append('观察到针对恢复区的 Vim 命令；未获得可确认磁盘配置变化的证据，保存操作仍需核对。')
            break
        relevant = {
            'location': {'cd', 'pwd'}, 'directory': {'mkdir'}, 'beacon': {'ls'},
            'move': {'cp', 'mv'}, 'cleanup': {'rm'}, 'preserve': {'rm', 'mv'},
            'seal': {'tar', 'cat'}, 'extraction': {'tar'}, 'log_record': {'tail', 'cat'},
            'permissions': {'chmod'}, 'receipt': {'其他命令'},
            'process_absent': {'top'}, 'process_identity': {'top'},
            'archive_missing': {'tar'}, 'archive_layout': {'tar'},
            'archive_content': {'tar'}, 'archive_permissions': {'tar'},
        }
        if event['command'] in relevant.get(item['code'], set()):
            command = event['command']
            if command == '其他命令':
                continue  # Never claim an unidentified command was the relay.
            evidence.append(f'本次检查前记录到 {command} 输入，退出码为 {event["exit_code"]}；检查结果仍为“{item["observation"]}”。')
            if (item['code'] == 'move' and command == 'cp'
                    and 'inbox' in event.get('operand_roles', []) and 'evidence' in event.get('operand_roles', [])):
                item['possible_causes'] = ['最近记录的是复制；复制不会移除源文件，需核对任务是否要求移动或改名']
            elif (item['code'] == 'beacon' and command == 'ls' and event.get('known_options')
                  and not any('a' in f or 'A' in f for f in event.get('flags', []))):
                item['possible_causes'] = ['最近的列表操作没有记录到包含隐藏项的选项；需确认实际观察范围', '名称识别或输入也可能有误']
            elif item['code'] == 'extraction' and command == 'tar' and any('t' in f for f in event.get('flags', [])):
                item['possible_causes'] = ['最近记录到列清单操作；列清单不会提取成员，需核对是否已实际解包']
            break
    return evidence
