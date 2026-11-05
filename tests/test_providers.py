import copy
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import providers
import studio


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.calls.append(('POST', self.path, self.headers.get('Authorization'), payload))
        if self.server.redirect:
            self.send_response(307)
            self.send_header('Location', self.server.base + '/unexpected-target')
            self.end_headers()
        else:
            self.respond({'data': {'id': 'job/id:1'}, 'private': 'do-not-log'}, self.server.post_status)

    def do_GET(self):
        self.server.calls.append(('GET', self.path, self.headers.get('Authorization'), None))
        if self.path == '/media.mp4':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'fixture-media-bytes')
        else:
            self.respond({'data': {'state': self.server.state, 'urls': [self.server.base + '/media.mp4']}})


class ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.server.calls = []
        self.server.state = 'queued'
        self.server.post_status = 200
        self.server.redirect = False
        self.config = json.loads((ROOT / 'assets/providers/json-http.example.json').read_text())
        self.config.update(name='test-provider', base_url=self.server.base)
        self.config['headers_from_env'] = {'Authorization': {'env': 'COZY_TEST_KEY', 'prefix': 'Bearer '}}
        self.config['submit']['task_id_pointer'] = '/data/id'
        self.config['poll'].update(state_pointer='/data/state', output_urls_pointer='/data/urls')
        self.config_path = self.root / 'provider.json'
        studio.save(self.config_path, self.config)
        self.request_path = self.root / 'request.json'
        studio.save(self.request_path, {'model': 'fixture-model', 'prompt': '猫在窗边', 'image_url': 'https://example.invalid/reference.png'})
        self.doc = {'duration': 5, 'shots': [{'id': 'S01', 'duration': 5, 'generation_duration': 5,
                                          'action': 'cat rests', 'candidates': []}]}
        studio.save(self.root / 'project.json', self.doc)
        self.args = Namespace(project=self.root, provider=self.config_path, shot='S01', candidate='v1',
                              request=self.request_path, execute=True, seconds=None)
        self.env = patch.dict(providers.os.environ, {'COZY_TEST_KEY': 'fixture-secret'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_direct_api_lifecycle_without_comfyui(self):
        result = studio.submit(self.args)
        self.assertEqual(result['task_id'], 'job/id:1')
        self.assertEqual(studio.collect(self.args)[0]['state'], 'pending')
        self.server.state = 'completed'
        result = studio.collect(self.args)
        self.assertEqual(result[0]['state'], 'success')
        self.assertEqual((self.root / result[0]['files'][0]).read_bytes(), b'fixture-media-bytes')
        api_calls = [c for c in self.server.calls if c[1] != '/media.mp4']
        self.assertTrue(all(c[2] == 'Bearer fixture-secret' for c in api_calls))
        media = [c for c in self.server.calls if c[1] == '/media.mp4']
        self.assertIsNone(media[0][2])
        self.assertIn('/tasks/job%2Fid%3A1', [c[1] for c in self.server.calls])
        self.assertEqual(len([c for c in self.server.calls if c[0] == 'POST']), 1)
        record = (self.root / 'project.json').read_text()
        self.assertNotIn('fixture-secret', record)
        self.assertNotIn('/media.mp4', record)
        self.assertNotIn('do-not-log', record)
        self.assertNotIn('prompt_id', record)

    def test_cli_submit_and_collect(self):
        command = [sys.executable, str(ROOT / 'scripts/studio.py')]
        submitted = subprocess.run(command + ['submit', str(self.root), '--provider', str(self.config_path),
            '--request', str(self.request_path), '--shot', 'S01', '--candidate', 'cli-v1', '--execute'],
            capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(submitted.stdout)['state'], 'submitted')
        self.server.state = 'completed'
        collected = subprocess.run(command + ['collect', str(self.root), '--provider', str(self.config_path)],
            capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(collected.stdout)[0]['state'], 'success')

    def test_dry_run_does_not_call_api_or_require_credentials(self):
        self.args.execute = False
        with patch.dict(providers.os.environ, {}, clear=True):
            result = studio.submit(self.args)
        self.assertTrue(result['dry_run'])
        self.assertEqual(self.server.calls, [])
        self.assertEqual(studio.load(self.root)[1]['shots'][0]['candidates'], [])

    def test_uncertain_submit_is_not_repeated_and_can_be_recovered(self):
        self.server.post_status = 503
        with self.assertRaisesRegex(RuntimeError, 'uncertain'):
            studio.submit(self.args)
        candidate = studio.load(self.root)[1]['shots'][0]['candidates'][0]
        self.assertEqual(candidate['state'], 'submission_unknown')
        self.args.candidate = 'v2'
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            studio.submit(self.args)
        self.assertEqual(len(self.server.calls), 1)
        recover = Namespace(project=self.root, provider=self.config_path, shot='S01', candidate='v1',
                            task_id='job/id:1', output_node=None, recover=True, request=None, seconds=None)
        studio.register(recover)
        self.server.state = 'completed'
        self.assertEqual(studio.collect(self.args)[0]['state'], 'success')
        self.assertEqual(len([c for c in self.server.calls if c[0] == 'POST']), 1)

    def test_same_task_ids_in_different_providers_do_not_collide(self):
        studio.submit(self.args)
        config2 = copy.deepcopy(self.config)
        config2['name'] = 'other-account'
        path2 = self.root / 'provider2.json'
        studio.save(path2, config2)
        studio.register(Namespace(project=self.root, provider=path2, shot='S01', candidate='other-v1',
                                  task_id='job/id:1', output_node=None, request=None, seconds=5))
        self.server.state = 'completed'
        self.assertEqual(len(studio.collect(self.args)), 1)
        candidates = studio.load(self.root)[1]['shots'][0]['candidates']
        self.assertEqual([c['state'] for c in candidates], ['success', 'submitted'])

    def test_unknown_state_does_not_trigger_post_or_download(self):
        studio.submit(self.args)
        self.server.calls.clear()
        self.server.state = 'new-provider-state'
        self.assertEqual(studio.collect(self.args)[0]['state'], 'unknown')
        self.assertEqual(len(self.server.calls), 1)
        self.assertEqual(self.server.calls[0][0], 'GET')

    def test_reject_api_redirect_without_replaying_post(self):
        self.server.redirect = True
        with self.assertRaisesRegex(RuntimeError, 'uncertain'):
            studio.submit(self.args)
        self.assertEqual(len(self.server.calls), 1)

    def test_missing_credentials_fail_before_attempt_recorded(self):
        with patch.dict(providers.os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'environment'):
            studio.submit(self.args)
        self.assertEqual(self.server.calls, [])
        self.assertEqual(studio.load(self.root)[1]['shots'][0]['candidates'], [])

    def test_candidate_limit_prevents_paid_submission(self):
        self.doc['limits'] = {'max_candidates_per_shot': 0}
        studio.save(self.root / 'project.json', self.doc)
        with self.assertRaisesRegex(ValueError, 'limit'):
            studio.submit(self.args)
        self.assertEqual(self.server.calls, [])

    def test_embedded_credentials_rejected_before_request(self):
        studio.save(self.request_path, {'model': 'fixture', 'api_key': 'not-a-real-key'})
        with self.assertRaisesRegex(ValueError, 'credentials'):
            studio.submit(self.args)
        self.assertEqual(self.server.calls, [])

    def test_result_field_can_select_a_nested_url(self):
        config = copy.deepcopy(self.config)
        config['poll']['output_urls_pointer'] = '/data/urls/0'
        self.server.state = 'completed'
        result = providers.JsonHttpProvider(config).poll('job/id:1')
        self.assertEqual(len(result['assets']), 1)


class IndependentProjectTests(unittest.TestCase):
    def test_no_implicit_comfyui_backend(self):
        with self.assertRaisesRegex(ValueError, 'Choose a provider'):
            providers.load_provider()

    def test_http_and_credential_url_constraints(self):
        for url in ['http://remote.example.invalid', 'https://user:key@example.invalid', 'file:///tmp/image']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                providers.url_checked(url)

    def test_import_then_review_without_any_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            doc = {'duration': 5, 'shots': [{'id': 'S01', 'action': 'cat', 'duration': 5, 'generation_duration': 5}]}
            studio.save(root / 'project.json', doc)
            file = root / 'external.mp4'
            file.write_bytes(b'external-tool-result')
            studio.import_asset(Namespace(project=root, shot='S01', candidate='v1', file=file,
                                          source_label='external-sdk', task_id=None, seconds=5))
            candidate = studio.load(root)[1]['shots'][0]['candidates'][0]
            self.assertIsNone(candidate['review'])
            studio.select(Namespace(project=root, shot='S01', candidate='v1', verdict='accept',
                                    note='fixture acceptance', asset=0, trim_in=0))
            self.assertEqual(studio.load(root)[1]['shots'][0]['selected_candidate'], 'v1')

    def test_v1_comfyui_records_remain_readable(self):
        old = {'id': 'v1', 'prompt_id': 'legacy-task', 'output_node': '2'}
        self.assertTrue(studio.provider_matches(old, providers.ComfyUIProvider('http://127.0.0.1:8188')))


if __name__ == '__main__':
    unittest.main()
