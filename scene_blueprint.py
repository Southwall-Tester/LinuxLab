"""Compile a thematic blueprint into a safe, fixed Linux exercise layout.

The model describes a world and the purpose of its objects. The compiler owns
filenames, extensions, hidden attributes and role identity. These structural
checks do not establish the quality or consistency of a generated story.
"""
import re
import unicodedata

import layout
import tasks


ROLE_SPECS = {
    'entry': {'meaning': '故事中开始工作、发现定位线索的入口', 'default_stem': 'arrival'},
    'workspace': {'meaning': '学习者整理材料和产出的工作区域', 'default_stem': 'workshop'},
    'originals': {'meaning': '必须完整保存、可用于恢复的原始资料', 'default_stem': 'records'},
    'inbox': {'meaning': '等待分类、整理和辨认的混合资料', 'default_stem': 'incoming'},
    'supplies': {'meaning': '以归档形式提供的后续任务材料', 'default_stem': 'resources'},
    'logs': {'meaning': '按时间记录事件、用于辨认有效信息的资料', 'default_stem': 'journal'},
    'evidence': {'meaning': '整理后的线索及其阅读规则', 'default_stem': 'findings'},
    'service': {'meaning': '需要配置、设定权限和启动的工作程序', 'default_stem': 'workflow'},
    'roster': {'meaning': '需要保留并随最终产物交付的名单', 'default_stem': 'members'},
    'delivery': {'meaning': '最终整理并交付给故事中接收方的成果', 'default_stem': 'handoff'},
    'finale': {'meaning': '最后阶段提供更新要求和补充材料的地方', 'default_stem': 'closing'},
    'metrics': {'meaning': '原始资料中的记录数据与需要保留的缓存', 'default_stem': 'observations'},
}
RAW_FIELDS = {'id', 'title', 'description', 'background', 'ending', 'entities', 'stages'}
_STEM = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_-]{0,19}')
_ID = re.compile(r'[a-z][a-z0-9_-]{0,47}')

# This table is implementation detail. The model sees only neutral role names.
# source -> (role, local purpose suffix). File extensions and hidden attributes
# are copied from the canonical source by the compiler, never chosen by a model.
_ASSETS = {
    'airlock': ('entry', 'area'),
    'work': ('workspace', 'area'),
    'evidence': ('evidence', 'records'),
    'blackbox': ('originals', 'source'),
    'backup': ('originals', 'backup'),
    'inbox': ('inbox', 'queue'),
    'supplies': ('supplies', 'store'),
    'logs': ('logs', 'records'),
    'recovered': ('supplies', 'recovered'),
    'finale': ('finale', 'stage'),
    'dispatch': ('delivery', 'package'),
    'boot.log': ('originals', 'events'),
    '.integrity': ('originals', 'integrity'),
    'sensors': ('metrics', 'samples'),
    'pressure.csv': ('metrics', 'measurements'),
    'route.pending': ('evidence', 'guide'),
    'route.txt': ('evidence', 'guide'),
    'crew.csv': ('roster', 'members'),
    'manifest.txt': ('supplies', 'manifest'),
    'relay.conf': ('service', 'config'),
    'relay.conf.draft': ('service', 'config'),
    'relay.sh': ('service', 'run'),
    'receipt.txt': ('service', 'receipt'),
    'comms.log': ('logs', 'events'),
    'pulse.log': ('service', 'activity'),
    'rescue.tar.gz': ('delivery', 'archive'),
    'capsule.tar.gz': ('finale', 'materials'),
    'final.log': ('finale', 'events'),
    'discard.tmp': ('finale', 'discard'),
    'WELCOME.txt': ('entry', 'welcome'),
    'MAP.txt': ('workspace', 'map'),
    'decoy-guide.txt': ('inbox', 'guide'),
    'sensor.tmp': ('metrics', 'cache'),
    '.decoy-cache.tmp': ('inbox', 'cache'),
}


def _keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f'情境蓝图 {label} 的字段不完整或含有额外字段。')


