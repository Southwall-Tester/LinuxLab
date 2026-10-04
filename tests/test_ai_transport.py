"""Provider options and safe failure reporting using an entirely fake opener."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import urllib.error


APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import ai_tutor


def envelope(content='{"ok": true}', finish='stop'):
    return json.dumps({'choices': [{'finish_reason': finish,
                                   'message': {'content': content}}]}).encode('utf-8')


class FakeResponse:
    def __init__(self, raw):
        self.raw = io.BytesIO(raw)
        self.read_sizes = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True
        self.raw.close()

    def read(self, size):
        self.read_sizes.append(size)
        return self.raw.read(size)


class AITransportTest(unittest.TestCase):
    def setUp(self):
        self.config = {'base_url': 'https://api.deepseek.com', 'model': 'fixture',
                       'api_key': 'transport-fixture-private-key', 'timeout_seconds': 3}
        self.messages = [{'role': 'system', 'content': '只输出 JSON。'},
                         {'role': 'user', 'content': '测试'}]
        self.raw = envelope()
        self.error = None
        self.calls = []
        self.responses = []
        self.opener = Mock()
        self.opener.open.side_effect = self.open
        self.factory_patch = patch('ai_tutor.urllib.request.build_opener', return_value=self.opener)
        self.factory = self.factory_patch.start()
        self.network_patch = patch('socket.create_connection', side_effect=AssertionError('network forbidden in transport test'))
        self.network_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.addCleanup(self.network_patch.stop)

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        response = FakeResponse(self.raw)
        self.responses.append(response)
        return response

    def request(self, **kwargs):
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                return ai_tutor.request_json(self.config, self.messages, **kwargs)
        finally:
            # Transport code must never print a key, URL, payload or provider reply.
            self.assertEqual(stdout.getvalue(), '')
            self.assertEqual(stderr.getvalue(), '')

    def assert_failure(self, expected):
        with self.assertRaises(ai_tutor.AIError) as caught:
            self.request()
        self.assertIn(expected, str(caught.exception))
        self.assertNotIn(self.config['api_key'], str(caught.exception))
        self.assertNotIn('provider-private-body', str(caught.exception))
        return caught.exception

    def test_deepseek_options_apply_to_exact_hostname_with_optional_path_or_port(self):
        for base in ('https://api.deepseek.com', 'https://api.deepseek.com/v1',
                     'https://API.DEEPSEEK.COM:443/v1',
                     'https://api.deepseek.com/v1/chat/completions'):
            with self.subTest(base=base):
                self.config['base_url'] = base
                self.assertEqual(self.request(), {'ok': True})
                request, timeout = self.calls[-1]
                payload = json.loads(request.data)
                self.assertEqual(payload['thinking'], {'type': 'disabled'})
                self.assertEqual(payload['response_format'], {'type': 'json_object'})
                self.assertEqual(payload['max_tokens'], 600)
                self.assertEqual(request.full_url.count('/chat/completions'), 1)
                self.assertEqual(timeout, 3)

    def test_deepseek_options_are_not_sent_to_other_or_lookalike_hosts(self):
        for base in ('https://example.invalid/v1', 'http://127.0.0.1:9999/v1',
                     'https://proxy.deepseek.com', 'https://api.deepseek.com.example.invalid',
                     'https://example.invalid/api.deepseek.com'):
            with self.subTest(base=base):
                self.config['base_url'] = base
                self.assertEqual(self.request(max_tokens=4500), {'ok': True})
                payload = json.loads(self.calls[-1][0].data)
                self.assertNotIn('thinking', payload)
                self.assertNotIn('response_format', payload)
                self.assertEqual(payload['max_tokens'], 4500)

    def test_custom_token_budget_headers_and_inputs_preserve_contract(self):
        original_config, original_messages = copy.deepcopy(self.config), copy.deepcopy(self.messages)
        self.assertEqual(self.request(max_tokens=4500), {'ok': True})
        request, timeout = self.calls[0]
        payload = json.loads(request.data)
        self.assertEqual(payload['messages'], self.messages)
        self.assertEqual(payload['model'], self.config['model'])
        self.assertEqual(payload['max_tokens'], 4500)
        self.assertIs(payload['stream'], False)
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + self.config['api_key'])
        self.assertNotIn(self.config['api_key'], request.data.decode('utf-8'))
        self.assertEqual(self.config, original_config)
        self.assertEqual(self.messages, original_messages)
        self.factory.assert_called_once_with(ai_tutor.NoRedirect)
        self.assertEqual(self.responses[0].read_sizes, [131073])
        self.assertTrue(self.responses[0].closed)

    def test_unfinished_responses_keep_specific_error_and_ignore_private_content(self):
        for finish in ('length', 'content_filter', 'tool_calls', 'provider-private-body'):
            with self.subTest(finish=finish):
                content = json.dumps({'secret': self.config['api_key']})
                self.raw = envelope(content, finish)
                error = self.assert_failure('回复未正常完成')
                self.assertNotIn('请求失败', str(error))
                self.assertTrue(self.responses[-1].closed)

    def test_response_size_limit_keeps_specific_error_instead_of_generic_fallback(self):
        self.raw = b'x' * 131073 + self.config['api_key'].encode('ascii')
        error = self.assert_failure('返回内容过长')
        self.assertNotIn('请求失败', str(error))
        self.assertEqual(self.responses[0].read_sizes, [131073])
        self.assertTrue(self.responses[0].closed)

    def test_invalid_outer_or_inner_json_has_json_error_without_echo(self):
        bad_json = 'provider-private-body ' + self.config['api_key']
        for raw in (bad_json.encode('utf-8'), envelope(bad_json), envelope('```json\n{}\n```')):
            with self.subTest(raw_type='envelope' if raw.startswith(b'{') else 'raw'):
                self.raw = raw
                error = self.assert_failure('不是所需 JSON 格式')
                self.assertNotIn('请求失败', str(error))

    def test_malformed_envelope_is_safe_generic_failure(self):
        for result in ({}, {'choices': []}, {'choices': [{'message': {'content': []}}]},
                       {'choices': [{'message': {'content': None}}]}):
            with self.subTest(result=result):
                self.raw = json.dumps(result).encode('utf-8')
                self.assert_failure('回复格式无效')

    def test_timeout_and_http_failures_have_distinct_safe_messages(self):
        self.error = TimeoutError('provider-private-body ' + self.config['api_key'])
        self.assert_failure('请求超时')
        body = io.BytesIO(('provider-private-body ' + self.config['api_key']).encode('utf-8'))
        self.error = urllib.error.HTTPError('https://example.invalid/private', 401,
                                           'provider-private-body ' + self.config['api_key'], {}, body)
        self.assert_failure('HTTP 401')
        self.assertTrue(body.closed)

    def test_redirect_is_not_followed_and_reports_only_status(self):
        body = io.BytesIO(b'provider-private-body')
        self.error = urllib.error.HTTPError('https://example.invalid/private', 302,
                                           self.config['api_key'], {'Location': 'https://other.invalid'}, body)
        self.assert_failure('HTTP 302')
        self.assertEqual(len(self.calls), 1)
        self.factory.assert_called_once_with(ai_tutor.NoRedirect)
        self.assertIsNone(ai_tutor.NoRedirect().redirect_request(None, None, 302, None, None,
                                                                'https://other.invalid'))
        self.assertTrue(body.closed)

    def test_completed_and_missing_finish_reason_are_accepted(self):
        for finish in ('stop', None):
            with self.subTest(finish=finish):
                self.raw = envelope('{"answer": "有效 JSON"}', finish)
                self.assertEqual(self.request(), {'answer': '有效 JSON'})
        self.raw = json.dumps({'choices': [{'message': {'content': '{"ok": true}'}}]}).encode('utf-8')
        self.assertEqual(self.request(), {'ok': True})


if __name__ == '__main__':
    unittest.main()
