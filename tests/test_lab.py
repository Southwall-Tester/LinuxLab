"""Run with python3 -m unittest discover -s tests -v inside WSL/Linux.

The walkthrough intentionally lives outside the student distribution.
"""
import io
import json
import os
from pathlib import Path
import pty
import select
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import orbit


class LabTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='orbit-test-')
        self.env = dict(os.environ, ORBIT_DATA_DIR=self.temp.name, PYTHONUTF8='1',
                        ORBIT_ENGINE=str(APP / 'orbit.py'),
                        ORBIT_AI_CONFIG=str(Path(self.temp.name) / 'test-ai.local.json'))
        p = subprocess.run([sys.executable, str(APP / 'orbit.py'), 'prepare'],
                           env=self.env, capture_output=True, text=True, check=True)
        self.session = Path(p.stdout.strip())
        self.root = self.session / 'station'
        self.env['ORBIT_HOME'] = str(self.session)
        self.s = json.loads((self.session / 'state.json').read_text())

    def tearDown(self):
        self.cli('stop')
        self.temp.cleanup()

    def cli(self, *args, cwd=None, ok=True):
        p = subprocess.run([sys.executable, str(APP / 'orbit.py'), *args], env=self.env,
                           cwd=cwd or self.root, capture_output=True, text=True, timeout=10)
        if ok:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        else:
            self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout + p.stderr

    def shell(self, command, cwd=None):
        p = subprocess.run(['bash', '-c', command], env=self.env, cwd=cwd or self.root,
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def state(self):
        return json.loads((self.session / 'state.json').read_text())

    def solve_to(self, phase):
        for n in range(1, phase + 1):
            if n == 1:
                self.shell('ls -a airlock; mkdir -p work/evidence')
                self.cli('check', self.s['beacon'], cwd=self.root / 'airlock')
            elif n == 2:
                self.shell('cp -a blackbox work/backup'); self.cli('check')
            elif n == 3:
                self.shell('ls inbox/decoy-*.tmp; mv inbox/route.pending work/evidence/route.txt; rm inbox/decoy-*.tmp')
                self.cli('check')
            elif n == 4:
                self.shell('mkdir -p work/recovered; tar -tzf supplies/rescue.tar.gz; tar -xzf supplies/rescue.tar.gz -C work/recovered; cat work/recovered/manifest.txt')
                self.cli('check', self.s['seal'])
            elif n == 5:
                text = self.shell('cat work/evidence/route.txt; tail -n 5 logs/comms.log')
                self.assertIn(self.s['code'], text); self.cli('check', self.s['code'])
            elif n == 6:
                # Real Vim in Ex mode for a reproducible full walkthrough.
                script = f"%s/MODE=maintenance/MODE=rescue/\n%s/CHANNEL=000/CHANNEL={self.s['channel']}/\n%s/AUTH=UNSET/AUTH={self.s['code']}/\nwq\n"
                p = subprocess.run(['vim', '-Nu', 'NONE', '-n', '-es', 'work/recovered/relay.conf'],
                                   input=script, text=True, cwd=self.root, env=self.env, capture_output=True)
                self.assertEqual(p.returncode, 0, p.stderr); self.cli('check')
            elif n == 7:
                self.shell('chmod 700 relay.sh; chmod 600 relay.conf; ./relay.sh', cwd=self.root / 'work/recovered')
                self.cli('check')
            elif n == 8:
                self.cli('load')
                text = self.shell('top -b -n 1 -w 180')
                probe = [line for line in text.splitlines() if 'station-pulse' in line]
                self.assertEqual(len(probe), 1, text)
                pid = probe[0].split()[0]
                self.cli('check', pid)

    def final_files(self):
        self.shell('tar -xzf finale/capsule.tar.gz -C work; mv work/dispatch/relay.conf.draft work/dispatch/relay.conf; rm work/dispatch/discard.tmp; cp inbox/crew.csv work/recovered/receipt.txt work/dispatch/')
        (self.root / 'work/dispatch/relay.conf').write_text(orbit.cfg(self.s, final=True))
        self.shell('chmod 600 work/dispatch/relay.conf')
        self.pack()

    def pack(self):
        self.shell('tar -czf rescue.tar.gz dispatch', cwd=self.root / 'work')

    def test_full_real_command_walkthrough_and_resume(self):
        self.cli('check', 'wrong', ok=False)
        self.cli('hint'); self.cli('hint', '3'); self.cli('learn')
        self.solve_to(8)
        self.final_files()
        output = self.cli('check')
        self.assertIn('RESCUE COMPLETE', output)
        self.assertEqual(self.state()['done'], list(range(1, 10)))
        report = json.loads((self.session / 'report.json').read_text())
        self.assertTrue(report['completed'])
        self.assertEqual(report['hints']['1'], 3)
        p = subprocess.run([sys.executable, str(APP / 'orbit.py'), 'prepare'], env=self.env,
                           capture_output=True, text=True, check=True)
        self.assertEqual(p.stdout.strip(), str(self.session))
        self.assertIn('RESCUE COMPLETE', self.cli('check'))

    def test_copy_requires_hidden_file_and_original(self):
        self.solve_to(1)
        self.shell('cp -a blackbox work/backup; rm work/backup/.integrity')
        self.assertIn('.integrity', self.cli('check', ok=False))
        self.shell('cp blackbox/.integrity work/backup/.integrity; rm blackbox/boot.log')
        self.cli('check', ok=False)

    def test_repair_keeps_scene_and_previous_progress(self):
        self.solve_to(2)
        self.shell('rm inbox/crew.csv')
        self.cli('check', ok=False)
        self.cli('repair')
        self.assertTrue((self.root / 'inbox/crew.csv').exists())
        self.assertEqual(self.state()['done'], [1, 2])
        saved = list((self.session / 'recovery').iterdir())
        self.assertEqual(len(saved), 1)
        self.assertFalse((saved[0] / 'inbox/crew.csv').exists())

    def test_glob_cleanup_selection_and_overbroad_patterns(self):
        self.solve_to(2)
        expanded = self.shell("printf '%s\\n' inbox/decoy-*.tmp").splitlines()
        self.assertEqual(set(expanded), {'inbox/' + n for n in orbit.cleanup_targets(self.s)})
        self.assertIn('inbox/decoy-.tmp', expanded)  # star can match zero characters
        self.assertEqual(self.shell("printf '%s\\n' 'inbox/decoy-*.tmp'").strip(),
                         'inbox/decoy-*.tmp')  # quoted pattern remains literal
        self.assertNotIn('inbox/.decoy-cache.tmp', self.shell("printf '%s\\n' inbox/*.tmp").splitlines())
        self.shell('mv inbox/route.pending work/evidence/route.txt; rm inbox/decoy-a.tmp inbox/decoy-b.tmp')
        self.assertIn('decoy-', self.cli('check', ok=False))  # incomplete batch
        self.cli('repair')
        for pattern, lost in [('inbox/decoy-*', 'decoy-guide.txt'), ('inbox/*.tmp', 'sensor.tmp')]:
            self.shell('mv inbox/route.pending work/evidence/route.txt; rm ' + pattern)
            self.assertIn(lost, self.cli('check', ok=False))
            self.assertEqual(self.state()['done'], [1, 2])
            self.cli('repair')
        self.shell('mv inbox/route.pending work/evidence/route.txt; rm inbox/decoy-*.tmp; rm inbox/.decoy-cache.tmp')
        self.assertIn('.decoy-cache.tmp', self.cli('check', ok=False))
        self.cli('repair')
        self.shell('mv inbox/route.pending work/evidence/route.txt; rm inbox/decoy-*.tmp')
        self.cli('check')
        for name, text in orbit.cleanup_kept(self.s).items():
            self.assertEqual((self.root / 'inbox' / name).read_text(), text)

    def test_legacy_cleanup_session_resumes_without_new_requirements(self):
        # Build the old two-decoy fixture only in this test's temporary session.
        for name in orbit.cleanup_targets(self.s)[2:] + list(orbit.cleanup_kept(self.s)):
            (self.root / 'inbox' / name).unlink()
        self.s.pop('cleanup_version')
        orbit.atomic_json(self.session / 'state.json', self.s)
        p = subprocess.run([sys.executable, str(APP / 'orbit.py'), 'prepare'],
                           env=self.env, capture_output=True, text=True, check=True)
        self.assertEqual(p.stdout.strip(), str(self.session))
        self.solve_to(2)
        self.assertNotIn('decoy-guide.txt', [p.name for p in (self.root / 'inbox').iterdir()])
        self.shell('mv inbox/route.pending work/evidence/route.txt; rm inbox/decoy-a.tmp inbox/decoy-b.tmp')
        self.cli('check')
        self.assertEqual(self.state()['done'], [1, 2, 3])

    def test_wrong_answer_config_and_permission_fail(self):
        self.solve_to(4)
        self.cli('check', 'EXPIRED', ok=False)
        self.cli('check', self.s['code'])
        p = self.root / 'work/recovered/relay.conf'
        p.write_text(orbit.cfg(self.s) + 'MODE=rescue\n')
        self.assertIn('重复', self.cli('check', ok=False))
        p.write_text(orbit.cfg(self.s)); self.cli('check')
        self.cli('relay', ok=False)
        self.shell('chmod 777 work/recovered/relay.sh; chmod 600 work/recovered/relay.conf')
        self.cli('relay', ok=False)
        self.shell('chmod 700 work/recovered/relay.sh')
        self.cli('check', ok=False)  # no launch receipt yet
        self.shell('./relay.sh', cwd=self.root / 'work/recovered')
        self.cli('check')

    def test_live_pid_validation_and_cleanup(self):
        self.solve_to(7)
        self.cli('check', '1', ok=False)
        self.cli('load'); w = self.state()['worker']
        self.assertTrue(orbit.worker_alive(w))
        self.cli('check', '1', ok=False)
        self.cli('stop')
        time.sleep(0.1)
        self.assertFalse(orbit.worker_alive(w))
        self.cli('check', str(w['pid']), ok=False)
        self.cli('load')
        self.cli('check', str(self.state()['worker']['pid']))

    def test_archive_checks_contents_paths_modes_and_duplicates(self):
        self.solve_to(8); self.final_files()
        p = self.root / 'work/dispatch/relay.conf'
        good = p.read_text(); p.write_text(orbit.cfg(self.s)); self.pack()
        self.cli('check', ok=False)
        p.write_text(good)  # repairing source alone does not repair the tar
        self.cli('check', ok=False)
        p.chmod(0o777); self.pack(); self.cli('check', ok=False)
        p.chmod(0o600)
        (self.root / 'work/dispatch/discard.tmp').write_text('extra')
        self.pack(); self.cli('check', ok=False)
        (self.root / 'work/dispatch/discard.tmp').unlink()
        path = self.root / 'work/rescue.tar.gz'
        for name in ['../outside', '/absolute']:
            orbit.make_tar(path, {name: ('bad', 0o644)})
            self.cli('check', ok=False)
        with tarfile.open(path, 'w:gz') as t:
            for _ in range(2):
                b = good.encode(); info = tarfile.TarInfo('dispatch/relay.conf')
                info.size, info.mode = len(b), 0o600
                t.addfile(info, io.BytesIO(b))
        self.assertIn('重复', self.cli('check', ok=False))
        path.write_bytes(b'not a gzip file'); self.cli('check', ok=False)
        self.pack(); self.cli('check')

    def test_symlink_is_not_accepted_as_backup(self):
        self.solve_to(1)
        self.shell('ln -s ../blackbox work/backup')
        self.assertIn('符号链接', self.cli('check', ok=False))

    def test_new_round_preserves_old_files(self):
        old = (self.root / 'MAP.txt').read_bytes()
        p = subprocess.run([sys.executable, str(APP / 'orbit.py'), 'prepare', '--new'],
                           env=self.env, capture_output=True, text=True, check=True)
        new = Path(p.stdout.strip())
        self.assertNotEqual(new, self.session)
        self.assertEqual((self.root / 'MAP.txt').read_bytes(), old)
        self.assertNotEqual(json.loads((new / 'state.json').read_text())['station_id'], self.s['station_id'])

    def test_tutor_rules_exist_and_refresh_on_resume(self):
        expected = (APP / 'docs/STUDENT-AGENTS.md').read_text()
        for forbidden in ['维护模式', 'Git 工作约定', 'commit', 'push', 'Release']:
            self.assertNotIn(forbidden, expected)
        self.assertIn('不直接编辑学生作业文件', expected)
        self.assertIn('该单步的修正', expected)
        self.assertEqual((self.root / 'AGENTS.md').read_text(), expected)
        self.assertTrue((self.root / 'STUDENT.md').is_file())
        (self.root / 'AGENTS.md').write_text('outdated copy')
        (self.root / 'notes.md').unlink()  # an older session has no notes copy
        subprocess.run([sys.executable, str(APP / 'orbit.py'), 'prepare'], env=self.env,
                       capture_output=True, text=True, check=True)
        self.assertEqual((self.root / 'AGENTS.md').read_text(), expected)
        self.assertEqual((self.root / 'notes.md').read_bytes(), (APP / 'notes.md').read_bytes())
        # Repair can restore an older checkpoint; it must refresh the rules too.
        (self.session / 'checkpoints/phase-1/AGENTS.md').write_text('old developer instructions')
        self.cli('repair')
        self.assertEqual((self.root / 'AGENTS.md').read_text(), expected)

    def test_notes_available_anywhere_without_progress_changes(self):
        before = self.state()
        self.assertEqual((self.root / 'notes.md').read_bytes(), (APP / 'notes.md').read_bytes())
        index = self.cli('notes', cwd=self.root / 'airlock')
        self.assertIn('lab notes ls', index)
        self.assertIn('notes.md', index)
        section = self.cli('notes', 'ls', cwd=self.root / 'work')
        self.assertIn('human-readable', section)
        self.assertNotIn('## grep', section)
        for topic in ['cd', 'pwd']:
            self.assertIn('change directory', self.cli('notes', topic))
        self.assertIn('glob', self.cli('notes', '*'))
        rendered = self.cli('notes', 'all')
        self.assertIn('human-readable', rendered)
        self.assertIn('sources', rendered)
        self.assertNotIn('**', rendered)
        self.assertNotIn('| ---', rendered)
        self.assertNotIn('## tail', self.cli('notes', 'tail'))
        self.cli('notes', '../state.json', ok=False)
        self.assertEqual(self.state(), before)

    def test_lab_input_errors_are_friendly_and_preserve_session(self):
        before = self.state()
        cases = [
            (('note', 'tail'), 'lab notes tail'),
            (('chekc',), 'lab check'),
            (('notess', 'tail'), 'lab notes tail'),
            (('NOTES', 'tail'), '大小写'),
            (('zzzzzzz',), 'lab help'),
            (('ls',), '前面不用加 lab'),
            (('exit',), '直接输入 exit'),
            (('notes', 'til'), 'lab notes tail'),
            (('notes', 'cp', 'mv'), '一次查询一个'),
            (('notes', '--unknown'), 'lab notes'),
            (('hint', 'four'), '1、2、3'),
            (('hint', '0'), '1、2、3'),
            (('hint', '4'), '1、2、3'),
            (('check', 'one', 'two'), '最多一个答案'),
            (('learn', 'tail'), 'lab notes'),
            (('--unknown',), 'lab help'),
            (('_worker',), 'lab load'),
        ]
        cases += [((name, 'extra'), '用法') for name in
                  ['mission', 'status', 'help', 'root', 'load', 'stop', 'repair', 'report', 'doctor', 'relay']]
        cases.append((('prepare', '--unknown'), 'bash start.sh'))
        for args, expected in cases:
            with self.subTest(args=args):
                output = self.cli(*args, ok=False)
                self.assertIn(expected, output)
                for raw in ['Traceback', 'usage: orbit.py', 'invalid choice:', 'unrecognized arguments:', 'argparse']:
                    self.assertNotIn(raw, output)
                self.assertEqual(self.state(), before)
        self.assertEqual(self.cli('--help'), self.cli('help'))
        self.assertIn('一次查询一个', self.cli('notes', '--help'))

    def test_shell_unknown_commands_suggest_without_execution(self):
        before = self.state()
        rc = shlex.quote(str(APP / 'shellrc.sh'))
        for wrong, expected in [('lss', 'ls'), ('lablearn', 'lab learn'), ('cd..', 'cd ..')]:
            # The quoted argument must remain data, even in the suggested command.
            command = f'source {rc} >/dev/null; ' + shlex.join([wrong, '; touch work/not-executed'])
            p = subprocess.run(['bash', '-c', command], env=self.env, cwd=self.root,
                               capture_output=True, text=True, timeout=10)
            self.assertEqual(p.returncode, 127)
            self.assertIn(expected, p.stderr)
            self.assertIn("'; touch work/not-executed'", p.stderr)
            self.assertFalse((self.root / 'work/not-executed').exists())
        self.assertEqual(self.state(), before)

    def test_real_interactive_launcher_vim_and_resume(self):
        master, slave = pty.openpty()
        env = dict(self.env, TERM='xterm-256color')
        p = subprocess.Popen(['bash', str(APP / 'start.sh')], env=env, stdin=slave, stdout=slave,
                             stderr=slave, start_new_session=True)
        os.close(slave)
        captured = bytearray()

        def wait_for(needle, timeout=8):
            deadline = time.monotonic() + timeout
            chunk = bytearray()
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        data = os.read(master, 65536)
                    except OSError:
                        break
                    chunk.extend(data); captured.extend(data)
                    if needle.encode() in chunk:
                        return
            self.fail(f'PTY did not show {needle!r}: ' + captured.decode(errors='replace'))

        try:
            wait_for('本关工具')
            os.write(master, b'vim work/terminal-proof.txt\n')
            time.sleep(0.5)
            os.write(master, b'iREAL-VIM-EDIT\x1b:wq\r')
            time.sleep(0.4)
            os.write(master, f'cd airlock\nmkdir -p ../work/evidence\nlab check {self.s["beacon"]}\n'.encode())
            wait_for('[通过 01/09]')
            os.write(master, b'exit\n')
            p.wait(timeout=6)
            self.assertEqual((self.root / 'work/terminal-proof.txt').read_text().strip(), 'REAL-VIM-EDIT')
            self.assertEqual(self.state()['done'], [1])
            self.assertEqual(p.returncode, 0)
        finally:
            if p.poll() is None:
                p.terminate(); p.wait(timeout=3)
            os.close(master)


if __name__ == '__main__':
    unittest.main()
