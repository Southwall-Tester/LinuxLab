"""Error episodes and evidence references are not a knowledge mastery score."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import error_patterns
import learning


class ErrorPatternsTest(unittest.TestCase):
    def setUp(self):
        self.s = {'done': [], 'events': [], 'shell_sequence': 0}
        self.item = dict(kind='path_typo', command='cd', observed='wrok', expected='work',
                         location='.', concept='paths', certainty='candidate',
                         summary='在当前位置找不到 wrok，有近似目录 work。',
                         evidence=['输入失败；此处只有候选名称。'], signature='test-path')

    def record(self, items, words, code, location='.', phase=1):
        self.s['shell_sequence'] += 1
        error_patterns.record(self.s, items, words, code, location, phase, '2026-10-04T08:00:00+00:00')

    def test_unrelated_success_does_not_close_error_and_real_followup_does(self):
        self.record([self.item], ['cd', 'wrok'], 1)
        self.record([], ['ls', 'work'], 0)
        self.record([], ['cd', 'work'], 0, location='inbox')
        p = self.s['learning']['input_errors']['patterns']['test-path']
        self.assertTrue(p['active'])
        self.record([], ['cd', 'work'], 0)
        self.assertFalse(p['active'])
        self.record([self.item], ['cd', 'wrok'], 1)
        self.assertEqual((p['attempts'], p['episodes'], p['resolved_episodes']), (2, 2, 1))
        self.assertEqual(self.s['learning']['concepts']['paths']['failures'], 0)

    def test_input_issue_only_overrides_check_when_observation_is_newer(self):
        self.s['events'].append({'phase': 1, 'result': 'retry', 'operation_cursor': 1})
        self.s['learning'] = {'concepts': {}, 'tutor_levels': {},
                             'active_issue': {'phase': 1, 'code': 'directory'}}
        self.record([self.item], ['cd', 'wrok'], 1)
        self.assertIsNone(error_patterns.current_issue(self.s, 1))
        self.record([self.item], ['cd', 'wrok'], 1)
        self.assertEqual(error_patterns.current_issue(self.s, 1)['code'], 'path_typo')
        self.assertIsNone(error_patterns.current_issue(self.s, 2))

    def test_help_different_operands_and_destination_do_not_close_source_error(self):
        item = dict(self.item, command='cp')
        self.record([item], ['cp', 'wrok', 'destination'], 1)
        for words in (['cp', '--help', 'work', 'destination'],
                      ['cp', 'other', 'work'], ['cp', 'work', 'different']):
            self.record([], words, 0)
        pattern = self.s['learning']['input_errors']['patterns']['test-path']
        self.assertTrue(pattern['active'])
        self.record([], ['cp', 'work', 'destination'], 0)
        self.assertFalse(pattern['active'])

    def test_help_and_unrelated_mkdir_do_not_resolve_command_typo(self):
        item = dict(self.item, kind='command_typo', command='mkdir', observed='mkidr', expected='mkdir')
        self.record([item], ['mkidr', 'work/example'], 127)
        self.record([], ['mkdir', '--help'], 0)
        self.record([], ['mkdir', 'work/other'], 0)
        pattern = self.s['learning']['input_errors']['patterns']['test-path']
        self.assertTrue(pattern['active'])
        self.record([], ['mkdir', 'work/example'], 0)
        self.assertFalse(pattern['active'])

    def test_a_previous_episode_correction_cannot_close_the_new_episode(self):
        item = dict(self.item, command='cp')
        self.record([item], ['cp', 'wrok', 'first'], 1)
        self.record([], ['cp', 'work', 'first'], 0)
        self.record([item], ['cp', 'wrok', 'second'], 1)
        self.record([], ['cp', 'work', 'first'], 0)
        pattern = self.s['learning']['input_errors']['patterns']['test-path']
        self.assertTrue(pattern['active'])
        self.assertEqual(pattern['resolved_episodes'], 1)
        self.record([], ['cp', 'work', 'second'], 0)
        self.assertFalse(pattern['active'])
        self.assertEqual(pattern['resolved_episodes'], 2)

    def test_context_is_bounded_and_does_not_export_raw_state(self):
        self.s['code'] = 'PRIVATE-ANSWER'
        for _ in range(20):
            self.record([self.item], ['cd', 'wrok'], 1)
        context = error_patterns.context(self.s, 1)
        self.assertEqual(len(context['evidence']), 12)
        self.assertEqual(context['evidence'][0]['id'], 'input-9')
        self.assertEqual(context['patterns'][0]['episodes'], 1)
        self.assertNotIn('PRIVATE-ANSWER', str(context))
        self.assertNotIn('signature', str(context))
        self.assertNotIn('correction_keys', str(context))
        context['patterns'][0]['attempts'] = 900
        self.assertEqual(error_patterns.context(self.s, 1)['patterns'][0]['attempts'], 20)

    def test_report_copy_removes_local_fingerprints_without_changing_state(self):
        self.record([self.item], ['cd', 'wrok'], 1)
        self.s['events'].append({'diagnosis': {'observation_key': 'local-key', 'code': 'directory'}})
        result = error_patterns.report_copy(self.s)
        self.assertNotIn('correction_keys', str(result))
        self.assertNotIn('observation_key', str(result))
        self.assertIn('correction_keys', str(self.s))
        self.assertEqual(result['events'][0]['diagnosis']['code'], 'directory')

    def test_new_input_problem_brings_related_review_forward(self):
        topic = learning.touch_topic(self.s, 'paths', '2026-10-03T08:00:00+00:00')
        topic['next_review'] = '2026-11-03T08:00:00+00:00'
        topic['review_successes'] = 2
        self.record([self.item], ['cd', 'wrok'], 1)
        self.assertEqual(topic['next_review'], '2026-10-04T08:00:00+00:00')
        self.assertEqual(topic['last_seen'], topic['next_review'])
        self.assertEqual(topic['review_successes'], 2)
        self.assertEqual(topic['failures'], 0)

    def test_review_uses_problem_episodes_instead_of_repeated_inputs(self):
        learning.touch_topic(self.s, 'copy', '2026-10-04T08:00:00+00:00')
        for _ in range(5):
            self.record([self.item], ['cd', 'wrok'], 1)
        output = learning.review(self.s, at='2026-10-04T09:00:00+00:00')
        self.assertLess(output.index('paths ·'), output.index('copy ·'))
        self.assertIn('输入尝试段 1 段', output)
        self.assertNotIn('输入尝试段 5 段', output)

    def test_local_history_and_pattern_counts_are_bounded(self):
        for index in range(520):
            item = dict(self.item, signature='pattern-' + str(index))
            self.record([item], ['cd', 'wrok'], 1)
        state = self.s['learning']['input_errors']
        self.assertEqual(len(state['events']), 500)
        self.assertEqual(len(state['patterns']), 200)


if __name__ == '__main__':
    unittest.main()
