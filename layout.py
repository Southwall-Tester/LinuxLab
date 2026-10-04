"""Map stable task asset roles to validated per-session filenames."""
import re
from pathlib import PurePosixPath

BINDING_KEYS = (
    'airlock', 'work', 'evidence', 'blackbox', 'backup', 'inbox', 'supplies',
    'logs', 'recovered', 'finale', 'dispatch', 'boot.log', '.integrity',
    'sensors', 'pressure.csv', 'route.pending', 'route.txt', 'crew.csv',
    'manifest.txt', 'relay.conf', 'relay.conf.draft', 'relay.sh', 'receipt.txt',
    'comms.log', 'pulse.log', 'rescue.tar.gz', 'capsule.tar.gz', 'final.log',
    'discard.tmp', 'WELCOME.txt', 'MAP.txt', 'decoy-guide.txt', 'sensor.tmp',
    '.decoy-cache.tmp',
)
DEFAULT_BINDINGS = {name: name for name in BINDING_KEYS}
PROTECTED_NAMES = {'AGENTS.md', 'STUDENT.md', 'notes.md', 'docs', 'LOCAL-AI.md'}
_COMPONENT = re.compile(r'[A-Za-z0-9_.-]{1,64}')
# One substitution pass prevents cascades; slashes separate filename components.
_TOKEN = re.compile(
    r'(?<![A-Za-z0-9_.-])('
    + '|'.join(re.escape(name) for name in sorted(BINDING_KEYS, key=len, reverse=True))
    + r')(?![A-Za-z0-9_.-])'
)


def validate_bindings(mapping):
    if not isinstance(mapping, dict) or set(mapping) != set(BINDING_KEYS):
        raise ValueError('情境 bindings 必须恰好包含内置模板中的全部文件与目录标识。')
    result = {}
    used = set()
    for source in BINDING_KEYS:
        target = mapping[source]
        if (not isinstance(target, str) or not _COMPONENT.fullmatch(target)
                or target in ('.', '..') or '..' in target or target.startswith('-')):
            raise ValueError(f'情境路径 {source} 需要安全的 ASCII 单个名称，不能包含路径分隔符、空白或命令符。')
        if target.startswith('.') != source.startswith('.'):
            raise ValueError(f'情境路径 {source} 必须保留是否隐藏的属性。')
        suffix = ''.join(PurePosixPath(source).suffixes)
        if ''.join(PurePosixPath(target).suffixes) != suffix:
            raise ValueError(f'情境路径 {source} 必须保留原文件扩展名。')
        if target in PROTECTED_NAMES:
            raise ValueError('情境不能使用教学规则或说明文档的保留文件名。')
        if target in BINDING_KEYS and target != source:
            raise ValueError('情境映射不能借用另一个任务标识的原名，以免路径说明混淆。')
        if target.startswith('.beacon-') or (target.startswith('decoy-') and target.endswith('.tmp')):
            raise ValueError('情境不能占用信标或待清理文件的固定命名结构。')
        if target in used:
            raise ValueError('情境中的文件与目录映射名称不能重复。')
        used.add(target)
        result[source] = target
    return result


def bindings(state):
    # Missing bindings mean a pre-theme session, whose paths used space names.
    return validate_bindings(state.get('asset_bindings', DEFAULT_BINDINGS))


def rel(state, canonical_path):
    value = str(canonical_path)
    if '\\' in value or value.startswith('/'):
        raise ValueError('任务路径必须使用 POSIX 相对路径。')
    parts = value.split('/')
    if any(part == '..' for part in parts):
        raise ValueError('任务路径不能包含上级目录。')
    mapping = bindings(state)
    return '/'.join(mapping.get(part, part) for part in parts)


def text(state, value):
    mapping = bindings(state)
    return _TOKEN.sub(lambda match: mapping[match.group(0)], value)
