"""Bounded post-command observations, not an interpreter or stderr classifier.

Only a small set of unambiguous command forms is understood. No commands are
executed, no file contents are read, and unknown syntax is left unclassified.
Paths are checked lexically before lstat; symlinks and external operands are
excluded. A missing path after a failed command is evidence, not its proven cause.
"""
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import re
import stat

from cli_messages import PUBLIC_COMMANDS
from knowledge import PHASE_CONCEPTS


COMMAND_CONCEPTS = {
    'ls': 'hidden', 'pwd': 'paths', 'cd': 'paths', 'mkdir': 'mkdir',
    'cp': 'copy', 'mv': 'move', 'rm': 'glob', 'rmdir': 'mkdir',
    'tar': 'archive_read', 'cat': 'logs', 'tail': 'logs', 'head': 'logs',
    'vim': 'editing', 'chmod': 'permissions', 'top': 'process',
    'grep': 'logs', 'find': 'paths', 'du': 'paths', 'df': 'paths',
    'less': 'logs', 'man': 'paths', 'help': 'paths', 'lab': 'paths', 'exit': 'paths',
}
_LAB_WORDS = {'notes', 'hint', 'learn', 'check', 'status', 'help', 'tutor', 'notebook', 'review'}
_SHORT_FLAGS = {
    'ls': set('aAlhtrRdFSip'), 'cd': set('LP'), 'pwd': set('LP'),
    'mkdir': set('pv'), 'rmdir': set('pv'), 'cp': set('arRifnvpuHLPlsdx'),
    'mv': set('ifnvTbu'), 'rm': set('rfidvI'), 'cat': set('AbEnstTv'),
    'tail': set('fqv'), 'head': set('qv'), 'chmod': set('Rfv'),
}
_LONG_FLAGS = {
    'ls': {'--all', '--almost-all', '--directory', '--recursive', '--human-readable', '--reverse'},
    'cd': set(), 'pwd': {'--logical', '--physical'},
    'mkdir': {'--parents', '--verbose'}, 'rmdir': {'--parents', '--verbose'},
    'cp': {'--archive', '--recursive', '--force', '--interactive', '--no-clobber', '--verbose',
           '--parents', '--dereference', '--no-dereference'},
    'mv': {'--force', '--interactive', '--no-clobber', '--verbose', '--no-target-directory'},
    'rm': {'--force', '--recursive', '--verbose', '--dir'},
    'cat': {'--show-all', '--number', '--number-nonblank', '--squeeze-blank', '--show-ends', '--show-tabs'},
    'tail': {'--quiet', '--silent', '--verbose'}, 'head': {'--quiet', '--silent', '--verbose'},
    'chmod': {'--recursive', '--verbose', '--changes', '--silent', '--quiet'},
    'tar': {'--extract', '--create', '--list', '--verbose', '--gzip'},
}
_VALUE_FLAGS = {'tail': {'-n', '-c', '--lines', '--bytes'},
                'head': {'-n', '-c', '--lines', '--bytes'}}
_MIN_OPERANDS = {'mkdir': 1, 'rmdir': 1, 'cp': 2, 'mv': 2, 'rm': 1, 'chmod': 2}
_NAME = re.compile(r'[A-Za-z0-9_.-]{1,64}')
_SENSITIVE = re.compile(r'(?i)(api[-_]?key|auth|token|code|secret|password|passwd|credential|'
                        r'\.beacon|(?:^|[-_.])sk[-_]|seal-|link-|evac-|(?:orbit|linuxlab)\{|'
                        r'ai\.local|^\.env(?:\.|$)|id_rsa|id_ed25519|state\.json)')
_SPECIAL = re.compile(r'[\x00-\x20\x7f-\x9f;|&$`()<>{}\[\]*?~\\:]')


def _private(s):
    keys = ('beacon', 'seal', 'channel', 'code', 'final_channel', 'final_code',
            'receipt', 'integrity', 'flag', 'station_id', 'id', 'api_key')
    result = [str(s[key]) for key in keys if s.get(key) is not None and str(s[key])]
    worker = s.get('worker')
    if isinstance(worker, dict):
        result.extend(str(worker[key]) for key in ('pid', 'token') if worker.get(key) is not None)
    return result


