import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import edit
import studio


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg and ffprobe required')
class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        for number, color in enumerate(['red', 'blue']):
            cmd = ['ffmpeg', '-hide_banner', '-v', 'error', '-f', 'lavfi', '-i',
                   f'color=c={color}:s=160x90:r=24:d=1.5']
            if number == 0:
                cmd += ['-f', 'lavfi', '-i', 'sine=frequency=330:duration=1.5']
            cmd += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-t', '1.5', str(cls.root / f'clip{number}.mp4')]
            subprocess.run(cmd, check=True, capture_output=True)
        for name, seconds in [('voice', 1), ('music', 0.5), ('long-voice', 3)]:
            subprocess.run(['ffmpeg', '-hide_banner', '-v', 'error', '-f', 'lavfi', '-i',
                            f'sine=frequency=220:duration={seconds}', str(cls.root / f'{name}.wav')],
                           check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.doc = {'duration': 2, 'shots': [
            {'id': f'S{i}', 'duration': 1, 'generation_duration': 1.5, 'action': 'fixture',
             'trim_in': 0.25, 'selected_candidate': 'v1', 'selected_file': f'clip{i}.mp4',
             'candidates': [{'id': 'v1', 'state': 'success', 'files': [f'clip{i}.mp4'],
                             'review': {'verdict': 'accept'}}]} for i in range(2)]}
        studio.save(self.root / 'project.json', self.doc)
        self.args = Namespace(project=self.root, out=str(self.root / f'{self._testMethodName}.mp4'),
                              width=160, height=90, fps=24, fit='pad', mute_native=False, native_db=0,
                              voice=None, voice_db=0, music=None, music_db=-14,
                              loop_music=False, duck_music=False)

    def test_compose_audio_and_silent_shots_exact_duration_and_decode(self):
        result = edit.compose(self.args)
        self.assertAlmostEqual(result['duration'], 2, delta=0.05)
        self.assertEqual(result['full_decode'], 'passed')
        self.assertEqual({s['codec_type'] for s in result['streams']}, {'video', 'audio'})
        video = next(s for s in result['streams'] if s['codec_type'] == 'video')
        self.assertEqual((video['width'], video['height']), (160, 90))
        self.assertEqual([s['shot'] for s in result['sources']], ['S0', 'S1'])
        with self.assertRaisesRegex(ValueError, 'exists'):
            edit.compose(self.args)

    def test_voice_music_duck_and_explicit_loop(self):
        self.args.voice = str(self.root / 'voice.wav')
        self.args.music = str(self.root / 'music.wav')
        self.args.duck_music = True
        with self.assertRaisesRegex(ValueError, 'Music is short'):
            edit.compose(self.args)
        self.args.loop_music = True
        self.assertEqual(edit.compose(self.args)['full_decode'], 'passed')

    def test_long_voice_rejected_without_silent_truncation(self):
        self.args.voice = str(self.root / 'long-voice.wav')
        with self.assertRaisesRegex(ValueError, 'longer than film'):
            edit.compose(self.args)
        self.assertFalse(Path(self.args.out).exists())

    def test_required_music_missing_blocks_final_output(self):
        self.doc['audio'] = {'music_required': True, 'music': None}
        studio.save(self.root / 'project.json', self.doc)
        with self.assertRaisesRegex(ValueError, 'Background music is required'):
            edit.compose(self.args)
        self.assertFalse(Path(self.args.out).exists())

    def test_project_relative_audio_is_mixed_and_can_duck(self):
        self.doc['audio'] = {'music_required': True, 'music': 'long-voice.wav',
                             'voiceover': 'voice.wav', 'native_audio': False}
        studio.save(self.root / 'project.json', self.doc)
        self.args.duck_music = True
        result = edit.compose(self.args)
        self.assertEqual(result['full_decode'], 'passed')
        self.assertTrue(result['audio_mix']['native_muted'])
        self.assertEqual([s['file'] for s in result['audio_mix']['sources']],
                         [str((self.root / 'voice.wav').resolve()), str((self.root / 'long-voice.wav').resolve())])
        # The second shot has no native audio and voice ends at 1s: music must remain.
        import array
        samples = array.array('f', subprocess.check_output(
            ['ffmpeg', '-v', 'error', '-ss', '1.2', '-i', self.args.out,
             '-t', '0.3', '-vn', '-f', 'f32le', '-ac', '1', '-']))
        self.assertGreater(max(abs(v) for v in samples), 0.001)

    def test_cli_music_overrides_project_path(self):
        self.doc['audio'] = {'music_required': True, 'music': 'does-not-exist.wav',
                             'music_source': {'note': 'belongs to the overridden asset'}}
        studio.save(self.root / 'project.json', self.doc)
        self.args.music = str(self.root / 'long-voice.wav')
        result = edit.compose(self.args)
        self.assertEqual(result['audio_mix']['sources'][0]['file'], str(Path(self.args.music).resolve()))
        self.assertIsNone(result['audio_mix']['music_source'])

    def test_missing_project_music_asset_blocks_final_output(self):
        self.doc['audio'] = {'music_required': True, 'music': 'missing.wav'}
        studio.save(self.root / 'project.json', self.doc)
        with self.assertRaisesRegex(ValueError, 'music file does not exist'):
            edit.compose(self.args)
        self.assertFalse(Path(self.args.out).exists())

    def test_intentionally_music_free_project_can_mute_native(self):
        self.doc['audio'] = {'music_required': False, 'music': None, 'native_audio': False}
        studio.save(self.root / 'project.json', self.doc)
        edit.compose(self.args)
        import array
        samples = array.array('f', subprocess.check_output(
            ['ffmpeg', '-v', 'error', '-i', self.args.out, '-vn', '-f', 'f32le', '-ac', '1', '-']))
        self.assertLess(max(abs(v) for v in samples), 0.000001)

    def test_insufficient_video_rejected_without_freeze(self):
        self.doc['shots'][0]['trim_in'] = 1
        studio.save(self.root / 'project.json', self.doc)
        with self.assertRaisesRegex(ValueError, 'insufficient source duration'):
            edit.compose(self.args)

    def test_unreviewed_candidate_cannot_be_composed(self):
        self.doc['shots'][0]['candidates'][0]['review'] = None
        studio.save(self.root / 'project.json', self.doc)
        with self.assertRaisesRegex(ValueError, 'visually accepted'):
            edit.compose(self.args)

    def test_review_frames_have_actual_timestamps(self):
        args = Namespace(file=str(self.root / 'clip0.mp4'), out=str(self.root / 'frames'), count=3)
        result = edit.frames(args)
        self.assertEqual([f['time'] for f in result['frames']], [0.25, 0.75, 1.25])
        self.assertTrue(all(Path(f['file']).stat().st_size > 0 for f in result['frames']))
        with self.assertRaisesRegex(ValueError, 'empty or new'):
            edit.frames(args)


if __name__ == '__main__':
    unittest.main()
