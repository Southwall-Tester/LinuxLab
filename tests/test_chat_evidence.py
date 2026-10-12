"""Diagnostic metadata must remain grounded in learner speech, not AI text."""
import json
import unittest
from unittest.mock import patch

import test_lab as fixtures
import chat_evidence
import tutor_chat
import orbit


class ChatEvidenceTests(unittest.TestCase):
    setUp = fixtures.LabTest.setUp
    tearDown = fixtures.LabTest.tearDown
    cli = fixtures.LabTest.cli
    state = fixtures.LabTest.state

    def test_model_candidates_are_saved_separately_with_cursors(self):
        question = '我认为 cat -n 会修改原文件行号，对吗？'
        model = dict(reply='cat -n 只改变输出显示，不会修改原文件。', signals=[dict(
            topic='command:cat', kind='question', quote='cat -n 会修改原文件行号',
            hypothesis='原话可能混淆显示与修改，也可能在核对猜想，需要用无关文件验证。')])
        with patch('ai_tutor.load_config', return_value={'api_key': 'fixture-secret'}), patch('ai_tutor.request_json', return_value=model):
            reply, _, source = tutor_chat.respond(self.session, question)
        state = self.state()
        raw, analysis = state['dialogue_evidence'][0], state['dialogue_analysis'][0]
        self.assertEqual(source, 'model_inference')
        self.assertEqual(raw['learner']['text'], question)
        self.assertEqual(raw['assistant']['text'], reply)
        self.assertEqual(raw['prior_help_level'], 0)
        self.assertEqual(raw['event_cursor'], 0)
        self.assertEqual(raw['response_event_id'], 1)
        self.assertEqual(analysis['origin'], 'model_inference')
        self.assertEqual(analysis['status'], 'unverified')
        self.assertEqual(analysis['signals'], model['signals'])
        self.assertEqual(state['done'], [])

    def test_ai_reply_cannot_be_forged_as_a_learner_quote(self):
        question = 'cat 怎么用？'
        model = dict(reply='不会修改原文件。', signals=[dict(topic='command:cat', kind='explanation',
                     quote='不会修改原文件', hypothesis='此处引用的是 AI 的话，必须拒绝。')])
        with patch('ai_tutor.load_config', return_value={'api_key': 'fixture-secret'}), patch('ai_tutor.request_json', return_value=model):
            reply, _, source = tutor_chat.respond(self.session, question)
        self.assertEqual(reply, '不会修改原文件。')
        self.assertEqual(source, 'model_inference')
        analysis = self.state()['dialogue_analysis'][0]
        self.assertEqual(analysis['origin'], 'local_rule')
        self.assertNotIn('AI 的话', json.dumps(analysis, ensure_ascii=False))

    def test_unknown_concepts_and_unanchored_quotes_fall_back_without_losing_chat(self):
        for override in (dict(topic='concept:invented'), dict(kind='mastered'), dict(quote='AI虚构的学生解释'),
                         dict(hypothesis=self.s['seal']), dict(quote=['not-text'])):
            signal = dict(topic='command:cat', kind='question', quote='cat', hypothesis='需要实际验证。')
            signal.update(override)
            result = chat_evidence.candidates({'signals': [signal]}, 'cat 什么意思', self.s)
            self.assertEqual(result['origin'], 'local_rule')
            self.assertEqual(result['status'], 'unverified')

    def test_work_during_http_is_not_work_after_help(self):
        def concurrent(*args, **kwargs):
            with tutor_chat.locked(self.session) as state:
                state['shell_sequence'] = 1
                orbit.atomic_json(self.session / 'state.json', state)
            return dict(reply='这是概念说明。', signals=[])
        with patch('ai_tutor.load_config', return_value={'api_key': 'fixture-secret'}), patch('ai_tutor.request_json', side_effect=concurrent):
            tutor_chat.respond(self.session, '只是确认一个概念')
        raw = self.state()['dialogue_evidence'][0]
        self.assertEqual(raw['operation_cursor'], 0)
        self.assertEqual(raw['response_operation_cursor'], 1)

    def test_clear_keeps_diagnostic_records_and_help_history(self):
        tutor_chat.respond(self.session, 'pwd 是什么？', offline=True)
        tutor_chat.clear(self.session)
        tutor_chat.respond(self.session, 'cat 是什么？', offline=True)
        state = self.state()
        self.assertEqual(state['dialogue_total'], 2)
        self.assertEqual(state['dialogue_evidence'][1]['prior_help_level'], 3)
        self.assertEqual(state['dialogue_evidence'][0]['sequence'], 1)
        self.assertEqual(state['dialogue_evidence'][1]['sequence'], 2)
        self.assertEqual(len(state['dialogue_analysis']), 2)

    def test_missing_model_metadata_keeps_chinese_explanation_as_weak_topic_evidence(self):
        question = '所以复制整个目录时需要先检查目标是否已存在。'
        result = chat_evidence.candidates({'reply': '这是讲解。'}, question, self.s)
        self.assertEqual(result['origin'], 'local_rule')
        self.assertEqual(result['signals'][0]['topic'], 'concept:copy')
        self.assertEqual(result['signals'][0]['quote'], question)

    def test_repair_during_http_discards_old_context_without_creating_help_evidence(self):
        def repair(*args, **kwargs):
            self.cli('repair')
            return dict(reply='这份旧语境回答不应显示。', signals=[])
        with patch('ai_tutor.load_config', return_value={'api_key': 'fixture-secret'}), patch('ai_tutor.request_json', side_effect=repair):
            reply, _, source = tutor_chat.respond(self.session, 'pwd 怎么理解？')
        self.assertEqual(source, 'context_changed')
        self.assertNotIn('旧语境回答不应显示', reply)
        self.assertEqual(self.state().get('dialogue_total', 0), 0)


if __name__ == '__main__':
    unittest.main()
