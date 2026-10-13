"""Maintenance-only solutions in isolated directories, never a learner helper."""
import gzip
import io
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import assessment_tasks as tasks
import knowledge


@unittest.skipUnless(os.name == 'posix' and Path('/proc/self/stat').exists(), 'Linux / WSL required')
class AssessmentTasksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='linuxlab-assessment-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        # Our test runner stands in for the shell that owns child processes.
        parent_patch = patch.object(tasks.os, 'getppid', return_value=os.getpid())
        parent_patch.start()
        self.addCleanup(parent_patch.stop)

    def create(self, task_id):
        root = self.base / task_id
        manifest = tasks.create(task_id, root, 'repeatable-test-seed')
        return root, manifest

    def shell(self, root, command):
        subprocess.run(['bash', '-c', 'set -e\n' + command], cwd=root, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def solve(self, root, manifest):
        topic, family = manifest['topic'], manifest['family']
        answer, cwd = '', root
        token = tasks._digest(f"{manifest['id']}:repeatable-test-seed")[:12]
        q = shlex.quote
        if topic == 'paths':
            target = next(item['path'] for item in manifest['private']['checks'] if item['kind'] == 'content')
            cwd = (root / target).parent
            self.shell(root, f'cd {q(str(cwd))}\ncat code.txt > /dev/null')
            answer = (root / target).read_text().strip()
        elif topic == 'hidden':
            self.shell(root, 'ls -a > /dev/null')
            target = {'file': '.access', 'directory': '.vault/code.txt', 'contrast': '.record'}[family]
            answer = (root / target).read_text().strip()
        elif topic == 'mkdir':
            self.shell(root, {'parents': 'mkdir -p course/week1/notes',
                              'siblings': 'mkdir existing/notes existing/reports',
                              'space': "mkdir -p 'project files/day 1/notes'"}[family])
        elif topic == 'copy':
            self.shell(root, {'new_target': 'cp -a source backup',
                              'existing_target': 'cp -a source/. backup/',
                              'selective': 'mkdir backup\ncp -a source/.settings source/sub backup/'}[family])
        elif topic == 'move':
            self.shell(root, {'rename': 'mv draft.txt final.txt',
                              'existing_directory': 'mv draft.txt archive/',
                              'directory_rename': 'mv draft archive/final'}[family])
        elif topic == 'glob':
            self.shell(root, {'suffix': 'rm -- *.tmp', 'single_digit': 'rm -- part-[0-9].txt',
                              'zero_width': 'rm -- note-*.txt'}[family])
        elif topic == 'archive_read':
            self.shell(root, {'nested': 'tar -xzf input.tar.gz -C restore',
                              'strip': 'tar -xzf input.tar.gz -C restore --strip-components=1',
                              'selective': 'tar -xzf input.tar.gz -C restore bundle/docs/readme.txt'}[family])
        elif topic == 'logs':
            self.shell(root, 'tail -n 10 events.log > /dev/null')
            lines = (root / 'events.log').read_text().splitlines()
            lines = [line for line in lines if ' READY ' in line]
            if family == 'filtered':
                lines = [line for line in lines if 'device=A ' in line]
            if family == 'timestamp':
                lines.sort()
            answer = lines[-1].split('value=')[1]
        elif topic == 'config':
            target = 'active/app.conf' if family == 'active_file' else 'app.conf'
            self.shell(root, f'cp requirements.txt {q(target)}')
        elif topic == 'editing':
            if not shutil.which('vim'):
                self.skipTest('Vim required for actual editor assessment tests')
            if family == 'replace':
                self.shell(root, f"vim -Nu NONE -n -es notes.txt -c {q('call setline(2, \"' + token + '\")')} -c wq")
            else:
                if family == 'discard':
                    self.shell(root, "vim -Nu NONE -n -es notes.txt -c 'normal! ggitemporary' -c 'q!' ")
                self.shell(root, f"vim -Nu NONE -n -es notes.txt -c {q('call append(line("$"), "' + token + '")')} -c wq")
            answer = {'append': 'normal', 'replace': ':w', 'discard': 'discard'}[family]
        elif topic == 'permissions':
            self.shell(root, {'private': 'chmod 600 secret.conf',
                              'shared': 'chmod 640 shared/report.txt\nchmod 750 shared',
                              'executable': 'chmod 750 runner.sh\nchmod 640 runner.conf'}[family])
        elif topic == 'execution':
            self.shell(root, {'direct': 'chmod u+x run.sh\n./run.sh',
                              'argument': 'chmod u+x run.sh\n./run.sh "$(cat argument.txt)"',
                              'working_directory': 'chmod u+x bin/run.sh\ncd run\n../bin/run.sh'}[family])
        elif topic == 'process':
            if family == 'shell_identity':
                info = tasks._proc(os.getpid())
                answer = f"{info['pid']} {info['name']}"
            else:
                child = subprocess.Popen(['sleep', '120' if family == 'child_identity' else '180'])
                self.addCleanup(self.cleanup_process, child)
                # Reading stdout synchronizes a ps observation after exec.
                subprocess.run(['ps', '-o', 'pid,ppid,state,comm', '-p', str(child.pid)], check=True,
                               stdout=subprocess.PIPE)
                answer = f'{child.pid} {os.getpid()}' if family == 'child_identity' else f'{child.pid} S'
        elif topic == 'archive_build':
            self.shell(root, 'tar -czf delivery.tar.gz package' if family == 'wrapper'
                       else 'tar -czf delivery.tar.gz -C package .')
        elif topic == 'integrity':
            self.shell(root, {'backup': 'cp -a original backup',
                              'restore': 'mkdir recovery\ncp work/data.txt recovery/data.txt\ncp backup/data.txt work/data.txt',
                              'compare': 'cmp reference.txt versions/two.txt\ncp versions/two.txt work.txt'}[family])
        return answer, cwd

    @staticmethod
    def cleanup_process(child):
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=5)

    def test_catalog_covers_every_concept_with_three_families(self):
        catalog = tasks.catalog()
        self.assertEqual(len(catalog), 45)
        self.assertEqual({item['topic'] for item in catalog}, set(knowledge.CONCEPTS))
        self.assertEqual(len({item['id'] for item in catalog}), len(catalog))
        for topic in knowledge.CONCEPTS:
            self.assertEqual(len({item['family'] for item in catalog if item['topic'] == topic}), 3)
        self.assertTrue(all('private' not in item and item['version'] == 1 for item in catalog))

    def test_every_task_starts_incomplete_and_accepts_a_real_solution(self):
        for task in tasks.catalog():
            with self.subTest(task=task['id']):
                root, manifest = self.create(task['id'])
                initial = tasks.evaluate(manifest, root, cwd=root)
                self.assertFalse(initial['passed'])
                self.assertFalse(initial['technical_error'])
                answer, cwd = self.solve(root, manifest)
                result = tasks.evaluate(manifest, root, answer=answer, cwd=cwd)
                self.assertTrue(result['passed'], result)
                self.assertFalse(result['technical_error'])
                self.assertNotIn('private', result)

    def test_creation_does_not_overwrite_existing_work(self):
        root, manifest = self.create('mkdir.parents.v1')
        original = (root / 'keep.txt').read_bytes()
        with self.assertRaises(ValueError):
            tasks.create('mkdir.parents.v1', root, 'new-seed')
        self.assertEqual((root / 'keep.txt').read_bytes(), original)
        with self.assertRaises(ValueError):
            tasks.create('unknown', self.base / 'unknown', 'seed')

    def test_seed_changes_observations_but_is_reproducible(self):
        left = self.base / 'left'
        right = self.base / 'right'
        other = self.base / 'other'
        one = tasks.create('hidden.file.v1', left, 'same')
        two = tasks.create('hidden.file.v1', right, 'same')
        three = tasks.create('hidden.file.v1', other, 'different')
        self.assertEqual(one['private'], two['private'])
        self.assertNotEqual(one['private'], three['private'])

    def test_rejects_symbolic_hard_links_and_fifo_without_reading_them(self):
        outside = self.base / 'outside.txt'
        outside.write_text('private external data')
        for kind in ['symlink', 'hardlink', 'fifo']:
            with self.subTest(kind=kind):
                root = self.base / kind
                manifest = tasks.create('mkdir.parents.v1', root, 'safe')
                victim = root / 'unsafe'
                if kind == 'symlink':
                    victim.symlink_to(outside)
                elif kind == 'hardlink':
                    os.link(outside, victim)
                else:
                    os.mkfifo(victim)
                result = tasks.evaluate(manifest, root)
                self.assertFalse(result['passed'])
                self.assertNotIn('private external data', str(result))
                victim.unlink()
        self.assertEqual(outside.read_text(), 'private external data')

    def test_create_rejects_symlink_root_and_symlink_ancestor(self):
        real = self.base / 'real'
        real.mkdir()
        link = self.base / 'link'
        link.symlink_to(real, target_is_directory=True)
        for target in [link, link / 'child']:
            with self.assertRaises(ValueError):
                tasks.create('mkdir.parents.v1', target, 'seed')

    def test_wrong_root_or_version_is_technical_failure(self):
        root, manifest = self.create('hidden.file.v1')
        other = self.base / 'other'
        other.mkdir()
        self.assertTrue(tasks.evaluate(manifest, other)['technical_error'])
        manifest['schema_version'] = 999
        self.assertTrue(tasks.evaluate(manifest, root)['technical_error'])

    def test_bounded_workspace_and_read_only_grading(self):
        root, manifest = self.create('hidden.file.v1')
        before = {path.name: path.read_bytes() for path in root.iterdir()}
        result = tasks.evaluate(manifest, root, 'wrong')
        self.assertFalse(result['passed'])
        self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, before)
        self.assertNotIn((root / '.access').read_text().strip(), result['feedback'])
        with (root / 'oversize').open('wb') as handle:
            handle.truncate(tasks.MAX_FILE + 1)
        self.assertFalse(tasks.evaluate(manifest, root)['passed'])

    def test_archive_blocks_traversal_links_duplicates_and_compression_bombs(self):
        root, manifest = self.create('archive_build.contents.v1')
        self.solve(root, manifest)
        self.assertTrue(tasks.evaluate(manifest, root)['passed'])
        good = (root / 'delivery.tar.gz').read_bytes()
        for kind in ['traversal', 'symlink', 'duplicate', 'extra', 'absolute']:
            with self.subTest(kind=kind):
                raw = io.BytesIO(gzip.decompress(good))
                out = io.BytesIO()
                with tarfile.open(fileobj=raw, mode='r:') as source, tarfile.open(fileobj=out, mode='w:gz') as target:
                    for item in source:
                        target.addfile(item, source.extractfile(item) if item.isfile() else None)
                    name = {'traversal': '../outside', 'symlink': 'link', 'duplicate': 'report.txt',
                            'extra': 'unrequested', 'absolute': '/tmp/outside'}[kind]
                    extra = tarfile.TarInfo(name)
                    if kind == 'symlink':
                        extra.type, extra.linkname = tarfile.SYMTYPE, '/etc/passwd'
                    target.addfile(extra)
                (root / 'delivery.tar.gz').write_bytes(out.getvalue())
                self.assertFalse(tasks.evaluate(manifest, root)['passed'])
        (root / 'delivery.tar.gz').write_bytes(gzip.compress(b'0' * (tasks.MAX_TOTAL + 1)))
        self.assertFalse(tasks.evaluate(manifest, root)['passed'])
        self.assertFalse((self.base / 'outside').exists())

    def test_completed_artifact_does_not_accept_wrong_understanding_answer(self):
        root, manifest = self.create('editing.append.v1')
        answer, cwd = self.solve(root, manifest)
        self.assertTrue(tasks.evaluate(manifest, root, answer, cwd)['passed'])
        self.assertFalse(tasks.evaluate(manifest, root, 'insert', cwd)['passed'])
        self.assertEqual(manifest['required_commands'], ['vim'])

    def test_dead_or_unrelated_process_is_rejected(self):
        root, manifest = self.create('process.child_identity.v1')
        child = subprocess.Popen(['sleep', '120'])
        child.terminate()
        child.wait(timeout=5)
        result = tasks.evaluate(manifest, root, f'{child.pid} {os.getpid()}')
        self.assertFalse(result['passed'])
        self.assertFalse(result['technical_error'])
        self.assertFalse(tasks.evaluate(manifest, root, f'{os.getpid()} {os.getppid()}')['passed'])

    def test_expired_or_replaced_terminal_is_technical_error(self):
        root, manifest = self.create('process.shell_identity.v1')
        child = subprocess.Popen(['sleep', '120'])
        manifest['private']['shell'] = tasks._proc(child.pid)
        child.terminate()
        child.wait(timeout=5)
        result = tasks.evaluate(manifest, root, '1 anything')
        self.assertFalse(result['passed'])
        self.assertTrue(result['technical_error'])
        self.assertIn('lab assess abandon', result['feedback'])
        manifest['private']['shell'] = tasks._proc(os.getpid())
        manifest['private']['shell']['started'] -= 1
        self.assertTrue(tasks.evaluate(manifest, root)['technical_error'])

    def test_switched_terminal_is_technical_error_and_top_is_allowed(self):
        root, manifest = self.create('process.shell_identity.v1')
        self.assertEqual(manifest['required_commands'], ['ps', 'top'])
        with patch.object(tasks.os, 'getppid', return_value=os.getpid() + 100000):
            result = tasks.evaluate(manifest, root)
        self.assertTrue(result['technical_error'])

    def test_execution_check_does_not_execute_modified_student_script(self):
        root, manifest = self.create('execution.direct.v1')
        (root / 'run.sh').write_text('#!/bin/sh\ntouch unexpected\n')
        result = tasks.evaluate(manifest, root)
        self.assertFalse(result['passed'])
        self.assertFalse((root / 'unexpected').exists())


if __name__ == '__main__':
    unittest.main()
