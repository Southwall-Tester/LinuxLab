"""Post-command evidence boundaries, including privacy and native syntax gaps."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import input_diagnostics
from knowledge import CONCEPTS


class InputDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='orbit-input-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'station'
        self.root.mkdir()
        for directory in ('work', 'logs', 'blackbox', 'inbox'):
            (self.root / directory).mkdir()
        (self.root / 'work' / 'report.txt').write_text('private contents are not read')
        (self.root / 'logs' / 'events.log').write_text('private contents are not read')
        self.state = {'beacon': '4287', 'code': 'LINK-PRIVATE', 'seal': 'SEAL-PRIVATE',
                      'id': 'session-private', 'worker': {'pid': 876543, 'token': 'worker-private'}}

    def detect(self, *words, status=1, cwd=None):
        result = input_diagnostics.detect(self.state, self.root, cwd or self.root, list(words), status)
        for item in result:
            self.assertEqual(set(item), {'kind', 'command', 'observed', 'expected', 'location',
                                         'concept', 'certainty', 'summary', 'evidence', 'signature'})
            self.assertIn(item['concept'], CONCEPTS)
            self.assertIn(item['certainty'], ('observed', 'candidate'))
            self.assertRegex(item['signature'], r'^[a-f0-9]{64}$')
            self.assertNotIn(str(self.base), json.dumps(item))
        return result

    def test_command_spelling_case_spacing_and_ambiguity(self):
        for wrong, right, kind in (('mkidr', 'mkdir', 'command_typo'),
                                    ('MKDIR', 'mkdir', 'command_case'),
                                    ('cd..', 'cd', 'command_spacing'),
                                    ('labnotes', 'lab', 'command_spacing')):
            with self.subTest(wrong=wrong):
                item = self.detect(wrong, status=127)[0]
                self.assertEqual((item['command'], item['observed'], item['expected']), (right, wrong, right))
                self.assertEqual(item['kind'], kind)
                self.assertEqual(item['certainty'], 'candidate')
        self.assertEqual(self.detect('c', status=127), [])
        self.assertEqual(self.detect('cp', status=127), [])  # An installed-command/PATH issue is not a typo.
        self.assertEqual(self.detect('mkidr', status=1), [])

    def test_missing_operands_and_option_values_are_syntax_observations(self):
        for words in (('cp',), ('cp', 'work'), ('mv', 'work'), ('mkdir',), ('chmod', '600')):
            with self.subTest(words=words):
                item = self.detect(*words)[0]
                self.assertEqual(item['kind'], 'missing_operands')
                self.assertEqual(item['certainty'], 'observed')
                self.assertEqual(item['expected'], '')
        item = self.detect('tail', '-n')[0]
        self.assertEqual(item['kind'], 'option_value_missing')
        self.assertEqual(item['observed'], '-n')
        for command in ('cat', 'tail', 'head', 'cd', 'ls'):
            self.assertEqual(self.detect(command), [])

    def test_lab_subcommand_typo_never_consumes_answers_or_question_text(self):
        item = self.detect('lab', 'sttaus', status=2)[0]
        self.assertEqual(item['kind'], 'lab_command_typo')
        self.assertEqual(item['command'], 'lab')
        self.assertEqual(item['observed'], 'sttaus')
        self.assertEqual(item['expected'], 'status')
        self.assertIn('只是平台语法', item['summary'])
        self.state['done'] = [1]
        self.assertEqual(self.detect('lab', 'sttaus')[0]['concept'], 'copy')
        for words in (('lab', 'check', '4287'), ('lab', 'chek', 'unknown-answer'),
                      ('lab', 'tutor', 'private-question'), ('lab', 'scene', 'private-theme'),
                      ('lab', 'check'), ('lab', 'notes', 'unknown-topic')):
            self.assertEqual(self.detect(*words), [])

    def test_long_option_spelling_is_only_a_candidate(self):
        item = self.detect('cp', '--recusrive', 'blackbox', 'work')[0]
        self.assertEqual(item['kind'], 'option_typo')
        self.assertEqual(item['observed'], '--recusrive')
        self.assertEqual(item['expected'], '--recursive')
        self.assertEqual(item['certainty'], 'candidate')
        self.assertEqual(self.detect('ls', '--al', 'missing'), [])  # Valid long-option abbreviations.

    def test_valid_rare_or_complicated_options_do_not_trigger_guesses(self):
        cases = [
            ('cp', '--reflink=auto', 'blackbox', 'work'), ('cp', '-t', 'work', 'blackbox'),
            ('ls', '--hyperlink=auto', 'missing'), ('ls', '-Z', 'missing'),
            ('tail', '-n5', 'missing'), ('tail', '--pid=123', '-f', 'missing'),
            ('tar', '-xzf', 'missing.tar.gz'), ('find', 'missing', '-name', '*.txt'),
            ('grep', 'private-pattern', 'missing'), ('chmod', '--reference=work/report.txt', 'missing'),
            ('mkdir', '-m', '700', 'missing'), ('cp', '--help'), ('cp', '--version'),
        ]
        for words in cases:
            with self.subTest(words=words):
                self.assertEqual(self.detect(*words), [])

    def test_missing_reading_path_name_case_and_spelling(self):
        for token, expected, kind in (('wrok/report.txt', 'work/report.txt', 'path_typo'),
                                       ('work/REPORT.txt', 'work/report.txt', 'path_case'),
                                       ('work/missing.txt', '', 'path_missing')):
            with self.subTest(token=token):
                item = self.detect('cat', token)[0]
                self.assertEqual((item['observed'], item['expected'], item['kind']), (token, expected, kind))
                self.assertIn('命令结束后', item['summary'])
                self.assertIn('没有采集原生错误输出', item['evidence'][0])

    def test_relative_start_point_is_not_rewritten_as_proven_cause(self):
        item = self.detect('cat', 'logs/events.log', cwd=self.root / 'work')[0]
        self.assertEqual(item['kind'], 'path_base')
        self.assertEqual(item['observed'], 'logs/events.log')
        self.assertEqual(item['expected'], '../logs/events.log')
        self.assertEqual(item['location'], 'work')
        self.assertEqual(item['certainty'], 'candidate')

    def test_destination_creation_is_not_mistaken_for_a_missing_source(self):
        self.assertEqual(self.detect('mkdir', 'new-directory'), [])
        self.assertEqual(self.detect('cp', 'work/report.txt', 'new-file.txt'), [])
        self.assertEqual(self.detect('mv', 'work/report.txt', 'new-file.txt'), [])
        self.assertEqual(self.detect('vim', 'new-file.txt'), [])
        self.assertEqual(self.detect('rm', 'missing.txt'), [])
        self.assertEqual(self.detect('tail', '-n', '5', 'logs/events.log'), [])
        self.assertEqual(self.detect('cat', 'work/report.txt'), [])
        self.assertEqual(self.detect('cp', 'work/missing.txt', 'new-file.txt')[0]['kind'], 'path_missing')

    def test_secrets_sensitive_names_external_paths_and_links_are_not_retained(self):
        (self.base / 'outside').mkdir()
        (self.root / 'external').symlink_to(self.base / 'outside', target_is_directory=True)
        (self.root / 'internal-link').symlink_to(self.root / 'work', target_is_directory=True)
        tokens = ['4287', 'LINK-PRIVATE', '.beacon-4287', 'SEAL-PRIVATE', '876543',
                  'worker-private', 'api_key.txt', 'auth.conf', 'token-data', 'secret.txt',
                  'ai.local.json', '.env', 'sk-providerunknown',
                  '../outside/missing', '../../outside', str(self.base / 'outside/missing'),
                  'external/missing', 'internal-link/missing',
                  'external/../work/missing', 'internal-link/../work/missing',
                  'https://remote.invalid/private', 'user@remote:private']
        for token in tokens:
            with self.subTest(token=token):
                self.assertEqual(self.detect('cat', token), [])
                self.assertEqual(self.detect('cp', token), [])
        self.assertEqual(self.detect('cat', 'missing', cwd=self.base / 'outside'), [])

    def test_private_or_ambiguous_neighbor_is_not_suggested(self):
        (self.root / 'work' / 'token.txt').touch()
        self.assertEqual(self.detect('cat', 'work/tokne.txt')[0]['expected'], '')
        (self.root / 'work' / 'rate.txt').touch()
        (self.root / 'work' / 'date.txt').touch()
        item = self.detect('cat', 'work/late.txt')[0]
        self.assertEqual(item['expected'], '')

    def test_success_complex_input_and_shell_data_are_not_classified(self):
        self.assertEqual(self.detect('mkidr', status=0), [])
        for words in (('cat', '$HOME/private'), ('cat', 'work/*'), ('cp', 'x;', 'work'),
                      ('cat', 'a|b'), ('cp', '$(something)', 'work'), ('cat', 'two words'),
                      ('command', 'cp', 'missing'), ('env', 'TOKEN=value', 'cp')):
            with self.subTest(words=words):
                self.assertEqual(self.detect(*words), [])

    def test_signature_is_stable_and_does_not_include_raw_secret_or_root(self):
        one = self.detect('cat', 'work/missing.txt', status=1)[0]
        two = self.detect('cat', 'work/missing.txt', status=2)[0]
        self.assertEqual(one['signature'], two['signature'])
        self.assertNotEqual(one['signature'], self.detect('cat', 'work/another.txt')[0]['signature'])
        self.assertNotIn(str(self.root), json.dumps(one))

    def test_paths_only_use_metadata_never_read_or_execute_contents(self):
        with patch('pathlib.Path.read_text', side_effect=AssertionError('must not read contents')), \
                patch('pathlib.Path.read_bytes', side_effect=AssertionError('must not read contents')), \
                patch('subprocess.run', side_effect=AssertionError('must not execute commands')):
            item = self.detect('cat', 'work/reprot.txt')[0]
        self.assertEqual(item['expected'], 'work/report.txt')


if __name__ == '__main__':
    unittest.main()
