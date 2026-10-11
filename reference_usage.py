"""Bounded reference lookups; never retain raw commands or help contents."""
from learning import stamp

TOPICS = frozenset(('basics navigation glob ls pwd cd mkdir cp mv rm cat head tail '
                    'tar chmod top ps id grep find du df vim').split())
SOURCES = frozenset(('notes', 'lab_help', 'command_help', 'man', 'shell_help'))


def record(state, source, topic=''):
    if not state.get('tracking_enabled'):
        return
    topic = 'glob' if topic == '*' else topic
    if source not in SOURCES or (topic and topic not in TOPICS):
        return
    sequence = state.get('reference_total', 0) + 1
    state['reference_total'] = sequence
    rows = state.setdefault('reference_lookups', [])
    rows.append(dict(sequence=sequence, at=stamp(), phase=min(len(state['done']) + 1, 9),
                     source=source, topic=topic, operation_cursor=state.get('shell_sequence', 0),
                     after_completion=len(state['done']) >= 9))
    del rows[:-2000]


def observe_shell(state, words, exit_code, command_kind, complex_line):
    if exit_code != 0 or complex_line or command_kind not in (None, 'file', 'builtin'):
        return
    source, topic = None, ''
    if len(words) == 2 and words[0] in TOPICS and (words[1] == '--help' or words == ['vim', '-h']):
        source, topic = 'command_help', words[0]
    elif len(words) == 2 and words[0] == 'help':
        source, topic = 'shell_help', words[1]
    elif words and words[0] == 'man':
        if len(words) == 2:
            source, topic = 'man', words[1]
        elif len(words) == 3 and words[1] in ('1', '2', '3', '5', '7', '8'):
            source, topic = 'man', words[2]
    if source and topic in TOPICS:
        record(state, source, topic)
