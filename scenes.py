"""Validated narrative bundles; story text never changes assessment rules."""
import copy
import json
from pathlib import Path
import re
import unicodedata

from layout import bindings, validate_bindings

APP = Path(__file__).resolve().parent
BUILTIN_SCENES = ('space', 'ocean', 'museum', 'anime')
MAX_BUNDLE_BYTES = 65536
FIELDS = {'id', 'title', 'description', 'background', 'titles',
          'introductions', 'rewards', 'ending', 'bindings'}
V2_FIELDS = FIELDS | {'schema_version', 'task_ids', 'entities'}


def _text(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'情境字段 {label} 需要非空文字，最多 {limit} 个字符。')
    if any(unicodedata.category(char).startswith('C') for char in value):
        raise ValueError(f'情境字段 {label} 不能包含控制字符或不可见格式字符。')
    return value


def validate_bundle(bundle):
    if not isinstance(bundle, dict) or set(bundle) not in (FIELDS, V2_FIELDS):
        raise ValueError('情境文件字段不完整或含有不支持的字段；请参照内置 JSON 情境包。')
    result = {}
    ident = bundle['id']
    if not isinstance(ident, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', ident):
        raise ValueError('情境 id 只能用小写英文字母开头，后接字母、数字、下划线或连字符，最多 48 位。')
    result['id'] = ident
    for key, limit in [('title', 80), ('description', 200),
                       ('background', 1200), ('ending', 1200)]:
        result[key] = _text(bundle[key], key, limit)
    for key, limit in [('titles', 80), ('introductions', 1200), ('rewards', 80)]:
        values = bundle[key]
        if not isinstance(values, list) or len(values) != 9:
            raise ValueError(f'情境字段 {key} 必须按关卡顺序包含 9 段文字。')
        result[key] = [_text(value, f'{key}[{index + 1}]', limit)
                       for index, value in enumerate(values)]
    result['bindings'] = validate_bindings(bundle['bindings'])
    if set(bundle) == V2_FIELDS:
        from scene_blueprint import validate_entities, compile_bindings
        from tasks import task_ids
        if type(bundle['schema_version']) is not int or bundle['schema_version'] != 2:
            raise ValueError('不支持这个情景编译版本。')
        if bundle['task_ids'] != list(task_ids()):
            raise ValueError('情景必须对应课程规定的任务标识和顺序。')
        entities = validate_entities(bundle['entities'])
        if result['bindings'] != compile_bindings(entities):
            raise ValueError('情景文件名必须与其语义对象编译结果一致。')
        result.update(schema_version=2, task_ids=list(task_ids()), entities=entities)
    if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > MAX_BUNDLE_BYTES:
        raise ValueError('情境包内容不能超过 64 KiB。')
    return result


def load(name='space'):
    if not isinstance(name, str) or not name:
        raise ValueError('请提供情境名称或本地 .json 文件路径。')
    if name in BUILTIN_SCENES:
        path = APP / 'scenes' / (name + '.json')
    elif name.lower().endswith('.json'):
        path = Path(name).expanduser()
    else:
        raise ValueError('没有这个内置情境。用 lab scene 查看名称，或提供本地 .json 情境包。')
    try:
        with path.open('rb') as source:
            raw = source.read(MAX_BUNDLE_BYTES + 1)
    except OSError as exc:
        raise ValueError('无法读取情境文件；请检查路径和文件权限。') from exc
    if len(raw) > MAX_BUNDLE_BYTES:
        raise ValueError('情境文件不能超过 64 KiB。')
    try:
        bundle = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError('情境文件不是有效的 UTF-8 JSON。') from exc
    return validate_bundle(bundle)


def get(state):
    if 'scene_bundle' in state:
        return validate_bundle(state['scene_bundle'])
    name = state.get('scene', 'space')
    if name not in BUILTIN_SCENES:
        raise ValueError('当前情境缺少有效快照；请用 lab scene 选择内置情境或本地情境包。')
    return load(name)


def initialize(state, name='space'):
    bundle = validate_bundle(name) if isinstance(name, dict) else load(name)
    state['scene'] = bundle['id']
    state['scene_bundle'] = copy.deepcopy(bundle)
    state['asset_bindings'] = dict(bundle['bindings'])
    return bundle


def choose(state, name=''):
    if not name:
        current = get(state)
        options = [load(key) for key in BUILTIN_SCENES]
        return '\n'.join([
            '当前情境：' + current['title'],
            *[f'  {item["id"]} · {item["title"]} · {item["description"]}'
              for item in options],
            '用 lab scene 名称 或 lab scene 本地文件.json 切换故事。',
            '已有周目的文件名沿用当前周目；切换不改任务要求、学生文件和进度。',
            '要使用新主题的配套文件名，在项目目录运行 bash start.sh --new --scene anime。',
        ])
    bundle = load(name)
    # Old sessions used original paths, including those with ocean/museum skins.
    # Validate all inputs before mutating state, so rejected bundles are atomic.
    existing_bindings = bindings(state)
    state['scene'] = bundle['id']
    state['scene_bundle'] = copy.deepcopy(bundle)
    state['asset_bindings'] = existing_bindings
    return ('已选择：' + bundle['title'] + '。输入 lab 查看完整故事与当前任务。\n'
            '已有周目的文件名沿用当前周目，任务要求与学习进度不变。\n'
            '要使用新主题配套文件名，在项目目录运行 bash start.sh --new --scene '
            + (name if name in BUILTIN_SCENES else '本地文件.json') + '。')
