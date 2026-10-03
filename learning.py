"""Local learning evidence and interval review; never a mastery score."""
from datetime import datetime, timedelta, timezone

from knowledge import CONCEPTS, PHASE_CONCEPTS, diagnosis


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def learning_state(s):
    return s.setdefault('learning', {'format': 1, 'concepts': {}, 'tutor_levels': {},
                                     'active_issue': None})


def touch_topic(s, key, at):
    return learning_state(s)['concepts'].setdefault(key, {
        'first_seen': at, 'last_seen': at, 'failures': 0, 'checks_passed': 0,
        'review_successes': 0, 'review_attempts': 0, 'next_review': at,
    })


def record_check(s, phase, passed, code='unknown', at=None, facts=None):
    at = at or stamp()
    state = learning_state(s)
    s['events'][-1]['operation_cursor'] = s.get('shell_sequence', 0)
    previous_issue = state.get('active_issue')
    item = None if passed else diagnosis(code, phase)
    # In a final archive, even a field-format error also involves a saved snapshot.
    if item and phase == 9 and code.startswith('config_'):
        item['concepts'] = list(dict.fromkeys(['archive_build', *item['concepts']]))
    if item:
        from activity import evidence_for
        item['evidence'] = evidence_for(s, phase, item, facts or [])
    keys = PHASE_CONCEPTS[phase] if passed else item['concepts']
    for key in keys:
        entry = touch_topic(s, key, at)
        entry['last_seen'] = at
        entry['checks_passed' if passed else 'failures'] += 1
        if not passed:
            entry['next_review'] = at
            entry['review_successes'] = 0
        elif not entry['failures'] and not entry['review_attempts']:
            entry['next_review'] = (datetime.fromisoformat(at) + timedelta(days=1)).isoformat(timespec='seconds')
    state['active_issue'] = None if passed else dict(item, phase=phase, at=at)
    if passed and previous_issue and previous_issue.get('phase') == phase:
        s['events'][-1]['resolved_observation'] = previous_issue['observation']
    if item:
        s['events'][-1]['diagnosis'] = item
    return item


def active_issue(s, phase):
    item = s.get('learning', {}).get('active_issue')
    if item and item.get('phase') == phase:
        return item
    return diagnosis('unknown', phase)


def tutor_context(s, phase, level=None, topic=''):
    state = learning_state(s)
    item = active_issue(s, phase)
    key = f'{phase}:{topic or item["code"]}'
    selected = level or min(state['tutor_levels'].get(key, 0) + 1, 3)
    state['tutor_levels'][key] = max(selected, state['tutor_levels'].get(key, 0))
    return item, selected


def notebook(s, at=None):
    at = at or stamp()
    entries = s.get('learning', {}).get('concepts', {})
    lines = ['# 我的 Linux 学习手册', '',
             f'关卡检查通过：{len(s["done"])}/9。更新时间：{at}。', '',
             '这里记录观察到的检查结果和复习作答，不等同于掌握程度或独立完成证明。',
             '一次失败可能有多种原因；通过检查也不能证明使用过某条命令或某个编辑器。', '',
             '## 学习记录', '']
    if not entries:
        lines += ['尚无知识点记录。按当前任务练习；检查或主动求助后会逐步积累。',
                  '旧周目的历史错误不自动猜测归因；新的检查会记录具体类别。', '']
    for key, entry in entries.items():
        topic = CONCEPTS[key]
        due = '可复习' if entry['next_review'] <= at else '尚未到建议时间'
        lines += [f'## {topic["title"]}', '', topic['explanation'], '',
                  f'关联失败 {entry["failures"]} 次；关联关卡检查通过 {entry["checks_passed"]} 次。',
                  f'复习作答 {entry["review_attempts"]} 次；当前连续答对 {entry["review_successes"]} 次。',
                  f'首次记录：{entry["first_seen"]}；最近记录：{entry["last_seen"]}。',
                  f'建议复习：{entry["next_review"]}（{due}）。', '',
                  f'查阅：lab notes {topic["note"]}；小练习：lab review {key}。', '']
    lines += ['## 最近的诊断', '']
    diagnostics = [e for e in s['events'] if e.get('diagnosis')][-10:]
    for event in diagnostics:
        item = event['diagnosis']
        lines += [f'- 第 {event["phase"]} 关 · {event["at"]} · {item["observation"]}。',
                  '  可能原因（待核实）：' + '；'.join(item['possible_causes']) + '。']
        for evidence in item.get('evidence', []):
            lines.append('  操作依据：' + evidence)
    if not diagnostics:
        lines.append('尚无结构化诊断记录。')
    resolved = [e for e in s['events'] if e.get('resolved_observation')][-10:]
    if resolved:
        lines += ['', '## 后续检查结果', '']
        for event in resolved:
            lines.append(f'- 第 {event["phase"]} 关在 {event["at"]} 通过检查；此前观察：{event["resolved_observation"]}。')
        lines.append('这说明后续结果满足检查条件，不证明之前推测的原因或具体修正过程。')
    lines += ['', '复习间隔采用 1、7、30 天的可解释规则，不是经验证的个人遗忘曲线；不自动跳过关卡。', '']
    return '\n'.join(lines)


def review(s, topic='', answer='', at=None):
    at = at or stamp()
    entries = s.get('learning', {}).get('concepts', {})
    if not topic:
        lines = ['已遇到知识点的复习清单（不推进关卡）：']
        for key, entry in sorted(entries.items(), key=lambda row:
                                 (row[1]['next_review'] > at, -row[1]['failures'], row[1]['next_review'])):
            status = '现在可复习' if entry['next_review'] <= at else '建议 ' + entry['next_review']
            lines.append(f'  {key} · {CONCEPTS[key]["title"]} · {status}')
        if not entries:
            lines.append('暂无记录。先完成当前任务的观察与练习。')
        lines.append('用法：lab review 知识点；看题后用 lab review 知识点 A/B/C 作答。')
        return '\n'.join(lines)
    if topic not in entries:
        raise ValueError('该知识点尚无本局学习记录。用 lab review 查看可复习清单。')
    item = CONCEPTS[topic]
    if not answer:
        # Mark a presented question; repeated answer submissions cannot advance the interval.
        learning_state(s)['review_pending'] = topic
        return item['title'] + '\n' + item['question'] + '\n' + '\n'.join(item['choices'])
    if answer.upper() not in ('A', 'B', 'C'):
        raise ValueError('复习答案请使用 A、B 或 C；用 lab review 知识点 先看题。')
    if s.get('learning', {}).get('review_pending') != topic:
        raise ValueError('请先用 lab review 知识点 查看本次题目，再作答。')
    entry = entries[topic]
    entry['review_attempts'] += 1
    correct = answer.upper() == item['answer']
    # Same-day repetitions remain practice, not additional spaced-review milestones.
    if correct and entry.get('last_review_day') != at[:10]:
        entry['review_successes'] += 1
        entry['last_review_day'] = at[:10]
        days = [1, 7, 30][min(entry['review_successes'] - 1, 2)]
        entry['next_review'] = (datetime.fromisoformat(at) + timedelta(days=days)).isoformat(timespec='seconds')
    elif not correct:
        entry['review_successes'] = 0
        entry['next_review'] = at
    entry['last_seen'] = at
    learning_state(s).pop('review_pending', None)
    s['events'].append(dict(at=at, result='review', concept=topic, correct=correct))
    return ('本题回答正确。' if correct else '本题尚未答对。') + '\n' + item['explanation'] + '\n关卡进度不变。'
