"""Scene-independent task integration; walkthroughs are never shipped to students."""
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import unittest

import test_lab as fixtures

APP = fixtures.APP
import layout
import lessons
import orbit
import scenes
import tasks


class SceneIntegration(unittest.TestCase):
    setUp = fixtures.LabTest.setUp
    tearDown = fixtures.LabTest.tearDown
    cli = fixtures.LabTest.cli
    shell = fixtures.LabTest.shell
    state = fixtures.LabTest.state

    def custom_bundle(self):
        # This theme is built as ordinary JSON, with no entry in the scene registry.
        names = {
            name: ('.meal-' + name[1:] if name.startswith('.') else 'meal-' + name)
            for name in layout.BINDING_KEYS
        }
        return {
            'id': 'food-library',
            'title': '食谱图书馆',
            'description': '为社区厨房整理可复用的烹饪资料。',
            'background': '社区厨房准备开放食谱图书馆，你负责资料服务的整理和恢复。',
            'titles': ['找到阅览入口', '备份手写食谱', '整理借阅通知', '打开资料包',
                       '辨认最新安排', '配置借阅服务', '启动阅览终端', '查找巡检进程', '交付开放资料'],
            'introductions': [f'食谱图书馆第 {phase} 项准备：和志愿者完成本项资料工作。'
                              for phase in range(1, 10)],
            'rewards': [f'图书馆准备 {phase} 已完成' for phase in range(1, 10)],
            'ending': '社区厨房完成资料交接，食谱图书馆可以开始本次开放活动。',
            'bindings': names,
        }

    def write_bundle(self, bundle):
        path = Path(self.temp.name) / 'food-library.json'
        path.write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
        return path

    def new_round(self, source, launcher=False):
        if launcher:
            result = subprocess.run(
                ['bash', str(APP / 'start.sh'), '--new', '--scene', str(source)],
                input='exit\n', text=True, capture_output=True, env=self.env, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            pointer = json.loads((Path(self.temp.name) / 'current.json').read_text())
            self.session = Path(pointer['session'])
        else:
            output = self.cli('prepare', '--new', '--scene', str(source))
            self.session = Path(output.strip())
        self.root = self.session / 'station'
        self.env['ORBIT_HOME'] = str(self.session)
        self.s = self.state()

    def path(self, logical):
        return self.root / layout.rel(self.s, logical)

    def task_shell(self, command, cwd=None):
        return self.shell(layout.text(self.s, command), cwd=self.path(cwd) if cwd else None)

    def solve_to(self, phase):
        for n in range(len(self.state()['done']) + 1, phase + 1):
            if n == 1:
                self.task_shell('ls -a airlock; mkdir -p work/evidence')
                self.cli('check', self.s['beacon'], cwd=self.path('airlock'))
            elif n == 2:
                self.task_shell('cp -a blackbox work/backup')
                self.cli('check')
            elif n == 3:
                self.task_shell('ls inbox/decoy-*.tmp; mv inbox/route.pending work/evidence/route.txt; rm inbox/decoy-*.tmp')
                self.cli('check')
            elif n == 4:
                self.task_shell('mkdir -p work/recovered; tar -tzf supplies/rescue.tar.gz; tar -xzf supplies/rescue.tar.gz -C work/recovered; cat work/recovered/manifest.txt')
                self.cli('check', self.s['seal'])
            elif n == 5:
                output = self.task_shell('cat work/evidence/route.txt; tail -n 5 logs/comms.log')
                self.assertIn(self.s['code'], output)
                self.cli('check', self.s['code'])
            elif n == 6:
                script = (f"%s/MODE=maintenance/MODE={tasks.mode(self.s)}/\n"
                          f"%s/CHANNEL=000/CHANNEL={self.s['channel']}/\n"
                          f"%s/AUTH=UNSET/AUTH={self.s['code']}/\nwq\n")
                result = subprocess.run(
                    ['vim', '-Nu', 'NONE', '-n', '-es', layout.rel(self.s, 'work/recovered/relay.conf')],
                    input=script, text=True, cwd=self.root, env=self.env,
                    capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.cli('check')
            elif n == 7:
                self.task_shell('chmod 700 relay.sh; chmod 600 relay.conf; ./relay.sh',
                                cwd='work/recovered')
                self.cli('check')
            elif n == 8:
                self.cli('load')
                output = self.shell('top -b -n 1 -w 180')
                pid = str(self.state()['worker']['pid'])
                probe = [line for line in output.splitlines()
                         if 'station-pulse' in line and line.split()[0] == pid]
                self.assertEqual(len(probe), 1, output)
                self.cli('check', probe[0].split()[0])

    def final_files(self):
        self.task_shell('tar -xzf finale/capsule.tar.gz -C work; mv work/dispatch/relay.conf.draft work/dispatch/relay.conf; rm work/dispatch/discard.tmp; cp inbox/crew.csv work/recovered/receipt.txt work/dispatch/')
        self.path('work/dispatch/relay.conf').write_text(orbit.cfg(self.s, final=True))
        self.task_shell('chmod 600 work/dispatch/relay.conf')
        self.pack()

    def pack(self):
        self.task_shell('tar -czf rescue.tar.gz dispatch', cwd='work')

    def assert_completed(self):
        output = self.cli('check')
        self.assertIn(scenes.get(self.s)['ending'], output)
        self.assertEqual(self.state()['done'], list(range(1, 10)))
        report = json.loads((self.session / 'report.json').read_text())
        self.assertTrue(report['completed'])
        self.assertEqual(report['scene'], self.s['scene'])
        with tarfile.open(self.path('work/rescue.tar.gz')) as archive:
            files = {member.name for member in archive if member.isfile()}
        expected = {layout.rel(self.s, 'dispatch/' + name)
                    for name in ('relay.conf', 'crew.csv', 'receipt.txt')}
        self.assertEqual(files, expected)

    def test_anime_full_real_command_walkthrough(self):
        self.new_round('anime')
        self.assertTrue(self.path('airlock').is_dir())
        self.assertNotEqual(self.path('airlock').name, 'airlock')
        self.assertFalse((self.root / 'airlock').exists())
        self.cli('check', 'wrong', cwd=self.path('airlock'), ok=False)
        self.assertEqual(self.state()['events'][-1]['diagnosis']['code'], 'directory')
        self.solve_to(1)
        self.task_shell('cp -a blackbox work/backup; rm work/backup/.integrity')
        output = self.cli('check', ok=False)
        self.assertIn(layout.rel(self.s, '.integrity'), output)
        self.assertEqual(self.state()['events'][-1]['diagnosis']['code'], 'backup')
        self.task_shell('cp blackbox/.integrity work/backup/.integrity')
        self.cli('check')
        self.solve_to(8)
        self.final_files()
        self.assert_completed()

    def test_arbitrary_json_full_walkthrough_and_archive_permissions(self):
        bundle = self.custom_bundle()
        source = self.write_bundle(bundle)
        self.assertNotIn(bundle['id'], scenes.BUILTIN_SCENES)
        # The real launcher accepts a plain local JSON without an API config.
        self.new_round(source, launcher=True)
        self.assertEqual(self.s['scene_bundle'], bundle)
        self.assertEqual(self.s['asset_bindings'], bundle['bindings'])
        self.assertFalse((self.root / 'blackbox').exists())
        self.assertTrue(self.path('blackbox/boot.log').is_file())
        self.solve_to(8)
        self.final_files()
        self.task_shell('chmod 777 work/dispatch/relay.conf')
        self.pack()
        self.cli('check', ok=False)
        self.assertEqual(self.state()['done'], list(range(1, 9)))
        self.task_shell('chmod 600 work/dispatch/relay.conf')
        # Fixing the source alone must still leave the bad archive rejected.
        self.cli('check', ok=False)
        self.pack()
        self.assert_completed()

    def test_scene_snapshot_switch_repair_and_resume(self):
        original_bundle = self.custom_bundle()
        source = self.write_bundle(original_bundle)
        self.new_round(source)
        source.unlink()
        self.assertEqual(self.cli('prepare').strip(), str(self.session))
        self.assertIn(original_bundle['background'], self.cli())
        self.solve_to(2)
        current_paths = sorted(str(path.relative_to(self.root)) for path in self.root.rglob('*'))
        original_roster = self.path('inbox/crew.csv').read_bytes()
        self.cli('scene', 'ocean')
        changed = self.state()
        self.assertEqual(changed['done'], [1, 2])
        self.assertEqual(changed['asset_bindings'], original_bundle['bindings'])
        self.assertEqual(sorted(str(path.relative_to(self.root)) for path in self.root.rglob('*')), current_paths)
        self.assertEqual(self.path('inbox/crew.csv').read_bytes(), original_roster)
        self.assertIn(scenes.load('ocean')['title'], self.cli())
        self.task_shell('rm inbox/crew.csv')
        self.cli('check', ok=False)
        self.cli('repair')
        self.assertEqual(self.path('inbox/crew.csv').read_bytes(), original_roster)
        self.assertEqual(self.state()['asset_bindings'], original_bundle['bindings'])
        self.assertEqual(self.state()['done'], [1, 2])
        self.assertEqual(self.state()['scene'], 'ocean')
        self.assertEqual(self.cli('prepare').strip(), str(self.session))
        self.assertEqual(self.state()['asset_bindings'], original_bundle['bindings'])
        self.solve_to(3)
        self.assertEqual(self.state()['done'], [1, 2, 3])

    def test_task_contract_shared_and_no_story_template_leak(self):
        bundle = self.custom_bundle()
        # Canonical-looking words in narrative are prose, never rename targets.
        bundle['introductions'][0] += ' 故事里的 airlock 只是角色提及的原词。'
        custom = {'station_id': 'TEST-CONTRACT', 'cleanup_version': 1}
        scenes.initialize(custom, bundle)
        baseline = dict(station_id='TEST-CONTRACT', cleanup_version=1, scene='space')
        for phase in range(1, 10):
            with self.subTest(phase=phase):
                technical = tasks.requirements(phase, custom)
                self.assertEqual(technical, layout.text(custom, tasks.requirements(phase, baseline)))
                rendered = lessons.brief(phase, custom)
                self.assertIn(bundle['introductions'][phase - 1], rendered)
                self.assertIn(technical, rendered)
                for obsolete in ('空间站', '救援舱', '气闸', '黑匣子', '船员', '{station}'):
                    self.assertNotIn(obsolete, rendered)
                for canonical in layout.BINDING_KEYS:
                    exact = r'(?<![A-Za-z0-9_.-])' + re.escape(canonical) + r'(?![A-Za-z0-9_.-])'
                    self.assertIsNone(re.search(exact, technical), canonical)
        self.assertIn('故事里的 airlock', lessons.brief(1, custom))
        self.assertIn('MODE=rescue', tasks.requirements(6, custom))
        self.assertIn('MODE=evacuate', tasks.requirements(9, custom))

    def test_mapped_paths_keep_observation_roles_and_diagnosis(self):
        self.new_round('anime')
        self.solve_to(1)
        self.cli('tracking', 'on')
        self.task_shell('mkdir -p work/backup')
        command = layout.text(self.s, 'cp -r blackbox/* work/backup')
        self.shell(command)
        observed = subprocess.run(
            [sys.executable, str(APP / 'orbit.py'), '--observe-shell', '0', '0'],
            input='1 ' + command, text=True, cwd=self.root, env=self.env,
            capture_output=True, timeout=10)
        self.assertEqual(observed.returncode, 0, observed.stderr)
        self.cli('check', ok=False)
        state = self.state()
        event = state['shell_observations'][-1]
        self.assertEqual(event['operand_roles'], ['original', 'backup'])
        self.assertFalse(event['facts']['backup_hidden_present'])
        self.assertEqual(state['events'][-1]['diagnosis']['concepts'][0], 'hidden')
        self.assertNotIn(command, json.dumps(state))

    def test_legacy_round_keeps_original_material_after_story_switch(self):
        # Recreate old metadata/material only in this disposable fixture.
        legacy = self.state()
        for key in ('task_schema', 'asset_bindings', 'scene_bundle', 'scene'):
            legacy.pop(key, None)
        self.path('inbox/route.pending').write_text(orbit.route(legacy), encoding='utf-8')
        orbit.atomic_json(self.session / 'state.json', legacy)
        self.s = legacy
        self.solve_to(2)
        self.cli('scene', 'ocean')
        self.assertNotIn('task_schema', self.state())
        self.solve_to(3)
        self.assertEqual(self.state()['done'], [1, 2, 3])

    def test_compiled_blueprint_material_and_native_path_workflow(self):
        from test_scene_blueprint import example_blueprint
        from scene_blueprint import compile_blueprint

        compiled = compile_blueprint(example_blueprint('garden'))
        self.new_round(self.write_bundle(compiled))
        self.assertEqual(self.s['material_version'], 2)
        self.assertEqual(self.s['contract_hash'], tasks.contract_hash())
        # Literal paths and native commands independently check the compiler binding.
        self.assertTrue((self.root / 'entry-garden-area').is_dir())
        original = self.root / 'originals-garden-source/originals-garden-events.log'
        self.assertNotIn('BLACKBOX', original.read_text())
        self.shell('mkdir -p workspace-garden-area/evidence-garden-records')
        self.cli('check', self.s['beacon'], cwd=self.root / 'entry-garden-area')
        self.shell('cp -a originals-garden-source workspace-garden-area/originals-garden-backup')
        self.cli('check')
        self.solve_to(8)
        self.assertIn('MODE=active', self.path('work/recovered/relay.conf').read_text())
        self.assertNotIn('rescue window', self.path('finale/final.log').read_text())
        self.final_files()
        self.assertIn('MODE=deliver', self.path('work/dispatch/relay.conf').read_text())
        self.assert_completed()


class SceneSchemaTest(unittest.TestCase):
    custom_bundle = SceneIntegration.custom_bundle

    def test_bindings_reject_conflicts_traversal_and_hidden_changes(self):
        original = self.custom_bundle()
        cases = [
            ('work', original['bindings']['airlock']),
            ('airlock', '../outside'),
            ('airlock', '..\\outside'),
            ('airlock', '/absolute'),
            ('airlock', 'folder/child'),
            ('airlock', 'folder;touch-file'),
            ('airlock', '$(touch-file)'),
            ('airlock', '-option'),
            ('airlock', '.hidden-room'),
            ('.integrity', 'visible-check'),
            ('relay.conf', 'relay.txt'),
            ('relay.conf.draft', 'relay.draft'),
            ('airlock', 'docs'),
            ('airlock', '.beacon-1111'),
            ('discard.tmp', 'decoy-new.tmp'),
        ]
        for key, invalid in cases:
            with self.subTest(key=key, invalid=invalid):
                bundle = copy.deepcopy(original)
                bundle['bindings'][key] = invalid
                with self.assertRaises(ValueError):
                    scenes.validate_bundle(bundle)
        for change in ('missing', 'extra'):
            with self.subTest(change=change):
                bundle = copy.deepcopy(original)
                if change == 'missing':
                    bundle['bindings'].pop('airlock')
                else:
                    bundle['bindings']['unrecognized'] = 'anything'
                with self.assertRaises(ValueError):
                    scenes.validate_bundle(bundle)

    def test_narrative_requires_nine_stages_and_plain_visible_text(self):
        original = self.custom_bundle()
        for field in ('titles', 'introductions', 'rewards'):
            for count in (0, 8, 10):
                with self.subTest(field=field, count=count):
                    bundle = copy.deepcopy(original)
                    bundle[field] = ['stage'] * count
                    with self.assertRaises(ValueError):
                        scenes.validate_bundle(bundle)
            for invalid in ('', '   ', 7, {'text': 'nested'}, 'visible\x1b[2J', 'hidden\u200btext'):
                with self.subTest(field=field, invalid=invalid):
                    bundle = copy.deepcopy(original)
                    bundle[field][3] = invalid
                    with self.assertRaises(ValueError):
                        scenes.validate_bundle(bundle)
        for control in ('\x00', '\x1b', '\u202e', '\n', '\t'):
            bundle = copy.deepcopy(original)
            bundle['background'] += control
            with self.subTest(control=repr(control)), self.assertRaises(ValueError):
                scenes.validate_bundle(bundle)
        for change in ('missing', 'extra'):
            bundle = copy.deepcopy(original)
            if change == 'missing':
                bundle.pop('ending')
            else:
                bundle['commands'] = ['anything']
            with self.subTest(change=change), self.assertRaises(ValueError):
                scenes.validate_bundle(bundle)

    def test_invalid_scene_switch_does_not_change_state(self):
        import tempfile

        state = {'station_id': 'TEST-ONLY', 'done': [1, 2]}
        scenes.initialize(state, self.custom_bundle())
        before = copy.deepcopy(state)
        invalid = self.custom_bundle()
        invalid['bindings']['airlock'] = '../outside'
        with tempfile.TemporaryDirectory(prefix='orbit-scene-invalid-') as temporary:
            source = Path(temporary) / 'invalid.json'
            source.write_text(json.dumps(invalid), encoding='utf-8')
            with self.assertRaises(ValueError):
                scenes.choose(state, str(source))
        self.assertEqual(state, before)


if __name__ == '__main__':
    unittest.main()
