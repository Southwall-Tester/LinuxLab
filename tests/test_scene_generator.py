"""Model boundaries and non-destructive export for interest-led scenes."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import ai_tutor
import scene_blueprint
import scene_generator
import tasks
from test_scene_blueprint import example_blueprint


def example_bundle():
    return scene_blueprint.compile_blueprint(example_blueprint())


class SceneGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = {'enabled': True, 'base_url': 'https://example.invalid',
                       'api_key': 'secret-test-key-never-send', 'model': 'test',
                       'timeout_seconds': 2}
        self.load_patch = patch('scene_generator.ai_tutor.load_config', return_value=self.config)
        self.load_mock = self.load_patch.start()
        self.request_patch = patch('scene_generator.ai_tutor.request_json', side_effect=self.default_reply)
        self.request_mock = self.request_patch.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.load_patch.stop)
        self.addCleanup(self.request_patch.stop)

    def default_reply(self, config, messages, max_tokens):
        return {'aligned': True, 'issues': []} if max_tokens == 700 else example_blueprint()

    def reply_with(self, result):
        self.request_mock.side_effect = None
        self.request_mock.return_value = result

    def test_interest_question_is_model_output_without_learner_context(self):
        self.reply_with({'question': '你想把这次实验放进什么样的故事世界？'})
        question = scene_generator.ask_interest()
        self.assertEqual(question, self.request_mock.return_value['question'])
        config, messages = self.request_mock.call_args.args
        self.assertEqual(config, self.config)
        self.assertEqual([m['role'] for m in messages], ['system', 'user'])
        self.assertEqual(messages[1]['content'], '请询问我希望进入什么主题的实验情境。')
        self.assertNotIn(self.config['api_key'], json.dumps(messages))
        self.assertEqual(self.request_mock.call_args.kwargs['max_tokens'], 250)

    def test_interest_question_rejects_invalid_or_control_output(self):
        for result in ({}, {'question': ''}, {'question': 'a' * 161},
                       {'question': '主题？\x1b[2J'}, {'question': '主题？\n第二问'},
                       {'question': self.config['api_key']}, {'question': '主题？', 'extra': True}):
            with self.subTest(result=result):
                self.reply_with(result)
                with self.assertRaises(scene_generator.SceneGenerationError):
                    scene_generator.ask_interest()

    def test_theme_request_has_only_theme_contract_and_semantic_schema(self):
        self.assertEqual(scene_generator.create('城市庆典'), example_bundle())
        config, messages = self.request_mock.call_args_list[0].args
        data = json.loads(messages[1]['content'])
        self.assertEqual(set(data), {'theme', 'teaching_contract', 'asset_roles', 'schema'})
        self.assertEqual(data['theme'], '城市庆典')
        self.assertEqual(data['teaching_contract'], tasks.generation_contract())
        self.assertEqual(data['asset_roles'], {role: spec['meaning'] for role, spec in scene_blueprint.ROLE_SPECS.items()})
        self.assertEqual(set(data['schema']['stages']), set(tasks.task_ids()))
        self.assertNotIn('bindings', data['schema'])
        self.assertNotIn(self.config['api_key'], json.dumps(messages))
        self.assertEqual([call.kwargs['max_tokens'] for call in self.request_mock.call_args_list], [4500, 700])
        review = json.loads(self.request_mock.call_args_list[1].args[1][1]['content'])
        self.assertEqual(set(review), {'theme', 'teaching_contract', 'candidate'})
        self.assertEqual(review['candidate'], example_blueprint())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_empty_or_invalid_theme_does_not_request(self):
        for theme in ('', '   ', '\x1b[2J', 'a' * 301, None):
            with self.subTest(theme=theme):
                with self.assertRaises(scene_generator.SceneGenerationError):
                    scene_generator.create(theme)
        self.load_mock.assert_not_called()
        self.request_mock.assert_not_called()

    def test_key_is_neither_in_request_content_nor_export(self):
        scene_generator.create('故事 ' + self.config['api_key'])
        self.assertNotIn(self.config['api_key'], json.dumps(self.request_mock.call_args.args[1]))
        bad = example_blueprint()
        bad['background'] = self.config['api_key']
        self.reply_with(bad)
        with self.assertRaises(scene_generator.SceneGenerationError):
            scene_generator.generate('故事', self.root / 'rejected.json')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_schema_and_path_rejection_leave_no_files(self):
        incomplete = example_blueprint()
        incomplete['stages'].pop(tasks.task_ids()[0])
        unsafe = example_blueprint()
        unsafe['entities']['workspace']['stem'] = '../escape'
        for result in (None, [], {'id': 'broken'}, incomplete, unsafe):
            with self.subTest(result=result):
                self.reply_with(result)
                with self.assertRaises(scene_generator.SceneGenerationError):
                    scene_generator.generate('城市庆典', self.root / 'nested' / 'scene.json')
                self.assertEqual(list(self.root.iterdir()), [])

    def test_structure_failure_retries_once_with_specific_feedback(self):
        self.request_mock.side_effect = [{'id': 'incomplete'}, example_blueprint(),
                                         {'aligned': True, 'issues': []}]
        self.assertEqual(scene_generator.create('城市庆典'), example_bundle())
        self.assertEqual(self.request_mock.call_count, 3)
        revised_context = json.loads(self.request_mock.call_args_list[1].args[1][1]['content'])
        self.assertIn('本地结构检查未通过', revised_context['revision_feedback'])

    def test_review_rejection_is_revised_before_any_bundle_is_returned(self):
        revised = example_blueprint()
        revised['title'] = '修订后的研究所'
        issue = '第二阶段需要说明保存原始资料对研究的意义。'
        self.request_mock.side_effect = [example_blueprint(), {'aligned': False, 'issues': [issue]},
                                         revised, {'aligned': True, 'issues': []}]
        self.assertEqual(scene_generator.create('植物研究所')['title'], revised['title'])
        self.assertEqual(self.request_mock.call_count, 4)
        context = json.loads(self.request_mock.call_args_list[2].args[1][1]['content'])
        self.assertIn(issue, context['revision_feedback'])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_persistent_review_rejection_saves_nothing(self):
        rejected = {'aligned': False, 'issues': ['故事要求删除原件，与保全要求冲突。']}
        self.request_mock.side_effect = [example_blueprint(), rejected, example_blueprint(), rejected]
        with self.assertRaisesRegex(scene_generator.SceneGenerationError, '重生成后仍不符合要求'):
            scene_generator.generate('植物研究所', self.root / 'nested' / 'rejected.json')
        self.assertEqual(self.request_mock.call_count, 4)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_malformed_or_credential_echo_review_is_not_treated_as_approval(self):
        for result in (None, {}, {'aligned': 'true', 'issues': []},
                       {'aligned': False, 'issues': []}, {'aligned': True, 'issues': ['有问题']},
                       {'aligned': False, 'issues': ['字符\x1b[2J']},
                       {'aligned': False, 'issues': [self.config['api_key']]},
                       {'aligned': True, 'issues': [], 'extra': True}):
            with self.subTest(result=result):
                self.request_mock.side_effect = [example_blueprint(), result]
                with self.assertRaisesRegex(scene_generator.SceneGenerationError, '内容复核格式无效'):
                    scene_generator.generate('植物研究所', self.root / 'rejected.json')
                self.assertEqual(list(self.root.iterdir()), [])

    def test_disabled_config_and_network_failure_never_generate(self):
        target = self.root / 'new' / 'scene.json'
        self.load_mock.side_effect = ai_tutor.AIError('AI 尚未启用；当前使用本地提示。')
        with self.assertRaisesRegex(scene_generator.SceneGenerationError, '--scene space'):
            scene_generator.generate('城市庆典', target)
        self.request_mock.assert_not_called()
        self.load_mock.side_effect = None
        self.request_mock.side_effect = ai_tutor.AIError('AI 请求失败，已改用本地提示。')
        with self.assertRaisesRegex(scene_generator.SceneGenerationError, '未生成情境'):
            scene_generator.generate('城市庆典', target)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_file_is_not_overwritten_and_no_request_is_sent(self):
        target = self.root / 'existing.json'
        target.write_text('keep this', encoding='utf-8')
        with self.assertRaisesRegex(scene_generator.SceneGenerationError, '未覆盖'):
            scene_generator.generate('城市庆典', target)
        self.assertEqual(target.read_text(encoding='utf-8'), 'keep this')
        self.request_mock.assert_not_called()

    def test_non_json_export_is_rejected_before_request(self):
        with self.assertRaisesRegex(scene_generator.SceneGenerationError, '.json'):
            scene_generator.generate('城市庆典', self.root / 'scene.txt')
        self.request_mock.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_export_and_default_file_names_are_reusable_and_unique(self):
        with patch('scene_generator.APP', self.root):
            one = scene_generator.generate('城市庆典')
            two = scene_generator.generate('城市庆典')
        files = list((self.root / 'scenes').glob('generated-*.json'))
        self.assertEqual(len(files), 2)
        self.assertNotEqual(one, two)
        for path in files:
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), example_bundle())
        self.assertIn('bash start.sh --new --scene ', one)
        self.assertIn('lab scene ', one)

    def test_file_created_during_request_is_not_overwritten(self):
        target = self.root / 'raced.json'
        def race(*args, **kwargs):
            target.write_text('another writer', encoding='utf-8')
            return self.default_reply(*args, **kwargs)
        self.request_mock.side_effect = race
        with self.assertRaises(scene_generator.SceneGenerationError):
            scene_generator.generate('城市庆典', target)
        self.assertEqual(target.read_text(encoding='utf-8'), 'another writer')

    def test_write_failure_removes_only_its_own_partial_export(self):
        target = self.root / 'failed.json'
        class BrokenStream:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def write(self, payload):
                raise OSError('write failed')
        real_fdopen = scene_generator.os.fdopen
        def broken_fdopen(fd, *args, **kwargs):
            real_fdopen(fd, *args, **kwargs).close()
            return BrokenStream()
        with patch('scene_generator.os.fdopen', side_effect=broken_fdopen):
            with self.assertRaises(scene_generator.SceneGenerationError):
                scene_generator.generate('城市庆典', target)
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
