"""Public rename must preserve legacy rounds, entry points and credentials."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_error_tracking as tracking

APP = Path(__file__).resolve().parents[1]


class BrandingTest(unittest.TestCase):
    def setUp(self):
        self.case = tracking.ErrorTrackingIntegration()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()

    def public_cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, str(APP / 'linuxlab.py'), *args],
                                env=self.case.env, cwd=self.case.root,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_new_entry_resumes_legacy_round_and_preserves_error_handling(self):
        before = self.case.state()
        self.assertEqual(self.public_cli('prepare').strip(), str(self.case.session))
        self.assertEqual(self.case.state()['id'], before['id'])
        self.assertEqual(self.case.state()['format'], before['format'])
        self.assertEqual(self.case.state()['done'], before['done'])
        self.assertIn('LinuxLab /', self.public_cli('status'))
        self.assertIn('LinuxLab /', self.case.cli('status'))
        error = self.public_cli('statuz', expected=1)
        self.assertIn('[LinuxLab]', error)
        self.assertNotIn('Traceback', error)

    def test_existing_completion_credential_is_preserved_in_renamed_report(self):
        state = self.case.state()
        state.update(done=list(range(1, 10)), flag='ORBIT{LEGACY-FIXTURE}')
        self.case.write_state(state)
        output = self.public_cli('check')
        self.assertIn('ORBIT{LEGACY-FIXTURE}', output)
        self.assertEqual(self.case.state()['flag'], 'ORBIT{LEGACY-FIXTURE}')
        report = json.loads((self.case.session / 'report.json').read_text())
        self.assertEqual(report['lab'], 'LinuxLab')
        self.assertEqual(report['result'], 'ORBIT{LEGACY-FIXTURE}')

    def test_real_terminal_displays_linuxlab_and_uses_public_entry(self):
        terminal = tracking._InteractiveShell(self.case, self.case.env)
        startup = terminal.output.decode('utf-8', errors='replace')
        self.assertIn('LinuxLab', startup)
        self.assertNotIn('ORBIT /', startup)
        self.assertIn('linuxlab.py', terminal.command('printf "%s\\n" "$ORBIT_ENGINE"'))
        terminal.finish()


if __name__ == '__main__':
    unittest.main()
