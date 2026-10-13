"""Versioned, replayable Bayesian teaching decisions for the local learner.

The persisted events are observations; this module derives a separate policy
decision. Parameters are engineering defaults, not measured model accuracy.
No filesystem, learner-answer access, network or third-party packages are used.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import math

from knowledge import CONCEPTS


POLICY_VERSION = 'linuxlab-bkt-v1'
PARAMETER_VERSION = 'engineering-defaults-v1'
DEFAULT_PARAMETERS = {
    'q0': .30,
    'slip': .05,
    'guess': .20,
    'learning_rate': .10,
    'confirmation_threshold': .95,
    'max_probability': .995,
    'half_life_days': 60.0,
    'review_after_days': 7.0,
}
LABELS = {
    'needs_learning': '需要学习',
    'practicing': '正在掌握',
    'ready_to_check': '接近掌握',
    'mastered': '已掌握',
    'review_due': '需要复测',
}


def new_profile():
    """Return a new JSON-serializable profile without any learner evidence."""
    return {
        'schema_version': 1,
        'policy_version': POLICY_VERSION,
        'parameter_version': PARAMETER_VERSION,
        'parameters': dict(DEFAULT_PARAMETERS),
        'events': [],
    }


def _time(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('at must be an ISO 8601 timestamp with timezone') from exc
    else:
        raise ValueError('at must be an ISO 8601 timestamp with timezone')
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('at must include a timezone')
    return result.astimezone(timezone.utc)


def _iso(value):
    return value.isoformat().replace('+00:00', 'Z') if value else None


def _number(value, name, low=0.0, high=1.0):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low < value < high):
        raise ValueError(f'{name} must be a finite number between {low} and {high}')
    return float(value)


def _test_parameters(item, parameters):
    slip = _number(item.get('slip', parameters['slip']), 'slip')
    guess = _number(item.get('guess', parameters['guess']), 'guess')
    if guess >= 1 - slip:
        raise ValueError('guess must be less than 1 - slip')
    return slip, guess


def _profile(profile):
    if not isinstance(profile, dict):
        raise ValueError('profile must be an object')
    if (type(profile.get('schema_version')) is not int
            or profile['schema_version'] != 1
            or profile.get('policy_version') != POLICY_VERSION
            or profile.get('parameter_version') != PARAMETER_VERSION):
        raise ValueError('unsupported learner profile or policy version')
    parameters = profile.get('parameters')
    if not isinstance(parameters, dict) or set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError('profile must contain the complete versioned parameters')
    for name in ('q0', 'learning_rate', 'confirmation_threshold', 'max_probability'):
        _number(parameters[name], name)
    if not parameters['q0'] < parameters['confirmation_threshold'] <= parameters['max_probability']:
        raise ValueError('require q0 < confirmation_threshold <= max_probability')
    for name in ('half_life_days', 'review_after_days'):
        _number(parameters[name], name, 0, 100000)
    _test_parameters(parameters, parameters)
    if not isinstance(profile.get('events'), list):
        raise ValueError('profile events must be a list')
    return parameters


def _event(evidence, parameters):
    if not isinstance(evidence, dict):
        raise ValueError('evidence must be an object')
    try:
        # A detached JSON copy prevents later mutation of caller-owned lists.
        result = json.loads(json.dumps(evidence, allow_nan=False, ensure_ascii=False))
    except (ValueError, TypeError) as exc:
        raise ValueError('evidence must contain finite JSON values') from exc
    for name in ('id', 'topic', 'task_id', 'family', 'at'):
        if not isinstance(result.get(name), str) or not result[name].strip():
            raise ValueError(f'evidence {name} must be a nonempty string')
    if result['topic'] not in CONCEPTS:
        raise ValueError('unknown evidence topic')
    result['at'] = _iso(_time(result['at']))
    for name, default in (('independent', False), ('observed', False),
                          ('technical_error', False)):
        result.setdefault(name, default)
    for name in ('passed', 'independent', 'observed', 'technical_error'):
        if type(result.get(name)) is not bool:
            raise ValueError(f'evidence {name} must be boolean')
    result.setdefault('kind', 'assessment')
    if result['kind'] not in ('assessment', 'training'):
        raise ValueError('evidence kind must be assessment or training')
    result.setdefault('contract_version', 1)
    if type(result['contract_version']) is not int or result['contract_version'] < 1:
        raise ValueError('contract_version must be a positive integer')
    for name in ('session_id', 'attempt_id'):
        if name in result and (not isinstance(result[name], str) or not result[name]):
            raise ValueError(f'{name} must be a nonempty string')
    result.setdefault('checks', [])
    if not isinstance(result['checks'], list):
        raise ValueError('checks must be a list')
    if 'objectives' in result and (not isinstance(result['objectives'], list)
            or any(not isinstance(v, str) or not v for v in result['objectives'])):
        raise ValueError('objectives must be a list of nonempty strings')
    _test_parameters(result, parameters)
    return result


def record(profile, evidence):
    """Append a detached observation; retry is idempotent, conflicting IDs fail.

    A task instance's first submission counts, keyed by attempt_id (or id).
    Submission IDs should be ``assessment:<attempt_id>``. Subsequent raw events
    may still be retained under distinct IDs without counting the attempt twice.
    """
    parameters = _profile(profile)
    candidate = _event(evidence, parameters)
    for existing in profile['events']:
        if existing.get('id') == candidate['id']:
            if _event(existing, parameters) != candidate:
                raise ValueError('evidence ID already exists with a different payload')
            return False
    profile['events'].append(candidate)
    return True


def _posterior(probability, passed, slip, guess):
    numerator = probability * ((1 - slip) if passed else slip)
    denominator = numerator + (1 - probability) * (guess if passed else 1 - guess)
    return numerator / denominator


def _decay(probability, earlier, later, parameters):
    if earlier is None:
        return probability
    days = max(0, (later.date() - earlier.date()).days)
    if not days:
        return probability
    floor = min(parameters['q0'], probability)
    return floor + (probability - floor) * 2 ** (-days / parameters['half_life_days'])


def _next_review(probability, anchor, confirmed, parameters):
    if confirmed is None or anchor is None:
        return None
    periodic = confirmed + timedelta(days=parameters['review_after_days'])
    threshold = parameters['confirmation_threshold']
    if probability < threshold:
        decay_due = anchor
    else:
        days = parameters['half_life_days'] * math.log2(
            (probability - parameters['q0']) / (threshold - parameters['q0']))
        decay_due = datetime.combine(anchor.date(), datetime.min.time(), timezone.utc)
        decay_due += timedelta(days=math.floor(days) + 1)
    return min(periodic, decay_due)


def summarize(profile, at=None):
    """Replay evidence into per-CONCEPTS policy decisions at the given time."""
    parameters = _profile(profile)
    now = _time(at)
    events = [_event(event, parameters) for event in profile['events']]
    if len({event['id'] for event in events}) != len(events):
        raise ValueError('profile contains duplicate evidence IDs')
    events = sorted((event for event in events if _time(event['at']) <= now),
                    key=lambda event: _time(event['at']))
    output = {}
    for topic, concept in CONCEPTS.items():
        probability = parameters['q0']
        anchor = last_assessment = confirmed = None
        confirmed_probability = None
        latest_independent_pass = False
        needs_reassessment = False
        trained = False
        attempts, positive_days, negative_days = set(), set(), set()
        families, evidence_ids, scored_ids, observations = set(), [], [], []
        reasons = []
        for event in events:
            if event['topic'] != topic:
                continue
            evidence_ids.append(event['id'])
            instant = _time(event['at'])
            if confirmed is not None:
                planned_review = _next_review(confirmed_probability, confirmed, confirmed, parameters)
                if (instant >= planned_review
                        or _decay(probability, anchor, instant, parameters)
                        < parameters['confirmation_threshold']):
                    needs_reassessment = True
            reason = None
            if event['technical_error']:
                reason = 'technical_error_excluded'
            elif not event['observed']:
                reason = 'incomplete_observation_excluded'
            elif event['kind'] == 'training':
                if not event['passed']:
                    reason = 'training_not_completed'
                elif trained:
                    reason = 'training_window_already_counted'
                else:
                    probability = _decay(probability, anchor, instant, parameters)
                    probability += (1 - probability) * parameters['learning_rate']
                    probability = min(probability, parameters['max_probability'])
                    anchor, trained = instant, True
                    scored_ids.append(event['id'])
                    reason = 'completed_training_prediction'
            else:
                attempt = event.get('attempt_id', event['id'])
                if attempt in attempts:
                    reason = 'attempt_first_submission_only'
                else:
                    attempts.add(attempt)
                    if not event['independent']:
                        reason = 'assisted_assessment_excluded'
                    else:
                        last_assessment = instant
                        latest_independent_pass = event['passed']
                        day_key = (event['family'], instant.date())
                        if not event['passed']:
                            needs_reassessment = True
                        seen_days = positive_days if event['passed'] else negative_days
                        if day_key in seen_days:
                            reason = 'correlated_family_day_excluded'
                        else:
                            seen_days.add(day_key)
                            trained = False
                            probability = _decay(probability, anchor, instant, parameters)
                            slip, guess = _test_parameters(event, parameters)
                            probability = min(parameters['max_probability'],
                                _posterior(probability, event['passed'], slip, guess))
                            anchor = instant
                            scored_ids.append(event['id'])
                            if event['passed']:
                                families.add(event['family'])
                                if confirmed is None:
                                    needs_reassessment = False
                                reason = 'independent_pass_counted'
                                if (probability >= parameters['confirmation_threshold']
                                        and len(families) >= 2):
                                    confirmed = instant
                                    confirmed_probability = probability
                                    needs_reassessment = False
                            else:
                                reason = 'independent_failure_counted'
            observations.append({'id': event['id'], 'reason': reason})
        next_review = _next_review(confirmed_probability, confirmed, confirmed, parameters)
        probability = _decay(probability, anchor, now, parameters)
        due = confirmed is not None and (
            needs_reassessment or probability < parameters['confirmation_threshold']
            or (next_review is not None and now >= next_review))
        can_confirm = (confirmed is not None and not due and not needs_reassessment
                       and latest_independent_pass
                       and probability >= parameters['confirmation_threshold']
                       and len(families) >= 2)
        if due:
            status, decision = 'review_due', 'reassess'
            reasons.append('previous_confirmation_requires_new_independent_check')
        elif can_confirm:
            status, decision = 'mastered', 'advance'
            reasons.append('threshold_and_independent_family_coverage_met')
        else:
            status = ('needs_learning' if probability < .4 else
                      'practicing' if probability < .8 else 'ready_to_check')
            if last_assessment is None:
                decision = 'placement_check'
                reasons.append('start_with_independent_placement')
            elif needs_reassessment:
                decision = 'reassess'
                reasons.append('new_independent_failure_requires_reassessment')
            else:
                decision = 'teach' if probability < .4 else 'practice' if probability < .8 else 'assess'
            if len(families) < 2:
                reasons.append('need_two_independent_structural_families')
            if probability < parameters['confirmation_threshold']:
                reasons.append('below_confirmation_threshold')
        output[topic] = {
            'topic': topic, 'title': concept['title'], 'status': status,
            'label': LABELS[status], 'p_mastery': probability,
            'p_next_success': probability * (1 - parameters['slip'])
                              + (1 - probability) * parameters['guess'],
            'decision': decision, 'reasons': reasons,
            'evidence_ids': evidence_ids, 'scored_evidence_ids': scored_ids,
            'passed_families': sorted(families), 'next_review_at': _iso(next_review),
            'last_assessment_at': _iso(last_assessment),
            'last_confirmed_at': _iso(confirmed),
            'needs_reassessment': needs_reassessment or due,
            'observations': observations, 'origin': 'bayesian_policy',
            'human_reviewed': False, 'policy_version': POLICY_VERSION,
            'parameter_version': PARAMETER_VERSION, 'parameters': dict(parameters),
        }
    return output


def calibration_report(profile):
    """Compare frozen pre-submission predictions with local observations.

    This is local operational monitoring, not a cross-learner validation study.
    Historical predictions are never reconstructed using later learner evidence.
    No parameters are fitted, and no learning-effectiveness claim is produced.
    A topic/family/UTC-day contributes its first independent trial regardless of
    outcome, avoiding outcome-dependent selection of retries into the sample.
    """
    parameters = _profile(profile)
    events = [_event(event, parameters) for event in profile['events']]
    if len({event['id'] for event in events}) != len(events):
        raise ValueError('profile contains duplicate evidence IDs')
    events.sort(key=lambda event: _time(event['at']))
    attempts, families = set(), set()
    samples, followups = [], []
    groups = [[] for _ in range(5)]
    for event in events:
        attempt = (event['topic'], event.get('attempt_id', event['id']))
        if attempt in attempts:
            continue
        attempts.add(attempt)
        if (event['kind'] != 'assessment' or not event['independent']
                or not event['observed'] or event['technical_error']):
            continue
        family = (event['topic'], event['family'], _time(event['at']).date())
        if family in families:
            continue
        families.add(family)
        prediction = event.get('prediction_before')
        if not isinstance(prediction, dict):
            continue
        predicted = prediction.get('p_success')
        if (isinstance(predicted, bool) or not isinstance(predicted, (int, float))
                or not math.isfinite(predicted) or not 0 <= predicted <= 1):
            continue
        actual = int(event['passed'])
        sample = (float(predicted), actual)
        samples.append(sample)
        groups[min(int(predicted * 5), 4)].append(sample)
        if prediction.get('status') == 'mastered':
            followups.append(actual)
    bins = []
    for index, group in enumerate(groups):
        count = len(group)
        bins.append({
            'lower': index / 5, 'upper': (index + 1) / 5, 'n': count,
            'mean_predicted': sum(p for p, _ in group) / count if count else None,
            'actual_pass_rate': sum(y for _, y in group) / count if count else None,
        })
    followup_count = len(followups)
    return {
        'sample_count': len(samples),
        'brier_score': (sum((p - y) ** 2 for p, y in samples) / len(samples)
                        if samples else None),
        'calibration_bins': bins,
        'confirmed_followups': {
            'count': followup_count,
            'pass_rate': sum(followups) / followup_count if followup_count else None,
            'false_confirmation_rate': ((followup_count - sum(followups)) / followup_count
                                        if followup_count else None),
        },
        'source': 'local_observations', 'effectiveness_validated': False,
    }


def _entropy(probability):
    if probability <= 0 or probability >= 1:
        return 0.0
    return -probability * math.log2(probability) - (1 - probability) * math.log2(1 - probability)


def _information_gain(probability, slip, guess):
    passed = probability * (1 - slip) + (1 - probability) * guess
    return max(0.0, _entropy(probability)
        - passed * _entropy(_posterior(probability, True, slip, guess))
        - (1 - passed) * _entropy(_posterior(probability, False, slip, guess)))


def select_task(profile, catalog, topic='', at=None):
    """Choose a short useful task; callers filter course prerequisites first.

    The caller must select a fresh instance when presenting a returned template.
    No mastered/not-due topic and no already scored same-family/day assessment
    is offered. Uncovered structures take priority, then information per second.
    """
    parameters = _profile(profile)
    if topic and topic not in CONCEPTS:
        raise ValueError('unknown selection topic')
    now = _time(at)
    summaries = summarize(profile, now)
    day_families = set()
    for event in profile['events']:
        instant = _time(event['at'])
        if (instant <= now and instant.date() == now.date()
                and event.get('kind', 'assessment') == 'assessment'
                and event.get('observed') and event.get('independent')
                and not event.get('technical_error')):
            day_families.add((event['topic'], event['family']))
    candidates = []
    for index, item in enumerate(catalog):
        if not isinstance(item, dict):
            raise ValueError('catalog items must be objects')
        for name in ('id', 'topic', 'family'):
            if not isinstance(item.get(name), str) or not item[name]:
                raise ValueError(f'catalog {name} must be a nonempty string')
        if item['topic'] not in CONCEPTS:
            raise ValueError('unknown catalog topic')
        if type(item.get('version')) is not int or item['version'] < 1:
            raise ValueError('catalog version must be a positive integer')
        duration = _number(item.get('duration_seconds'), 'duration_seconds', 0, 100000)
        slip, guess = _test_parameters(item, parameters)
        kind = item.get('kind', 'assessment')
        if kind not in ('assessment', 'training'):
            raise ValueError('catalog kind must be assessment or training')
        if (not isinstance(item.get('objectives'), list) or not item['objectives']
                or any(not isinstance(v, str) or not v for v in item['objectives'])):
            raise ValueError('catalog objectives must be a nonempty string list')
        if topic and item['topic'] != topic:
            continue
        summary = summaries[item['topic']]
        if summary['status'] == 'mastered':
            continue
        if kind == 'assessment' and (item['topic'], item['family']) in day_families:
            continue
        want_assessment = summary['decision'] in ('placement_check', 'assess', 'reassess')
        stage_fit = (kind == 'assessment') == want_assessment
        uncovered = item['family'] not in summary['passed_families']
        information = _information_gain(summary['p_mastery'], slip, guess) / duration
        priority = (stage_fit, summary['status'] == 'review_due', uncovered, information, -index)
        candidates.append((priority, item))
    return deepcopy(max(candidates, key=lambda candidate: candidate[0])[1]) if candidates else None
