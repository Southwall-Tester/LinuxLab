"""Real launcher onboarding against a local HTTP fixture, without a provider."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import threading
import time
import unittest


APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import ai_tutor
import scene_blueprint
from test_scene_blueprint import example_blueprint


class SceneOnboardingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='orbit-scene-onboarding-')
        self.base = Path(self.temp.name)
        self.data = self.base / 'data'
        self.config_path = self.base / 'ai.local.json'
        self.env = dict(os.environ, ORBIT_DATA_DIR=str(self.data),
                        ORBIT_AI_CONFIG=str(self.config_path), PYTHONUTF8='1',
                        TERM='xterm-256color')
        self.env.pop('ORBIT_HOME', None)
        self.blueprint = example_blueprint()
        self.bundle = scene_blueprint.compile_blueprint(self.blueprint)
        self.question = '你想在哪个故事世界里练习 Linux？'
        self.responses = [{'question': self.question}, self.blueprint,
                          {'aligned': True, 'issues': []}]
        self.calls = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                index = len(owner.calls)
                # Do not retain Authorization headers or print credentials.
                owner.calls.append(request)
                content = owner.responses[index] if index < len(owner.responses) else {}
                payload = {'choices': [{'finish_reason': 'stop',
                                       'message': {'content': json.dumps(content, ensure_ascii=False)}}]}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode('utf-8'))

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = dict(ai_tutor.TEMPLATE, enabled=True,
                           base_url=f'http://127.0.0.1:{self.server.server_port}/v1',
                           api_key='onboarding-test-key-private', model='fixture', timeout_seconds=2)
        self.write_config()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.stop_server)

    def stop_server(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
            self.server = None

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')

    def pointer(self):
        return self.data / 'current.json'

    def session(self):
        return Path(json.loads(self.pointer().read_text(encoding='utf-8'))['session'])

    def state(self):
        return json.loads((self.session() / 'state.json').read_text(encoding='utf-8'))

    def sessions(self):
        directory = self.data / 'sessions'
        return sorted(directory.iterdir()) if directory.exists() else []

    def no_session(self):
        self.assertFalse(self.pointer().exists())
        self.assertEqual(self.sessions(), [])

    def seed_offline_session(self):
        result = subprocess.run([sys.executable, str(APP / 'orbit.py'), 'prepare', '--scene', 'space'],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.pointer().exists())

    def failed_launch(self, *args, answer='植物研究所\n'):
        result = subprocess.run(['bash', str(APP / 'start.sh'), *args], env=self.env,
                                input=answer, capture_output=True, text=True, timeout=12)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertNotIn('真实 Bash 已就绪', output)
        self.assertNotIn(self.config['api_key'], output)
        return output

    def open_launcher(self, *args):
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(['bash', str(APP / 'start.sh'), *args], env=self.env,
                                       stdin=slave, stdout=slave, stderr=slave,
                                       start_new_session=True)
        finally:
            os.close(slave)
        captured = bytearray()

        def cleanup():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            os.close(master)
        self.addCleanup(cleanup)

        def wait_for(needle, timeout=12):
            deadline = time.monotonic() + timeout
            while needle.encode('utf-8') not in captured and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        part = os.read(master, 65536)
                    except OSError:
                        break
                    if not part:
                        break
                    captured.extend(part)
                elif process.poll() is not None:
                    break
            if needle.encode('utf-8') not in captured:
                self.fail(f'PTY did not show {needle!r}: ' + captured.decode('utf-8', errors='replace'))

        def send(text):
            os.write(master, text.encode('utf-8'))

        def finish():
            send('exit\n')
            process.wait(timeout=8)
            self.assertEqual(process.returncode, 0)
            output = captured.decode('utf-8', errors='replace')
            self.assertNotIn(self.config['api_key'], output)
            return output

        return wait_for, send, finish, captured

    def test_real_launcher_interviews_generates_then_resumes_without_api(self):
        wait_for, send, finish, captured = self.open_launcher('--new')
        wait_for(self.question)
        wait_for('你的主题：')
        self.assertEqual(len(self.calls), 1)
        self.no_session()
        self.assertNotIn('真实 Bash 已就绪', captured.decode('utf-8', errors='replace'))
        send('植物研究所\n')
        wait_for('本关工具')
        output = finish()
        self.assertLess(output.index(self.question), output.index('已生成：植物研究所'))
        self.assertLess(output.index('已生成：植物研究所'), output.index('真实 Bash 已就绪'))
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.calls[0]['max_tokens'], 250)
        self.assertEqual(self.calls[1]['max_tokens'], 4500)
        self.assertEqual(self.calls[2]['max_tokens'], 700)
        context = json.loads(self.calls[1]['messages'][1]['content'])
        self.assertEqual(set(context), {'theme', 'teaching_contract', 'asset_roles', 'schema'})
        self.assertEqual(context['theme'], '植物研究所')
        self.assertNotIn(self.config['api_key'], json.dumps(self.calls, ensure_ascii=False))
        state = self.state()
        self.assertEqual(state['scene_bundle'], self.bundle)
        self.assertEqual(state['asset_bindings'], self.bundle['bindings'])
        self.assertEqual(state['done'], [])
        self.assertTrue((self.session() / 'station' / self.bundle['bindings']['airlock']).is_dir())
        self.assertTrue((self.session() / 'station' / self.bundle['bindings']['work']).is_dir())
        original_pointer = self.pointer().read_bytes()
        original_sessions = self.sessions()
        self.stop_server()
        wait_for, send, finish, captured = self.open_launcher()
        wait_for('本关工具')
        resumed = finish()
        self.assertNotIn(self.question, resumed)
        self.assertNotIn('你的主题：', resumed)
        self.assertNotIn('正在联系', resumed)
        self.assertEqual(self.pointer().read_bytes(), original_pointer)
        self.assertEqual(self.sessions(), original_sessions)
        self.assertEqual(self.state()['scene_bundle'], self.bundle)

    def test_disabled_ai_new_launcher_creates_no_session(self):
        self.config['enabled'] = False
        self.write_config()
        output = self.failed_launch('--new')
        self.assertIn('尚未启用', output)
        self.assertIn('--scene space', output)
        self.assertEqual(self.calls, [])
        self.no_session()

    def test_invalid_model_question_creates_no_session(self):
        self.responses = [{'question': '格式错误\x1b[2J'}]
        output = self.failed_launch('--new')
        self.assertIn('兴趣提问格式无效', output)
        self.assertEqual(len(self.calls), 1)
        self.no_session()

    def test_invalid_generated_bundle_creates_no_session(self):
        self.responses[1:] = [{'id': 'incomplete'}, {'id': 'still-incomplete'}]
        output = self.failed_launch('--new')
        self.assertIn('重生成后仍不符合要求', output)
        self.assertEqual(len(self.calls), 3)
        retry = json.loads(self.calls[2]['messages'][1]['content'])
        self.assertIn('本地结构检查未通过', retry['revision_feedback'])
        self.no_session()

    def test_failed_new_generation_preserves_existing_round_and_pointer(self):
        self.seed_offline_session()
        original_pointer = self.pointer().read_bytes()
        original_state = (self.session() / 'state.json').read_bytes()
        original_sessions = self.sessions()
        self.responses[1:] = [{'id': 'incomplete'}, {'id': 'still-incomplete'}]
        self.failed_launch('--new')
        self.assertEqual(self.pointer().read_bytes(), original_pointer)
        self.assertEqual((self.session() / 'state.json').read_bytes(), original_state)
        self.assertEqual(self.sessions(), original_sessions)
        self.config['enabled'] = False
        self.write_config()
        self.failed_launch('--new')
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.pointer().read_bytes(), original_pointer)
        self.assertEqual((self.session() / 'state.json').read_bytes(), original_state)
        self.assertEqual(self.sessions(), original_sessions)

    def test_missing_ai_config_can_resume_existing_round(self):
        self.seed_offline_session()
        self.config_path.unlink()
        original_pointer = self.pointer().read_bytes()
        wait_for, send, finish, captured = self.open_launcher()
        wait_for('本关工具')
        output = finish()
        self.assertNotIn('你的主题：', output)
        self.assertNotIn('正在联系', output)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.pointer().read_bytes(), original_pointer)

    def test_explicit_offline_scene_skips_interview(self):
        self.config['enabled'] = False
        self.write_config()
        wait_for, send, finish, captured = self.open_launcher('--new', '--scene', 'museum')
        wait_for('本关工具')
        output = finish()
        self.assertNotIn('你的主题：', output)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.state()['scene'], 'museum')


if __name__ == '__main__':
    unittest.main()
