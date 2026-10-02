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
    with zipfile.ZipFile(windows_package) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == {'orbit-lab/' + n for n in manifest['files']}
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(z.read('orbit-lab/' + name)).hexdigest() == digest, name
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
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        assert result.wasSuccessful(), 'Packaged artifact failed validation'
    record = {'package_sha256': manifest['sha256'], 'file_hashes_verified': len(manifest['files']),
              'windows_package_sha256': manifest['windows_sha256'],
              'packaged_integration_tests': names, 'passed': True,
              'elapsed_seconds': round(time.monotonic() - start, 3),
              'platform': sys.platform, 'python': sys.version.split()[0]}
    (ROOT / 'dist/validation.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
