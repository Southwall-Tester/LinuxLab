"""Real isolated rounds, local HTTP conversations and native terminal recovery."""
from contextlib import contextmanager
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

import test_lab as fixtures
import ai_tutor
import orbit
import pliac_bridge
import tutor_chat

APP = fixtures.APP


class ChatIntegration(unittest.TestCase):
    setUp = fixtures.LabTest.setUp
    tearDown = fixtures.LabTest.tearDown
    cli = fixtures.LabTest.cli
    shell = fixtures.LabTest.shell
    state = fixtures.LabTest.state
    solve_to = fixtures.LabTest.solve_to

    def chat(self, text, *args):
        proc = subprocess.run([sys.executable, str(APP / 'linuxlab.py'), 'chat', *args],
                              input=text, text=True, capture_output=True, env=self.env,
                              cwd=self.root, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout + proc.stderr

    def turns(self):
        return json.loads((self.session / 'tutor-chat.json').read_text())['turns']

    @contextmanager
    def provider(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(handler):
                requests.append(json.loads(handler.rfile.read(int(handler.headers['Content-Length']))))
                reply = ('tar 负责查看、恢复归档，cat 负责读取恢复后的文本清单。'
                         if len(requests) == 1 else '接着刚才的问题：cat -n 会给所有输出行编号，不修改文件。')
                raw = json.dumps({'choices': [{'finish_reason': 'stop', 'message': {
                    'content': json.dumps({'reply': reply}, ensure_ascii=False)}}]}).encode()
                handler.send_response(200)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Content-Length', str(len(raw)))
                handler.end_headers()
                handler.wfile.write(raw)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        Path(self.env['ORBIT_AI_CONFIG']).write_text(json.dumps(dict(
            enabled=True, base_url=f'http://127.0.0.1:{server.server_port}/v1',
            api_key='chat-fixture-private-key', model='fixture', timeout_seconds=3)))
        try:
            yield requests
        finally:
            server.shutdown()
            thread.join(5)
            server.server_close()

    def test_multiturn_http_resume_clear_and_evidence_boundaries(self):
        self.solve_to(3)
        before = self.state()
        artifact = self.root / 'supplies/rescue.tar.gz'
        original = artifact.read_bytes()
        with self.provider() as requests:
            output = self.chat('这一关和 cat 有什么关系，不是 tar 解压吗？\n那 -n 呢？\n/exit\n')
            self.assertIn('AI >', output)
            self.assertIn('不修改文件', output)
            self.assertEqual(len(requests), 2)
            messages = requests[1]['messages']
            self.assertIn('这一关和 cat', messages[-3]['content'])
            self.assertEqual(messages[-2]['role'], 'assistant')
            self.assertIn('tar 负责', messages[-2]['content'])
            context = json.loads(messages[1]['content'].split('\n', 1)[1])
            self.assertIn('给所有输出行编号', context['command_notes']['cat'])
            self.assertIn('tar', context['command_notes'])
            self.chat('继续解释\n/exit\n')
            self.assertEqual(len(requests[2]['messages']), 7)
            self.chat('/clear\n重新开始\n/exit\n')
            self.assertEqual(len(requests[3]['messages']), 3)
            payload = json.dumps(requests, ensure_ascii=False)
            for secret in ai_tutor.private_values(before) + ['chat-fixture-private-key']:
                self.assertNotIn(secret, payload)
        after = self.state()
        self.assertEqual(after['done'], before['done'])
        self.assertEqual(artifact.read_bytes(), original)
        self.assertEqual(len(self.turns()), 4)
        self.assertEqual(self.turns()[0]['user']['origin'], 'learner_expression')
        self.assertEqual(self.turns()[0]['assistant']['origin'], 'model_inference')
        self.assertEqual(after['events'][-1]['level'], 3)
        self.assertEqual(after['events'][-1]['channel'], 'chat')
        after['platform_binding'] = dict(binding_id='fixture', course_id='fixture', course_version=1,
                                         student_id='fixture', mode='preview')
        report = pliac_bridge.snapshot(after)
        self.assertEqual(report['events'][-1]['kind'], 'tutor')
        self.assertEqual(report['events'][-1]['prompt_level'], 3)
        self.assertIn('这一关和 cat', report['dialogue_evidence'][0]['learner']['text'])
        self.assertIn('tar 负责', report['dialogue_evidence'][0]['assistant']['text'])
        self.assertNotIn('这一关和 cat', json.dumps(report['events'], ensure_ascii=False))
        self.assertEqual(report['dialogue_analysis'][0]['status'], 'unverified')
        self.assertEqual(report['dialogue_total'], 4)

    def test_offline_never_calls_provider_and_does_not_execute_input(self):
        marker = Path(self.temp.name) / 'must-not-exist'
        with self.provider() as requests:
            output = self.chat(f'touch {marker}\n/exit\n', '--offline')
            self.assertEqual(requests, [])
        self.assertIn('本地资料模式', output)
        self.assertNotIn('AI >', output)
        self.assertFalse(marker.exists())
        self.assertEqual(self.state()['done'], [])
        self.assertEqual(self.turns()[0]['assistant']['origin'], 'local_material')

    def test_missing_config_and_controls_do_not_claim_ai_or_fake_progress(self):
        original = (self.session / 'state.json').read_bytes()
        self.chat('/help\n/exit\n')
        self.assertEqual((self.session / 'state.json').read_bytes(), original)
        self.assertFalse((self.session / 'tutor-chat.json').exists())
        output = self.chat('pwd 是什么\n')
        self.assertIn('尚未配置 AI', output)
        self.assertIn('本地 >', output)
        self.assertIn('返回 Bash', output)
        self.assertEqual(len(self.turns()), 1)

    def test_oversized_question_is_rejected_and_absolute_path_question_allowed(self):
        output = self.chat('x' * 1300 + '\n/home/example 是绝对路径吗\n/exit\n', '--offline')
        self.assertIn('问题过长', output)
        self.assertEqual(len(self.turns()), 1)
        self.assertTrue(self.turns()[0]['user']['text'].startswith('/home/example'))

    def test_failures_redact_answers_and_provider_keys(self):
        config = dict(api_key='fixture-private-key')
        for reply in ({'reply': self.s['seal']}, {'reply': 'fixture-private-key'},
                      {'reply': 'lab check guessed-answer'}, {'reply': '\x1b[2J'},
                      {'reply': ''}, {'wrong': 'field'}):
            with self.subTest(reply_kind=list(reply)):
                with patch('ai_tutor.load_config', return_value=config), patch('ai_tutor.request_json', return_value=reply):
                    result, notice, source = tutor_chat.respond(self.session, self.s['seal'] + ' fixture-private-key')
                self.assertEqual(source, 'local_material')
                self.assertTrue(notice)
                serialized = json.dumps(self.turns(), ensure_ascii=False)
                self.assertNotIn(self.s['seal'], serialized)
                self.assertNotIn('fixture-private-key', serialized)
        # Ordinary concept examples, digits and command syntax remain useful.
        text = 'cat -n example.txt 显示行号。\nVim 中先按 Esc，再用 :q! 放弃修改。'
        self.assertEqual(tutor_chat.checked_reply({'reply': text}, self.s, ''), text)

    def test_network_does_not_hold_state_lock_and_stale_context_is_discarded(self):
        def change_context(*args, **kwargs):
            with (self.session / 'state.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            tutor_chat.clear(self.session)
            return {'reply': '这段旧语境回答不应显示。'}
        with patch('ai_tutor.load_config', return_value={'api_key': 'fixture-key'}), \
                patch('ai_tutor.request_json', side_effect=change_context):
            reply, notice, source = tutor_chat.respond(self.session, '相对路径是什么')
        self.assertEqual(source, 'context_changed')
        self.assertNotIn('这段旧语境回答', reply)
        self.assertEqual(self.turns(), [])
        self.assertFalse(any(e.get('channel') == 'chat' for e in self.state()['events']))

    def test_next_phase_does_not_send_previous_phase_conversation(self):
        with self.provider() as requests:
            self.chat('上一关的特定话题\n/exit\n')
            self.solve_to(1)
            self.chat('这一关怎么理解\n/exit\n')
            self.assertEqual(len(requests[1]['messages']), 3)
            self.assertNotIn('上一关的特定话题', json.dumps(requests[1], ensure_ascii=False))

    def test_history_is_bounded_without_erasing_help_events(self):
        for index in range(103):
            tutor_chat.respond(self.session, f'问题 {index}', offline=True)
        self.assertEqual(len(self.turns()), 100)
        self.assertEqual(len([e for e in self.state()['events'] if e.get('channel') == 'chat']), 103)
        with patch('ai_tutor.load_config', return_value={'api_key': 'fixture-key'}), \
                patch('ai_tutor.request_json', return_value={'reply': '这是概念解释。'}) as request:
            tutor_chat.respond(self.session, '追问')
        self.assertEqual(len(request.call_args.args[1]), 15)

    def test_invalid_history_and_symlinks_are_preserved(self):
        path = self.session / 'tutor-chat.json'
        path.write_text('broken-json')
        with self.assertRaises(ValueError):
            tutor_chat.respond(self.session, 'test', offline=True)
        self.assertEqual(path.read_text(), 'broken-json')
        path.unlink()
        outside = Path(self.temp.name) / 'outside.json'
        outside.write_text('original')
        path.symlink_to(outside)
        with self.assertRaises(orbit.LabError):
            tutor_chat.respond(self.session, 'test', offline=True)
        self.assertEqual(outside.read_text(), 'original')

    def test_second_chat_exits_promptly_without_blocking_lab(self):
        with (self.session / 'tutor-chat.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            output = self.cli('chat', ok=False)
            self.assertIn('已有答疑对话', output)
            self.assertIn('01', self.cli('status'))

    def test_malformed_model_markdown_remains_readable(self):
        text = '| 选项 | 作用 |\n| --- | --- |\n| -n | 编号 | 多出一列 |'
        self.assertEqual(tutor_chat.display_reply(text), text)

    def test_followup_keeps_authored_command_reference_outside_current_tools(self):
        notes = tutor_chat.command_reference(self.s, '那它的 -n 呢？', [
            {'user': {'text': 'cat怎么用'}, 'assistant': {'text': '用于读取文本'}}])
        self.assertIn('给所有输出行编号', notes['cat'])
        self.assertIn('navigation', notes)

    def test_real_bash_returns_after_exit_interrupt_and_eof(self):
        master, slave = pty.openpty()
        proc = subprocess.Popen(['bash', '--noprofile', '--rcfile', str(APP / 'shellrc.sh'), '-i'],
                                stdin=slave, stdout=slave, stderr=slave, cwd=self.root,
                                env=self.env, start_new_session=True)
        os.close(slave)
        output = bytearray()

        def until(text):
            target = text.encode()
            end = time.monotonic() + 12
            while target not in output:
                if time.monotonic() >= end:
                    self.fail('terminal timeout: ' + output.decode(errors='replace'))
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    output.extend(os.read(master, 65536))
            output.clear()

        try:
            until('真实 Bash 已就绪')
            for leave in (b'/exit\n', b'\x03', b'\x04'):
                os.write(master, b'lab chat --offline\n')
                until('你 > ')
                # Chat waiting for input must not block another normal command.
                self.cli('status')
                os.write(master, leave)
                until('返回 Bash')
                os.write(master, b"printf 'CHAT_%s_OK\\n' RETURN\n")
                until('CHAT_RETURN_OK')
            os.write(master, b'exit\n')
            proc.wait(timeout=10)
            self.assertEqual(proc.returncode, 0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            os.close(master)
        self.assertEqual(self.state()['done'], [])


if __name__ == '__main__':
    unittest.main()
