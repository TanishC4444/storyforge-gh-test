import io
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch
from storyforge.soundtracks import context, plan, wav_stream, Vultr, discover_stories


class SoundtracksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'request.json').write_text(json.dumps({'title':'Harbor', 'characters':[{'name':'Mara','description':'afraid of storms'}], 'world_rules':['The harbor floods'], 'api_key':'must-not-leak'}))
        (self.root / 'story.txt').write_text('Wind and rain crossed the ocean. A fire burned.')

    def test_story_character_world_context_and_secret_exclusion(self):
        cue = plan(self.root)
        for text in ('Mara', 'harbor floods', 'crossed the ocean'):
            self.assertIn(text, cue['prompt'])
        self.assertNotIn('must-not-leak', cue['prompt'])
        self.assertEqual(set(cue['layers']), {'wind','water','fire'})
        (self.root / '.env').write_text('SECRET=do-not-read')
        self.assertNotIn('do-not-read', str(context(self.root)))

    def test_stream_is_valid_reproducible_wav(self):
        cue = plan(self.root, 'score')
        audio = b''.join(wav_stream(cue, seconds=5))
        self.assertEqual(audio, b''.join(wav_stream(cue, seconds=5)))
        with wave.open(io.BytesIO(audio)) as track:
            self.assertEqual(track.getnframes(), 80000)
            self.assertEqual(track.getframerate(), 16000)
            self.assertEqual(track.getnchannels(), 1)
        self.assertEqual(len(audio), 160044)
        self.assertTrue(any(audio[10000:20000]))

    def test_missing_context_and_invalid_mode(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(ValueError): context(empty)
        with self.assertRaises(ValueError): plan(self.root, 'invalid')

    def test_discover_real_runs_excludes_examples(self):
        self.assertEqual(discover_stories(self.root), [self.root])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for directory in ('outputs/actual', 'runs/active', 'examples/fixture-output'):
                target = root / directory
                target.mkdir(parents=True)
                (target / 'FINAL_STORY.txt').write_text('A story')
            self.assertEqual(discover_stories(root), sorted([root / 'outputs/actual', root / 'runs/active']))

    @patch.dict('os.environ', {'VULTR_INFERENCE_API_KEY':'test-key'})
    def test_provider_request_and_instrumental_score(self):
        provider = Vultr()
        spec = {'id':'minimax-music3', 'lyrics':'required', 'duration':{'min':30,'max':360}, 'prompt_max_length':6000}
        with patch.object(provider, 'json', side_effect=[{'data':[spec]}, {'id':'music_abc'}]) as request:
            result = provider.create(plan(self.root, 'song'), spec['id'], 30, 'Rain over the harbor')
            self.assertEqual(result['id'], 'music_abc')
            self.assertEqual(request.call_args.args[1]['lyrics'], 'Rain over the harbor')
        with patch.object(provider, 'json', side_effect=[{'data':[spec]}, {'id':'music_score'}]) as request:
            provider.create(plan(self.root, 'score'), spec['id'], 60)
            body = request.call_args.args[1]
            self.assertIn('[Instrumental]', body['lyrics'])
            self.assertIn('no singing', body['prompt'])
        for mode, lyrics, seconds in [('song','',30),('song','words',5)]:
            with patch.object(provider, 'json', return_value={'data':[spec]}):
                with self.assertRaises(ValueError): provider.create(plan(self.root, mode), spec['id'], seconds, lyrics)
        with self.assertRaises(ValueError): provider.open('https://example.com')

if __name__ == '__main__': unittest.main()
