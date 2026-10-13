"""Real isolated LinuxLab command, profile and terminal assessment workflows."""
import json
import os
from pathlib import Path
import pty
import select
import shlex
import subprocess
import sys
import time
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import test_lab as fixtures
import assessment
import assessment_tasks
import tutor_chat
import mastery

APP = fixtures.APP


class AssessmentIntegration(unittest.TestCase):
    setUp = fixtures.LabTest.setUp
    tearDown = fixtures.LabTest.tearDown
    cli = fixtures.LabTest.cli
    shell = fixtures.LabTest.shell
    state = fixtures.LabTest.state

    def attempt(self):
        return assessment.active(self.session, self.state())

    def workspace(self):
        return assessment.workdir(self.session, self.attempt())

    def profile(self, topic=''):
        args = ['profile'] + ([topic] if topic else []) + ['--json']
        return json.loads(self.cli(*args))['topics']

    def observed(self, command, cwd=None, kind='file', expected=0):
        cwd = cwd or self.workspace()
        proc = subprocess.run(['bash', '-c', command], env=self.env, cwd=cwd,
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        observed = subprocess.run([sys.executable, str(APP / 'orbit.py'), '--observe-shell',
                                   str(proc.returncode), '0'], input='1 ' + command,
                                  env=dict(self.env, ORBIT_OBSERVED_CWD=str(cwd),
                                           ORBIT_OBSERVED_COMMAND_KIND=kind), cwd=cwd,
                                  capture_output=True, text=True, timeout=10)
        self.assertEqual(observed.returncode, 0, observed.stderr)
        return proc.stdout

    def solve_copy(self):
        family = self.attempt()['task']['family']
        if family == 'new_target':
            self.observed('cp -a source backup')
        elif family == 'existing_target':
            self.observed('cp -a source/. backup/')
        else:
            self.observed('mkdir backup')
            self.observed('cp -a source/.settings source/sub backup/')

    def test_profile_three_variants_resume_and_new_round(self):
        before = self.state()
        families = set()
        for expected in (.6705882353, .9062761506, .9786920333):
            self.cli('assess', 'copy')
            families.add(self.attempt()['task']['family'])
            self.solve_copy()
            result = self.cli('assess', 'submit', cwd=self.workspace())
            self.assertIn('短测通过', result)
            summary = self.profile('copy')['copy']
            self.assertAlmostEqual(summary['p_mastery'], expected, places=8)
            event_count = len(json.loads((Path(self.temp.name) / 'learner-profile.json').read_text())['events'])
            self.cli('assess', 'submit', cwd=self.workspace())
            self.assertEqual(len(json.loads((Path(self.temp.name) / 'learner-profile.json').read_text())['events']), event_count)
        self.assertEqual(len(families), 3)
        self.assertEqual(summary['status'], 'mastered')
        self.assertFalse(summary['human_reviewed'])
        self.assertEqual(self.state()['done'], before['done'])
        self.assertEqual(self.state()['events'], before['events'])
        self.cli('report')
        report = json.loads((self.session / 'report.json').read_text())
        self.assertEqual(report['learner_profile']['topics']['copy']['status'], 'mastered')
        self.assertIn('概率画像', (self.session / 'learning-notebook.md').read_text())
        old_session = self.session
        created = subprocess.run([sys.executable, str(APP / 'orbit.py'), 'prepare', '--new', '--scene', 'ocean'],
                                 env=self.env, capture_output=True, text=True, check=True)
        self.session = Path(created.stdout.strip())
        self.root = self.session / 'station'
        self.env['ORBIT_HOME'] = str(self.session)
        self.assertEqual(self.profile('copy')['copy']['status'], 'mastered')
        self.assertTrue((old_session / 'state.json').is_file())
        self.assertNotIn('threshold_and', self.cli('profile', 'copy'))
        self.cli('assess', 'copy')  # Explicit challenge remains available after confirmation.
        self.observed('cp -a source/data.txt partial.txt')
        self.cli('assess', 'submit', cwd=self.workspace(), ok=False)
        self.assertEqual(self.profile('copy')['copy']['status'], 'review_due')

    def test_help_tracking_and_first_submission(self):
        self.cli('assess', 'copy')
        self.observed('cp --help', cwd=self.root)
        self.solve_copy()
        self.cli('assess', 'submit', cwd=self.workspace())
        summary = self.profile('copy')['copy']
        self.assertAlmostEqual(summary['p_mastery'], .37)
        self.assertEqual(summary['passed_families'], [])
        self.cli('assess', 'copy')
        self.cli('tracking', 'off')
        self.cli('tracking', 'on')
        self.solve_copy()
        self.cli('assess', 'submit', cwd=self.workspace())
        self.assertAlmostEqual(self.profile('copy')['copy']['p_mastery'], .37)
        self.assertFalse(self.attempt()['evidence'][0]['observed'])
        self.cli('assess', 'copy')
        # A first independent failed submission is never rewritten by corrections.
        self.observed('cp -a source/data.txt partial.txt')
        self.cli('assess', 'submit', cwd=self.workspace(), ok=False)
        first = self.attempt()['evidence'][0]
        self.solve_copy()
        self.cli('assess', 'submit', cwd=self.workspace())
        self.assertEqual(self.attempt()['evidence'][0], first)
        self.assertFalse(first['passed'])
        self.assertEqual(self.attempt()['evidence'][-1]['kind'], 'training')
        self.assertTrue(self.attempt()['evidence'][-1]['passed'])

    def test_guided_failure_then_correction_records_learning_once(self):
        self.cli('assess', 'copy')
        self.cli('assess', 'hint')
        self.observed('cp -a source/data.txt partial.txt')
        self.cli('assess', 'submit', cwd=self.workspace(), ok=False)
        self.assertAlmostEqual(self.profile('copy')['copy']['p_mastery'], .3)
        self.solve_copy()
        self.cli('assess', 'submit', cwd=self.workspace())
        self.assertAlmostEqual(self.profile('copy')['copy']['p_mastery'], .37)
        self.cli('assess', 'submit', cwd=self.workspace())
        self.assertAlmostEqual(self.profile('copy')['copy']['p_mastery'], .37)

    def test_active_chat_uses_short_task_without_story_evidence(self):
        self.cli('assess', 'copy')
        before = self.state()
        context = tutor_chat.context(before, question='复制是什么')
        self.assertTrue(context['assessment'])
        self.assertEqual(list(context['concepts']), ['copy'])
        self.assertNotIn('private', json.dumps(context))
        proc = subprocess.run([sys.executable, str(APP / 'linuxlab.py'), 'chat', '--offline'],
                              input='复制是什么\n/exit\n', env=self.env, cwd=self.root,
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('短测本地讲解', proc.stdout)
        self.assertEqual(self.state()['events'], before['events'])
        self.assertEqual(self.state().get('dialogue_total', 0), before.get('dialogue_total', 0))
        self.assertTrue(self.attempt()['help'])
        self.assertEqual(len(self.attempt()['dialogue']), 1)
        self.solve_copy()
        self.cli('assess', 'submit', cwd=self.workspace())
        self.assertEqual(self.profile('copy')['copy']['passed_families'], [])

    def test_profile_symlink_and_attempt_symlink_rejected(self):
        outside = Path(self.temp.name) / 'outside.json'
        outside.write_text('untouched')
        profile = Path(self.temp.name) / 'learner-profile.json'
        profile.symlink_to(outside)
        self.assertIn('符号链接', self.cli('profile', ok=False))
        profile.unlink()
        self.cli('assess', 'copy')
        path = self.session / 'assessments' / (self.state()['assessment_active'] + '.json')
        saved = path.read_text()
        path.unlink()
        path.symlink_to(outside)
        self.assertIn('符号链接', self.cli('assess', 'show', ok=False))
        self.assertEqual(outside.read_text(), 'untouched')
        path.unlink()
        path.write_text(saved)

    def test_profile_crash_replay_and_learner_data_isolation(self):
        self.cli('assess', 'copy')
        self.solve_copy()
        self.cli('assess', 'submit', cwd=self.workspace())
        path = Path(self.temp.name) / 'learner-profile.json'
        original = path.read_text()
        path.unlink()  # Simulate durable first submission before profile commit.
        summary = self.profile('copy')['copy']
        self.assertAlmostEqual(summary['p_mastery'], .6705882353)
        self.assertEqual(json.loads(path.read_text()), json.loads(original))
        import tempfile
        with tempfile.TemporaryDirectory(prefix='linuxlab-second-learner-') as other:
            env = dict(self.env, ORBIT_DATA_DIR=other)
            p = subprocess.run([sys.executable, str(APP / 'orbit.py'), 'prepare', '--scene', 'space'],
                               env=env, capture_output=True, text=True, check=True)
            env['ORBIT_HOME'] = p.stdout.strip()
            p = subprocess.run([sys.executable, str(APP / 'orbit.py'), 'profile', 'copy', '--json'],
                               env=env, capture_output=True, text=True, check=True)
            self.assertAlmostEqual(json.loads(p.stdout)['topics']['copy']['p_mastery'], .3)

    def test_all_consumed_does_not_claim_all_mastered_and_next_teaches(self):
        for _ in range(3):
            self.cli('assess', 'copy')
            self.observed('cp -a source/data.txt partial.txt')
            self.cli('assess', 'submit', cwd=self.workspace(), ok=False)
            self.cli('assess', 'abandon')
        output = self.cli('next', 'copy')
        self.assertNotIn('均已达标', output)
        self.assertIn('指导练习', output)

    def test_prediction_metrics_preserve_prior_predictions(self):
        empty = json.loads(self.cli('profile', '--metrics', '--json'))
        self.assertEqual(empty['sample_count'], 0)
        self.assertIsNone(empty['brier_score'])
        self.cli('assess', 'copy')
        self.solve_copy()
        self.cli('assess', 'submit', cwd=self.workspace())
        first = self.attempt()['evidence'][0]['prediction_before']
        self.assertAlmostEqual(first['p_mastery'], .3)
        self.assertAlmostEqual(first['p_success'], .425)
        report = json.loads(self.cli('profile', '--metrics', '--json'))
        self.assertEqual(report['sample_count'], 1)
        self.assertAlmostEqual(report['brier_score'], .575 ** 2)
        self.assertFalse(report['effectiveness_validated'])
        self.cli('assess', 'submit', cwd=self.workspace())
        self.assertEqual(json.loads(self.cli('profile', '--metrics', '--json')), report)

    def test_calibration_status_is_automatic_and_cold_start_is_read_only(self):
        path = Path(self.temp.name) / 'learner-profile.json'
        report = json.loads(self.cli('profile', '--calibration', 'copy', '--json'))
        self.assertEqual(set(report['topics']), {'copy'})
        self.assertEqual(report['topics']['copy']['eligible_count'], 0)
        self.assertEqual(report['topics']['copy']['status'], 'cold_start')
        self.assertFalse(path.exists())
        self.assertIn('无需手动启动', self.cli('profile', '--calibration', 'copy'))
        self.cli('profile', '--calibration', '--metrics', ok=False)
        self.assertFalse(path.exists())

    def test_prediction_is_durable_before_grading_and_reused_after_crash(self):
        self.cli('assess', 'copy')
        self.solve_copy()
        def crash_after_snapshot(*args, **kwargs):
            item = self.attempt()
            self.assertIn('model_snapshot', item)
            self.assertAlmostEqual(item['model_snapshot']['prediction_before']['p_success'], .425)
            raise OSError('isolated checker interruption')
        with patch.object(assessment_tasks, 'evaluate', side_effect=crash_after_snapshot):
            with self.assertRaisesRegex(OSError, 'isolated checker'):
                assessment.submit(self.session, self.state())
        snapshot = self.attempt()['model_snapshot']
        self.assertEqual(self.attempt()['evidence'], [])
        self.cli('assess', 'submit', cwd=self.workspace())
        item = self.attempt()
        event = item['evidence'][0]
        self.assertEqual(item['model_snapshot'], snapshot)
        self.assertEqual(event['prediction_before'], snapshot['prediction_before'])
        self.assertEqual(event['bkt_parameters'], snapshot['bkt_parameters'])
        self.assertEqual(event['parameter_version'], snapshot['parameter_version'])

    def test_real_submission_activates_calibration_and_new_round_keeps_it(self):
        # Authored test data in the isolated fixture, never real learner records.
        outcomes = 'PFFPPPFFPPFPFPPFPFFPPPFPPPPPPP'
        profile = mastery.new_profile()
        tasks = [t for t in assessment_tasks.catalog() if t['topic'] == 'copy']
        beginning = datetime.now(timezone.utc) - timedelta(days=29)
        for index, outcome in enumerate(outcomes[:-1]):
            at = beginning + timedelta(days=index)
            task = tasks[index % len(tasks)]
            row = mastery.summarize(profile, at)['copy']
            mastery.record(profile, dict(
                id='fixture:' + str(index), attempt_id='fixture:' + str(index),
                session_id='isolated-calibration-fixture', topic='copy',
                task_id=task['id'], family=task['family'], contract_version=1,
                at=at.isoformat(), passed=outcome == 'P', independent=True,
                observed=True, technical_error=False, kind='assessment',
                parameter_version=mastery.PARAMETER_VERSION,
                bkt_parameters=dict(mastery.DEFAULT_PARAMETERS),
                slip=.05, guess=.20,
                prediction_before=dict(p_mastery=row['p_mastery'], p_success=row['p_next_success'],
                                       status=row['status'], parameter_version=mastery.PARAMETER_VERSION)))
        frozen = deepcopy(profile['events'])
        profile_path = Path(self.temp.name) / 'learner-profile.json'
        assessment.atomic(profile_path, profile)
        self.cli('assess', 'copy')
        self.solve_copy()
        self.cli('assess', 'submit', cwd=self.workspace())
        calibrated = json.loads(profile_path.read_text())
        self.assertEqual(calibrated['events'][:29], frozen)
        status = json.loads(self.cli('profile', '--calibration', 'copy', '--json'))['topics']['copy']
        version = status['active_version']
        self.assertNotEqual(version, mastery.PARAMETER_VERSION)
        self.assertEqual(status['eligible_count'], 30)
        self.assertEqual(status['parameters']['confirmation_threshold'], .95)
        self.assertEqual(self.attempt()['evidence'][0]['parameter_version'], mastery.PARAMETER_VERSION)
        self.cli('assess', 'copy')
        self.solve_copy()
        with patch.object(assessment_tasks, 'evaluate', side_effect=OSError('snapshot interruption')):
            with self.assertRaises(OSError):
                assessment.submit(self.session, self.state())
        frozen_prediction = deepcopy(self.attempt()['model_snapshot']['prediction_before'])
        self.assertEqual(frozen_prediction['shadow_previous']['version'], mastery.PARAMETER_VERSION)
        # Another round can add evidence during a retry. Both predictions must
        # still compare the same earlier information, not give the shadow hindsight.
        with assessment.profile_store(self.session) as shared:
            mastery.record(shared, dict(id='fixture:intervening-training',
                topic='copy', task_id='fixture-training', family='guided', at=assessment.stamp(),
                passed=True, independent=False, observed=True, technical_error=False,
                kind='training', parameter_version=version, bkt_parameters=status['parameters']))
        self.cli('assess', 'submit', cwd=self.workspace())
        event = self.attempt()['evidence'][0]
        self.assertEqual(event['prediction_before'], frozen_prediction)
        self.assertEqual(event['parameter_version'], version)
        self.assertEqual(event['bkt_parameters'], status['parameters'])
        self.assertEqual(event['slip'], status['parameters']['slip'])
        self.assertEqual(event['guess'], status['parameters']['guess'])
        predicted = event['prediction_before']['p_mastery'] * (1 - event['slip'])
        predicted += (1 - event['prediction_before']['p_mastery']) * event['guess']
        self.assertAlmostEqual(event['prediction_before']['p_success'], predicted)
        self.assertNotEqual((event['slip'], event['guess']), (.05, .20))
        model_count = len(json.loads(profile_path.read_text())['calibration']['topics']['copy']['versions'])
        self.cli('profile', '--calibration')
        self.assertEqual(len(json.loads(profile_path.read_text())['calibration']['topics']['copy']['versions']), model_count)
        created = subprocess.run([sys.executable, str(APP / 'orbit.py'), 'prepare', '--new', '--scene', 'ocean'],
                                 env=self.env, capture_output=True, text=True, check=True)
        self.session = Path(created.stdout.strip())
        self.root = self.session / 'station'
        self.env['ORBIT_HOME'] = str(self.session)
        after = json.loads(self.cli('profile', '--calibration', 'copy', '--json'))['topics']['copy']
        self.assertEqual(after['active_version'], version)
        self.assertEqual(json.loads(profile_path.read_text())['events'][:29], frozen)

    def test_automatic_route_starts_at_prerequisite(self):
        self.cli('next')
        self.assertEqual(self.attempt()['task']['topic'], 'paths')
        self.assertEqual(self.attempt()['mode'], 'assessment')

    def test_native_command_failure_is_an_independent_observation(self):
        self.cli('assess', 'copy')
        self.observed('cp missing.txt backup.txt', expected=1)
        self.cli('assess', 'submit', cwd=self.workspace(), ok=False)
        first = self.attempt()['evidence'][0]
        self.assertTrue(first['observed'])
        self.assertTrue(first['independent'])
        self.assertFalse(first['passed'])
        self.assertAlmostEqual(self.profile('copy')['copy']['p_mastery'], .015 / .575)
        self.cli('assess', 'submit', cwd=self.workspace(), ok=False)
        self.assertEqual(len(self.attempt()['evidence']), 1)

    def test_real_terminal_short_assessment(self):
        # A real prompt hook observes ./ and ../bin execution and Bash builtins.
        master, slave = pty.openpty()
        proc = subprocess.Popen(['bash', '--noprofile', '--rcfile', str(APP / 'shellrc.sh'), '-i'],
                                env=self.env, cwd=self.root, stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        transcript = bytearray()
        def prompt():
            deadline = time.monotonic() + 12
            chunk = bytearray()
            while time.monotonic() < deadline:
                if select.select([master], [], [], .1)[0]:
                    data = os.read(master, 65536)
                    chunk.extend(data)
                    transcript.extend(data)
                    if chunk.endswith(b'$ '):
                        return
            self.fail('terminal prompt timeout: ' + transcript.decode(errors='replace')[-1500:])
        def command(line):
            os.write(master, line.encode() + b'\n')
            prompt()
        try:
            prompt()
            for _ in range(3):
                command('lab assess execution')
                task = self.attempt()['task']
                root = self.workspace()
                command('cd -- ' + shlex.quote(str(root)))
                if task['family'] == 'working_directory':
                    command('chmod u+x bin/run.sh')
                    command('cd run')
                    command('../bin/run.sh')
                else:
                    command('chmod u+x run.sh')
                    argument = (' ' + shlex.quote((root / 'argument.txt').read_text().strip())) if task['family'] == 'argument' else ''
                    command('./run.sh' + argument)
                command('lab assess submit')
                self.assertTrue(self.attempt()['evidence'][0]['independent'])
                self.assertTrue(self.attempt()['last_result']['passed'])
            self.assertEqual(self.profile('execution')['execution']['status'], 'mastered')
            self.assertEqual(self.state()['done'], [])
        finally:
            if proc.poll() is None:
                os.write(master, b'exit\n')
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    proc.wait(timeout=5)
            os.close(master)


if __name__ == '__main__':
    unittest.main()
