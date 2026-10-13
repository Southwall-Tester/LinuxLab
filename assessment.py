"""Standalone learner profile, isolated short assessments and teaching decisions.

The story save, immutable first submissions, and derived probability profile are
different records. A new story round shares the local learner, never its files.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import stat

import assessment_tasks
from knowledge import CONCEPTS, PHASE_CONCEPTS
import mastery

REASONS = {
    'start_with_independent_placement': '先完成起点短测，系统会据此安排练习。',
    'need_two_independent_structural_families': '下一步完成不同结构的独立短测。',
    'below_confirmation_threshold': '继续练习并完成达标短测，达到 95% 后确认掌握。',
    'threshold_and_independent_family_coverage_met': '已达到概率阈值，并通过至少两种结构的独立短测。',
    'previous_confirmation_requires_new_independent_check': '已到复习时间或出现新的困难，安排一次独立复测。',
    'new_independent_failure_requires_reassessment': '最近独立短测发现薄弱点，修正后用新变式复测。',
}


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def safe(root, relative):
    root = Path(root)
    rel = Path(relative)
    if root.is_symlink() or rel.is_absolute() or '..' in rel.parts:
        raise ValueError('画像或短测路径异常，请保留现场。')
    path = root
    for part in rel.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('画像和短测目录不能包含符号链接。')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('短测路径离开了学习目录。')
    return path


def read(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 20_000_000:
        raise ValueError('画像或短测记录格式异常，请保留现场。')
    return json.loads(path.read_text(encoding='utf-8'))


def atomic(path, data):
    if path.is_symlink():
        raise ValueError('学习记录不能写入符号链接。')
    temp = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        with temp.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def base(session):
    session = Path(session)
    if session.is_symlink() or session.parent.name != 'sessions' or session.parent.is_symlink():
        raise ValueError('画像需要有效的 LinuxLab 周目目录。')
    return session.parent.parent


@contextmanager
def profile_store(session):
    import fcntl
    folder = base(session)
    path = safe(folder, 'learner-profile.json')
    lockpath = safe(folder, 'learner-profile.lock')
    if lockpath.exists() and not stat.S_ISREG(lockpath.stat().st_mode):
        raise ValueError('画像锁文件类型异常。')
    with lockpath.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        profile = read(path) if path.exists() else mastery.new_profile()
        before = json.dumps(profile, sort_keys=True, ensure_ascii=False)
        yield profile
        if json.dumps(profile, sort_keys=True, ensure_ascii=False) != before:
            atomic(path, profile)


def active(session, state):
    ident = state.get('assessment_active')
    if not ident:
        return None
    if not isinstance(ident, str) or not re.fullmatch('[0-9a-f]{24}', ident):
        raise ValueError('短测编号异常。')
    path = safe(session, 'assessments/' + ident + '.json')
    item = read(path)
    if item.get('id') != ident or item.get('session_id') != state['id']:
        raise ValueError('短测与当前周目不匹配。')
    return item


def save_attempt(session, item):
    atomic(safe(session, 'assessments/' + item['id'] + '.json'), item)


def workdir(session, item):
    return safe(session, 'assessment-work/' + item['id'])


def pending(session, state):
    item = active(session, state)
    return item if item and item['status'] not in ('passed', 'abandoned') else None


def update_profile(session, state, evidence=None):
    # First submission is durable before profile commit. Replaying after a crash
    # is idempotent; a later correction never rewrites that first observation.
    item = active(session, state)
    with profile_store(session) as profile:
        for record in ((item or {}).get('evidence', [])):
            mastery.record(profile, record)
        if evidence:
            mastery.record(profile, evidence)
        summary = mastery.summarize(profile)
        has_evidence = bool(profile['events'])
    if has_evidence or 'learner_profile' in state:
        state['learner_profile'] = dict(policy_version=mastery.POLICY_VERSION,
                                        updated_at=stamp(), topics=summary)
    return summary


def profile_view(session, state, topic='', as_json=False):
    if topic and topic not in CONCEPTS:
        raise ValueError('未知知识点；用 lab profile 查看知识点编号。')
    summaries = update_profile(session, state)
    selected = {topic: summaries[topic]} if topic else summaries
    if as_json:
        return json.dumps(dict(policy_version=mastery.POLICY_VERSION, topics=selected),
                          ensure_ascii=False, indent=2)
    lines = ['我的 Linux 能力画像 · 系统评估', '']
    for key, row in selected.items():
        lines.append(f"{key:14} {CONCEPTS[key]['title']} · {row['label']} · 掌握概率 {row['p_mastery']:.1%}")
        if topic:
            titles = {t['family']: t['title'] for t in assessment_tasks.catalog() if t['topic'] == topic}
            lines += [f"下一题预测通过率：{row['p_next_success']:.1%}",
                      '已通过结构变式：' + ('、'.join(titles.get(f, f) for f in row['passed_families']) or '先完成一项短测')]
            lines.extend('  ' + REASONS.get(reason, '根据最近的测评记录安排下一步。') for reason in row['reasons'])
            if row.get('next_review_at'):
                lines.append('建议复习：' + row['next_review_at'])
            with profile_store(session) as profile:
                events = [e for e in profile['events'] if e['topic'] == topic][-3:]
            if events:
                lines.append('最近依据：')
                for event in events:
                    mode = '独立测评' if event['independent'] and event['observed'] else '训练记录'
                    lines.append('  ' + event['at'] + ' · ' + mode + ' · '
                                 + ('通过' if event['passed'] else '尚未通过') + ' · '
                                 + titles.get(event['family'], '九关练习'))
    lines += ['', 'lab next 自动安排下一步；lab assess 知识点 开始达标短测。',
              '当前采用版本化初始参数；系统确认用于教学安排，真实测评记录用于持续校准。']
    return '\n'.join(lines)


def metrics_view(session, state, as_json=False):
    update_profile(session, state)
    with profile_store(session) as profile:
        report = mastery.calibration_report(profile)
    if as_json:
        return json.dumps(report, ensure_ascii=False, indent=2)
    lines = ['本机预测质量记录', f"可用独立测评：{report['sample_count']} 次"]
    if report['sample_count']:
        lines.append(f"概率预测误差（Brier，越低越好）：{report['brier_score']:.4f}")
    else:
        lines.append('完成独立短测后开始积累；旧记录不补造提交前预测。')
    followups = report['confirmed_followups']
    if followups['count']:
        lines.append(f"确认掌握后的独立复测：{followups['count']} 次，通过率 {followups['pass_rate']:.1%}")
    else:
        lines.append('确认掌握后的独立复测：尚无记录。')
    lines.append('这里统计本机实际记录；产品效果验收另用隔离学生与模板的数据集。')
    return '\n'.join(lines)


def brief_profile(state):
    rows = state.get('learner_profile', {}).get('topics', {})
    if not rows:
        return '能力画像：lab profile；个性化练习：lab next。'
    known = sum(row['status'] == 'mastered' for row in rows.values())
    due = sum(row['status'] == 'review_due' for row in rows.values())
    return f'能力画像：已掌握 {known}/{len(CONCEPTS)}，待复习 {due}。lab next 自动安排下一步。'


def notebook_section(state):
    rows = state.get('learner_profile', {}).get('topics', {})
    if not rows:
        return ''
    lines = ['\n## 概率画像与下一步', '',
             '| 知识点 | 系统判断 | 掌握概率 |', '| --- | --- | --- |']
    for key, row in rows.items():
        lines.append(f"| {CONCEPTS[key]['title']} | {row['label']} | {row['p_mastery']:.1%} |")
    lines += ['', '用 lab next 执行个性化学习安排；用 lab profile 知识点 查看概率依据。',
              '系统确认与教师复核分开保存，九关故事进度单独记录。', '']
    return '\n'.join(lines)


# Authored prerequisites govern only the adaptive practice route, not the story
# contract or a new inferred knowledge graph. Explicit topic selection is allowed.
PREREQUISITES = {
    'hidden': ('paths',), 'mkdir': ('paths',), 'copy': ('paths', 'hidden'), 'move': ('copy',),
    'glob': ('hidden',), 'archive_read': ('paths',),
    'logs': ('paths',), 'editing': ('paths',), 'permissions': ('paths',),
    'config': ('editing',), 'execution': ('permissions',), 'process': ('execution',),
    'archive_build': ('archive_read',), 'integrity': ('copy',),
}


def choose(profile, topic=''):
    rows = mastery.summarize(profile)
    candidates = assessment_tasks.catalog()
    if not topic:
        candidates = [task for task in candidates if all(
            rows[parent]['status'] == 'mastered'
            for parent in PREREQUISITES.get(task['topic'], ()))]
    selected = mastery.select_task(profile, candidates, topic=topic)
    if selected is not None:
        return selected
    # An explicit challenge stays available after confirmation. If today's
    # independent structures are exhausted, continue guided practice instead of
    # incorrectly saying the learner has mastered every topic.
    available = [task for task in candidates if (not topic or task['topic'] == topic)
                 and (topic or rows[task['topic']]['status'] != 'mastered')]
    if not available:
        return None
    recent = {e['task_id']: index for index, e in enumerate(profile['events'])}
    selected = min(available, key=lambda task: (
        rows[task['topic']]['p_mastery'], recent.get(task['id'], -1)))
    return dict(selected, practice_only=rows[selected['topic']]['status'] != 'mastered')


def show(session, item):
    task = item['task']
    lines = [f"短测 · {CONCEPTS[task['topic']]['title']} · {task.get('title', task['family'])}",
             '模式：' + ('指导练习' if item['mode'] == 'training' or item['help'] else '独立达标测评'),
             '', task['prompt'], '', '练习目录：' + str(workdir(session, item)),
             '进入目录：cd -- ' + shlex.quote(str(workdir(session, item))),
             '完成后：lab assess submit [题目要求的答案]',
             '需要帮助：lab assess hint；保存稍后继续：exit；结束本题：lab assess abandon。']
    if item.get('last_result'):
        lines += ['', result_text(item)]
    return '\n'.join(lines)


def start(session, state, topic='', adaptive=False):
    if topic and topic not in CONCEPTS:
        raise ValueError('未知知识点；用 lab profile 查看知识点编号。')
    current = pending(session, state)
    if current:
        if topic and topic != current['task']['topic']:
            raise ValueError('当前短测已保存。先完成它，或用 lab assess abandon 结束后再切换。')
        return show(session, current)
    update_profile(session, state)
    with profile_store(session) as profile:
        task = choose(profile, topic)
        if task is None:
            return '当前学习目标均已达标。到期后 lab next 会安排复习；也可 lab assess 知识点 主动挑战。'
        summary = mastery.summarize(profile)[task['topic']]
        events = [e for e in profile['events'] if e['topic'] == task['topic']]
        # Placement is a test. After difficulty, teach then verify on a new task.
        recent_tests = 0
        for event in reversed(events):
            if event['kind'] == 'training':
                break
            if event['kind'] == 'assessment':
                recent_tests += 1
        train = bool(task.get('practice_only') or (adaptive and events
                     and events[-1]['kind'] != 'training'
                     and (summary['p_mastery'] < .4 or recent_tests >= 2)))
    ident = secrets.token_hex(12)
    safe(session, 'assessments').mkdir(exist_ok=True)
    safe(session, 'assessment-work').mkdir(exist_ok=True)
    root = safe(session, 'assessment-work/' + ident)
    root.mkdir()
    manifest = assessment_tasks.create(task['id'], root, ident)
    item = dict(id=ident, session_id=state['id'], created_at=stamp(),
                task=manifest, mode='training' if train else 'assessment', status='active',
                tracking_complete=bool(state.get('tracking_enabled')), observations=[],
                observation_total=0, help=[], evidence=[])
    if train:
        item['help'].append(dict(source='guided_lesson', at=stamp()))
    save_attempt(session, item)
    state['assessment_active'] = ident
    state['assessment_context'] = dict(id=ident, topic=manifest['topic'],
                                      prompt=manifest['prompt'], title=manifest.get('title', ''),
                                      scope=manifest.get('scope', 'Linux 短测'))
    prefix = ('针对本次薄弱点：' + CONCEPTS[task['topic']]['explanation'] + '\n\n') if train else ''
    return prefix + show(session, item)


def help_requested(session, state, source, topic=''):
    item = pending(session, state)
    if not item:
        return False
    target = item['task']['topic']
    if topic and topic not in (target, CONCEPTS[target]['note'], 'all', 'sources', 'basics'):
        return False
    if len(item['help']) < 100:
        item['help'].append(dict(source=source, at=stamp()))
    save_attempt(session, item)
    return True


def teach(session, state):
    item = pending(session, state)
    if not item:
        raise ValueError('先用 lab assess 知识点 开始一个短测。')
    help_requested(session, state, 'assessment_hint')
    topic = CONCEPTS[item['task']['topic']]
    level = min(len(item['help']), 2)
    return ('短测讲解 · ' + topic['title'] + '\n' + topic['explanation'] + '\n'
            + topic['hints'][level] + '\n本题将记录为指导练习，随后用新变式完成独立测评。')


def tracking_off(session, state):
    item = pending(session, state)
    if item:
        item['tracking_complete'] = False
        save_attempt(session, item)


OBSERVED_COMMANDS = frozenset('pwd cd ls mkdir cp mv rm tar cat head tail vim chmod ps top sleep sh bash run.sh diff cmp find grep touch printf echo'.split())


def observe(session, state, line, exit_code, cwd, command_kind=None):
    item = pending(session, state)
    if not item or not state.get('tracking_enabled'):
        return
    line = re.sub(r'^\s*\d+\s+\*?\s*', '', line, count=1)
    try:
        words = shlex.split(line, comments=True)
    except ValueError:
        words = []
    if not words or words[0] == 'lab':
        return
    opaque = any(c in line for c in (';', '|', '&', '\n'))
    name = Path(words[0]).name
    # Help is tracked independently from success. A request at any point makes
    # this a supported trial; later successful operations cannot erase it.
    target = CONCEPTS[item['task']['topic']]['note']
    related = {target, *item['task'].get('required_commands', [])}
    if target == 'navigation':
        related.update(('cd', 'pwd'))
    lookup = (name in related and any(w in ('--help', '-h') for w in words[1:])
              or name in ('man', 'help') and words[-1] in related)
    if lookup:
        if len(item['help']) < 100:
            item['help'].append(dict(source='native_help', at=stamp()))
        save_attempt(session, item)
    if not Path(cwd).resolve().is_relative_to(workdir(session, item).resolve()):
        return
    valid = command_kind in ('file', 'builtin') and not opaque
    command = name if valid and name in OBSERVED_COMMANDS else 'other'
    if command == 'run.sh':
        script = (Path(cwd) / words[0]).resolve()
        if script not in (workdir(session, item) / 'run.sh', workdir(session, item) / 'bin/run.sh'):
            command = 'other'
    item['observation_total'] += 1
    item['observations'].append(dict(sequence=item['observation_total'], at=stamp(),
                                     command=command, exit_code=exit_code,
                                     semantic=valid))
    if len(item['observations']) > 500:
        item['observations'] = item['observations'][-500:]
        item['tracking_complete'] = False
    save_attempt(session, item)


def result_text(item):
    result = item['last_result']
    lines = ['[短测通过]' if result['passed'] else '[继续练习]', result['feedback']]
    for check in result['checks']:
        lines.append(('  ✓ ' if check['passed'] else '  · ') + check['label'])
    if item.get('credit_message'):
        lines.append(item['credit_message'])
    lines.append('下一步：lab next；查看画像：lab profile ' + item['task']['topic'])
    return '\n'.join(lines)


def submit(session, state, answer=''):
    item = active(session, state)
    if not item or item['status'] == 'abandoned':
        raise ValueError('先用 lab assess 知识点 开始短测。')
    if item['status'] == 'passed':
        update_profile(session, state)
        return result_text(item), 0
    if len(answer) > 1000:
        raise ValueError('短测答案过长，请只提交题面要求的内容。')
    result = assessment_tasks.evaluate(item['task'], workdir(session, item), answer, cwd=Path.cwd())
    commands = {o['command'] for o in item['observations'] if o['semantic']
                and (not result['passed'] or o['exit_code'] == 0)}
    required = item['task'].get('required_commands', [])
    observed = item['tracking_complete'] and (not required or any(c in commands for c in required))
    independent = item['mode'] == 'assessment' and not item['help'] and observed
    if result.get('technical_error'):
        item['last_result'] = result
        item['credit_message'] = '本次属于环境问题，保留原测评机会；修复环境后再提交。'
        save_attempt(session, item)
        return result_text(item), 1
    kind = 'assessment' if item['mode'] == 'assessment' and not item['help'] else 'training'
    with profile_store(session) as profile:
        previous = mastery.summarize(profile)[item['task']['topic']]
        probability = previous['p_mastery']
        prediction = dict(p_mastery=probability,
                          p_success=probability * (1 - item['task'].get('slip', .05))
                          + (1 - probability) * item['task'].get('guess', .2),
                          status=previous['status'], policy_version=mastery.POLICY_VERSION,
                          parameter_version=profile['parameter_version'])
    evidence = dict(id='assessment:' + item['id'], attempt_id=item['id'],
                    session_id=state['id'], topic=item['task']['topic'],
                    task_id=item['task']['id'], family=item['task']['family'],
                    contract_version=item['task']['version'], at=stamp(),
                    passed=bool(result['passed']), independent=independent,
                    kind=kind, observed=observed, technical_error=False,
                    slip=item['task'].get('slip', .05), guess=item['task'].get('guess', .2),
                    objectives=item['task'].get('objectives', []), checks=result['checks'],
                    prediction_before=prediction,
                    help=list(item['help']), observations=list(item['observations']),
                    answer=answer)
    if not item['evidence']:
        item['evidence'].append(evidence)
        item['first_result'] = result
        item['credit_message'] = ('独立测评结果已计入画像。' if independent else
                                  '已记录训练结果；用新变式完成独立测评。' if observed else
                                  '已保存作答；开启操作记录，并在练习目录亲自操作后进行新的独立测评。')
    elif result['passed'] and not any(e['kind'] == 'training' and e['passed'] for e in item['evidence']):
        # Feedback exposed after the first result is assistance on a correction.
        evidence.update(id='training:' + item['id'], attempt_id=item['id'] + ':training',
                        kind='training', independent=False)
        item['evidence'].append(evidence)
        item['credit_message'] = '已记录纠错后的训练成果；首次测评保留，下一题验证独立应用。'
    item['last_result'] = result
    item['status'] = 'passed' if result['passed'] else 'submitted'
    if result['passed']:
        state.pop('assessment_context', None)
    save_attempt(session, item)
    summaries = update_profile(session, state)
    row = summaries[item['task']['topic']]
    return (result_text(item) + f"\n系统判断：{row['label']}；掌握概率 {row['p_mastery']:.1%}。",
            0 if result['passed'] else 1)


def abandon(session, state):
    item = active(session, state)
    if not item:
        return '当前没有短测。lab next 开始下一步。'
    update_profile(session, state)
    item['status'] = 'abandoned'
    save_attempt(session, item)
    state.pop('assessment_active', None)
    state.pop('assessment_context', None)
    return '本题现场和已提交结果已保留。用 lab next 安排下一步。'


def in_workdir(session, state):
    item = pending(session, state)
    return bool(item and Path.cwd().resolve().is_relative_to(workdir(session, item).resolve()))


STORY_COMMANDS = {
    'paths': {'cd', 'pwd'}, 'hidden': {'ls'}, 'mkdir': {'mkdir'}, 'copy': {'cp'},
    'move': {'mv'}, 'glob': {'rm'}, 'archive_read': {'tar'}, 'logs': {'tail', 'cat'},
    'config': {'vim'}, 'editing': {'vim'}, 'permissions': {'chmod'},
    'execution': {'sh', 'bash'}, 'process': {'ps', 'top'}, 'archive_build': {'tar'},
    'integrity': {'cp'},
}


def story_pass(session, state, phase):
    """A successful authored story exercise can seed a single learning transition."""
    if not state.get('tracking_enabled'):
        return
    rows = [o for o in state.get('shell_observations', [])
            if o['phase'] == phase and o['exit_code'] == 0
            and o.get('command_kind') in ('file', 'builtin')]
    if any(e['result'] == 'repair' and e.get('phase') == phase for e in state['events']):
        return
    changed = False
    with profile_store(session) as profile:
        for topic in PHASE_CONCEPTS[phase]:
            if not any(o['command'] in STORY_COMMANDS[topic] for o in rows):
                continue
            evidence = dict(id=f"story:{state['id']}:{phase}:{topic}",
                            attempt_id=f"story:{state['id']}:{phase}:{topic}",
                            session_id=state['id'], topic=topic, task_id='story-' + str(phase),
                            family='story-' + str(phase), contract_version=1,
                            at=state['events'][-1]['at'], passed=True, independent=False,
                            kind='training', observed=True, technical_error=False)
            changed = mastery.record(profile, evidence) or changed
    if changed:
        update_profile(session, state)
