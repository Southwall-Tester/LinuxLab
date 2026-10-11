"""Real CLI/PTY lookups in disposable learner homes, plus parser boundaries."""
import json
import unittest

import test_error_tracking as fixtures
import activity
import pliac_bridge
import reference_usage


class ReferenceUsageTests(unittest.TestCase):
    setUp = fixtures.ErrorTrackingIntegration.setUp
    state = fixtures.ErrorTrackingIntegration.state
    cli = fixtures.ErrorTrackingIntegration.cli

    def test_real_shell_and_notes_record_topics_once_and_respect_tracking(self):
        terminal = fixtures._InteractiveShell(self, self.env)
        for command in ('lab notes cp', 'cp --help', 'help cd', 'lab help', 'lab notes', 'lab --help'):
            terminal.command(command)
        state = self.state()
        rows = state['reference_lookups']
        self.assertEqual([(r['source'], r['topic']) for r in rows],
                         [('notes', 'cp'), ('command_help', 'cp'), ('shell_help', 'cd'),
                          ('lab_help', ''), ('notes', ''), ('lab_help', '')])
        self.assertFalse(any(r['after_completion'] for r in rows))
        self.assertEqual(state['reference_total'], 6)
        self.assertEqual(rows[0]['operation_cursor'], 0)
        self.assertGreater(rows[2]['operation_cursor'], rows[1]['operation_cursor'])
        terminal.command('lab tracking off')
        terminal.command('lab notes cp')
        terminal.command('cp --help')
        self.assertEqual(self.state()['reference_lookups'], rows)
        terminal.finish()

    def test_parser_rejects_failed_opaque_compound_and_unrelated_options(self):
        state = dict(done=[], tracking_enabled=True)
        for words, code, kind, compound in [
            (['cp', '--help'], 1, 'file', False),
            (['cp', '--help'], 0, 'alias', False),
            (['cp', '--help'], 0, 'file', True),
            (['ls', '-h'], 0, 'file', False),
            (['man', 'private-topic'], 0, 'file', False),
            (['cp', '--version'], 0, 'file', False),
        ]:
            reference_usage.observe_shell(state, words, code, kind, compound)
        self.assertNotIn('reference_lookups', state)
        reference_usage.observe_shell(state, ['man', '1', 'cp'], 0, 'file', False)
        self.assertEqual(state['reference_lookups'][0]['topic'], 'cp')
        reference_usage.record(state, 'notes', '*')
        self.assertEqual(state['reference_lookups'][1]['topic'], 'glob')

    def test_export_whitelist_review_and_retention(self):
        state = self.state()
        state['done'] = list(range(1, 10))
        reference_usage.record(state, 'notes', 'cp')
        self.assertTrue(state['reference_lookups'][0]['after_completion'])
        state['reference_lookups'][0]['private_extra'] = 'never-export'
        state['platform_binding'] = dict(binding_id='test', course_id='course', course_version=1,
                                        student_id='synthetic', mode='preview')
        wire = pliac_bridge.snapshot(state)
        self.assertNotIn('never-export', json.dumps(wire))
        self.assertEqual(wire['reference_total'], 1)
        for _ in range(2001):
            reference_usage.record(state, 'notes', 'cp')
        self.assertEqual(len(state['reference_lookups']), 2000)
        self.assertEqual(state['reference_total'], 2002)


if __name__ == '__main__':
    unittest.main()
