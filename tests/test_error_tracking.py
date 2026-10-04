"""Temporary-round tests for input episodes and repeated-check evidence.

Run inside WSL/Linux. No learner history, provider configuration or live round
is read; every launcher receives a disposable HOME and ORBIT_DATA_DIR.
"""
import json
import os
from pathlib import Path
import pty
import re
import select
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import orbit


class _InteractiveShell:
    def __init__(self, case, env):
        self.case = case
        self.master, slave = pty.openpty()
        try:
            self.process = subprocess.Popen(
                ['bash', str(APP / 'start.sh')], env=env,
                stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        finally:
            os.close(slave)
        self.output = bytearray()
        self.closed = False
        case.addCleanup(self.close)
        self.read_prompt()

    def read_prompt(self, timeout=10):
        chunk = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if select.select([self.master], [], [], 0.1)[0]:
                try:
                    data = os.read(self.master, 65536)
                except OSError:
                    break
                if not data:
                    break
                chunk.extend(data)
                self.output.extend(data)
                if re.search(rb'\r?\n[$#] $', chunk):
                    return chunk.decode('utf-8', errors='replace').replace('\r', '')
            elif self.process.poll() is not None:
                break
        self.case.fail('No interactive prompt: ' + self.output.decode('utf-8', errors='replace'))

    def command(self, text):
        os.write(self.master, (text + '\n').encode('utf-8'))
        return self.read_prompt()

    def finish(self):
        # Bare exit inherits the last command status (including a tested 127).
        os.write(self.master, b'exit 0\n')
        self.process.wait(timeout=8)
        self.case.assertEqual(self.process.returncode, 0)
        self.close()

    def close(self):
        if self.closed:
            return
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
        os.close(self.master)
        self.closed = True


class ErrorTrackingIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='orbit-error-tracking-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home),
                        ORBIT_DATA_DIR=str(self.base / 'data'),
                        ORBIT_AI_CONFIG=str(self.base / 'unused-ai.local.json'),
                        ORBIT_ENGINE=str(APP / 'orbit.py'), PYTHONUTF8='1',
                        TERM='xterm-256color')
        self.env.pop('ORBIT_HOME', None)
        result = subprocess.run(
            [sys.executable, str(APP / 'orbit.py'), 'prepare', '--scene', 'space'],
            env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.session = Path(result.stdout.strip())
        self.root = self.session / 'station'
        self.env['ORBIT_HOME'] = str(self.session)

    def state(self):
        return json.loads((self.session / 'state.json').read_text(encoding='utf-8'))

    def write_state(self, state):
        (self.session / 'state.json').write_text(json.dumps(state), encoding='utf-8')

    def cli(self, *args, ok=True, cwd=None, input_text=None):
        result = subprocess.run(
            [sys.executable, str(APP / 'orbit.py'), *args], env=self.env,
            cwd=cwd or self.root, input=input_text, capture_output=True,
            text=True, timeout=10)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def shell(self, command):
        result = subprocess.run(['bash', '-c', command], env=self.env, cwd=self.root,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def observe(self, line, exit_code=0):
        self.cli('--observe-shell', str(exit_code), '0', input_text='1 ' + line)

    def patterns(self, kind='command_typo'):
        patterns = self.state().get('learning', {}).get('input_errors', {}).get('patterns', {})
        return [item for item in patterns.values() if item['kind'] == kind]

    def one_typo(self):
        patterns = self.patterns()
        self.assertEqual(len(patterns), 1, patterns)
        return patterns[0]

    def partial_backup(self):
        """Reach phase two in the disposable fixture and omit its hidden file."""
        self.shell('mkdir -p work/evidence')
        self.cli('check', self.state()['beacon'], cwd=self.root / 'airlock')
        self.shell('mkdir work/backup; cp -r blackbox/* work/backup/')
        self.observe('cp -r blackbox/* work/backup/')
        self.cli('check', ok=False)
        state = self.state()
        self.assertEqual(state['events'][-1]['diagnosis']['code'], 'backup')
        self.assertEqual(state['events'][-1]['diagnosis']['concepts'][0], 'hidden')
        self.assertTrue(state['events'][-1]['diagnosis']['evidence'])
        return state

    def test_new_round_enables_tracking_with_marker(self):
        self.assertIs(self.state()['tracking_enabled'], True)
        self.assertTrue((self.session / 'tracking.enabled').is_file())

    def test_resume_migrates_missing_setting_but_preserves_explicit_off(self):
        state = self.state()
        state.pop('tracking_enabled', None)
        self.write_state(state)
        (self.session / 'tracking.enabled').unlink(missing_ok=True)
        self.cli('prepare')
        self.assertIs(self.state()['tracking_enabled'], True)
        self.assertTrue((self.session / 'tracking.enabled').exists())
        self.cli('tracking', 'off')
        self.cli('prepare')
        self.assertIs(self.state()['tracking_enabled'], False)
        self.assertFalse((self.session / 'tracking.enabled').exists())

    def test_pty_repeated_typo_resolution_and_recurrence(self):
        # Inherited history filters must not silently suppress repeated errors.
        terminal = _InteractiveShell(self, dict(self.env, HISTCONTROL='ignoreboth:erasedups',
                                                HISTIGNORE='mkidr*:mkdir*'))
        for _ in range(3):
            terminal.command('mkidr work/example')
        pattern = self.one_typo()
        self.assertEqual((pattern['attempts'], pattern['episodes'], pattern['resolved_episodes']),
                         (3, 1, 0))
        terminal.command('mkdir work/example')
        self.assertEqual(self.one_typo()['resolved_episodes'], 1)
        self.assertFalse(self.one_typo()['active'])
        terminal.command('mkidr work/example')
        pattern = self.one_typo()
        self.assertEqual((pattern['attempts'], pattern['episodes'], pattern['resolved_episodes']),
                         (4, 2, 1))
        self.assertIn('失败输入 4 次', terminal.command('lab activity'))
        self.assertIn('连续尝试段 2 段', terminal.command('lab notebook'))
        terminal.finish()

    def test_pty_empty_enter_does_not_repeat_previous_error(self):
        terminal = _InteractiveShell(self, self.env)
        terminal.command('mkidr work/example')
        before = self.state()
        for _ in range(3):
            terminal.command('')
        after = self.state()
        self.assertEqual(after['shell_sequence'], before['shell_sequence'])
        self.assertEqual(after['learning']['input_errors'], before['learning']['input_errors'])
        terminal.finish()

    def test_pty_tracking_off_stops_observations_and_input_patterns(self):
        terminal = _InteractiveShell(self, self.env)
        terminal.command('mkidr work/example')
        terminal.command('lab tracking off')
        before = self.state()
        terminal.command('mkidr work/example')
        terminal.command('pwd')
        after = self.state()
        self.assertFalse(after['tracking_enabled'])
        self.assertEqual(after.get('shell_observations'), before.get('shell_observations'))
        self.assertEqual(after['learning']['input_errors'], before['learning']['input_errors'])
        terminal.finish()

    def test_pty_prompt_hook_preserves_command_exit_status(self):
        terminal = _InteractiveShell(self, self.env)
        terminal.command('mkidr work/example')
        self.assertIn('STATUS=127\n', terminal.command('printf \'STATUS=%s\\n\' "$?"'))
        terminal.command('false')
        self.assertIn('STATUS=1\n', terminal.command('printf \'STATUS=%s\\n\' "$?"'))
        terminal.command('true')
        self.assertIn('STATUS=0\n', terminal.command('printf \'STATUS=%s\\n\' "$?"'))
        terminal.finish()

    def test_pty_never_imports_or_changes_old_history_files(self):
        history_files = [self.home / '.bash_history', self.session / 'history',
                         self.base / 'inherited-history']
        for index, path in enumerate(history_files):
            path.write_bytes(f'mkidr HISTORY_SENTINEL_{index}\n'.encode())
        original = {path: path.read_bytes() for path in history_files}
        terminal = _InteractiveShell(self, dict(self.env, HISTFILE=str(history_files[-1])))
        self.assertEqual(self.state().get('shell_observations', []), [])
        self.assertEqual(self.patterns(), [])
        self.assertNotIn('HISTORY_SENTINEL_', terminal.command('history'))
        terminal.command('mkidr work/example')
        self.assertEqual(self.one_typo()['attempts'], 1)
        terminal.finish()
        for path, content in original.items():
            self.assertEqual(path.read_bytes(), content)

    def test_repeated_identical_checks_preserve_attempts_but_count_one_problem(self):
        before = self.partial_backup()
        for _ in range(2):
            self.cli('check', ok=False)
        after = self.state()
        self.assertEqual(after['attempts']['2'], 3)
        self.assertEqual(len(after['events']), len(before['events']) + 2)
        self.assertEqual(after['learning']['concepts']['hidden']['failures'], 1)
        self.assertEqual(after['learning']['active_issue']['repeat_checks'], 2)
        self.assertEqual(after['events'][-1]['diagnosis']['evidence'],
                         before['events'][-1]['diagnosis']['evidence'])

    def test_unrelated_observation_does_not_reset_check_problem_or_evidence(self):
        before = self.partial_backup()
        self.shell('pwd')
        self.observe('pwd')
        self.cli('check', ok=False)
        after = self.state()
        self.assertGreater(after['shell_sequence'], before['shell_sequence'])
        self.assertEqual(after['learning']['concepts']['hidden']['failures'], 1)
        self.assertEqual(after['learning']['active_issue']['repeat_checks'], 1)
        self.assertEqual(after['events'][-1]['diagnosis']['evidence'],
                         before['events'][-1]['diagnosis']['evidence'])

    def test_changed_backup_still_failing_is_a_new_check_problem(self):
        self.partial_backup()
        backup_log = self.root / 'work/backup/boot.log'
        backup_log.write_text(backup_log.read_text(encoding='utf-8') + 'changed\n', encoding='utf-8')
        self.cli('check', ok=False)
        state = self.state()
        self.assertEqual(state['attempts']['2'], 2)
        self.assertEqual(state['events'][-1]['diagnosis']['code'], 'backup')
        self.assertEqual(state['learning']['concepts']['copy']['failures'], 2)
        self.assertEqual(state['learning']['active_issue']['repeat_checks'], 0)

    def test_unrelated_notes_do_not_create_new_phase_one_three_four_seven_problems(self):
        initial = self.state()
        for phase, directory in ((1, 'work/evidence'), (3, 'inbox'),
                                 (4, 'work/recovered'), (7, 'work/recovered')):
            with self.subTest(phase=phase):
                # Isolate each failure in this disposable round; no real learner
                # progress or submission is involved in the fixture setup.
                state = json.loads(json.dumps(initial))
                state['done'] = list(range(1, phase))
                self.write_state(state)
                folder = self.root / directory
                folder.mkdir(parents=True, exist_ok=True)
                self.cli('check', 'WRONG', ok=False, cwd=self.root / 'airlock')
                before = self.state()
                (folder / f'my-notes-{phase}.txt').write_text('personal note\n')
                self.cli('check', 'WRONG', ok=False, cwd=self.root / 'airlock')
                after = self.state()
                self.assertEqual(after['learning']['active_issue']['problem_id'],
                                 before['learning']['active_issue']['problem_id'])
                self.assertEqual(after['learning']['active_issue']['repeat_checks'], 1)
                self.assertEqual(after['learning']['concepts'], before['learning']['concepts'])
                self.assertEqual(after['attempts'][str(phase)], 2)

    def observation_key(self, phase, answer=''):
        result = orbit.check_observation_key(self.root, self.state(), phase, answer)
        self.assertIsNotNone(result)
        return result

    def fixture_file(self, relative, text='fixture\n'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def test_phase_one_observes_directory_type_not_notes_or_mode(self):
        folder = self.root / 'work/evidence'
        folder.mkdir(parents=True)
        before = self.observation_key(1)
        note = self.fixture_file('work/evidence/my-notes.txt')
        folder.chmod(0o700)
        self.assertEqual(self.observation_key(1), before)
        note.unlink()
        folder.rmdir()
        folder.write_text('this is a file, not a directory\n')
        self.assertNotEqual(self.observation_key(1), before)

    def test_required_file_edits_change_each_relevant_phase_key(self):
        for phase, relative in ((2, 'work/backup/boot.log'),
                                (3, 'work/evidence/route.txt'),
                                (4, 'work/recovered/manifest.txt'),
                                (6, 'work/recovered/relay.conf'),
                                (7, 'work/recovered/receipt.txt'),
                                (9, 'work/rescue.tar.gz')):
            with self.subTest(phase=phase):
                path = self.fixture_file(relative, 'first attempt\n')
                before = self.observation_key(phase)
                path.write_text('second attempt\n')
                self.assertNotEqual(self.observation_key(phase), before)

    def test_cleanup_targets_are_observed_for_existence_only(self):
        target = self.root / 'inbox/decoy-a.tmp'
        self.assertTrue(target.exists())
        before = self.observation_key(3)
        target.write_text('irrelevant content while the deletion target still exists\n')
        target.chmod(0o700)
        self.assertEqual(self.observation_key(3), before)
        target.unlink()
        self.assertNotEqual(self.observation_key(3), before)

    def test_only_phase_seven_config_and_script_modes_count(self):
        config = self.fixture_file('work/recovered/relay.conf')
        script = self.fixture_file('work/recovered/relay.sh')
        receipt = self.fixture_file('work/recovered/receipt.txt')
        config.chmod(0o644)
        script.chmod(0o644)
        receipt.chmod(0o644)
        before_four = self.observation_key(4)
        before_seven = self.observation_key(7)
        config.chmod(0o600)
        self.assertEqual(self.observation_key(4), before_four)
        self.assertNotEqual(self.observation_key(7), before_seven)
        before_seven = self.observation_key(7)
        script.chmod(0o700)
        self.assertEqual(self.observation_key(4), before_four)
        self.assertNotEqual(self.observation_key(7), before_seven)
        before_seven = self.observation_key(7)
        receipt.chmod(0o600)
        self.assertEqual(self.observation_key(7), before_seven)

    def test_backup_notes_and_modes_are_ignored_but_nested_copy_fact_counts(self):
        self.fixture_file('work/backup/boot.log')
        before = {phase: self.observation_key(phase) for phase in (2, 9)}
        self.fixture_file('blackbox/personal-note.txt')
        self.fixture_file('work/backup/personal-note.txt')
        (self.root / 'blackbox/boot.log').chmod(0o600)
        for phase in (2, 9):
            self.assertEqual(self.observation_key(phase), before[phase])
        nested = self.fixture_file('work/backup/blackbox/boot.log')
        after = {phase: self.observation_key(phase) for phase in (2, 9)}
        for phase in (2, 9):
            self.assertNotEqual(after[phase], before[phase])
        nested.write_text('the diagnostic reads only this file existence\n')
        for phase in (2, 9):
            self.assertEqual(self.observation_key(phase), after[phase])

    def test_unrelated_large_directory_does_not_disable_repeat_grouping(self):
        folder = self.root / 'work/recovered'
        folder.mkdir(parents=True)
        before = self.observation_key(4)
        for index in range(270):
            (folder / f'note-{index}.txt').write_text('notes\n')
        self.assertEqual(self.observation_key(4), before)

    def test_leaf_and_parent_symlinks_are_never_followed(self):
        outside = self.base / 'outside-task'
        outside.mkdir()
        target = outside / 'relay.conf'
        target.write_text('outside original\n')
        recovered = self.root / 'work/recovered'
        recovered.mkdir(parents=True)
        linked_file = recovered / 'relay.conf'
        linked_file.symlink_to(target)
        with patch.object(orbit.os, 'open', wraps=os.open) as opened:
            before = self.observation_key(6)
        self.assertTrue(all(call.args[1] & os.O_NOFOLLOW for call in opened.call_args_list))
        self.assertNotIn('relay.conf', [call.args[0] for call in opened.call_args_list])
        target.write_text('outside changed\n')
        self.assertEqual(self.observation_key(6), before)
        linked_file.unlink()
        recovered.rmdir()
        recovered.symlink_to(outside, target_is_directory=True)
        with patch.object(orbit.os, 'open', wraps=os.open) as opened:
            before = self.observation_key(7)
        self.assertNotIn('recovered', [call.args[0] for call in opened.call_args_list])
        target.write_text('outside changed again\n')
        self.assertEqual(self.observation_key(7), before)

    def test_unused_submission_text_does_not_split_a_problem(self):
        for phase in (2, 3, 6, 7, 9):
            with self.subTest(phase=phase):
                self.assertEqual(self.observation_key(phase, 'first'),
                                 self.observation_key(phase, 'second'))
        for phase in (1, 4, 5, 8):
            with self.subTest(phase=phase):
                self.assertNotEqual(self.observation_key(phase, 'first'),
                                    self.observation_key(phase, 'second'))


if __name__ == '__main__':
    unittest.main()
