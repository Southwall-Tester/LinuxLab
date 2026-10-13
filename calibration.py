"""Bounded local BKT fitting, forward validation, deployment and rollback.

This is an engineering feedback loop for one local learner, not a population
effectiveness study. q0, confirmation gates and forgetting remain fixed: a
single learner sequence cannot reliably identify all of those parameters.
"""
from copy import deepcopy
import math
import time

import mastery
from knowledge import CONCEPTS


POLICY = {
    'min_samples': 30, 'min_families': 3, 'min_passes': 6, 'min_failures': 6,
    'retrain_every': 12, 'max_samples': 120, 'validation_samples': 12,
    'min_split_passes': 2, 'min_split_failures': 2,
    'min_training_transitions': 6,
    'min_validation_improvement': .01, 'paired_standard_errors': 2.0,
    'monitor_samples': 12, 'rollback_brier_margin': .02,
    'rollback_worse_pairs': 9, 'max_replay_events': 5000,
    'max_candidates': 216, 'max_fit_seconds': 3.0,
}


def _metadata(profile, topic):
    return profile.get('calibration', {}).get('topics', {}).get(topic, {})


def _version_parameters(profile, topic, version):
    if version == mastery.PARAMETER_VERSION:
        return dict(profile['parameters'])
    for item in _metadata(profile, topic).get('versions', []):
        if item['version'] == version:
            return dict(item['parameters'])
    raise ValueError('unknown calibrated parameter version')


def active_parameters(profile, topic, at=None):
    mastery._profile(profile)
    if topic not in CONCEPTS:
        raise ValueError('unknown parameter topic')
    now = mastery._time(at)
    version = mastery.PARAMETER_VERSION
    for switch in _metadata(profile, topic).get('transitions', []):
        if mastery._time(switch['at']) <= now:
            version = switch['version']
    return {'version': version, 'parameters': _version_parameters(profile, topic, version)}


def _events(profile, topic, at):
    late = mastery._late_arrivals(profile, topic)
    return sorted((e for e in profile['events']
                   if e['topic'] == topic and e['id'] not in late and mastery._time(e['at']) <= at),
                  key=lambda e: mastery._time(e['at']))


def _eligible(events):
    attempts, families, selected = set(), set(), []
    for event in events:
        attempt = event.get('attempt_id', event['id'])
        if attempt in attempts:
            continue
        attempts.add(attempt)
        if (event.get('kind', 'assessment') != 'assessment' or not event.get('independent')
                or not event.get('observed') or event.get('technical_error') or event.get('help')):
            continue
        family = (event['family'], mastery._time(event['at']).date())
        if family in families:
            continue
        families.add(family)
        selected.append(event)
    return selected


def _simulate(profile, topic, events, parameters, at):
    replay = mastery.new_profile()
    replay['parameters'] = dict(parameters)
    # Raw terminal observations and dialogue remain in the original profile.
    # Optimizer replay only needs these small inference fields.
    fields = ('id', 'attempt_id', 'topic', 'task_id', 'family', 'at', 'passed',
              'kind', 'independent', 'observed', 'technical_error')
    replay['events'] = [{key: event[key] for key in fields if key in event} for event in events]
    predictions = {}
    result = mastery._summarize(replay, at, predictions=predictions,
                                override=parameters, transitions=False, only_topic=topic)[topic]
    return predictions, result


def _score(predictions, events):
    losses, confirmed_ids, failed_ids = [], [], []
    for event in events:
        prediction = predictions[event['id']]
        losses.append((prediction['p_success'] - int(event['passed'])) ** 2)
        if prediction['confirmed']:
            confirmed_ids.append(event['id'])
            if not event['passed']:
                failed_ids.append(event['id'])
    return {
        'sample_count': len(events),
        'brier_score': sum(losses) / len(losses) if losses else None,
        'confirmed_followups': {
            'count': len(confirmed_ids), 'failure_count': len(failed_ids),
            'false_confirmation_rate': len(failed_ids) / len(confirmed_ids) if confirmed_ids else None,
            'failed_evidence_ids': failed_ids,
        },
    }


def shadow_prediction(profile, topic, at=None):
    """Freeze the previous-model prediction on the caller's current evidence.

    Call under the same profile lock as the deployed prediction; save both in
    the attempt snapshot so retries cannot give one model more information.
    """
    current = active_parameters(profile, topic, at)
    monitor = _metadata(profile, topic).get('monitor')
    if (not monitor or monitor['status'] != 'monitoring'
            or monitor['version'] != current['version']):
        return None
    now = mastery._time(at)
    parameters = _version_parameters(profile, topic, monitor['previous_version'])
    events = _events(profile, topic, now)
    _, state = _simulate(profile, topic, events, parameters, now)
    probability = state['p_mastery']
    return {'version': monitor['previous_version'],
            'p_success': probability * (1 - parameters['slip']) + (1 - probability) * parameters['guess'],
            'evidence_count': _cursor(profile, now), 'at': mastery._iso(now)}


