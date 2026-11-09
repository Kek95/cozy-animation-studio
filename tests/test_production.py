import copy
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import production
import studio


class ProductionGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.doc = json.loads((ROOT / 'assets/daily-montage-30s-project.example.json').read_text())
        self.doc['shots'] = self.doc['shots'][:2]
        self.doc['duration'] = sum(s['duration'] for s in self.doc['shots'])
        self.doc['duration_range'] = [self.doc['duration']] * 2
        self.doc['production_policy']['pilot_shots'] = ['S01']
        self.evidence = 'review.txt'; (self.root / self.evidence).write_text('Fixture observations; not real production acceptance.')
        for ref in self.doc['reference_assets']:
            ref['file'] = ref['id'] + '.png'; (self.root / ref['file']).write_bytes(ref['id'].encode())
            ref['sha256'] = production.sha256(self.root / ref['file'])
            ref['review'] = self.review()
        refs = {r['id']: r for r in self.doc['reference_assets']}
        for s in self.doc['shots']:
            s['image_file'] = s['id'] + '.png'; (self.root / s['image_file']).write_bytes(s['id'].encode())
            s['image_sha256'] = production.sha256(self.root / s['image_file']); s['image_review'] = self.review()
            s['image_conditioning'] = [dict(reference_id=rid, source_sha256=refs[rid]['sha256'],
                method='fixture upload', input_field='images', evidence_file=self.evidence) for rid in s['required_reference_ids']]
            s['video_conditioning'] = dict(source_sha256=s['image_sha256'], method='fixture upload',
                input_field='first_frame', evidence_file=self.evidence)
        self.request = {'model': 'Seedance 2.0 Mini'}

    def review(self):
        return dict(verdict='accept', observations='Fixture observations', evidence=[self.evidence])

    def approve_pilot(self):
        clip = self.root / 'pilot.mp4'; clip.write_bytes(b'fixture-source-not-real-video')
        self.doc['shots'][0]['candidates'] = [dict(id='v1', state='success', files=[clip.name], review=self.review())]
        self.doc['quality_review']['pilot'] = dict(self.review(), shot='S01', candidate='v1', source_sha256=production.sha256(clip))

    def test_planning_examples_have_no_fabricated_assets_and_valid_contracts(self):
        for name in ('cozy-episode-project.example.json', 'daily-montage-30s-project.example.json'):
            d = json.loads((ROOT / 'assets' / name).read_text())
            self.assertEqual(production.plan_errors(d), [])
            self.assertEqual(d['story_mode'], 'daily_montage')
            self.assertTrue(all(s['image_file'] is None and not s['candidates'] for s in d['shots']))
            self.assertTrue(all(r['file'] is None and r['review']['verdict'] == 'pending' for r in d['reference_assets']))
            self.assertGreaterEqual(len(d['story']['life_blocks']), 5)

    def test_references_keyframe_and_conditioning_must_match_actual_files(self):
        s = self.doc['shots'][0]
        self.assertEqual(production.keyframe_errors(self.doc, self.root, s), [])
        (self.root / s['image_file']).write_bytes(b'changed frame')
        self.assertTrue(any('hash' in e for e in production.keyframe_errors(self.doc, self.root, s)))
        s['image_sha256'] = production.sha256(self.root / s['image_file'])
        self.assertTrue(any('video conditioning' in e for e in production.generation_errors(self.doc, self.root, 'S01', self.request)))
        s['image_conditioning'] = []
        self.assertTrue(any('no actual image conditioning' in e for e in production.keyframe_errors(self.doc, self.root, s)))

    def test_pilot_needed_before_expansion_and_old_source_invalidates_it(self):
        self.assertEqual(production.generation_errors(self.doc, self.root, 'S01', self.request), [])
        self.assertTrue(any('pilot' in e for e in production.generation_errors(self.doc, self.root, 'S02', self.request)))
        self.approve_pilot()
        self.assertEqual(production.generation_errors(self.doc, self.root, 'S02', self.request), [])
        (self.root / 'pilot.mp4').write_bytes(b'changed source')
        self.assertFalse(production.pilot_passed(self.doc, self.root))

    def test_model_is_read_from_real_request_not_title_and_pointer_is_explicit(self):
        self.doc['production_policy']['require_pilot'] = False
        for payload in ({'model': 'Seedance 2.5'}, {'metadata': {'model': 'Seedance 2.0 Mini'}}):
            self.assertTrue(production.generation_errors(self.doc, self.root, 'S01', payload))
        nested = {'data': {'model': 'Seedance 2.0 Fast'}}
        self.assertEqual(production.generation_errors(self.doc, self.root, 'S01', nested, '/data/model'), [])
        graph = {'9': {'class_type': 'ByteDance2FirstLastFrameNode', 'inputs': {'model': 'Seedance 2.0 Mini'}}}
        self.assertEqual(production.request_models({'prompt': graph}), ['Seedance 2.0 Mini'])

    def test_blocked_video_never_reserves_candidate_or_calls_provider(self):
        studio.save(self.root / 'project.json', self.doc)
        request = self.root / 'request.json'; studio.save(request, {'model': 'Seedance 2.5'})
        backend = Mock(name='fixture-provider'); backend.name = 'fixture'; backend.config = {}
        args = Namespace(project=self.root, provider='unused', shot='S01', candidate='v1', request=request, execute=True, seconds=None)
        with patch.object(studio, 'backend', return_value=backend):
            with self.assertRaisesRegex(ValueError, 'Generation gate'):
                studio.submit(args)
        backend.submit.assert_not_called(); backend.preflight.assert_not_called()
        self.assertEqual(studio.load(self.root)[1]['shots'][0]['candidates'], [])

    def test_legacy_projects_still_have_plan_errors_in_read_only_check(self):
        self.doc.pop('production_policy'); self.doc['duration'] += 1
        result = production.check(self.doc, self.root, 'video', 'S01', self.request)
        self.assertFalse(result['ready']); self.assertTrue(result['blockers'])

    def test_extraction_and_technical_success_never_claim_viewing_or_listening(self):
        final = self.root / 'final.mp4'; final.write_bytes(b'fixture-final')
        digest = production.sha256(final); self.doc['final_file'] = final.name
        studio.save(self.root / 'technical.json', {'valid': True, 'sha256': digest})
        studio.save(self.root / 'cuts.json', {'source_sha256': digest})
        self.doc['quality_review'].update(technical_report='technical.json', cut_evidence='cuts.json')
        result = production.check(self.doc, self.root, 'final')
        self.assertTrue(result['can_deliver_test']); self.assertFalse(result['ready']); self.assertEqual(len(result['pending_reviews']), 3)
        for key, method in [('final_cuts','encoded_cut_frames'),('final_visual','continuous_playback'),('final_audio','subjective_listening')]:
            self.doc['quality_review'][key] = dict(state='passed', method=method, source_sha256=digest,
                observations='Fixture observation', evidence=[self.evidence])
        self.assertTrue(production.check(self.doc, self.root, 'final')['ready'])
        final.write_bytes(b'changed final')
        self.assertFalse(production.check(self.doc, self.root, 'final')['can_deliver_test'])

    def test_evidence_paths_cannot_point_outside_project(self):
        with self.assertRaises(ValueError): production.local_file(self.root, '../outside.txt')
        self.doc['shots'][0]['image_review']['evidence'] = []
        self.assertTrue(production.keyframe_errors(self.doc, self.root, self.doc['shots'][0]))
