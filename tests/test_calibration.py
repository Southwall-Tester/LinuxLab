"""Deterministic synthetic observations exercise the complete local feedback loop."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import calibration
import mastery


BASE = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
PROMOTION_OUTCOMES = 'PFFPPPFFPPFPFPPFPFFPPPFPPPPPPP'


def observation(index, passed, at=None, **changes):
    event = dict(id='sample-' + str(index), attempt_id='trial-' + str(index),
                 topic='paths', task_id='paths-' + str(index % 3),
                 family='f' + str(index % 3), at=(at or BASE + timedelta(days=index)).isoformat(),
                 passed=passed, kind='assessment', observed=True, independent=True,
                 technical_error=False, slip=.05, guess=.2, checks=[])
    event.update(changes)
    return event


def make_profile(outcomes=PROMOTION_OUTCOMES):
    profile = mastery.new_profile()
    for index, value in enumerate(outcomes):
        mastery.record(profile, observation(index, value == 'P'))
    return profile


def deploy(profile):
    return mastery.maybe_calibrate(profile, BASE + timedelta(days=29, hours=1))['topics']['paths']


def append_online(profile, index, passed, **changes):
    instant = BASE + timedelta(days=index)
    model = mastery.active_parameters(profile, 'paths', instant)
    state = mastery.summarize(profile, instant)['paths']
    params = model['parameters']
    prediction = dict(p_mastery=state['p_mastery'],
        p_success=state['p_mastery'] * (1 - params['slip']) + (1 - state['p_mastery']) * params['guess'],
        status=state['status'], policy_version=mastery.POLICY_VERSION,
        parameter_version=model['version'], frozen_at=instant.isoformat(), evidence_count=len(profile['events']),
        shadow_previous=mastery.shadow_prediction(profile, 'paths', instant))
    event = observation(index, passed, parameter_version=model['version'],
                        bkt_parameters=params, prediction_before=prediction,
                        slip=params['slip'], guess=params['guess'])
    event.update(changes)
    mastery.record(profile, event)
    return event


class AutomaticCalibrationTest(unittest.TestCase):
    def test_empty_legacy_profile_and_insufficient_data_do_not_write_metadata(self):
        profile = mastery.new_profile()
        original = deepcopy(profile)
        self.assertFalse(mastery.maybe_calibrate(profile)['changed'])
        self.assertEqual(profile, original)
        self.assertEqual(mastery.active_parameters(profile, 'paths')['version'], mastery.PARAMETER_VERSION)
        profile = make_profile(PROMOTION_OUTCOMES[:-1])
        original = deepcopy(profile)
        report = mastery.maybe_calibrate(profile, BASE + timedelta(days=30))
        self.assertFalse(report['changed'])
        self.assertEqual(profile, original)
        self.assertEqual(report['topics']['paths']['reason'], 'insufficient_samples')

    def test_candidate_is_selected_on_training_and_activated_after_fresh_holdout_improves(self):
        profile = make_profile()
        evidence = deepcopy(profile['events'])
        before = mastery.summarize(profile, BASE + timedelta(days=29))
        run = deploy(profile)
        self.assertTrue(run['accepted'])
        self.assertEqual(len(run['training_evidence_ids']), 18)
        self.assertEqual(len(run['validation_evidence_ids']), 12)
        self.assertGreaterEqual(run['validation_improvement'], .01)
        self.assertGreater(run['validation_improvement'], 2 * run['paired_standard_error'])
        self.assertEqual(run['candidate_parameters']['slip'], .2)
        self.assertEqual(run['candidate_parameters']['guess'], .4)
        self.assertFalse(run['learning_rate_searched'])
        self.assertLessEqual(run['candidate_count'], calibration.POLICY['max_candidates'])
        self.assertEqual(profile['events'], evidence)
        self.assertEqual(mastery.summarize(profile, BASE + timedelta(days=29)), before)
        at = BASE + timedelta(days=29, hours=1)
        model = mastery.active_parameters(profile, 'paths', at)
        actual = mastery.summarize(profile, at)['paths']
        _, replayed = calibration._simulate(profile, 'paths', profile['events'], model['parameters'], at)
        self.assertEqual(actual['p_mastery'], replayed['p_mastery'])
        self.assertEqual(actual['parameter_version'], model['version'])
        self.assertEqual(mastery.active_parameters(profile, 'paths', BASE)['version'], mastery.PARAMETER_VERSION)

    def test_no_stable_holdout_improvement_retains_current_version(self):
        profile = make_profile('PF' * 15)
        run = deploy(profile)
        self.assertFalse(run['accepted'])
        self.assertEqual(run['reason'], 'insufficient_validation_improvement')
        self.assertEqual(profile['calibration']['topics']['paths']['active_version'], mastery.PARAMETER_VERSION)
        self.assertEqual(profile['calibration']['topics']['paths']['transitions'], [])

    def test_candidate_with_worse_false_confirmation_rate_is_rejected_despite_brier_improvement(self):
        profile = make_profile(PROMOTION_OUTCOMES[:18] + 'PPPPPPPPPPFF')
        run = deploy(profile)
        self.assertGreater(run['validation_improvement'], .01)
        self.assertGreater(run['candidate_validation']['confirmed_followups']['false_confirmation_rate'],
                           run['baseline_validation']['confirmed_followups']['false_confirmation_rate'])
        self.assertFalse(run['accepted'])
        self.assertEqual(run['reason'], 'new_false_confirmations')

    def test_validation_outcomes_and_future_records_do_not_select_training_parameters(self):
        a = make_profile()
        b = make_profile(PROMOTION_OUTCOMES[:18] + 'PPPPPPPPPPFF')
        run_a, run_b = deploy(a), deploy(b)
        self.assertEqual(run_a['candidate_parameters'], run_b['candidate_parameters'])
        self.assertEqual(run_a['candidate_train'], run_b['candidate_train'])
        c = make_profile()
        for index in range(30, 45):
            mastery.record(c, observation(index, False))
        run_c = deploy(c)
        self.assertEqual(run_a['candidate_parameters'], run_c['candidate_parameters'])
        self.assertEqual(run_a['baseline_validation'], run_c['baseline_validation'])
        self.assertEqual(run_a['candidate_validation'], run_c['candidate_validation'])

    def test_eligibility_deduplicates_first_trial_family_day_and_excludes_help(self):
        profile = make_profile(PROMOTION_OUTCOMES[:-1])
        first = profile['events'][0]
        extras = (
            observation(100, True, at=BASE, family=first['family']),
            observation(101, True, attempt_id=first['attempt_id']),
            observation(102, True, help=[{'source': 'native_help'}]),
            observation(103, True, independent=False),
            observation(104, True, observed=False),
            observation(105, True, technical_error=True),
            observation(106, True, kind='training'),
        )
        for event in extras:
            mastery.record(profile, event)
        self.assertEqual(len(calibration._eligible(profile['events'])), 29)
        self.assertFalse(mastery.maybe_calibrate(profile, BASE + timedelta(days=110))['changed'])

    def test_active_parameters_affect_next_prediction_and_update_after_json_roundtrip(self):
        profile = make_profile()
        deploy(profile)
        profile = json.loads(json.dumps(profile))
        instant = BASE + timedelta(days=30)
        before = mastery.summarize(profile, instant)['paths']
        event = append_online(profile, 30, False)
        self.assertEqual(event['parameter_version'], 'paths-auto-v1')
        self.assertEqual(event['prediction_before']['p_success'],
                         before['p_mastery'] * .8 + (1 - before['p_mastery']) * .4)
        after = mastery.summarize(profile, instant)['paths']
        expected = before['p_mastery'] * .2 / (before['p_mastery'] * .2 + (1 - before['p_mastery']) * .6)
        self.assertAlmostEqual(after['p_mastery'], expected)
        original = deepcopy(profile['events'])
        mastery.maybe_calibrate(profile, instant)
        self.assertEqual(profile['events'], original)

    def test_online_regression_rolls_back_using_only_post_deployment_predictions(self):
        profile = make_profile()
        deploy(profile)
        old_events = deepcopy(profile['events'])
        for index in range(30, 42):
            append_online(profile, index, True)
            mastery.maybe_calibrate(profile, BASE + timedelta(days=index, hours=1))
        metadata = profile['calibration']['topics']['paths']
        monitor = metadata['monitor']
        self.assertEqual(metadata['active_version'], mastery.PARAMETER_VERSION)
        self.assertEqual(metadata['status'], 'rolled_back')
        self.assertGreaterEqual(monitor['current_brier'] - monitor['previous_brier'], .02)
        self.assertGreaterEqual(monitor['paired_worse_count'], 9)
        self.assertEqual({e['evidence_id'] for e in monitor['observations']},
                         {'sample-' + str(i) for i in range(30, 42)})
        self.assertEqual(profile['events'][:30], old_events)
        self.assertEqual(metadata['transitions'][-1]['reason'], 'online_regression')

    def test_old_version_late_submission_does_not_enter_online_monitor(self):
        profile = make_profile()
        deploy(profile)
        event = append_online(profile, 30, True)
        event['id'] = 'late'
        event['attempt_id'] = 'late'
        event['at'] = (BASE + timedelta(days=31)).isoformat()
        event['parameter_version'] = mastery.PARAMETER_VERSION
        event['prediction_before']['parameter_version'] = mastery.PARAMETER_VERSION
        mastery.record(profile, event)
        mastery.maybe_calibrate(profile, BASE + timedelta(days=32))
        self.assertEqual(profile['calibration']['topics']['paths']['monitor']['sample_count'], 1)

    def test_monitor_continues_on_disjoint_blocks_after_initial_success(self):
        profile = make_profile()
        deploy(profile)
        for index in range(30, 42):
            append_online(profile, index, index % 2 == 0)
        mastery.maybe_calibrate(profile, BASE + timedelta(days=41, hours=1))
        monitor = profile['calibration']['topics']['paths']['monitor']
        self.assertEqual(monitor['status'], 'monitoring')
        self.assertEqual(monitor['checked_count'], 12)
        for index in range(42, 54):
            append_online(profile, index, True)
        mastery.maybe_calibrate(profile, BASE + timedelta(days=53, hours=1))
        history = profile['calibration']['topics']['paths']['monitor_history']
        self.assertEqual(len(history), 2)
        first = {e['evidence_id'] for e in history[0]['observations']}
        second = {e['evidence_id'] for e in history[1]['observations']}
        self.assertFalse(first & second)

    def test_backdated_arrival_cannot_change_frozen_prefix_or_checkpoint_and_is_retained_raw(self):
        profile = make_profile()
        deploy(profile)
        historical_at = BASE + timedelta(days=10)
        current_at = BASE + timedelta(days=30)
        historical = mastery.summarize(profile, historical_at)
        probability = mastery.summarize(profile, current_at)['paths']['p_mastery']
        late = observation(100, False, at=BASE + timedelta(days=5, minutes=1))
        mastery.record(profile, late)
        self.assertEqual(mastery.summarize(profile, historical_at), historical)
        current = mastery.summarize(profile, current_at)['paths']
        self.assertEqual(current['p_mastery'], probability)
        self.assertIn({'id': late['id'], 'reason': 'late_arrival_excluded'}, current['observations'])
        self.assertEqual(len(calibration._eligible(calibration._events(profile, 'paths', current_at))), 30)
        self.assertEqual(profile['events'][-1]['id'], late['id'])

    def test_bad_frozen_parameters_and_checkpoint_metadata_are_rejected(self):
        for invalid in ({'learning_rate': True},
                        dict(mastery.DEFAULT_PARAMETERS, learning_rate=-1),
                        dict(mastery.DEFAULT_PARAMETERS, learning_rate='0.1'),
                        dict(mastery.DEFAULT_PARAMETERS, confirmation_threshold=.5)):
            profile = mastery.new_profile()
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                mastery.record(profile, observation(0, True, kind='training',
                    parameter_version='bad', bkt_parameters=invalid))
            self.assertEqual(profile['events'], [])
        profile = make_profile()
        deploy(profile)
        profile['calibration']['topics']['paths']['versions'][0]['parameters']['learning_rate'] = True
        with self.assertRaises(ValueError):
            mastery.summarize(profile)

    def test_monitor_requires_frozen_shadow_on_the_same_evidence_prefix(self):
        profile = make_profile()
        deploy(profile)
        first = append_online(profile, 30, True)
        second = append_online(profile, 31, True)
        # Mutate a detached fixture before storing, never a real persisted event.
        third = deepcopy(second)
        third.update(id='no-shadow', attempt_id='no-shadow', family='extra',
                     at=(BASE + timedelta(days=32)).isoformat())
        third['prediction_before'].pop('shadow_previous')
        mastery.record(profile, third)
        fourth = deepcopy(first)
        fourth.update(id='different-prefix', attempt_id='different-prefix', family='extra2',
                      at=(BASE + timedelta(days=33)).isoformat())
        fourth['prediction_before']['evidence_count'] += 1
        mastery.record(profile, fourth)
        mastery.maybe_calibrate(profile, BASE + timedelta(days=34))
        self.assertEqual(profile['calibration']['topics']['paths']['monitor']['sample_count'], 2)

    def test_later_fit_uses_new_validation_labels_and_bounds_the_scored_window(self):
        profile = make_profile('PF' * 15)
        first = deploy(profile)
        self.assertFalse(first['accepted'])
        for index in range(30, 42):
            mastery.record(profile, observation(index, index % 2 == 0))
        second = mastery.maybe_calibrate(profile, BASE + timedelta(days=42))['topics']['paths']
        self.assertFalse(set(first['validation_evidence_ids']) & set(second['validation_evidence_ids']))
        self.assertEqual(second['eligible_count'], 42)
        self.assertEqual(second['validation_evidence_ids'], ['sample-' + str(i) for i in range(30, 42)])
        for index in range(42, 150):
            mastery.record(profile, observation(index, index % 2 == 0))
        last = mastery.maybe_calibrate(profile, BASE + timedelta(days=150))['topics']['paths']
        self.assertEqual(len(last['training_evidence_ids']), 108)
        self.assertEqual(len(last['validation_evidence_ids']), 12)

    def test_cpu_budget_retains_model_without_partial_grid_promotion(self):
        profile = make_profile()
        original = deepcopy(profile['events'])
        with patch('calibration.time.monotonic', side_effect=[0., 4., 4.]):
            run = deploy(profile)
        self.assertFalse(run['accepted'])
        self.assertEqual(run['reason'], 'cpu_budget_exceeded')
        self.assertEqual(profile['events'], original)
        self.assertEqual(profile['calibration']['topics']['paths']['transitions'], [])

    def test_existing_deployment_can_rollback_above_the_fitting_event_limit(self):
        profile = make_profile()
        deploy(profile)
        for index in range(30, 42):
            append_online(profile, index, True)
        # A smaller injected limit exercises the same boundary without thousands
        # of redundant fixtures; this limit may stop fitting, never rollback.
        with patch.dict(calibration.POLICY, max_replay_events=40):
            mastery.maybe_calibrate(profile, BASE + timedelta(days=41, hours=1))
        metadata = profile['calibration']['topics']['paths']
        self.assertEqual(metadata['status'], 'rolled_back')
        self.assertEqual(metadata['active_version'], mastery.PARAMETER_VERSION)
        self.assertEqual(metadata['monitor']['sample_count'], 12)

    def test_historical_calibration_call_cannot_rewrite_deployment_metadata(self):
        profile = make_profile()
        deploy(profile)
        original = deepcopy(profile)
        result = mastery.maybe_calibrate(profile, BASE + timedelta(days=10))
        self.assertFalse(result['changed'])
        self.assertEqual(profile, original)

    def test_repeated_update_is_idempotent_and_cold_topics_stay_unmodified(self):
        profile = make_profile()
        deploy(profile)
        original = deepcopy(profile)
        result = mastery.maybe_calibrate(profile, BASE + timedelta(days=29, hours=2))
        self.assertFalse(result['changed'])
        self.assertEqual(profile, original)
        self.assertEqual(set(profile['calibration']['topics']), {'paths'})
        status = mastery.calibration_status(profile)
        self.assertFalse(status['effectiveness_validated'])
        self.assertEqual(status['topics']['paths']['active_version'], 'paths-auto-v1')

    def test_completed_training_transitions_enable_learning_rate_search_only_when_present(self):
        profile = mastery.new_profile()
        for index, value in enumerate(PROMOTION_OUTCOMES):
            if index < 6:
                mastery.record(profile, observation(100 + index, True,
                    at=BASE + timedelta(days=index, minutes=-1), kind='training', independent=False))
            mastery.record(profile, observation(index, value == 'P'))
        run = deploy(profile)
        self.assertEqual(run['training_transitions'], 6)
        self.assertTrue(run['learning_rate_searched'])
        self.assertLessEqual(run['candidate_count'], calibration.POLICY['max_candidates'])

    def test_historical_unsorted_prefix_is_stable_after_activation_and_switch_never_confirms(self):
        profile = make_profile()
        profile['events'][0], profile['events'][1] = profile['events'][1], profile['events'][0]
        before = mastery.summarize(profile, BASE + timedelta(days=20))
        deploy(profile)
        self.assertEqual(mastery.summarize(profile, BASE + timedelta(days=20)), before)
        # A model-only probability increase cannot make a never-confirmed topic mastered.
        simple = make_profile('PF')
        metadata = calibration._ensure_topic(simple, 'paths')
        params = dict(simple['parameters'], slip=.2, guess=.4)
        metadata['versions'].append({'version': 'test-v1', 'parameters': params})
        metadata['transitions'].append(dict(at=(BASE + timedelta(days=2)).isoformat(),
            after_event_count=2, version='test-v1', previous_version=mastery.PARAMETER_VERSION,
            checkpoint_probability=.995, reason='test'))
        self.assertNotEqual(mastery.summarize(simple, BASE + timedelta(days=2))['paths']['status'], 'mastered')


if __name__ == '__main__':
    unittest.main()
