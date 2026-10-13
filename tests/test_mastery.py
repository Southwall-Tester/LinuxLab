"""Probability, evidence hygiene and teaching decisions use isolated profiles."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knowledge import CONCEPTS
import mastery


BASE = datetime(2026, 10, 13, 10, tzinfo=timezone.utc)


def evidence(number, **changes):
    event = {
        'id': 'assessment:' + str(number), 'attempt_id': str(number),
        'topic': 'copy', 'task_id': 'copy-' + str(number),
        'family': 'structure-' + str(number), 'at': BASE.isoformat(),
        'passed': True, 'independent': True, 'observed': True,
        'technical_error': False, 'kind': 'assessment',
        'contract_version': 1, 'session_id': 'isolated-test',
        'checks': [{'id': 'result', 'passed': True}],
    }
    event.update(changes)
    return event


def task(number, **changes):
    item = {'id': 'task-' + str(number), 'topic': 'copy',
            'family': 'structure-' + str(number), 'version': 1,
            'duration_seconds': 60, 'slip': .05, 'guess': .20,
            'objectives': ['copy-structure']}
    item.update(changes)
    return item


class MasteryPolicyTest(unittest.TestCase):
    def setUp(self):
        self.profile = mastery.new_profile()

    def summary(self, at=BASE):
        return mastery.summarize(self.profile, at)['copy']

    def passes(self, count=3):
        for number in range(count):
            mastery.record(self.profile, evidence(number))

    def test_cold_start_covers_all_concepts_and_requests_placement(self):
        report = mastery.summarize(self.profile, BASE)
        self.assertEqual(set(report), set(CONCEPTS))
        result = report['copy']
        self.assertEqual(result['p_mastery'], .3)
        self.assertEqual(result['status'], 'needs_learning')
        self.assertEqual(result['decision'], 'placement_check')
        self.assertEqual(result['evidence_ids'], [])
        self.assertIsNone(result['next_review_at'])
        self.assertEqual(result['origin'], 'bayesian_policy')
        self.assertFalse(result['human_reviewed'])

    def test_three_independent_structures_match_public_numeric_example(self):
        expected = (.6705882352941176, .906276150627615, .9786920332936981)
        for number in range(3):
            mastery.record(self.profile, evidence(number,
                at=(BASE + timedelta(minutes=number)).isoformat()))
            result = self.summary(BASE + timedelta(hours=1))
            self.assertAlmostEqual(result['p_mastery'], expected[number], places=7)
        self.assertEqual(result['status'], 'mastered')
        self.assertEqual(result['decision'], 'advance')
        self.assertAlmostEqual(result['p_next_success'], .9340190249702736, places=7)
        self.assertEqual(len(result['passed_families']), 3)

    def test_idempotence_conflict_and_caller_mutation(self):
        original = evidence(1)
        self.assertTrue(mastery.record(self.profile, original))
        snapshot = deepcopy(self.profile)
        self.assertFalse(mastery.record(self.profile, original))
        self.assertEqual(snapshot, self.profile)
        original['checks'][0]['passed'] = False
        self.assertTrue(self.profile['events'][0]['checks'][0]['passed'])
        with self.assertRaisesRegex(ValueError, 'different payload'):
            mastery.record(self.profile, original)
        self.assertEqual(snapshot, self.profile)

    def test_same_attempt_first_submission_only(self):
        mastery.record(self.profile, evidence(1, passed=False))
        first = self.summary()['p_mastery']
        mastery.record(self.profile, evidence(2, attempt_id='1'))
        result = self.summary()
        self.assertEqual(result['p_mastery'], first)
        self.assertEqual(len(result['evidence_ids']), 2)
        self.assertEqual(len(result['scored_evidence_ids']), 1)
        self.assertTrue(result['needs_reassessment'])

    def test_family_day_limits_credit_across_sessions_and_task_names(self):
        for number in range(10):
            mastery.record(self.profile, evidence(number, family='same-structure',
                session_id='session-' + str(number)))
        result = self.summary()
        self.assertAlmostEqual(result['p_mastery'], .6705882352941176)
        self.assertEqual(result['passed_families'], ['same-structure'])
        self.assertEqual(len(result['scored_evidence_ids']), 1)
        self.assertNotEqual(result['status'], 'mastered')

    def test_different_days_same_family_cannot_satisfy_structure_gate(self):
        for day in range(4):
            mastery.record(self.profile, evidence(day, family='one-structure',
                at=(BASE + timedelta(days=day)).isoformat()))
        result = self.summary(BASE + timedelta(days=3))
        self.assertGreaterEqual(result['p_mastery'], .95)
        self.assertEqual(result['status'], 'ready_to_check')
        self.assertEqual(len(result['passed_families']), 1)
        mastery.record(self.profile, evidence('new-structure',
            at=(BASE + timedelta(days=3)).isoformat()))
        self.assertEqual(self.summary(BASE + timedelta(days=3))['status'], 'mastered')

    def test_exact_threshold_confirms_until_the_next_decay_day(self):
        mastery.record(self.profile, evidence(1))
        prior = self.summary()['p_mastery']
        guess = prior * .95 * .05 / (.95 * (1 - prior))
        mastery.record(self.profile, evidence(2, guess=guess))
        self.assertAlmostEqual(self.summary()['p_mastery'], .95)
        self.assertEqual(self.summary()['status'], 'mastered')
        self.assertEqual(self.summary(BASE + timedelta(days=1))['status'], 'review_due')

    def test_only_completed_observed_training_updates_once_per_window(self):
        for number, changes in enumerate(({'passed': False}, {'observed': False},
                {'technical_error': True}, {}, {}, {})):
            mastery.record(self.profile, evidence(number, kind='training', **changes))
        self.assertAlmostEqual(self.summary()['p_mastery'], .37)
        self.assertEqual(self.summary()['status'], 'needs_learning')
        mastery.record(self.profile, evidence('independent'))
        before_training = self.summary()['p_mastery']
        mastery.record(self.profile, evidence('next-training', kind='training'))
        self.assertAlmostEqual(self.summary()['p_mastery'],
                               before_training + (1 - before_training) * .1)

    def test_correlated_attempts_cannot_reopen_training_credit(self):
        mastery.record(self.profile, evidence('first', family='same'))
        mastery.record(self.profile, evidence('training', kind='training'))
        before = self.summary()['p_mastery']
        mastery.record(self.profile, evidence('repeat', family='same'))
        mastery.record(self.profile, evidence('training2', kind='training'))
        self.assertEqual(self.summary()['p_mastery'], before)

    def test_help_and_incomplete_observations_cannot_confirm_or_punish(self):
        for number, changes in enumerate(({'independent': False},
                {'observed': False}, {'technical_error': True},
                {'passed': False, 'observed': False},
                {'passed': False, 'technical_error': True})):
            mastery.record(self.profile, evidence(number, **changes))
        result = self.summary()
        self.assertEqual(result['p_mastery'], .3)
        self.assertFalse(result['needs_reassessment'])
        self.assertEqual(len(result['evidence_ids']), 5)
        self.assertEqual(result['scored_evidence_ids'], [])
        event = evidence('missing')
        del event['observed']
        del event['independent']
        mastery.record(self.profile, event)
        self.assertEqual(self.summary()['p_mastery'], .3)

    def test_new_independent_failure_revokes_confirmation_and_recovery_is_evaluated(self):
        self.passes()
        mastery.record(self.profile, evidence('fail', passed=False))
        result = self.summary()
        self.assertEqual(result['status'], 'review_due')
        self.assertEqual(result['decision'], 'reassess')
        self.assertTrue(result['needs_reassessment'])
        self.assertIsNotNone(result['last_confirmed_at'])
        mastery.record(self.profile, evidence('training', kind='training'))
        self.assertEqual(self.summary()['status'], 'review_due')
        for number in range(3):
            mastery.record(self.profile, evidence('recover-' + str(number)))
        self.assertEqual(self.summary()['status'], 'mastered')
        self.assertFalse(self.summary()['needs_reassessment'])

    def test_repeated_failure_is_correlated_but_still_requires_review(self):
        self.passes()
        mastery.record(self.profile, evidence('fail1', passed=False, family='structure-0'))
        first = self.summary()['p_mastery']
        mastery.record(self.profile, evidence('fail2', passed=False, family='structure-0'))
        self.assertEqual(self.summary()['p_mastery'], first)
        self.assertTrue(self.summary()['needs_reassessment'])

    def test_same_day_repetition_does_not_restore_confirmation(self):
        self.passes(5)
        mastery.record(self.profile, evidence('fail', passed=False, family='structure-0'))
        mastery.record(self.profile, evidence('retry', family='structure-0'))
        self.assertEqual(self.summary()['status'], 'review_due')

    def test_decay_and_due_review_are_replayable_and_do_not_mutate_events(self):
        self.passes()
        original = deepcopy(self.profile)
        initial = self.summary()
        later = self.summary(BASE + timedelta(days=60))
        self.assertAlmostEqual(later['p_mastery'], .3 + (initial['p_mastery'] - .3) / 2)
        self.assertEqual(later['status'], 'review_due')
        self.assertEqual(self.profile, original)
        due = datetime.fromisoformat(initial['next_review_at'].replace('Z', '+00:00'))
        self.assertEqual(self.summary(due)['status'], 'review_due')
        mastery.record(self.profile, evidence('review', at=(BASE + timedelta(days=4)).isoformat()))
        self.assertEqual(self.summary(BASE + timedelta(days=4))['status'], 'mastered')

    def test_help_cannot_move_review_deadline_or_restore_expired_status(self):
        self.passes()
        due = self.summary()['next_review_at']
        mastery.record(self.profile, evidence('early-training', kind='training',
            at=(BASE + timedelta(days=1)).isoformat()))
        self.assertEqual(self.summary(BASE + timedelta(days=1))['next_review_at'], due)
        mastery.record(self.profile, evidence('late-training', kind='training',
            at=(BASE + timedelta(days=4)).isoformat()))
        self.assertEqual(self.summary(BASE + timedelta(days=4))['status'], 'review_due')

    def test_failures_do_not_spontaneously_improve_over_time(self):
        mastery.record(self.profile, evidence(1, passed=False))
        self.assertLess(self.summary()['p_mastery'], .3)
        self.assertEqual(self.summary()['p_mastery'],
                         self.summary(BASE + timedelta(days=180))['p_mastery'])

    def test_time_travel_and_utc_day_boundary(self):
        mastery.record(self.profile, evidence(1, at='2026-10-13T23:30:00Z', family='same'))
        mastery.record(self.profile, evidence(2, at='2026-10-14T08:30:00+08:00', family='same'))
        self.assertEqual(self.summary()['p_mastery'], .3)
        result = self.summary('2026-10-14T01:00:00Z')
        self.assertEqual(len(result['scored_evidence_ids']), 2)
        self.assertEqual(self.profile['events'][1]['at'], '2026-10-14T00:30:00Z')

    def test_custom_choice_guess_is_used_and_probability_is_capped(self):
        mastery.record(self.profile, evidence(1, guess=1 / 3))
        self.assertAlmostEqual(self.summary()['p_mastery'], .285 / (.285 + .7 / 3))
        for number in range(2, 20):
            mastery.record(self.profile, evidence(number))
        self.assertEqual(self.summary()['p_mastery'], .995)

    def test_invalid_parameters_types_and_timestamps_are_rejected_atomically(self):
        for changes in ({'guess': True}, {'slip': '0.05'}, {'guess': float('nan')},
                {'guess': .98}, {'slip': -1}, {'passed': 1}, {'contract_version': True},
                {'at': '2026-10-13T12:00:00'}, {'topic': 'not-a-concept'}, {'checks': {}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                mastery.record(self.profile, evidence(1, **changes))
            self.assertEqual(self.profile['events'], [])
        for changes in ({'policy_version': 'future'}, {'schema_version': True},
                {'parameter_version': 'unknown'}, {'parameters': {}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                mastery.summarize({**self.profile, **changes}, BASE)

    def test_initial_selection_prefers_assessment_and_information_per_second(self):
        chosen = mastery.select_task(self.profile, [task(0, kind='training'),
            task(1, duration_seconds=120), task(2, duration_seconds=30)], 'copy', BASE)
        self.assertEqual(chosen['id'], 'task-2')
        chosen['objectives'].append('caller-change')
        self.assertEqual(task(2)['objectives'], ['copy-structure'])

    def test_selection_prefers_uncovered_family_and_teaches_during_practice(self):
        mastery.record(self.profile, evidence(1))
        selected = mastery.select_task(self.profile,
            [task(2), task(3, kind='training')], 'copy', BASE)
        self.assertEqual(selected['id'], 'task-3')
        tomorrow = BASE + timedelta(days=1)
        selected = mastery.select_task(self.profile,
            [task(1, duration_seconds=1), task(2)], 'copy', tomorrow)
        self.assertEqual(selected['id'], 'task-2')

    def test_selection_skips_mastered_topics_and_same_day_families_but_offers_review(self):
        self.passes()
        catalog = [task(number) for number in range(4)]
        self.assertIsNone(mastery.select_task(self.profile, catalog, 'copy', BASE))
        selected = mastery.select_task(self.profile, catalog, 'copy', BASE + timedelta(days=4))
        self.assertEqual(selected['id'], 'task-3')
        self.profile = mastery.new_profile()
        mastery.record(self.profile, evidence(1))
        self.assertIsNone(mastery.select_task(self.profile, [task(1)], 'copy', BASE))

    def test_selection_uses_task_specific_guess_and_rejects_bad_contracts(self):
        selected = mastery.select_task(self.profile,
            [task(1, guess=.5), task(2, guess=.2)], 'copy', BASE)
        self.assertEqual(selected['id'], 'task-2')
        for changes in ({'guess': True}, {'version': '1'}, {'duration_seconds': 0},
                {'objectives': []}, {'family': ''}, {'topic': 'unknown'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                mastery.select_task(self.profile, [task(1, **changes)], 'copy', BASE)


class CalibrationReportTest(unittest.TestCase):
    def setUp(self):
        self.profile = mastery.new_profile()

    def add(self, number, predicted=.8, status='ready_to_check', **changes):
        event = evidence(number, prediction_before={
            'p_mastery': .9, 'p_success': predicted, 'status': status,
            'policy_version': mastery.POLICY_VERSION,
            'parameter_version': mastery.PARAMETER_VERSION,
        }, **changes)
        mastery.record(self.profile, event)
        return event

    def test_exact_brier_bins_and_prior_confirmed_followups(self):
        self.add(1, .8, 'mastered', passed=True)
        self.add(2, .6, 'mastered', passed=False)
        self.add(3, .2, 'practicing', passed=True)
        self.add(4, .1, 'needs_learning', passed=False)
        before = deepcopy(self.profile)
        result = mastery.calibration_report(self.profile)
        self.assertEqual(result['sample_count'], 4)
        self.assertAlmostEqual(result['brier_score'], .2625)
        self.assertEqual(result['confirmed_followups'],
                         {'count': 2, 'pass_rate': .5, 'false_confirmation_rate': .5})
        self.assertEqual([row['n'] for row in result['calibration_bins']], [1, 1, 0, 1, 1])
        self.assertEqual(result['calibration_bins'][3],
                         {'lower': .6, 'upper': .8, 'n': 1,
                          'mean_predicted': .6, 'actual_pass_rate': 0.0})
        self.assertIsNone(result['calibration_bins'][2]['actual_pass_rate'])
        self.assertEqual(self.profile, before)
        self.assertEqual(result['source'], 'local_observations')
        self.assertFalse(result['effectiveness_validated'])

    def test_same_family_day_and_first_attempt_are_deduplicated_without_outcome_bias(self):
        event = self.add(1, .9, passed=False, family='same')
        self.assertFalse(mastery.record(self.profile, event))
        self.add(2, .9, passed=True, family='same', session_id='another-session')
        self.add(3, .9, passed=True, family='different', attempt_id='1')
        self.add(4, .7, passed=True, family='same',
                 at=(BASE + timedelta(days=1)).isoformat())
        result = mastery.calibration_report(self.profile)
        self.assertEqual(result['sample_count'], 2)
        self.assertAlmostEqual(result['brier_score'], .45)

    def test_help_training_faults_and_incomplete_observation_are_excluded(self):
        for number, changes in enumerate(({'independent': False}, {'kind': 'training'},
                {'observed': False}, {'technical_error': True})):
            self.add(number, .9, 'mastered', **changes)
        self.add(5, .4, passed=False)
        result = mastery.calibration_report(self.profile)
        self.assertEqual(result['sample_count'], 1)
        self.assertAlmostEqual(result['brier_score'], .16)
        self.assertEqual(result['confirmed_followups']['count'], 0)
        self.assertIsNone(result['confirmed_followups']['pass_rate'])

    def test_no_samples_and_missing_historical_prediction_are_not_backfilled(self):
        result = mastery.calibration_report(self.profile)
        self.assertEqual(result['sample_count'], 0)
        self.assertIsNone(result['brier_score'])
        self.assertTrue(all(row['n'] == 0 and row['mean_predicted'] is None
                            for row in result['calibration_bins']))
        mastery.record(self.profile, evidence('old', family='same'))
        # A fresh prediction on a correlated retry does not replace missing history.
        self.add('retry', .8, family='same')
        result = mastery.calibration_report(self.profile)
        self.assertEqual(result['sample_count'], 0)
        self.assertIsNone(result['confirmed_followups']['false_confirmation_rate'])

    def test_boundaries_and_missing_or_invalid_prediction_values(self):
        self.add(1, 0, passed=False)
        self.add(2, 1, passed=True)
        self.add(3, True)
        self.add(4, '0.9')
        self.add(5, -0.1)
        self.add(6, 1.1)
        mastery.record(self.profile, evidence(7, prediction_before={'p_mastery': .9}))
        result = mastery.calibration_report(self.profile)
        self.assertEqual(result['sample_count'], 2)
        self.assertEqual(result['brier_score'], 0)
        self.assertEqual(result['calibration_bins'][0]['mean_predicted'], 0)
        self.assertEqual(result['calibration_bins'][4]['mean_predicted'], 1)


if __name__ == '__main__':
    unittest.main()
