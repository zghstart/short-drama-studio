import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from common import read_json, write_json
from timeline import initialize, validate
import zenmux


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.manifest = initialize(self.root, 'Synthetic story', '1.3', 4)
        self.data = read_json(self.manifest)

    def test_init_distributes_remainder_frames_without_duration_drift(self):
        self.assertEqual([s['frames'] for s in self.data['shots']], [10, 10, 10, 9])
        self.assertEqual(validate(self.data)['frames'], 39)

    def test_init_does_not_replace_existing_creator_documents(self):
        before = (self.root / 'screenplay.md').read_bytes()
        with self.assertRaises(ValueError):
            initialize(self.root, 'Replacement', 2, 2)
        self.assertEqual(before, (self.root / 'screenplay.md').read_bytes())

    def test_duration_mismatch_is_rejected(self):
        self.data['target_frames'] += 1
        with self.assertRaises(ValueError):
            validate(self.data)

    def test_duplicate_ids_and_negative_inpoints_are_rejected(self):
        bad = copy.deepcopy(self.data)
        bad['shots'][1]['id'] = bad['shots'][0]['id']
        with self.assertRaises(ValueError):
            validate(bad)
        self.data['shots'][0]['in_seconds'] = -1
        with self.assertRaises(ValueError):
            validate(self.data)

    def test_end_exclusive_caption_can_reach_final_frame(self):
        self.data['captions'] = [{'start_frame': 30, 'end_frame': 39, 'text': 'END'}]
        validate(self.data)
        self.data['captions'][0]['end_frame'] = 40
        with self.assertRaises(ValueError):
            validate(self.data)

    def test_overlapping_captions_and_infinite_audio_gain_are_rejected(self):
        bad = copy.deepcopy(self.data)
        bad['captions'] = [{'start_frame': 0, 'end_frame': 12, 'text': 'A'}, {'start_frame': 11, 'end_frame': 20, 'text': 'B'}]
        with self.assertRaises(ValueError):
            validate(bad)
        self.data['music'] = {'file': 'music.wav', 'gain': float('inf')}
        with self.assertRaises(ValueError):
            validate(self.data)

    def test_planning_can_validate_before_media_exists(self):
        validate(self.data)
        with self.assertRaises(ValueError):
            validate(self.data, self.root, check_files=True)


class FakeTransport:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, path, body=None):
        self.calls.append((method, path))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class JobTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        prompt = self.root / 'prompt.txt'
        prompt.write_text('A fictional conversation.', encoding='utf-8')
        self.args = argparse.Namespace(model='provider/example', prompt=prompt, image=None, duration=10, ratio='9:16', resolution='verified-value', silent=False, job=self.root / 'job', dry_run=False)

    def test_dry_run_never_reads_credentials_or_calls_network(self):
        self.args.dry_run = True
        with patch.dict(os.environ, {}, clear=True), patch.object(zenmux, 'Transport', side_effect=AssertionError('Network must not be initialized')):
            result = zenmux.submit(self.args)
        self.assertTrue(result['dry_run'])
        self.assertFalse(self.args.job.exists())

    def test_unknown_post_outcome_is_preserved_and_never_repeated(self):
        transport = FakeTransport([TimeoutError('connection lost')])
        with self.assertRaises(TimeoutError):
            zenmux.submit(self.args, transport)
        self.assertEqual(read_json(self.args.job / 'state.json')['status'], 'submission_unknown')
        with self.assertRaises(ValueError):
            zenmux.submit(self.args, transport)
        self.assertEqual(len(transport.calls), 1)

    def test_successful_submit_is_not_repeated(self):
        transport = FakeTransport([(200, {'id': 'job-1', 'status': 'queued'})])
        zenmux.submit(self.args, transport)
        with self.assertRaises(ValueError):
            zenmux.submit(self.args, transport)
        self.assertEqual(len(transport.calls), 1)

    def test_lock_prevents_parallel_submission(self):
        self.args.job.mkdir()
        (self.args.job / '.submit.lock').touch()
        transport = FakeTransport([])
        with self.assertRaises(FileExistsError):
            zenmux.submit(self.args, transport)
        self.assertEqual(transport.calls, [])

    def test_server_error_without_id_remains_unknown(self):
        transport = FakeTransport([(503, {'error': {'message': 'temporary failure'}})])
        with self.assertRaises(RuntimeError):
            zenmux.submit(self.args, transport)
        self.assertEqual(read_json(self.args.job / 'state.json')['status'], 'submission_unknown')

    def test_poll_error_preserves_id_and_resumes(self):
        zenmux.submit(self.args, FakeTransport([(200, {'id': 'job-1', 'status': 'queued'})]))
        with self.assertRaises(RuntimeError):
            zenmux.poll(self.args.job, FakeTransport([(502, {'error': 'temporary'})]), once=True)
        self.assertEqual(read_json(self.args.job / 'state.json')['id'], 'job-1')
        result = zenmux.poll(self.args.job, FakeTransport([(200, {'id': 'job-1', 'status': 'succeeded', 'content': {'video_url': 'https://media.example.test/video.mp4'}})]), once=True)
        self.assertEqual(result['status'], 'succeeded')

    def test_api_key_is_in_stdin_not_arguments_and_is_redacted_from_response(self):
        credential = 'unit-test-credential'
        response = json.dumps({'error': {'message': credential}}) + '\n400'
        completed = subprocess.CompletedProcess([], 0, response, '')
        with patch.dict(os.environ, {'ZENMUX_API_KEY': credential}), patch.object(zenmux, 'proxy', return_value=None), patch.object(zenmux.subprocess, 'run', return_value=completed) as call:
            _, body = zenmux.Transport().request('GET', '/api/v1/models')
        self.assertIn(credential, call.call_args.kwargs['input'])
        self.assertNotIn(credential, json.dumps(call.call_args.args[0]))
        self.assertNotIn(credential, json.dumps(body))

    def test_media_download_uses_no_api_credential_and_checks_reused_file_hash(self):
        self.args.job.mkdir()
        write_json(self.args.job / 'state.json', {'id': 'job-1', 'status': 'succeeded', 'response': {'content': {'video_url': 'https://media.example.test/video.mp4'}}})
        def save(command, **kwargs):
            self.assertNotIn('--config', command)
            self.assertNotIn('--header', command)
            self.assertNotIn('input', kwargs)
            Path(command[command.index('--output') + 1]).write_bytes(b'\x00\x00\x00\x18ftypisom' + bytes(64))
            return subprocess.CompletedProcess(command, 0, '', '')
        with patch.object(zenmux, 'proxy', return_value=None), patch.object(zenmux.subprocess, 'run', side_effect=save):
            zenmux.download(self.args.job)
        self.assertTrue(zenmux.download(self.args.job)['reused'])
        (self.args.job / 'video.mp4').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            zenmux.download(self.args.job)


