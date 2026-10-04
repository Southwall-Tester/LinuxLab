"""Validate the built artifact in a fresh Linux directory, then exercise it."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / 'dist/manifest.json').read_text())
    package = ROOT / 'dist' / manifest['package']
    assert hashlib.sha256(package.read_bytes()).hexdigest() == manifest['sha256']
    windows_package = ROOT / 'dist' / manifest['windows_package']
    assert hashlib.sha256(windows_package.read_bytes()).hexdigest() == manifest['windows_sha256']
    student_rules = (ROOT / 'docs/STUDENT-AGENTS.md').read_bytes()
    assert student_rules != (ROOT / 'AGENTS.md').read_bytes()
    with zipfile.ZipFile(windows_package) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == {'orbit-lab/' + n for n in manifest['files']}
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(z.read('orbit-lab/' + name)).hexdigest() == digest, name
        assert z.read('orbit-lab/AGENTS.md') == student_rules
        assert z.read('orbit-lab/docs/STUDENT-AGENTS.md') == student_rules
        assert not any('ai.local' in name or 'learning-notebook' in name for name in z.namelist())
        example = json.loads(z.read('orbit-lab/ai.example.json'))
        assert example['enabled'] is False and example['api_key'] == ''
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='orbit-handout-') as temp:
        dest = Path(temp)
        with tarfile.open(package) as tar:
            members = list(tar)
            assert {m.name for m in members} == {'orbit-lab/' + n for n in manifest['files']}
            for m in members:
                assert m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts
                p = dest / m.name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(tar.extractfile(m).read())
                p.chmod(m.mode)
        app = dest / 'orbit-lab'
        for name, digest in manifest['files'].items():
            assert hashlib.sha256((app / name).read_bytes()).hexdigest() == digest, name
        assert not (app / 'tests').exists()
        assert (app / 'AGENTS.md').read_bytes() == student_rules
        assert (app / 'docs/STUDENT-AGENTS.md').read_bytes() == student_rules
        subprocess.run(['bash', str(app / 'setup.sh'), '--check'], check=True)
        subprocess.run(['bash', str(app / 'start.sh'), '--doctor'], check=True)
        # Run selected integration scenarios against the extracted executable code.
        sys.path.insert(0, str(app))
        __import__('orbit')
        spec = importlib.util.spec_from_file_location('handout_tests', ROOT / 'tests/test_lab.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.APP = app
        names = ['test_full_real_command_walkthrough_and_resume',
                 'test_lab_input_errors_are_friendly_and_preserve_session',
                 'test_shell_unknown_commands_suggest_without_execution',
                 'test_notes_available_anywhere_without_progress_changes',
                 'test_glob_cleanup_selection_and_overbroad_patterns',
                 'test_legacy_cleanup_session_resumes_without_new_requirements',
                 'test_real_interactive_launcher_vim_and_resume',
                 'test_tutor_rules_exist_and_refresh_on_resume']
        suite = unittest.TestSuite(module.LabTest(name) for name in names)
        # Exercise the installed handout's teaching code as well as the core lab.
        sys.path.insert(0, str(ROOT / 'tests'))
        import test_lab as fixtures
        fixtures.APP = app
        import test_teaching
        test_teaching.APP = app
        teaching_names = ['test_nine_phase_diagnostics_not_just_paths',
                          'test_tutor_review_resume_and_repair_preserve_evidence',
                          'test_real_shell_trace_changes_diagnosis_without_recording_raw_values',
                          'test_scene_switch_preserves_files_and_assessment',
                          'test_missing_config_falls_back_without_executing_question']
        suite.addTests(test_teaching.TeachingIntegration(name) for name in teaching_names)
        import test_scenes
        test_scenes.APP = app
        scene_names = ['test_anime_full_real_command_walkthrough',
                       'test_arbitrary_json_full_walkthrough_and_archive_permissions',
                       'test_compiled_blueprint_material_and_native_path_workflow',
                       'test_scene_snapshot_switch_repair_and_resume']
        suite.addTests(test_scenes.SceneIntegration(name) for name in scene_names)
        import test_scene_onboarding
        test_scene_onboarding.APP = app
        onboarding_names = ['test_real_launcher_interviews_generates_then_resumes_without_api',
                            'test_failed_new_generation_preserves_existing_round_and_pointer']
        suite.addTests(test_scene_onboarding.SceneOnboardingTest(name) for name in onboarding_names)
        import test_error_tracking
        test_error_tracking.APP = app
        tracking_names = ['test_new_round_enables_tracking_with_marker',
                          'test_pty_repeated_typo_resolution_and_recurrence',
                          'test_repeated_identical_checks_preserve_attempts_but_count_one_problem']
        suite.addTests(test_error_tracking.ErrorTrackingIntegration(name) for name in tracking_names)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        assert result.wasSuccessful(), 'Packaged artifact failed validation'
    record = {'package_sha256': manifest['sha256'], 'file_hashes_verified': len(manifest['files']),
              'windows_package_sha256': manifest['windows_sha256'],
              'packaged_integration_tests': names, 'passed': True,
              'packaged_teaching_tests': teaching_names,
              'packaged_scene_tests': scene_names, 'packaged_onboarding_tests': onboarding_names,
              'packaged_tracking_tests': tracking_names,
              'elapsed_seconds': round(time.monotonic() - start, 3),
              'platform': sys.platform, 'python': sys.version.split()[0]}
    (ROOT / 'dist/validation.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
