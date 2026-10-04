"""Opaque shell commands must not be interpreted as native Linux operations."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest


APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import activity
from knowledge import diagnosis


class ActivityCommandKindTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='orbit-kind-test-')
        self.addCleanup(self.temp.cleanup)
        self.session = Path(self.temp.name)
        self.root = self.session / 'station'
        (self.root / 'blackbox').mkdir(parents=True)
        (self.root / 'work' / 'backup').mkdir(parents=True)
        (self.root / 'blackbox' / '.integrity').write_text('fixture')

    def state(self):
        return {'done': [1], 'events': [], 'tracking_enabled': True}

    def evidence(self, state):
        state['events'].append({'phase': 2, 'result': 'retry'})
        return activity.evidence_for(state, 2, diagnosis('backup', 2), ['hidden_missing'])

    def test_alias_function_keyword_unknown_keep_metadata_without_native_features(self):
        for kind in ('alias', 'function', 'keyword', 'unknown', 'unrecognized-value'):
            with self.subTest(kind=kind):
                state = self.state()
                activity.record(state, self.session, '1 cp -r blackbox/* work/backup',
                                1, self.root, command_kind=kind)
                event = state['shell_observations'][0]
                self.assertEqual(event['command'], '未解释的命令')
                self.assertEqual(event['exit_code'], 1)
                self.assertEqual(event['phase'], 2)
                self.assertEqual(event['sequence'], 1)
                self.assertTrue(event['at'])
                self.assertEqual(event['flags'], [])
                self.assertEqual(event['operand_roles'], [])
                self.assertFalse(event['known_options'])
                self.assertFalse(event['plain_star_excludes_hidden'])
                self.assertEqual(self.evidence(state), [])
                self.assertNotIn('input_errors', state.get('learning', {}))

    def test_opaque_kind_does_not_create_typo_or_missing_operand_patterns(self):
        for kind in ('alias', 'function', 'keyword', 'unknown'):
            for line, code in (('1 mkidr work', 127), ('1 cp', 1), ('1 lab sttaus', 2)):
                with self.subTest(kind=kind, line=line):
                    state = self.state()
                    activity.record(state, self.session, line, code, self.root, command_kind=kind)
                    self.assertNotIn('input_errors', state.get('learning', {}))

    def test_missing_kind_still_allows_actual_command_lookup_typo_diagnosis(self):
        state = self.state()
        activity.record(state, self.session, '1 mkidr work', 127, self.root, command_kind='missing')
        patterns = list(state['learning']['input_errors']['patterns'].values())
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]['kind'], 'command_typo')
        self.assertEqual(patterns[0]['observed'], 'mkidr')
        self.assertEqual(patterns[0]['expected'], 'mkdir')

    def test_file_builtin_and_legacy_none_keep_existing_semantic_behavior(self):
        for kind in ('file', None):
            with self.subTest(kind=kind):
                state = self.state()
                activity.record(state, self.session, '1 cp -r blackbox/* work/backup',
                                0, self.root, command_kind=kind)
                event = state['shell_observations'][0]
                self.assertEqual(event['command'], 'cp')
                self.assertTrue(event['plain_star_excludes_hidden'])
                self.assertTrue(self.evidence(state))
        state = self.state()
        activity.record(state, self.session, '1 cd wrok', 1, self.root, command_kind='builtin')
        pattern = next(iter(state['learning']['input_errors']['patterns'].values()))
        self.assertEqual(pattern['kind'], 'path_typo')
        self.assertEqual(pattern['expected'], 'work')

    def test_evidence_reader_rejects_old_events_with_opaque_kind_and_native_name(self):
        state = self.state()
        activity.record(state, self.session, '1 cp -r blackbox/* work/backup', 0, self.root)
        for kind in ('alias', 'function', 'keyword', 'unknown'):
            with self.subTest(kind=kind):
                historical = copy.deepcopy(state)
                historical['shell_observations'][0]['command_kind'] = kind
                self.assertEqual(historical['shell_observations'][0]['command'], 'cp')
                self.assertEqual(self.evidence(historical), [])

    def test_successful_opaque_input_does_not_resolve_existing_error_pattern(self):
        state = self.state()
        activity.record(state, self.session, '1 mkidr work', 127, self.root, command_kind='missing')
        pattern = next(iter(state['learning']['input_errors']['patterns'].values()))
        self.assertTrue(pattern['active'])
        activity.record(state, self.session, '2 mkdir work', 0, self.root, command_kind='function')
        self.assertTrue(pattern['active'])
        self.assertEqual(pattern['resolved_episodes'], 0)

    def test_help_query_is_not_evidence_of_copying_files(self):
        state = self.state()
        activity.record(state, self.session, '1 cp --help -r blackbox/* work/backup',
                        0, self.root, command_kind='file')
        self.assertEqual(self.evidence(state), [])
        self.assertEqual(state['shell_observations'][0]['operand_roles'], [])


if __name__ == '__main__':
    unittest.main()
