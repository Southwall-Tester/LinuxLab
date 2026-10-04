"""Bounded local error episodes; model hypotheses never become observations."""
import copy
import hashlib
import json


def _input_key(s, words):
    # Local-only equality key; do not retain or send the command text to AI.
    return hashlib.sha256(json.dumps([s.get('id', ''), words], ensure_ascii=False).encode()).hexdigest()


def _correction_key(s, item, words):
    expected, observed, kind = item['expected'], item['observed'], item['kind']
    if not expected or any(word in ('--help', '--version') for word in words):
        return None
    candidate = list(words)
    if kind in ('command_typo', 'command_case'):
        candidate[0] = expected
    elif kind == 'command_spacing' and observed == 'cd..':
        candidate = ['cd', '..', *words[1:]]
    elif kind.startswith(('path_', 'option_')) and words[1:].count(observed) == 1:
        # Require the same surrounding arguments and the same token position.
        # Ambiguous repetitions or normalized path spellings remain unresolved.
        candidate[words.index(observed, 1)] = expected
    else:
        return None
    return _input_key(s, candidate)


def _state(s):
    from learning import learning_state
    return learning_state(s).setdefault('input_errors', {'sequence': 0, 'patterns': {}, 'events': []})


def report_copy(value):
    """Keep internal command/state equality fingerprints out of shared reports."""
    if isinstance(value, dict):
        return {key: report_copy(item) for key, item in value.items()
                if key not in ('correction_keys', 'observation_key')}
    if isinstance(value, list):
        return [report_copy(item) for item in value]
    return value


def record(s, items, words, exit_code, location, phase, at):
    """Count actual failed inputs separately from episodes of the same problem."""
    if not items and 'input_errors' not in s.get('learning', {}):
        return
    state = _state(s)
    if exit_code == 0 and words:
        for pattern in state['patterns'].values():
            if not pattern['active'] or pattern['phase'] != phase or pattern['location'] != location:
                continue
            corrected = (not any(word in ('--help', '--version') for word in words)
                         and _input_key(s, words) in pattern.get('correction_keys', []))
            if corrected:
                pattern['active'] = False
                pattern['resolved_episodes'] += 1
                pattern['last_success'] = at
                # This confirms a related successful input, not its mental cause.
                pattern['resolution'] = '后续观察到使用候选修正的同类命令成功；不证明已掌握知识。'
    for item in items:
        state['sequence'] += 1
        event_id = f'input-{state["sequence"]}'
        signature = item['signature']
        pattern = state['patterns'].get(signature)
        if pattern is None:
            pattern = dict(copy.deepcopy(item), attempts=0, episodes=0, resolved_episodes=0,
                           first_seen=at, last_seen=at, phases=[], active=False, phase=phase)
            state['patterns'][signature] = pattern
        if not pattern['active'] or pattern['phase'] != phase:
            pattern['episodes'] += 1
            pattern['correction_keys'] = []
        pattern.update(active=True, phase=phase, last_seen=at, last_id=event_id,
                       shell_sequence=s.get('shell_sequence', 0))
        pattern['attempts'] += 1
        correction = _correction_key(s, item, words)
        if correction:
            keys = pattern.setdefault('correction_keys', [])
            if correction not in keys:
                keys.append(correction)
            del keys[:-8]
        if phase not in pattern['phases']:
            pattern['phases'].append(phase)
        state['events'].append(dict(id=event_id, at=at, phase=phase,
                                    kind=item['kind'], command=item['command'],
                                    observation=item['summary'], certainty=item['certainty'],
                                    signature=signature))
        from learning import touch_topic
        topic = touch_topic(s, item['concept'], at)
        topic['last_seen'] = at
        topic['next_review'] = min(topic['next_review'], at)
    del state['events'][:-500]
    while len(state['patterns']) > 200:
        oldest = min(state['patterns'], key=lambda k: state['patterns'][k]['last_seen'])
        del state['patterns'][oldest]


def current_issue(s, phase):
    state = s.get('learning', {}).get('input_errors', {})
    candidates = [p for p in state.get('patterns', {}).values() if p['active'] and p['phase'] == phase]
    if not candidates:
        return None
    pattern = max(candidates, key=lambda p: p['shell_sequence'])
    check = s.get('learning', {}).get('active_issue')
    if check and check.get('phase') == phase:
        boundary = next((e.get('operation_cursor', 0) for e in reversed(s['events'])
                         if e.get('phase') == phase and e.get('result') == 'retry'), 0)
        if pattern['shell_sequence'] <= boundary:
            return None
    return {'code': pattern['kind'], 'observation': pattern['summary'],
            'concepts': [pattern['concept']], 'possible_causes': [
                '输入片段与本地检查结果支持这一候选解释；不代表已经确定学习者的理解问题。'],
            'certainty': pattern['certainty'], 'evidence': list(pattern['evidence']),
            'input_error': True, 'pattern': copy.deepcopy(pattern)}


def context(s, phase):
    state = s.get('learning', {}).get('input_errors', {})
    evidence = [e for e in state.get('events', []) if e['phase'] == phase][-12:]
    signatures = {e['signature'] for e in evidence}
    patterns = [p for k, p in state.get('patterns', {}).items() if k in signatures]
    fields = ('kind', 'command', 'observed', 'expected', 'location', 'attempts',
              'episodes', 'resolved_episodes', 'concept', 'last_seen', 'active', 'phase')
    return {'evidence': [{k: e[k] for k in ('id', 'kind', 'command', 'observation', 'certainty', 'at', 'phase')}
                         for e in evidence],
            'patterns': [{k: p[k] for k in fields} for p in patterns],
            'limits': ['未采集原生 stderr、按键或编辑器内部过程。',
                       'attempts 是失败输入次数；episodes 是同一问题的连续尝试段，不是知识缺陷次数。',
                       'resolved_episodes 仅表示观察到使用候选修正的相关命令成功。',
                       '记录仅来自本局，不能推断跨周目习惯；无法确定的原因应给出验证目标。']}


def lines(s):
    state = s.get('learning', {}).get('input_errors', {})
    patterns = sorted(state.get('patterns', {}).values(), key=lambda p: (-p['episodes'], -p['attempts']))[:12]
    result = ['具体输入问题（本局有限观察，原因仍需核实）：']
    for p in patterns:
        result += [f'- {p["summary"]}',
                   f'  位置：{p["location"]}；关卡：' + '、'.join(map(str, p['phases'])) +
                   f'；失败输入 {p["attempts"]} 次，连续尝试段 {p["episodes"]} 段，相关修正后成功 {p["resolved_episodes"]} 段。',
                   f'  最近证据：{p["last_id"]}；最近时间：{p["last_seen"]}。']
    if not patterns:
        result.append('尚无已识别的具体输入问题。')
    result.append('同一问题连试三次记为三次输入、一个尝试段；它们不等于三个独立知识错误。')
    return result
