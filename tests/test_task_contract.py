"""The course contract is independent of theme prose and per-session secrets."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import knowledge
import orbit
import tasks


class TaskContractTest(unittest.TestCase):
    def make_session(self, folder, metadata):
        session = Path(folder) / 'session'
        session.mkdir()
        (session / 'station').mkdir()
        (session / 'station' / 'student-work.txt').write_text('keep this work\n', encoding='utf-8')
        state = {'format': orbit.MARKER, 'done': [1], **metadata}
        (session / 'state.json').write_text(json.dumps(state), encoding='utf-8')
        return session, state

    def session_files(self, session):
        return {str(path.relative_to(session)): path.read_bytes()
                for path in session.rglob('*') if path.is_file()}

    def test_contract_has_semantic_roles_and_consistent_dependencies(self):
        contract = tasks.generation_contract()
        self.assertEqual(contract['course_id'], 'linux-foundations')
        self.assertEqual(contract['version'], 1)
        self.assertEqual(tasks.task_ids(), (
            'locate', 'backup', 'organize', 'extract', 'interpret-log',
            'configure', 'permissions', 'process', 'deliver'))
        allowed = {'entry', 'workspace', 'originals', 'inbox', 'supplies', 'logs',
                   'evidence', 'service', 'roster', 'delivery', 'finale', 'metrics'}
        used = set()
        for index, item in enumerate(contract['tasks']):
            self.assertEqual(item['concepts'], knowledge.PHASE_CONCEPTS[index + 1])
            self.assertEqual(item['prerequisites'], [] if index == 0 else [tasks.task_ids()[index - 1]])
            self.assertTrue(item['goal'])
            self.assertTrue(item['story_relation'])
            self.assertTrue(item['evidence'])
            self.assertTrue(item['assets'])
            self.assertLessEqual(set(item['assets']), allowed)
            used.update(item['assets'])
        self.assertEqual(used, allowed)
        serialized = json.dumps(contract, ensure_ascii=False)
        for implementation_detail in ('blackbox', 'relay.conf', 'STATION=', 'MODE=',
                                      'SEAL-', 'LINK-', 'EVAC-', 'station_id'):
            self.assertNotIn(implementation_detail, serialized)

    def test_export_is_isolated_and_hash_tracks_exact_contract(self):
        original = tasks.generation_contract()
        digest = tasks.contract_hash()
        exported = tasks.generation_contract()
        exported['tasks'][0]['concepts'].append('not-a-concept')
        exported['tasks'][0]['evidence'][0] = 'modified'
        exported['tasks'][0]['assets'].clear()
        self.assertEqual(tasks.generation_contract(), original)
        self.assertEqual(tasks.contract_hash(), digest)
        canonical = json.dumps(original, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')).encode('utf-8')
        self.assertEqual(digest, hashlib.sha256(canonical).hexdigest())
        self.assertNotIn('not-a-concept', knowledge.PHASE_CONCEPTS[1])
        with patch.object(tasks, 'CONTRACT_VERSION', 2):
            self.assertNotEqual(tasks.contract_hash(), digest)

    def test_new_material_modes_and_legacy_requirements_remain_distinct(self):
        legacy = {'station_id': 'TEST-ONLY', 'cleanup_version': 1}
        current = dict(legacy, material_version=2)
        self.assertEqual(tasks.mode(legacy), 'rescue')
        self.assertEqual(tasks.mode(legacy, final=True), 'evacuate')
        self.assertEqual(tasks.mode(current), 'active')
        self.assertEqual(tasks.mode(current, final=True), 'deliver')
        for state in (legacy, current):
            self.assertEqual(tasks.mode(state, initial=True), 'maintenance')
            self.assertEqual(tasks.mode(state, initial=True, final=True), 'maintenance')
            self.assertIn('MODE=' + tasks.mode(state), tasks.requirements(6, state))
            self.assertIn('MODE=' + tasks.mode(state, final=True), tasks.requirements(9, state))
        self.assertNotIn('MODE=rescue', tasks.requirements(6, current))
        self.assertNotIn('MODE=evacuate', tasks.requirements(9, current))

    def test_load_rejects_each_recorded_contract_mismatch_without_writing(self):
        metadata = {'course_id': tasks.COURSE_ID,
                    'contract_version': tasks.CONTRACT_VERSION,
                    'contract_hash': tasks.contract_hash()}
        for field, value in (('course_id', 'different-course'),
                             ('contract_version', tasks.CONTRACT_VERSION + 1),
                             ('contract_version', True),
                             ('contract_hash', '0' * 64),
                             ('contract_hash', None)):
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as folder:
                session, _ = self.make_session(folder, {**metadata, field: value})
                before = self.session_files(session)
                with self.assertRaises(orbit.LabError) as caught:
                    orbit.load_session(session)
                self.assertEqual(caught.exception.code, 'contract_mismatch')
                self.assertIn(field, str(caught.exception))
                self.assertIn('对应的程序版本', str(caught.exception))
                self.assertIn('迁移存档', str(caught.exception))
                self.assertEqual(self.session_files(session), before)

    def test_load_accepts_matching_identifiers_and_identifier_free_legacy_round(self):
        metadata = {'course_id': tasks.COURSE_ID,
                    'contract_version': tasks.CONTRACT_VERSION,
                    'contract_hash': tasks.contract_hash()}
        for recorded in ({}, metadata, {'contract_hash': tasks.contract_hash()}):
            with self.subTest(recorded=recorded), tempfile.TemporaryDirectory() as folder:
                session, state = self.make_session(folder, recorded)
                before = self.session_files(session)
                self.assertEqual(orbit.load_session(session), state)
                self.assertEqual(self.session_files(session), before)

    def test_changed_current_contract_rejects_existing_round(self):
        metadata = {'course_id': tasks.COURSE_ID,
                    'contract_version': tasks.CONTRACT_VERSION,
                    'contract_hash': tasks.contract_hash()}
        with tempfile.TemporaryDirectory() as folder:
            session, _ = self.make_session(folder, metadata)
            before = self.session_files(session)
            # Version can remain unchanged accidentally; the hash still guards
            # against resuming with different task evidence or dependencies.
            with patch.object(tasks, 'contract_hash', return_value='f' * 64):
                with self.assertRaises(orbit.LabError) as caught:
                    orbit.load_session(session)
            self.assertEqual(caught.exception.code, 'contract_mismatch')
            self.assertEqual(self.session_files(session), before)


if __name__ == '__main__':
    unittest.main()