def _paired_gain(baseline, candidate, events):
    differences = [
        (baseline[e['id']]['p_success'] - int(e['passed'])) ** 2
        - (candidate[e['id']]['p_success'] - int(e['passed'])) ** 2 for e in events]
    mean = sum(differences) / len(differences)
    variance = sum((d - mean) ** 2 for d in differences) / (len(differences) - 1)
    return mean, math.sqrt(variance / len(differences))


def _enough_classes(events, minimum):
    passed = sum(e['passed'] for e in events)
    return passed >= minimum and len(events) - passed >= minimum


def _gate(eligible):
    if len(eligible) < POLICY['min_samples']:
        return 'insufficient_samples'
    window = eligible[-POLICY['max_samples']:]
    if len({e['family'] for e in window}) < POLICY['min_families']:
        return 'insufficient_structural_families'
    if not _enough_classes(window, POLICY['min_passes']):
        return 'insufficient_passes_or_failures'
    train, validation = window[:-POLICY['validation_samples']], window[-POLICY['validation_samples']:]
    if not _enough_classes(train, POLICY['min_split_passes']):
        return 'insufficient_training_outcome_diversity'
    if not _enough_classes(validation, POLICY['min_split_passes']):
        return 'insufficient_validation_outcome_diversity'
    return None


def _ensure_topic(profile, topic):
    calibration = profile.setdefault('calibration', {'schema_version': 1, 'topics': {}})
    return calibration['topics'].setdefault(topic, {
        'active_version': mastery.PARAMETER_VERSION, 'versions': [],
        'transitions': [], 'runs': [], 'last_fit_count': 0,
        'monitor': None, 'monitor_history': [], 'status': 'cold_start',
        'reason': 'insufficient_samples', 'last_processed_count': 0,
    })


def _cursor(profile, at):
    return max((index + 1 for index, event in enumerate(profile['events'])
                if mastery._time(event['at']) <= at), default=0)


def _switch(profile, topic, parameters, version, previous_version, events, at, reason):
    _, state = _simulate(profile, topic, events, parameters, at)
    metadata = _ensure_topic(profile, topic)
    metadata['transitions'].append({
        'at': mastery._iso(at), 'after_event_count': _cursor(profile, at),
        'version': version, 'previous_version': previous_version,
        'checkpoint_probability': state['p_mastery'], 'reason': reason,
    })
    metadata['active_version'] = version
    return state['p_mastery']


def _monitor(profile, topic, metadata, events, eligible, at):
    monitor = metadata.get('monitor')
    if not monitor or monitor['status'] != 'monitoring':
        return False
    positions = {event['id']: index for index, event in enumerate(profile['events'])}
    after = [event for event in eligible
             if positions[event['id']] >= monitor['after_event_count']
             and event.get('parameter_version') == monitor['version']
             and event.get('prediction_before', {}).get('parameter_version') == monitor['version']
             and isinstance(event.get('prediction_before', {}).get('p_success'), (float, int))
             and not isinstance(event['prediction_before']['p_success'], bool)
             and 0 <= event['prediction_before']['p_success'] <= 1
             and isinstance(event.get('prediction_before', {}).get('shadow_previous'), dict)
             and event['prediction_before']['shadow_previous'].get('version') == monitor['previous_version']
             and type(event['prediction_before']['shadow_previous'].get('p_success')) in (float, int)
             and 0 <= event['prediction_before']['shadow_previous']['p_success'] <= 1
             and isinstance(event['prediction_before'].get('frozen_at'), str)
             and mastery._time(event['prediction_before']['shadow_previous'].get('at'))
                 == mastery._time(event['prediction_before']['frozen_at'])
             and type(event['prediction_before'].get('evidence_count')) is int
             and event['prediction_before']['shadow_previous'].get('evidence_count')
                 == event['prediction_before']['evidence_count']]
    # Monitoring uses only genuinely post-deployment records, in disjoint blocks.
    done = monitor.get('checked_count', 0)
    block = after[done:done + POLICY['monitor_samples']]
    old_parameters = _version_parameters(profile, topic, monitor['previous_version'])
    observations = []
    for event in block:
        predicted = event['prediction_before']['p_success']
        old_predicted = event['prediction_before']['shadow_previous']['p_success']
        actual = int(event['passed'])
        observations.append({
            'evidence_id': event['id'], 'actual': actual,
            'current_p_success': predicted, 'previous_p_success': old_predicted,
            'current_shadow_p_success': predicted,
            'current_loss': (predicted - actual) ** 2,
            'previous_loss': (old_predicted - actual) ** 2,
        })
    n = len(observations)
    monitor.update(sample_count=n, observations=observations,
        current_brier=sum(e['current_loss'] for e in observations) / n if n else None,
        previous_brier=sum(e['previous_loss'] for e in observations) / n if n else None,
        paired_worse_count=sum(e['current_loss'] > e['previous_loss'] for e in observations))
    if n < POLICY['monitor_samples']:
        return False
    regression = (monitor['current_brier'] - monitor['previous_brier'] >= POLICY['rollback_brier_margin']
                  and monitor['paired_worse_count'] >= POLICY['rollback_worse_pairs'])
    checkpoint = deepcopy(monitor)
    checkpoint['checked_at'] = mastery._iso(at)
    checkpoint['status'] = 'rolled_back' if regression else 'monitor_passed'
    metadata['monitor_history'].append(checkpoint)
    monitor['checked_count'] = done + n
    if regression:
        _switch(profile, topic, old_parameters, monitor['previous_version'],
                monitor['version'], events, at, 'online_regression')
        monitor['status'] = 'rolled_back'
        metadata.update(status='rolled_back', reason='online_regression')
    else:
        monitor['status'] = 'monitoring'
        metadata.update(status='monitoring', reason='online_block_passed')
    return True


