"""Learner speech and provided assistance, separate from diagnostic candidates."""
import re
import unicodedata

import ai_tutor
from knowledge import CONCEPTS

POLICY = 'linuxlab-dialogue-v1'
COMMANDS = frozenset('pwd cd ls mkdir cp mv rm cat head tail tar chmod top ps id grep find du df vim'.split())
KINDS = frozenset(('question', 'explanation', 'reported_error', 'uncertainty'))
TERMS = {'paths': ('相对路径', '绝对路径', '工作目录'), 'hidden': ('隐藏文件',),
         'copy': ('复制', '拷贝'), 'move': ('移动', '重命名'), 'glob': ('通配符',),
         'archive_read': ('解包', '解压', '归档成员'), 'logs': ('日志', '记录类型'),
         'config': ('配置', '重复键'), 'editing': ('缓冲区', '编辑器', '保存文件'),
         'permissions': ('权限', '执行位'), 'execution': ('脚本',), 'process': ('进程', 'PID'),
         'archive_build': ('打包', '归档快照'), 'integrity': ('原件', '完整性')}
RAW_FIELDS = ('id', 'sequence', 'phase', 'at', 'answered_at', 'event_cursor', 'response_event_id',
              'operation_cursor', 'response_operation_cursor', 'prior_help_level', 'learner', 'assistant')


def instructions():
    topics = {f'concept:{key}': value['title'] for key, value in CONCEPTS.items()}
    topics.update({f'command:{name}': name for name in sorted(COMMANDS)})
    return ('同时返回 signals 数组，最多三项，可为空。它是辅助诊断候选，不是确诊或评分。'
            '仅分析本次学习者原话，不把你自己的回答或以前的 AI 回答当成学习者观点。'
            '每项严格包含 topic、kind、quote、hypothesis。topic 从下面词表选取；'
            'kind 只能是 question（提问）、explanation（解释）、reported_error（自述报错）、'
            'uncertainty（表达不确定）。quote 必须逐字引用本次学习者文字中的连续片段，最多320字；'
            'hypothesis 最多240字，只给待核验的理解线索或替代解释，不能判定掌握、能力差或确诊。'
            '普通提问不等于理解错误，自述报错不等于实际观察；兴趣闲聊可返回空数组。'
            '不确定 topic 时留空数组，不机械关联本关全部知识。允许主题：' + str(topics))


def fallback(question):
    names = list(dict.fromkeys(re.findall(r'(?<![A-Za-z0-9_-])[a-z]+(?![A-Za-z0-9_-])', question)))
    topics = [('command:' + name, name) for name in names if name in COMMANDS]
    topics += [('concept:' + key, next(word for word in words if word in question))
               for key, words in TERMS.items() if any(word in question for word in words)]
    return [dict(topic=topic, kind='question' if re.search(r'[?？]|怎么|为什么|什么', question) else 'explanation',
                 quote=question if len(question) <= 320 else word, hypothesis='原话提及相关词项；仅为词项关联，需结合解释和实际操作核验，不能据此认定知识错误。')
            for topic, word in topics[:3]]


def sanitize(value, state, api_key=''):
    return ''.join(c for c in ai_tutor.redact(value, state, api_key)
                   if not unicodedata.category(c).startswith('C') or c in '\n\t').strip()


def candidates(value, question, state, api_key=''):
    """Bad diagnostic metadata never hides an otherwise usable tutor reply."""
    valid_topics = {'concept:' + k for k in CONCEPTS} | {'command:' + k for k in COMMANDS}
    signals = value.get('signals') if isinstance(value, dict) else None
    valid = isinstance(signals, list) and len(signals) <= 3
    if valid:
        for item in signals:
            if not isinstance(item, dict) or set(item) != {'topic', 'kind', 'quote', 'hypothesis'}:
                valid = False
                break
            if (not all(isinstance(v, str) for v in item.values()) or item['topic'] not in valid_topics
                    or item['kind'] not in KINDS or not 1 <= len(item['quote']) <= 320
                    or item['quote'] not in question or not 1 <= len(item['hypothesis']) <= 240
                    or any(unicodedata.category(c).startswith('C') and c not in '\n\t' for v in item.values() for c in v)
                    or ai_tutor.redact(item['hypothesis'], state, api_key) != item['hypothesis']):
                valid = False
                break
    return dict(policy_version=POLICY, origin='model_inference' if valid else 'local_rule',
                status='unverified', signals=signals if valid else fallback(question))


def record(state, turn, analysis, request_state):
    """Use two cursors: work during HTTP is not work after receiving help."""
    state['dialogue_total'] = state.get('dialogue_total', 0) + 1
    raw = dict(id=turn['id'], sequence=state['dialogue_total'], phase=turn['phase'],
               at=turn['requested_at'], answered_at=turn['at'],
               event_cursor=len(request_state['events']), response_event_id=len(state['events']),
               operation_cursor=request_state.get('shell_sequence', 0),
               response_operation_cursor=state.get('shell_sequence', 0),
               prior_help_level=max((e.get('level', 0) for e in request_state['events']
                                     if e.get('phase') == turn['phase'] and e.get('result') in ('hint', 'tutor')), default=0),
               learner=turn['user'], assistant=turn['assistant'])
    state['dialogue_evidence'] = (state.get('dialogue_evidence', []) + [raw])[-100:]
    state['dialogue_analysis'] = (state.get('dialogue_analysis', []) + [dict(turn_id=turn['id'], **analysis)])[-100:]


def export(state):
    raw = [{key: row[key] for key in RAW_FIELDS} for row in state.get('dialogue_evidence', [])]
    analyses = [{key: row[key] for key in ('turn_id', 'policy_version', 'origin', 'status', 'signals')}
                for row in state.get('dialogue_analysis', [])]
    return dict(dialogue_evidence=raw, dialogue_analysis=analyses, dialogue_total=state.get('dialogue_total', 0))
