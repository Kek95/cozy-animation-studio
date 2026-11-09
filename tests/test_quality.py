import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import quality
import studio

def plan():
    return json.loads((ROOT / 'assets/cozy-episode-project.example.json').read_text())

class PromptContractTests(unittest.TestCase):
    def test_new_plan_passes_and_is_not_mutated(self):
        d = plan(); before = copy.deepcopy(d)
        self.assertEqual(studio.validate(d) + quality.preflight(d), [])
        self.assertEqual(d, before)
        self.assertTrue(90 <= d['duration'] <= 120)

    def test_rejects_action_that_does_not_fit_its_edit(self):
        d = plan(); d['shots'][4]['motion_plan']['active_seconds'] = 30
        self.assertTrue(any('active_seconds' in e for e in quality.preflight(d)))

    def test_non_realtime_speed_requires_explicit_intent(self):
        d = plan(); d['shots'][0]['motion_plan']['speed_mode'] = 'slow'
        self.assertTrue(any('speed' in e for e in quality.preflight(d)))
        d['shots'][0]['motion_plan']['intentional_speed_change'] = 'User explicitly requested slow motion of rain.'
        self.assertEqual(quality.preflight(d), [])

    def test_rejects_scene_version_drift(self):
        d = plan(); d['shots'][4]['continuity']['layout_version'] = 'unapproved-room-v9'
        self.assertTrue(any('layout_version' in e for e in quality.preflight(d)))

    def test_rejects_window_reset_and_undeclared_prop_change(self):
        d = json.loads((ROOT / 'assets/single-process-project.example.json').read_text())
        c = next(s['continuity'] for s in d['shots'][1:]
                 if not s['continuity'].get('time_ellipsis')
                 and s['continuity']['prop_states_in'].get('window') != 'closed')
        c['prop_states_in']['window'] = 'closed'
        self.assertTrue(any('resets prior' in e for e in quality.preflight(d)))
        self.assertTrue(any('allowed_state_changes' in e for e in quality.preflight(d)))

    def test_transition_requires_a_reason_and_tracks_new_state(self):
        d = plan(); next(s for s in d['shots'] if s['continuity'].get('time_ellipsis'))['continuity']['transition_reason'] = ''
        self.assertTrue(any('transition_reason' in e for e in quality.preflight(d)))

    def test_missing_contact_chain_and_invalid_range(self):
        d = plan(); d['shots'][4]['interaction']['ordered_steps'] = []
        d['duration_range'] = [120, 90]
        errors = quality.preflight(d)
        self.assertTrue(any('ordered_steps' in e for e in errors))
        self.assertTrue(any('duration_range' in e for e in errors))

    def test_preflight_cli_fails_read_only_without_submitting(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / 'project.json'; d = plan(); del d['shots'][0]['interaction']; f.write_text(json.dumps(d)); before = f.read_bytes()
            p = subprocess.run([sys.executable, str(ROOT / 'scripts/studio.py'), 'preflight', td], capture_output=True, text=True)
            self.assertEqual(p.returncode, 1)
            self.assertFalse(json.loads(p.stdout)['valid'])
            self.assertEqual(f.read_bytes(), before)
            self.assertEqual(sorted(x.name for x in Path(td).iterdir()), ['project.json'])

    def test_explicit_short_sample_keeps_requested_duration(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run([sys.executable, str(ROOT / 'scripts/studio.py'), 'init', td, '--idea', 'sample', '--duration', '30'], check=True, capture_output=True)
            d = studio.load(td)[1]
            self.assertEqual(d['duration'], 30)
            self.assertEqual(d['duration_range'], [30, 30])
            self.assertEqual(d['production_preferences']['shot_count_guidance'], [10, 12])
            self.assertEqual(d['shots'], [])
            self.assertIsNone(d['generation']['video'])
