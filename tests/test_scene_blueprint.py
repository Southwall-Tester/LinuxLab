"""Independent compiler invariants for semantic scene blueprints."""
import copy
import json
from pathlib import Path, PurePosixPath
import sys
import unittest
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import layout
import scene_blueprint
import tasks


def example_blueprint(stem=None):
    return {
        'id': 'plant-research', 'title': '植物研究所', 'description': '整理植物观察资料',
        'background': '你和研究伙伴准备共享新一季的植物观察成果。',
        'ending': '整理完成，伙伴们可以继续分析这批观察成果。',
        'entities': {
            role: {'label': f'研究资料{index}', 'stem': stem or spec['default_stem']}
            for index, (role, spec) in enumerate(scene_blueprint.ROLE_SPECS.items())
        },
        'stages': {
            task_id: {'title': f'研究阶段 {index}',
                      'motivation': f'伙伴们需要这一阶段的成果，才能开展接下来的研究 {index}。',
                      'reward': f'研究工作完成了第 {index} 项准备。'}
            for index, task_id in enumerate(tasks.task_ids(), 1)
        },
    }


class SceneBlueprintTest(unittest.TestCase):
    def test_compiles_full_layout_even_when_all_stems_are_identical(self):
        raw = example_blueprint('garden')
        bundle = scene_blueprint.compile_blueprint(raw)
        mapping = bundle['bindings']
        self.assertEqual(set(mapping), set(layout.BINDING_KEYS))
        self.assertEqual(len(mapping), 34)
        self.assertEqual(len(set(mapping.values())), 34)
        # These expectations do not call the production naming helper.
        self.assertEqual(mapping['airlock'], 'entry-garden-area')
        self.assertEqual(mapping['blackbox'], 'originals-garden-source')
        self.assertEqual(mapping['backup'], 'originals-garden-backup')
        self.assertEqual(mapping['.integrity'], '.originals-garden-integrity')
        self.assertEqual(mapping['relay.conf.draft'], 'service-garden-config.conf.draft')
        self.assertEqual(mapping['rescue.tar.gz'], 'delivery-garden-archive.tar.gz')
        self.assertEqual(bundle['schema_version'], 2)
        self.assertEqual(bundle['task_ids'], list(tasks.task_ids()))
        self.assertEqual(bundle['entities'], raw['entities'])

    def test_compiler_owns_hidden_attributes_extensions_and_reserved_names(self):
        for stem in ('a' * 20, 'airlock', 'blackbox', 'AGENTS', 'beacon', 'decoy', '_'):
            with self.subTest(stem=stem):
                names = scene_blueprint.compile_blueprint(example_blueprint(stem))['bindings']
                self.assertEqual(len(names), len(set(names.values())))
                for source, target in names.items():
                    self.assertEqual(source.startswith('.'), target.startswith('.'))
                    self.assertEqual(PurePosixPath(source).suffixes, PurePosixPath(target).suffixes)
                    self.assertLessEqual(len(target), 64)
                    self.assertNotIn(target, layout.PROTECTED_NAMES)
                    self.assertNotIn(target, layout.BINDING_KEYS)
                    self.assertFalse(target.startswith('.beacon-'))
                    self.assertFalse(target.startswith('decoy-') and target.endswith('.tmp'))
                    self.assertNotIn('/', target)
                    self.assertNotIn('\\', target)

    def test_stage_dictionary_order_does_not_change_course_order(self):
        raw = example_blueprint()
        raw['stages'] = dict(reversed(list(raw['stages'].items())))
        bundle = scene_blueprint.compile_blueprint(raw)
        self.assertEqual(bundle['titles'], [f'研究阶段 {n}' for n in range(1, 10)])
        self.assertEqual(bundle['introductions'], [raw['stages'][key]['motivation'] for key in tasks.task_ids()])
        self.assertEqual(bundle['rewards'], [raw['stages'][key]['reward'] for key in tasks.task_ids()])

    def test_no_missing_extra_or_positional_task_ids(self):
        original = example_blueprint()
        cases = []
        missing = copy.deepcopy(original)
        missing['stages'].pop(tasks.task_ids()[0])
        cases.append(missing)
        extra = copy.deepcopy(original)
        extra['stages']['invented-task'] = {'title': '额外任务', 'motivation': '其他要求', 'reward': '额外进展'}
        cases.append(extra)
        positional = copy.deepcopy(original)
        positional['stages'] = list(positional['stages'].values())
        cases.append(positional)
        unknown = copy.deepcopy(original)
        unknown['stages']['wrong-id'] = unknown['stages'].pop(tasks.task_ids()[0])
        cases.append(unknown)
        for raw in cases:
            with self.subTest(stages=raw['stages']):
                with self.assertRaises(ValueError):
                    scene_blueprint.compile_blueprint(raw)

    def test_schema_exposes_only_neutral_roles_and_stable_task_ids(self):
        schema = scene_blueprint.schema()
        self.assertEqual(set(schema), scene_blueprint.RAW_FIELDS)
        self.assertEqual(set(schema['entities']), {
            'entry', 'workspace', 'originals', 'inbox', 'supplies', 'logs',
            'evidence', 'service', 'roster', 'delivery', 'finale', 'metrics',
        })
        self.assertEqual(set(schema['stages']), set(tasks.task_ids()))
        self.assertNotIn('bindings', schema)
        text = json.dumps(schema, ensure_ascii=False)
        for old_theme in ('airlock', 'blackbox', 'relay', 'rescue', 'capsule', 'station', '空间站', '气闸', '黑匣子'):
            self.assertNotIn(old_theme, text)

    def test_model_cannot_supply_bindings_or_extend_entities_or_stages(self):
        for target, key, value in (
            ('root', 'bindings', layout.DEFAULT_BINDINGS),
            ('entities', 'new-role', {'label': '多余', 'stem': 'extra'}),
            ('entry', 'path', '../../outside'),
            ('first-stage', 'command', 'a shell command'),
        ):
            raw = example_blueprint()
            node = {'root': raw, 'entities': raw['entities'], 'entry': raw['entities']['entry'],
                    'first-stage': raw['stages'][tasks.task_ids()[0]]}[target]
            node[key] = value
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    scene_blueprint.compile_blueprint(raw)
        raw = example_blueprint()
        raw['entities'].pop('metrics')
        with self.assertRaises(ValueError):
            scene_blueprint.compile_blueprint(raw)

    def test_rejects_full_filenames_path_syntax_and_control_characters(self):
        for stem in ('', '-option', '.hidden', 'name.txt', 'a/b', 'a\\b', 'two words',
                     'x' * 21, '植物', 'a;command', 'a\x1b[2J', 'a\u200bb'):
            raw = example_blueprint()
            raw['entities']['entry']['stem'] = stem
            with self.subTest(stem=stem):
                with self.assertRaises(ValueError):
                    scene_blueprint.compile_blueprint(raw)
        for label in ('', '字' * 25, '名字\n额外行', '名字\u200b'):
            raw = example_blueprint()
            raw['entities']['entry']['label'] = label
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    scene_blueprint.compile_blueprint(raw)

    def test_stage_limits_and_field_types_are_checked(self):
        for key, value in (('title', '字' * 61), ('reward', '字' * 61),
                           ('motivation', '字' * 161), ('motivation', ''),
                           ('title', ['不是字符串']), ('reward', '文字\n额外行')):
            raw = example_blueprint()
            raw['stages'][tasks.task_ids()[0]][key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    scene_blueprint.compile_blueprint(raw)
        for field in ('background', 'ending'):
            raw = example_blueprint()
            raw[field] = '字' * 241
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    scene_blueprint.compile_blueprint(raw)
        for ident in ('UPPER', '', '-wrong', '../wrong', 'a' * 49):
            raw = example_blueprint()
            raw['id'] = ident
            with self.subTest(ident=ident):
                with self.assertRaises(ValueError):
                    scene_blueprint.compile_blueprint(raw)

    def test_compilation_is_data_only_and_detaches_input(self):
        raw = example_blueprint()
        before = copy.deepcopy(raw)
        with patch('builtins.open', side_effect=AssertionError('compiler must not read files')):
            one = scene_blueprint.compile_blueprint(raw)
            two = scene_blueprint.compile_blueprint(raw)
        self.assertEqual(one, two)
        self.assertEqual(raw, before)
        one['entities']['entry']['label'] = '修改结果'
        one['titles'][0] = '修改标题'
        self.assertEqual(raw, before)
        self.assertNotEqual(one, two)


if __name__ == '__main__':
    unittest.main()
