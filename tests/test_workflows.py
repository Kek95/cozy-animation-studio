import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch as mock_patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import studio
import providers
import workflow


def example():
    return json.loads((ROOT / 'assets/project-example.json').read_text(encoding='utf-8'))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.graph = workflow.read(ROOT / 'assets/comfyui/seedance20_i2v_api.json')
        self.bindings = workflow.read(ROOT / 'assets/comfyui/seedance20_i2v_bindings.json')

    def test_patch_preserves_reference_connections_and_original(self):
        original = copy.deepcopy(self.graph)
        result = workflow.patch(self.graph, self.bindings, {'prompt': '猫在阳光中伸懒腰', 'duration': 6})
        for node_id, node in self.graph.items():
            for name, value in node['inputs'].items():
                if isinstance(value, list):
                    self.assertEqual(value, result[node_id]['inputs'][name])
        self.assertEqual(self.graph, original)
        self.assertEqual(result['9']['inputs']['model.duration'], 6)

    def test_seedance_preset_forbids_25_and_unsupported_fast_resolution(self):
        self.assertEqual(self.graph['9']['inputs']['model'], 'Seedance 2.0 Mini')
        for values in [{'model': 'Seedance 2.5'}, {'resolution': '4k'}]:
            with self.assertRaises(ValueError): workflow.patch(self.graph, self.bindings, values)
        result = workflow.patch(self.graph, self.bindings, {'model': 'Seedance 2.0 Fast'})
        self.assertEqual(result['9']['inputs']['model'], 'Seedance 2.0 Fast')

    def test_multi_reference_uses_separate_unchanged_image_links(self):
        graph = workflow.read(ROOT / 'assets/comfyui/image_multi_reference_api.json')
        bindings = workflow.read(ROOT / 'assets/comfyui/image_multi_reference_bindings.json')
        result = workflow.patch(graph, bindings, {'image_1': 'style.png', 'image_2': 'cast.png', 'image_3': 'room.png'})
        self.assertEqual(result['1']['class_type'], 'OpenAIGPTImageNodeV2')
        self.assertEqual([result['1']['inputs'][f'model.images.image_{i}'] for i in range(1,4)], [['3',0],['4',0],['5',0]])
        self.assertNotIn('image', result['1']['inputs'])

    def test_reject_link_replacement_and_link_injection(self):
        graph = {'1': {'class_type': 'Source', 'inputs': {'text': 'hello'}},
                 '2': {'class_type': 'Sink', 'inputs': {'image': ['1', 0]}}}
        with self.assertRaises(ValueError):
            workflow.patch(graph, {'image': {'node': '2', 'input': 'image'}}, {'image': 'file.png'})
        with self.assertRaises(ValueError):
            workflow.patch(graph, {'text': {'node': '1', 'input': 'text'}}, {'text': ['2', 0]})

    def test_reject_invalid_duration_and_changed_schema(self):
        for duration in [3, 30, True, float('nan'), float('inf')]:
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                workflow.patch(self.graph, self.bindings, {'duration': duration})
        self.graph['9']['class_type'] = 'DifferentNode'
        with self.assertRaisesRegex(ValueError, 'node class changed'):
            workflow.patch(self.graph, self.bindings, {'duration': 6})

    def test_reject_credentials_and_canvas_format(self):
        for key in ['api_key', 'Authorization', 'access_token']:
            graph = copy.deepcopy(self.graph)
            graph['9']['inputs'][key] = 'test-placeholder'
            with self.subTest(key=key), self.assertRaises(ValueError):
                workflow.patch(graph, self.bindings, {})
        with self.assertRaises(ValueError):
            workflow.patch({'nodes': []}, {}, {})


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.doc = example()
        studio.save(self.root / 'project.json', self.doc)

    def register(self, candidate='v1', prompt_id='test-task-01', shot='S01'):
        return studio.register(Namespace(project=self.root, shot=shot, candidate=candidate,
                                         prompt_id=prompt_id, output_node='2', workflow=None, seconds=None, server='http://127.0.0.1:8188'))

    def test_storyboard_duration_and_edit_handles(self):
        self.assertEqual(studio.validate(self.doc), [])
        self.doc['shots'][0]['duration'] = 7
        errors = studio.validate(self.doc)
        self.assertTrue(any('shorter' in e for e in errors))
        self.assertTrue(any('total' in e for e in errors))

    def test_new_project_requires_music_but_allows_planning_before_assets(self):
        target = self.root / 'new-film'
        studio.init(Namespace(project=target, title='test', idea='a quiet meal', duration=30, ratio='16:9'))
        doc = studio.load(target)[1]
        self.assertIs(doc['audio']['music_required'], True)
        self.assertIsNone(doc['audio']['music'])
        doc['shots'] = example()['shots']
        self.assertEqual(studio.validate(doc), [])

    def test_default_cli_project_accepts_full_length_cozy_plan(self):
        target = self.root / 'default-film'
        subprocess.run([sys.executable, str(ROOT / 'scripts/studio.py'), 'init', str(target),
                        '--idea', '整理阅读角，与猫一起喝茶'], check=True, capture_output=True, text=True)
        doc = studio.load(target)[1]
        plan = json.loads((ROOT / 'assets/cozy-episode-project.example.json').read_text())
        self.assertEqual(doc['duration'], 105)
        doc['shots'] = plan['shots']
        self.assertEqual(studio.validate(doc), [])
        self.assertIsNone(doc['audio']['music'])
        self.assertIsNone(doc['generation']['video'])

    def test_audio_settings_reject_ambiguous_types(self):
        for audio in [None, {'music_required': 'false'}, {'native_audio': 0},
                      {'music': {'path': 'music.wav'}}, {'voiceover': ''}]:
            with self.subTest(audio=audio):
                self.doc['audio'] = audio
                self.assertTrue(any('audio' in error for error in studio.validate(self.doc)))

    def test_invalid_ids_are_reported(self):
        for value in ['../../escape', None, '']:
            self.doc['shots'][0]['id'] = value
            with self.subTest(value=value):
                self.assertTrue(any('Invalid shot ID' in e for e in studio.validate(self.doc)))

    def test_registration_is_idempotent_but_never_reuses_task(self):
        self.assertEqual(self.register()['state'], 'submitted')
        self.assertEqual(self.register()['state'], 'already_registered')
        with self.assertRaises(ValueError):
            self.register(candidate='v2')
        with self.assertRaises(ValueError):
            self.register(prompt_id='test-task-02')
        self.assertEqual(len(studio.load(self.root)[1]['shots'][0]['candidates']), 1)

    def test_unknown_task_only_queries_original_id(self):
        self.register()
        with mock_patch.object(providers, 'request_json', side_effect=[{}, {}]) as request:
            result = studio.collect(Namespace(project=self.root, server='http://127.0.0.1:8188'))
        self.assertEqual(result[0]['state'], 'unknown')
        self.assertEqual([c.args[0] for c in request.call_args_list], ['http://127.0.0.1:8188/history/test-task-01', 'http://127.0.0.1:8188/queue'])

    def test_collect_uses_expected_output_and_safe_local_name(self):
        self.register()
        history = {'test-task-01': {'status': {'status_str': 'success', 'completed': True},
                   'outputs': {'2': {'videos': [{'filename': '../../remote.mp4', 'type': 'output'}]},
                               '99': {'images': [{'filename': 'unwanted.png'}]}}}}
        with mock_patch.object(providers, 'request_json', return_value=history), \
             mock_patch.object(studio, 'download', side_effect=lambda url, dest: dest.write_bytes(b'test-media')):
            result = studio.collect(Namespace(project=self.root, server='http://127.0.0.1:8188'))
        self.assertEqual(result[0]['files'], ['clips/S01/v1-00.mp4'])
        self.assertEqual((self.root / result[0]['files'][0]).read_bytes(), b'test-media')
        with mock_patch.object(providers, 'request_json', return_value={}) as request:
            self.assertEqual(studio.collect(Namespace(project=self.root, server='http://127.0.0.1:8188'))[0]['state'], 'success_cached')
        self.assertEqual(request.call_count, 0)

    def test_collect_current_singular_video_field(self):
        self.register()
        history = {'test-task-01': {'status': {'status_str': 'success', 'completed': True},
                   'outputs': {'2': {'video': [{'filename': 'current.mp4', 'type': 'output'}]}}}}
        with mock_patch.object(providers, 'request_json', return_value=history), \
             mock_patch.object(studio, 'download', side_effect=lambda url, dest: dest.write_bytes(b'fixture')):
            result = studio.collect(Namespace(project=self.root, server='http://127.0.0.1:8188'))
        self.assertEqual(result[0]['state'], 'success')
        self.assertTrue(result[0]['files'][0].endswith('.mp4'))

    def test_review_requires_collected_asset_and_reject_clears_selection(self):
        self.register()
        args = Namespace(project=self.root, shot='S01', candidate='v1', verdict='accept',
                         note='motion checked', asset=0, trim_in=0)
        with self.assertRaises(ValueError):
            studio.select(args)
        _, doc = studio.load(self.root)
        candidate = doc['shots'][0]['candidates'][0]
        candidate.update(state='success', files=['clips/candidate.mp4'])
        (self.root / 'clips').mkdir()
        (self.root / 'clips/candidate.mp4').write_bytes(b'test-media')
        studio.save(self.root / 'project.json', doc)
        studio.select(args)
        args.verdict = 'reject'
        studio.select(args)
        shot = studio.load(self.root)[1]['shots'][0]
        self.assertIsNone(shot['selected_candidate'])
        self.assertNotIn('selected_file', shot)


if __name__ == '__main__':
    unittest.main()