def _fit(profile, topic, events, eligible, at):
    started = time.monotonic()
    metadata = _ensure_topic(profile, topic)
    active = active_parameters(profile, topic, at)
    baseline = active['parameters']
    window = eligible[-POLICY['max_samples']:]
    train, validation = window[:-POLICY['validation_samples']], window[-POLICY['validation_samples']:]
    baseline_predictions, _ = _simulate(profile, topic, events, baseline, at)
    training_transitions = sum(baseline_predictions[e['id']]['training_transition'] for e in train)
    slips = sorted(set((.02, .05, .10, .15, .20, baseline['slip'])))
    guesses = sorted(set((.05, .10, .20, .30, .40, baseline['guess'])))
    rates = ([baseline['learning_rate']] if training_transitions < POLICY['min_training_transitions']
             else sorted(set((.02, .05, .10, .20, .30, baseline['learning_rate']))))
    baseline_train = _score(baseline_predictions, train)
    baseline_validation = _score(baseline_predictions, validation)
    best = (baseline_train['brier_score'], 0.0, baseline['slip'], baseline['guess'], baseline['learning_rate'])
    candidate, candidate_predictions = dict(baseline), baseline_predictions
    searched = 0
    budget_exhausted = False
    # Deterministic grid; only TRAIN losses influence selection and tie-breaking.
    for slip in slips:
        for guess in guesses:
            for rate in rates:
                if time.monotonic() - started >= POLICY['max_fit_seconds']:
                    budget_exhausted = True
                    break
                proposal = dict(baseline, slip=slip, guess=guess, learning_rate=rate)
                predictions, _ = _simulate(profile, topic, events, proposal, at)
                distance = sum(abs(proposal[k] - baseline[k]) for k in ('slip', 'guess', 'learning_rate'))
                key = (_score(predictions, train)['brier_score'], distance, slip, guess, rate)
                searched += 1
                if key < best:
                    best, candidate, candidate_predictions = key, proposal, predictions
            if budget_exhausted:
                break
        if budget_exhausted:
            break
    candidate_train = _score(candidate_predictions, train)
    candidate_validation = _score(candidate_predictions, validation)
    improvement, standard_error = _paired_gain(baseline_predictions, candidate_predictions, validation)
    baseline_confirmed = baseline_validation['confirmed_followups']
    candidate_confirmed = candidate_validation['confirmed_followups']
    new_false_ids = sorted(set(candidate_confirmed['failed_evidence_ids'])
                           - set(baseline_confirmed['failed_evidence_ids']))
    no_increased_rate = ((candidate_confirmed['false_confirmation_rate'] or 0)
                         <= (baseline_confirmed['false_confirmation_rate'] or 0))
    accepted = (not budget_exhausted and candidate_train['brier_score'] < baseline_train['brier_score'] - 1e-12
                and improvement >= POLICY['min_validation_improvement']
                and improvement > POLICY['paired_standard_errors'] * standard_error
                and not new_false_ids and no_increased_rate)
    reason = ('cpu_budget_exceeded' if budget_exhausted else 'forward_validation_passed' if accepted else
              'no_training_improvement' if candidate_train['brier_score'] >= baseline_train['brier_score'] - 1e-12 else
              'new_false_confirmations' if new_false_ids or not no_increased_rate else
              'insufficient_validation_improvement')
    run = {
        'at': mastery._iso(at), 'eligible_count': len(eligible),
        'baseline_version': active['version'], 'baseline_parameters': baseline,
        'candidate_parameters': candidate, 'candidate_count': searched,
        'fit_seconds': time.monotonic() - started,
        'training_evidence_ids': [e['id'] for e in train],
        'validation_evidence_ids': [e['id'] for e in validation],
        'training_transitions': training_transitions,
        'learning_rate_searched': len(rates) > 1,
        'baseline_train': baseline_train, 'candidate_train': candidate_train,
        'baseline_validation': baseline_validation, 'candidate_validation': candidate_validation,
        'validation_improvement': improvement, 'paired_standard_error': standard_error,
        'new_false_confirmation_ids': new_false_ids,
        'confirmation_validation_covered': bool(baseline_confirmed['count'] and candidate_confirmed['count']),
        'accepted': accepted, 'reason': reason,
    }
    metadata['runs'].append(run)
    metadata['last_fit_count'] = len(eligible)
    metadata.update(status='activated' if accepted else 'retained', reason=reason)
    if accepted:
        version = topic + '-auto-v' + str(len(metadata['versions']) + 1)
        metadata['versions'].append({
            'version': version, 'parameters': dict(candidate), 'created_at': mastery._iso(at),
            'previous_version': active['version'], 'run_index': len(metadata['runs']) - 1,
        })
        _switch(profile, topic, candidate, version, active['version'], events, at, 'validated_candidate')
        metadata['monitor'] = {
            'version': version, 'previous_version': active['version'],
            'after_event_count': _cursor(profile, at), 'status': 'monitoring',
            'sample_count': 0, 'checked_count': 0, 'current_brier': None,
            'previous_brier': None, 'paired_worse_count': 0, 'observations': [],
        }
        run['activated_version'] = version
    return run


