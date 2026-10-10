"""Optional stdlib-only platform adapter. No network or grading changes.

Only an explicit --manifest launch opts a round into sanitized file exchange.
Standalone rounds keep their original location and behavior.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import tasks
from knowledge import ISSUES, CONCEPTS

SCHEMA = 1
BINDING_KEYS = ('schema', 'binding_id', 'course_id', 'course_version', 'student_id',
                'mode', 'contract_version', 'contract_hash', 'scene', 'report_path')


def descriptor():
    return dict(schema=SCHEMA, course_id=tasks.COURSE_ID,
                contract_version=tasks.CONTRACT_VERSION, contract_hash=tasks.contract_hash(),
                stages=[dict(phase=i, task_id=t['id'], concepts=t['concepts'])
                        for i, t in enumerate(tasks.CONTRACTS, 1)],
                issues={key: dict(observation=value[0], concepts=value[1], hypotheses=value[2])
                        for key, value in ISSUES.items()})


def binding(path):
    path = Path(path)
    if not path.is_absolute() or path.stat().st_size > 100000:
        raise ValueError('平台绑定文件无效。')
    data = json.loads(path.read_text(encoding='utf-8'))
    if (data.get('schema') != SCHEMA or not re.fullmatch('[0-9a-f]{32}', data.get('binding_id', ''))
            or data.get('mode') not in ('preview', 'published')
            or data.get('contract_version') != tasks.CONTRACT_VERSION
            or data.get('contract_hash') != tasks.contract_hash()
            or data.get('scene') not in ('space', 'ocean', 'museum', 'anime', 'ai')
            or not isinstance(data.get('course_version'), int)
            or not isinstance(data.get('course_id'), str)
            or not isinstance(data.get('student_id'), str)):
        raise ValueError('平台绑定与当前任务契约不匹配；请从课程入口创建新周目。')
    target = Path(data.get('report_path', ''))
    if not target.is_absolute() or target.parent.resolve() != path.parent.resolve() or target.name != 'telemetry.json':
        raise ValueError('平台报告必须位于绑定文件同目录。')
    return {key: data[key] for key in BINDING_KEYS}


def attach(state):
    manifest = os.environ.get('PLIAC_LINUXLAB_MANIFEST')
    if not manifest:
        return
    data = binding(manifest)
    previous = state.get('platform_binding')
    if previous and previous != data:
        raise ValueError('本周目已绑定其他课程语境，不能重新分配。')
    state['platform_binding'] = data


def snapshot(state):
    context = state.get('platform_binding')
    if not context:
        return None
    events, levels = [], {}
    # Whitelist export: never forward answers, state, raw commands, paths, AI
    # explanations, diagnosis hypotheses, codes, credentials or free text.
    for cursor, event in enumerate(state['events'], 1):
        phase, kind = event.get('phase'), event.get('result')
        if type(phase) is not int or not 1 <= phase <= 9:
            continue
        if kind not in ('passed', 'retry', 'hint', 'tutor', 'repair'):
            continue
        if kind in ('hint', 'tutor'):
            levels[phase] = max(levels.get(phase, 0), event.get('level', 0))
        item = dict(id=cursor, phase=phase, kind=kind, at=event['at'],
                    prompt_level=levels.get(phase, 0), operation_cursor=event.get('operation_cursor', 0))
        if kind == 'retry':
            diagnosis = event.get('diagnosis', {})
            item.update(issue_code=diagnosis.get('code', 'unknown'),
                        concepts=[c for c in diagnosis.get('concepts', []) if c in CONCEPTS],
                        problem_id=diagnosis.get('problem_id', cursor),
                        repeat_checks=diagnosis.get('repeat_checks', 0))
        events.append(item)
    operations = [{k: e[k] for k in ('sequence', 'at', 'phase', 'command', 'exit_code',
                  'flags', 'operand_roles', 'known_options', 'facts', 'plain_star_excludes_hidden',
                  'config_changed_since_observation', 'command_kind') if k in e}
                  for e in state.get('shell_observations', [])]
    patterns = [dict(id='pattern-' + hashlib.sha256(signature.encode()).hexdigest()[:20],
                     kind=p['kind'], command=p['command'], concept=p['concept'],
                     phase=p['phase'], phases=p['phases'], attempts=p['attempts'], episodes=p['episodes'],
                     resolved_episodes=p['resolved_episodes'], active=p['active'], at=p['last_seen'],
                     operation_cursor=p.get('shell_sequence', 0))
                for signature, p in state.get('learning', {}).get('input_errors', {}).get('patterns', {}).items()]
    return dict(schema=SCHEMA, binding_id=context['binding_id'], course_id=context['course_id'],
                course_version=context['course_version'], student_id=context['student_id'], mode=context['mode'],
                contract_version=state.get('contract_version'), contract_hash=state.get('contract_hash'),
                lab_session_id=state['id'], events=events, operations=operations, input_patterns=patterns,
                tracking_enabled=bool(state.get('tracking_enabled')),
                operation_total=state.get('shell_sequence', 0),
                phases_passed=len(state['done']), completed=len(state['done']) == 9,
                validation_scope='文件结果与当前进程检查；不证明独立完成或概念掌握。')


def publish(state):
    report = snapshot(state)
    if report is None:
        return
    target = Path(state['platform_binding']['report_path'])
    # Atomic replacement across WSL/Windows avoids half-read JSON. Failure
    # cannot roll back native learner progress; a later command retries export.
    fd, name = tempfile.mkstemp(prefix='.telemetry-', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(report, out, ensure_ascii=False)
            out.write('\n')
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def publish_safely(state):
    try:
        publish(state)
    except (OSError, ValueError, KeyError) as exc:
        print('本地进度已保存；课程同步暂未更新：' + str(exc), file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='从 PLIAC 课程绑定启动真实 LinuxLab，或输出任务契约。')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--describe', action='store_true')
    group.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(descriptor(), ensure_ascii=False))
        return
    context = binding(args.manifest)
    if sys.platform != 'linux':
        raise ValueError('实训须在 Linux 或 WSL 中运行。')
    root = Path(__file__).resolve().parent
    # Isolated per-binding POSIX storage; leave ~/.local/share/orbit-lab alone.
    base = Path.home() / '.local/share/pliac-linuxlab' / context['binding_id']
    env = dict(os.environ, ORBIT_DATA_DIR=str(base), PLIAC_LINUXLAB_MANIFEST=str(args.manifest), PYTHONUTF8='1')
    command = ['bash', str(root / 'start.sh')]
    if not (base / 'current.json').exists() and context['scene'] != 'ai':
        command += ['--scene', context['scene']]
    print('PLIAC 草稿试跑（不记入正式学习证据）' if context['mode'] == 'preview' else 'PLIAC 课程实训（检查结果不等于掌握）', flush=True)
    print('操作在本机真实 Bash 中执行；lab hint / lab tutor / lab repair 保持原有用法。', flush=True)
    os.execvpe('bash', command, env)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        print('LinuxLab 课程接入：' + str(exc), file=sys.stderr)
        sys.exit(1)
