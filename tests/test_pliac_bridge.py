"""Optional PLIAC binding and privacy, on isolated real Linux rounds."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_lab
import pliac_bridge
import tasks


class BridgeTests(unittest.TestCase):
    setUp = test_lab.LabTest.setUp
    tearDown = test_lab.LabTest.tearDown
    cli = test_lab.LabTest.cli
    shell = test_lab.LabTest.shell
    state = test_lab.LabTest.state
    solve_to = test_lab.LabTest.solve_to
    final_files = test_lab.LabTest.final_files
    pack = test_lab.LabTest.pack

    def bind(self):
        self.manifest = Path(self.temp.name) / 'binding.json'
        self.report = Path(self.temp.name) / 'telemetry.json'
        self.context = dict(schema=1, binding_id='a' * 32, course_id='test-linux-course', course_version=1,
                            student_id='synthetic-test', mode='preview', scene='space',
                            contract_version=tasks.CONTRACT_VERSION, contract_hash=tasks.contract_hash(),
                            report_path=str(self.report))
        self.manifest.write_text(json.dumps(self.context), encoding='utf-8')
        self.env['PLIAC_LINUXLAB_MANIFEST'] = str(self.manifest)
        self.cli('prepare')

    def test_standalone_round_does_not_export_or_change_contract(self):
        self.cli('check', 'wrong', ok=False)
        self.assertNotIn('platform_binding', self.state())
        self.assertIsNone(pliac_bridge.snapshot(self.state()))
        self.assertEqual(tasks.contract_hash(), 'af9086405f85d7bbc01ec5f5d75edbbd172480297d7c748841e120dea67b56b4')

    def test_check_failures_hints_and_real_walkthrough_export_without_secrets(self):
        self.bind()
        self.cli('hint', '2')
        self.cli('check', 'wrong', ok=False)
        first = json.loads(self.report.read_text())
        self.assertEqual(first['events'][-1]['kind'], 'retry')
        self.assertEqual(first['events'][-1]['prompt_level'], 2)
        self.solve_to(8)
        self.final_files()
        self.cli('check')
        data = json.loads(self.report.read_text())
        self.assertEqual(data['phases_passed'], 9)
        self.assertTrue(data['completed'])
        self.assertEqual(data['events'][:len(first['events'])], first['events'])
        wire = json.dumps(data)
        state = self.state()
        for key in ('beacon', 'seal', 'code', 'final_code', 'receipt', 'integrity', 'flag'):
            self.assertNotIn(state[key], wire)
        for key in ('state', 'answer', 'reason', 'diagnosis', 'worker', 'report_path'):
            self.assertNotIn('"' + key + '"', wire)
        self.cli('prepare')
        self.assertEqual(self.state()['id'], state['id'])

    def test_shell_observation_hook_exports_bounded_mid_operation_error(self):
        self.bind()
        p = subprocess.run([sys.executable, str(test_lab.APP / 'orbit.py'), '--observe-shell', '127', '0'],
                           input='mkidr work/scratch', text=True, capture_output=True, cwd=self.root,
                           env=dict(self.env, ORBIT_OBSERVED_COMMAND_KIND='missing'))
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(self.report.read_text())
        self.assertEqual(data['operations'][-1]['exit_code'], 127)
        self.assertEqual(data['input_patterns'][-1]['kind'], 'command_typo')
        self.assertNotIn('work/scratch', json.dumps(data))
        self.assertNotIn('correction_keys', json.dumps(data))
        first_id = data['input_patterns'][-1]['id']
        subprocess.run([sys.executable, str(test_lab.APP / 'orbit.py'), '--observe-shell', '127', '0'],
                       input='mkidr work/scratch', text=True, capture_output=True, cwd=self.root,
                       env=dict(self.env, ORBIT_OBSERVED_COMMAND_KIND='missing'), check=True)
        repeated = json.loads(self.report.read_text())['input_patterns'][-1]
        self.assertEqual(repeated['id'], first_id)
        self.assertEqual(repeated['attempts'], 2)
        self.assertEqual(repeated['episodes'], 1)

    def test_binding_mismatch_and_contract_drift_are_rejected(self):
        self.bind()
        self.context['student_id'] = 'different'
        self.manifest.write_text(json.dumps(self.context))
        self.assertIn('不能重新分配', self.cli('prepare', ok=False))
        self.context['contract_hash'] = '0' * 64
        self.manifest.write_text(json.dumps(self.context))
        with self.assertRaisesRegex(ValueError, '契约不匹配'):
            pliac_bridge.binding(self.manifest)

    def test_export_failure_does_not_lose_native_progress(self):
        self.bind()
        state = self.state()
        state['platform_binding']['report_path'] = str(Path(self.temp.name) / 'missing' / 'telemetry.json')
        with patch('sys.stderr'):
            pliac_bridge.publish_safely(state)
        self.cli('hint')
        self.assertEqual(self.state()['hints']['1'], 1)


if __name__ == '__main__':
    unittest.main()