def _safe_name(value, private):
    if (not _NAME.fullmatch(value) or value in ('.', '..') or value.startswith('-')
            or _SENSITIVE.search(value) or re.search(r'[A-Za-z0-9]{24,}', value)):
        return False
    return not any(secret == value or (len(secret) >= 3 and secret in value) for secret in private)


def _one_edit(left, right):
    """One insertion/deletion/substitution or adjacent transposition, no guessing."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        changed = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
        return (len(changed) == 1 or (len(changed) == 2 and changed[1] == changed[0] + 1
                and left[changed[0]] == right[changed[1]] and left[changed[1]] == right[changed[0]]))
    short, long = sorted((left, right), key=len)
    return any(long[:i] + long[i + 1:] == short for i in range(len(long)))


def _unique_match(value, choices):
    same_case = [candidate for candidate in choices if candidate.lower() == value.lower()]
    if len(same_case) == 1:
        return same_case[0]
    candidates = [candidate for candidate in choices if _one_edit(value.lower(), candidate.lower())]
    return candidates[0] if len(candidates) == 1 else ''


def _parts(token, start, private):
    """Normalize a relative operand without ever stepping above the lab root."""
    parts = list(start)
    for part in token.split('/'):
        if part in ('', '.'):
            continue
        if part == '..':
            if not parts:
                return None
            parts.pop()
        elif _safe_name(part, private):
            parts.append(part)
        else:
            return None
    return tuple(parts)


def _inspect(root, parts):
    """Return (exists, first_missing_index), excluding every symlink/special node."""
    current = root
    try:
        if not stat.S_ISDIR(current.lstat().st_mode):
            return None
        for index, part in enumerate(parts):
            current = current / part
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError:
                return False, index
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                return None
            if index < len(parts) - 1 and not stat.S_ISDIR(mode):
                return None
        return True, None
    except OSError:
        return None


def _operand(token, root, cwd_parts, private):
    if not isinstance(token, str) or len(token) > 256 or _SPECIAL.search(token):
        return None
    if token.startswith('/'):
        try:
            relative = Path(token).relative_to(root).as_posix()
        except ValueError:
            return None
        start = ()
    else:
        relative, start = token, cwd_parts
    # Do not let lexical cancellation hide a symlink, e.g. link/../missing.
    traversed = tuple(start)
    for component in relative.split('/'):
        traversed = _parts(component, traversed, private)
        if traversed is None or _inspect(root, traversed) is None:
            return None
    parts = _parts(relative, start, private)
    if parts is None or _inspect(root, parts) is None:
        return None
    return parts


def _relative_operand(parts, cwd_parts):
    common = 0
    while common < min(len(parts), len(cwd_parts)) and parts[common] == cwd_parts[common]:
        common += 1
    return '/'.join(['..'] * (len(cwd_parts) - common) + list(parts[common:])) or '.'


def _item(kind, command, observed, expected, location, concept, certainty, summary, exit_code, evidence=()):
    result = dict(kind=kind, command=command, observed=observed, expected=expected,
                  location=location, concept=concept, certainty=certainty, summary=summary,
                  evidence=[f'这次简单输入结束时退出码为 {exit_code}；没有采集原生错误输出。', *evidence])
    # Time, repetition counts and incidental exit statuses do not split a pattern.
    stable = {key: result[key] for key in ('kind', 'command', 'observed', 'expected', 'location', 'concept')}
    result['signature'] = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return result


def _command_issue(command, words, location, exit_code, private):
    if exit_code != 127 or command in COMMAND_CONCEPTS:
        return []
    if command == 'cd..':
        return [_item('command_spacing', 'cd', command, 'cd', location, 'paths', 'candidate',
                      'cd 和 .. 之间可能少了空格。', exit_code)]
    if command.startswith('lab') and command[3:] in _LAB_WORDS:
        return [_item('command_spacing', 'lab', command, 'lab', location, 'paths', 'candidate',
                      'lab 和子命令之间可能少了空格。', exit_code)]
    if not re.fullmatch(r'[A-Za-z]{2,20}', command) or not _safe_name(command, private):
        return []
    candidate = _unique_match(command, COMMAND_CONCEPTS)
    if not candidate:
        return []
    case = command.lower() == candidate
    return [_item('command_case' if case else 'command_typo', candidate, command, candidate,
                  location, COMMAND_CONCEPTS[candidate], 'candidate',
                  f'输入的 {command} 与课程命令 {candidate} ' + ('仅大小写不同。' if case else '拼写接近。'), exit_code,
                  ['退出码与命令查找失败一致；近似名称仍需本人核对，不能排除环境问题。'])]


def _parse(command, arguments, location, exit_code, private):
    """Return operands or None, plus a conservative argument observation."""
    operands, issues = [], []
    separator = False
    index = 0
    while index < len(arguments):
        word = arguments[index]
        if word in ('--help', '--version'):
            return None, []
        if word == '--' and not separator:
            separator = True
        elif not separator and word in _VALUE_FLAGS.get(command, set()):
            if index + 1 == len(arguments):
                return None, [_item('option_value_missing', command, word, '', location,
                    COMMAND_CONCEPTS[command], 'observed', f'输入中的 {word} 后没有提供选项值。', exit_code)]
            index += 1
            if not re.fullmatch(r'[+-]?\d{1,6}', arguments[index]):
                return None, []
        elif not separator and word.startswith('--'):
            choices = _LONG_FLAGS.get(command, set()) | _VALUE_FLAGS.get(command, set())
            if word not in choices:
                # Native getopt may accept unambiguous long-option prefixes.
                # Unknown options with values or unusual text are never retained.
                if (not re.fullmatch(r'--[A-Za-z-]{3,32}', word)
                        or any(option.startswith(word) for option in choices)):
                    return None, []
                candidate = _unique_match(word, choices)
                if not candidate or not _safe_name(word[2:], private):
                    return None, []
                return None, [_item('option_typo', command, word, candidate, location,
                    COMMAND_CONCEPTS[command], 'candidate',
                    f'{word} 与 {command} 的选项 {candidate} 拼写接近，建议查原生帮助核对。', exit_code,
                    ['未识别的选项不等于无效选项；这里只记录一个拼写候选。'])]
        elif not separator and word.startswith('-') and word != '-':
            if not word[1:] or any(char not in _SHORT_FLAGS.get(command, set()) for char in word[1:]):
                return None, []
        else:
            operands.append(word)
        index += 1
    return operands, issues


def _path_issue(command, token, root, cwd_parts, location, exit_code, private):
    parts = _operand(token, root, cwd_parts, private)
    if parts is None:
        return None
    inspected = _inspect(root, parts)
    if inspected is None or inspected[0]:
        return None
    missing = inspected[1]
    observed = _relative_operand(parts, cwd_parts)
    parent_parts = parts[:missing]
    candidate_parts = None
    try:
        children = list(islice(root.joinpath(*parent_parts).iterdir(), 129))
        if len(children) <= 128:
            names = [child.name for child in children
                     if _safe_name(child.name, private)
                     and _inspect(root, (*parent_parts, child.name)) == (True, None)]
            candidate = _unique_match(parts[missing], names)
            if candidate:
                possible = (*parent_parts, candidate, *parts[missing + 1:])
                if _inspect(root, possible) == (True, None):
                    candidate_parts = possible
    except OSError:
        pass
    kind, expected = 'path_missing', ''
    summary = f'命令结束后，在当前实验目录位置找不到输入的 {observed}。'
    evidence = ['只检查了实验目录内的路径类型和名称，没有读取文件内容。']
    if candidate_parts:
        expected = _relative_operand(candidate_parts, cwd_parts)
        case = parts[missing].lower() == candidate_parts[missing].lower()
        kind = 'path_case' if case else 'path_typo'
        summary += f' 同一位置存在近似名称 {expected}，请核对' + ('大小写。' if case else '拼写。')
    elif cwd_parts and not token.startswith('/'):
        from_root = _parts(token, (), private)
        if from_root is not None and _inspect(root, from_root) == (True, None):
            kind = 'path_base'
            expected = _relative_operand(from_root, cwd_parts)
            summary += ' 相同写法从实验根目录出发能找到对象，可能混淆了相对路径的起点。'
            evidence.append('这里只是位置差异候选，不代表原生错误原因已确定。')
    return _item(kind, command, observed, expected, location, 'paths',
                 'observed' if kind == 'path_missing' else 'candidate', summary, exit_code, evidence)


def detect(s, root, cwd, words, exit_code):
    """Return sanitized local diagnostics for one failed, simple input."""
    if type(exit_code) is not int or not 1 <= exit_code <= 255 or not isinstance(words, list) or not words:
        return []
    if len(words) > 32 or any(not isinstance(word, str) or len(word) > 256 or _SPECIAL.search(word) for word in words):
        return []
    private = _private(s)
    # A secret anywhere in this input suppresses the entire diagnostic, including
    # missing-argument messages that would otherwise avoid echoing the operand.
    if any(_SENSITIVE.search(word) or any(secret == word or (len(secret) >= 3 and secret in word)
                                        for secret in private) for word in words):
        return []
    root = Path(os.path.abspath(root))
    cwd = Path(os.path.abspath(cwd))
    try:
        cwd_relative = cwd.relative_to(root).as_posix()
    except ValueError:
        return []
    cwd_parts = _parts(cwd_relative, (), private)
    if cwd_parts is None or _inspect(root, cwd_parts) != (True, None):
        return []
    location = '/'.join(cwd_parts) or '.'
    command = words[0]
    if command == 'lab':
        # Never consume answers, questions, scene themes or any other lab args.
        if len(words) != 2 or words[1] in PUBLIC_COMMANDS or not re.fullmatch(r'[A-Za-z]{2,20}', words[1]):
            return []
        candidate = _unique_match(words[1], PUBLIC_COMMANDS)
        if not candidate or not _safe_name(words[1], private):
            return []
        phase = min(len(s.get('done', [])) + 1, 9)
        return [_item('lab_command_typo', 'lab', words[1], candidate, location,
                      PHASE_CONCEPTS[phase][0], 'candidate',
                      f'平台子命令 {words[1]} 与 {candidate} 拼写接近；这只是平台语法观察，不据此推断知识掌握。',
                      exit_code)]
    if command not in COMMAND_CONCEPTS:
        return _command_issue(command, words, location, exit_code, private)
    if exit_code >= 126:
        return []  # Lookup/execution failures and signals do not establish operand errors.
    if command not in _SHORT_FLAGS and command != 'tar':
        return []
    operands, issues = _parse(command, words[1:], location, exit_code, private)
    if operands is None or issues:
        return issues
    path_operands = operands[1:] if command == 'chmod' else operands
    if any(token != '-' and _operand(token, root, cwd_parts, private) is None for token in path_operands):
        return []
    if command in _MIN_OPERANDS and len(operands) < _MIN_OPERANDS[command]:
        # Do not preserve an arbitrary operand just to report an argument count.
        return [_item('missing_operands', command, command, '', location,
                      COMMAND_CONCEPTS[command], 'observed',
                      f'这个简单 {command} 写法中只看到 {len(operands)} 个位置参数；常见用法至少需要 {_MIN_OPERANDS[command]} 个。',
                      exit_code, ['这是输入结构观察，不是从退出码推断出的原生报错。'])]
    if command in ('ls', 'cd', 'cat', 'tail', 'head'):
        sources = operands
    elif command in ('cp', 'mv') and len(operands) == 2:
        sources = operands[:1]
    elif command == 'chmod' and len(operands) == 2 and re.fullmatch(r'[0-7]{3,4}|[ugoa]+[+=-][rwxXst]+', operands[0]):
        sources = operands[1:]
    else:
        return []
    result = []
    for token in sources[:4]:
        if token == '-':
            continue  # stdin/stdout conventions are not filesystem operands.
        issue = _path_issue(command, token, root, cwd_parts, location, exit_code, private)
        if issue:
            result.append(issue)
    return result