HAS_MEDIA = shutil.which('ffmpeg') and shutil.which('ffprobe') and importlib.util.find_spec('PIL')


@unittest.skipUnless(HAS_MEDIA, 'FFmpeg, ffprobe and Pillow are required')
class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from make_demo import make_demo
        from render import render
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        cls.manifest = make_demo(cls.root)
        cls.result = render(cls.manifest)
        cls.output = cls.root / 'output/final.mp4'

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_exact_frame_count_audio_and_full_decode(self):
        from inspect_media import inspect
        result = inspect(self.output, 1.2, 30, True, True)
        self.assertEqual(int(result['frame_count']), 36)
        self.assertEqual(result['audio_streams'], 1)
        self.assertTrue(result['decode_checked'])

    def test_last_frame_still_contains_burned_in_caption(self):
        from PIL import Image
        frame = self.root / 'last.png'
        subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-ss', str(35 / 30), '-i', str(self.output), '-frames:v', '1', str(frame)], check=True)
        image = Image.open(frame).convert('RGB')
        region = image.crop((0, 250, 180, 310))
        pixels = region.load()
        self.assertGreater(sum(1 for y in range(region.height) for x in range(region.width) if min(pixels[x, y]) > 180), 10)

    def test_existing_final_is_not_replaced_without_intent(self):
        from render import render
        before = hashlib.sha256(self.output.read_bytes()).digest()
        with self.assertRaises(ValueError):
            render(self.manifest)
        self.assertEqual(before, hashlib.sha256(self.output.read_bytes()).digest())

    def test_non_latin_graphics_require_a_suitable_font(self):
        from render import graphics
        data = read_json(self.manifest)
        data['captions'][0]['text'] = '尾句'
        with self.assertRaises(ValueError):
            graphics(data, None, self.root / 'unrendered.mov', shutil.which('ffmpeg'))

    def test_short_source_is_not_stretched_to_cover_missing_action(self):
        from render import render
        data = read_json(self.manifest)
        data['shots'][0]['frames'] += 4
        data['target_frames'] += 4
        path = self.root / 'too-short.json'
        write_json(path, data)
        with self.assertRaisesRegex(ValueError, 'too short'):
            render(path, self.root / 'output/too-short.mp4')

    def test_output_never_replaces_an_input_asset(self):
        from render import render
        source = self.root / 'inputs/shot-01.mp4'
        before = hashlib.sha256(source.read_bytes()).digest()
        with self.assertRaises(ValueError):
            render(self.manifest, source, overwrite=True)
        self.assertEqual(before, hashlib.sha256(source.read_bytes()).digest())

    def test_external_voice_and_music_mix_into_intentionally_silent_shots(self):
        from render import render
        import array
        data = read_json(self.manifest)
        for shot in data['shots']:
            shot['audio'] = 'silent'
        data['voiceover'] = {'file': 'inputs/shot-01.mp4', 'gain': 1}
        data['music'] = {'file': 'inputs/shot-02.mp4', 'gain': .15}
        path = self.root / 'mixed.json'
        write_json(path, data)
        output = self.root / 'output/mixed.mp4'
        render(path, output)
        pcm = subprocess.check_output([shutil.which('ffmpeg'), '-v', 'error', '-i', str(output), '-map', '0:a:0', '-ac', '1', '-ar', '48000', '-f', 's16le', '-'])
        samples = array.array('h', pcm)
        self.assertGreater(max(abs(x) for x in samples[:9600]), 300)
        self.assertLess(max(abs(x) for x in samples[-9600:]), 50)


if __name__ == '__main__':
    unittest.main()