def maybe_calibrate(profile, at=None):
    mastery._profile(profile)
    now = mastery._time(at)
    reports, changed = {}, False
    for topic in CONCEPTS:
        events = _events(profile, topic, now)
        eligible = _eligible(events)
        metadata = _metadata(profile, topic)
        reason = _gate(eligible)
        if metadata.get('transitions') and mastery._time(metadata['transitions'][-1]['at']) > now:
            reports[topic] = {'status': 'retained', 'reason': 'historical_view_no_update', 'eligible_count': len(eligible)}
            continue
        if metadata and len(eligible) == metadata.get('last_processed_count'):
            reports[topic] = {'status': metadata['status'], 'reason': metadata['reason'], 'eligible_count': len(eligible)}
            continue
        if metadata:
            before = deepcopy(metadata)
            completed_monitor = _monitor(profile, topic, metadata, events, eligible, now)
            metadata['last_processed_count'] = len(eligible)
            changed = changed or metadata != before
            if completed_monitor or (metadata.get('monitor')
                    and metadata['monitor']['status'] == 'monitoring'
                    and metadata['monitor'].get('checked_count', 0) == 0):
                reports[topic] = {'status': metadata['status'], 'reason': metadata['reason'], 'eligible_count': len(eligible)}
                continue
        # The replay cap bounds fitting, never monitoring of an already deployed
        # version. Frozen paired predictions must retain their rollback path.
        if len(events) > POLICY['max_replay_events']:
            reports[topic] = {'status': 'retained', 'reason': 'replay_event_limit', 'eligible_count': len(eligible)}
            continue
        if reason:
            reports[topic] = {'status': 'cold_start', 'reason': reason, 'eligible_count': len(eligible)}
            continue
        if metadata and len(eligible) - metadata['last_fit_count'] < POLICY['retrain_every']:
            reports[topic] = {'status': metadata['status'], 'reason': 'waiting_for_fresh_validation', 'eligible_count': len(eligible)}
            continue
        reports[topic] = _fit(profile, topic, events, eligible, now)
        _metadata(profile, topic)['last_processed_count'] = len(eligible)
        changed = True
    return {'topics': reports, 'changed': changed}


def calibration_status(profile):
    mastery._profile(profile)
    now = mastery._time()
    topics = {}
    for topic in CONCEPTS:
        eligible = _eligible(_events(profile, topic, now))
        metadata = _metadata(profile, topic)
        model = active_parameters(profile, topic, now)
        topics[topic] = {
            'active_version': model['version'], 'parameters': model['parameters'],
            'eligible_count': len(eligible), 'last_fit_count': metadata.get('last_fit_count', 0),
            'status': metadata.get('status', 'cold_start'),
            'reason': metadata.get('reason', _gate(eligible) or 'awaiting_automatic_update'),
            'last_run': deepcopy((metadata.get('runs') or [None])[-1]),
            'monitor': deepcopy(metadata.get('monitor')),
            'excluded_late_event_count': len(mastery._late_arrivals(profile, topic)),
        }
    return {'schema_version': 1, 'policy': dict(POLICY), 'topics': topics,
            'source': 'local_observations', 'effectiveness_validated': False}