def _text(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'情境蓝图 {label} 需要非空文字，最多 {limit} 个字符。')
    if any(unicodedata.category(char).startswith('C') for char in value):
        raise ValueError(f'情境蓝图 {label} 不能包含控制字符或不可见格式字符。')
    return value.strip()


def validate_entities(entities):
    """Return a fresh, ordered set of neutral role descriptions."""
    _keys(entities, ROLE_SPECS, 'entities')
    result = {}
    for role in ROLE_SPECS:
        entity = entities[role]
        _keys(entity, ('label', 'stem'), 'entities.' + role)
        label = _text(entity['label'], 'entities.' + role + '.label', 24)
        stem = entity['stem']
        if not isinstance(stem, str) or not _STEM.fullmatch(stem):
            raise ValueError(f'情境角色 {role} 的词干只能用 1 到 20 位 ASCII 字母、数字、下划线或短横线，不能以短横线开头。')
        result[role] = {'label': label, 'stem': stem}
    return result


def schema():
    """Describe the model's semantic output; no physical layout is exposed."""
    return {
        'id': '小写英文字母开头，只用小写字母、数字、下划线或短横线，最多48字符',
        'title': '主题名称，非空，最多80字',
        'description': '主题简述，非空，最多200字',
        'background': '开场世界与角色设定，非空，最多240字',
        'ending': '九阶段完成后的故事结尾，非空，最多240字',
        'entities': {
            role: {
                'label': f'该题材中的中文语义名称，最多24字；用途：{spec["meaning"]}',
                'stem': ('符合题材的英文词干，1到20位ASCII字母/数字/下划线/短横线，'
                         '不能以短横线开头，不含点和扩展名；从该对象的主题含义取词，勿照抄角色键'),
            }
            for role, spec in ROLE_SPECS.items()
        },
        'stages': {
            task_id: {
                'title': '本阶段故事标题，非空，最多60字',
                'motivation': ('角色为什么需要完成本阶段任务，非空，最多160字；'
                               '承接已有故事，不增加任务要求、不写命令或答案'),
                'reward': '完成本阶段后的故事进展，非空，最多60字',
            }
            for task_id in tasks.task_ids()
        },
    }


def compile_bindings(entities):
    # Global role prefixes plus fixed purpose suffixes make even identical model
    # stems unambiguous. The longest possible name remains below 64 characters.
    from pathlib import PurePosixPath
    entities = validate_entities(entities)
    if set(_ASSETS) != set(layout.BINDING_KEYS):
        raise ValueError('情境编译器与任务文件清单不一致。')
    result = {}
    for source in layout.BINDING_KEYS:
        role, purpose = _ASSETS[source]
        suffix = ''.join(PurePosixPath(source).suffixes)
        hidden = '.' if source.startswith('.') else ''
        result[source] = f'{hidden}{role}-{entities[role]["stem"]}-{purpose}{suffix}'
    return layout.validate_bindings(result)


def compile_blueprint(raw):
    """Compile data only; never execute model text or read learner state/files."""
    _keys(raw, RAW_FIELDS, '根对象')
    ident = raw['id']
    if not isinstance(ident, str) or not _ID.fullmatch(ident):
        raise ValueError('情境 id 必须以小写英文字母开头，且仅含小写字母、数字、下划线或短横线，最多48位。')
    result = {'id': ident}
    for key, limit in (('title', 80), ('description', 200), ('background', 240), ('ending', 240)):
        result[key] = _text(raw[key], key, limit)
    entities = validate_entities(raw['entities'])
    task_ids = list(tasks.task_ids())
    _keys(raw['stages'], task_ids, 'stages')
    titles, introductions, rewards = [], [], []
    for task_id in task_ids:
        stage = raw['stages'][task_id]
        _keys(stage, ('title', 'motivation', 'reward'), 'stages.' + task_id)
        titles.append(_text(stage['title'], task_id + '.title', 60))
        introductions.append(_text(stage['motivation'], task_id + '.motivation', 160))
        rewards.append(_text(stage['reward'], task_id + '.reward', 60))
    result.update(titles=titles, introductions=introductions, rewards=rewards,
                  bindings=compile_bindings(entities), schema_version=2,
                  task_ids=task_ids, entities=entities)
    return result
