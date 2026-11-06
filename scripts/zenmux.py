"""ZenMux native video jobs and audio transcription. Credentials stay in env."""
import argparse
import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, urlsplit

from common import executable, read_json, write_json

BASE = 'https://zenmux.ai'
TERMINAL = {'succeeded', 'failed', 'canceled', 'cancelled'}


def proxy():
    for name in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
        if os.environ.get(name):
            return os.environ[name]
    if sys.platform == 'darwin':
        try:
            text = subprocess.check_output(['scutil', '--proxy'], text=True)
            values = dict(re.findall(r'^\s*(\w+)\s*:\s*(\S+)\s*$', text, re.M))
            if values.get('HTTPSEnable') == '1':
                return 'http://' + values['HTTPSProxy'] + ':' + values['HTTPSPort']
        except (OSError, subprocess.SubprocessError, KeyError):
            pass
    return None


class Transport:
    def __init__(self):
        self.key = os.environ.get('ZENMUX_API_KEY')
        if not self.key or any(c in self.key for c in ['\n', '\r', '"']):
            raise ValueError('Set ZENMUX_API_KEY in the environment.')
        self.proxy = proxy()

    def clean(self, value):
        # Redact even a provider error that unexpectedly echoes the credential.
        return json.loads(json.dumps(value, ensure_ascii=False).replace(self.key, '[REDACTED]'))

    def request(self, method, path, body=None):
        cmd = [executable('curl'), '--silent', '--show-error', '--connect-timeout', '15', '--max-time', '120']
        if self.proxy:
            cmd += ['--proxy', self.proxy]
        cmd += ['--request', method, '--config', '-', '--write-out', '\n%{http_code}']
        with tempfile.TemporaryDirectory(prefix='drama-request-') as directory:
            if body is not None:
                payload = Path(directory) / 'body.json'
                write_json(payload, body)
                cmd += ['--header', 'Content-Type: application/json', '--data-binary', '@' + str(payload)]
            result = subprocess.run(cmd + [BASE + path], input='header = "Authorization: Bearer ' + self.key + '"\n', capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(self.clean(result.stderr))
        raw, code = result.stdout.rsplit('\n', 1)
        try:
            response = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError('Non-JSON API response; HTTP ' + code)
        if not isinstance(response, dict):
            raise RuntimeError('Expected a JSON response object; HTTP ' + code)
        return int(code), self.clean(response)


def build_payload(args):
    if args.duration <= 0 or not args.model.strip():
        raise ValueError('A model id and positive duration are required.')
    content = [{'type': 'text', 'text': args.prompt.read_text(encoding='utf-8')}]
    if args.image:
        mime = mimetypes.guess_type(args.image.name)[0]
        if mime not in ['image/png', 'image/jpeg', 'image/webp']:
            raise ValueError('First frame must be PNG, JPEG or WebP.')
        content.append({'type': 'image_url', 'role': 'first_frame', 'image_url': {'url': 'data:' + mime + ';base64,' + base64.b64encode(args.image.read_bytes()).decode()}})
    result = {'model': args.model, 'content': content, 'duration': args.duration, 'ratio': args.ratio, 'generate_audio': not args.silent}
    if args.resolution:
        result['resolution'] = args.resolution
    return result


def submit(args, transport=None):
    payload = build_payload(args)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    if args.dry_run:
        return {'dry_run': True, 'model': args.model, 'duration': args.duration, 'ratio': args.ratio, 'resolution': args.resolution, 'reference_count': len(payload['content']) - 1, 'request_sha256': digest}
    state_path = args.job / 'state.json'
    if state_path.exists():
        state = read_json(state_path)
        raise ValueError('Job already recorded (' + state['status'] + '); use poll/download or a new directory after reviewing a confirmed failure.')
    transport = transport or Transport()
    args.job.mkdir(parents=True, exist_ok=True)
    lock = args.job / '.submit.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        # Recheck after acquiring the lock to cover another completed submit.
        if state_path.exists():
            raise ValueError('Job already exists; refusing duplicate submit.')
        state = {'status': 'submission_unknown', 'model': args.model, 'request_sha256': digest, 'created_at': time.time()}
        write_json(args.job / 'request.json', payload)
        write_json(state_path, state)
        code, response = transport.request('POST', '/api/v1/videos', payload)
        state['http_status'] = code
        state['response'] = response
        if isinstance(response, dict) and response.get('id'):
            state['id'] = str(response['id'])
            state['status'] = response.get('status', 'unknown')
        elif 400 <= code < 500:
            state['status'] = 'rejected'
        # A 5xx response without an id may follow acceptance: keep unknown.
        write_json(state_path, state)
        if code >= 400 or not state.get('id'):
            raise RuntimeError('Submission not confirmed: ' + json.dumps(response, ensure_ascii=False)[:1000])
        return {'id': state['id'], 'status': state['status'], 'job': str(args.job)}
    finally:
        lock.unlink(missing_ok=True)


def poll(job, transport=None, once=False, timeout=900, interval=15):
    if interval <= 0 or timeout <= 0:
        raise ValueError('Polling interval and timeout must be positive.')
    state_path = job / 'state.json'
    state = read_json(state_path)
    if not state.get('id'):
        raise ValueError('No accepted job id; reconcile the existing submission instead of resubmitting.')
    if state['status'] in TERMINAL:
        return {'id': state['id'], 'status': state['status'], 'job': str(job)}
    transport = transport or Transport()
    deadline = time.monotonic() + timeout
    while True:
        code, response = transport.request('GET', '/api/v1/videos/' + quote(state['id'], safe=''))
        if code >= 400:
            state['last_poll_error'] = {'http_status': code, 'response': response}
            write_json(state_path, state)
            raise RuntimeError('Polling failed; the existing task id was preserved.')
        status = response.get('status')
        state.update({'status': status or 'unknown', 'response': response, 'checked_at': time.time()})
        write_json(state_path, state)
        print(json.dumps({'id': state['id'], 'status': state['status']}), file=sys.stderr, flush=True)
        if status not in TERMINAL | {'queued', 'running'}:
            raise RuntimeError('Unknown server status; inspect saved response and preserve the task id.')
        if once or status in TERMINAL:
            return {'id': state['id'], 'status': status, 'job': str(job)}
        if time.monotonic() + interval > deadline:
            raise TimeoutError('Polling deadline reached; resume the same job later.')
        time.sleep(interval)


def download(job):
    state_path = job / 'state.json'
    state = read_json(state_path)
    if state.get('status') != 'succeeded':
        raise ValueError('Only succeeded jobs can be downloaded.')
    output = job / 'video.mp4'
    if output.exists():
        if state.get('file_sha256') != hashlib.sha256(output.read_bytes()).hexdigest():
            raise ValueError('Existing media has no matching recorded hash; refusing to overwrite it.')
        return {'file': str(output), 'sha256': state['file_sha256'], 'reused': True}
    url = state.get('response', {}).get('content', {}).get('video_url')
    parsed = urlsplit(url or '')
    if parsed.scheme not in ['https', 'http'] or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('Expected an HTTP(S) media URL without embedded credentials.')
    part = job / 'video.part'
    command = [executable('curl'), '--silent', '--show-error', '--fail', '--location', '--connect-timeout', '15', '--max-time', '180']
    existing_proxy = proxy()
    if existing_proxy:
        command += ['--proxy', existing_proxy]
    # This media request deliberately carries no API credential/header.
    result = subprocess.run(command + ['--output', str(part), url], capture_output=True, text=True)
    if result.returncode or not part.exists() or not part.stat().st_size:
        raise RuntimeError('Download failed; the successful generation remains resumable.')
    with part.open('rb') as handle:
        header = handle.read(64).lstrip()
    if header.startswith((b'<', b'{')):
        raise RuntimeError('The download appears to be an error document; generation was not resubmitted.')
    part.replace(output)
    state['file_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
    state['local_file'] = output.name
    write_json(state_path, state)
    return {'file': str(output), 'sha256': state['file_sha256'], 'bytes': output.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    models = sub.add_parser('models')
    models.add_argument('--output')
    models.add_argument('--contains', default='')
    create = sub.add_parser('submit')
    create.add_argument('--model', required=True)
    create.add_argument('--prompt', required=True, type=Path)
    create.add_argument('--image', type=Path)
    create.add_argument('--duration', required=True, type=int)
    create.add_argument('--resolution')
    create.add_argument('--ratio', default='9:16')
    create.add_argument('--silent', action='store_true')
    create.add_argument('--job', required=True, type=Path)
    create.add_argument('--dry-run', action='store_true')
    polling = sub.add_parser('poll')
    polling.add_argument('--job', required=True, type=Path)
    polling.add_argument('--once', action='store_true')
    polling.add_argument('--timeout', type=float, default=900)
    polling.add_argument('--interval', type=float, default=15)
    get = sub.add_parser('download')
    get.add_argument('--job', required=True, type=Path)
    asr = sub.add_parser('transcribe')
    asr.add_argument('--model', required=True)
    asr.add_argument('--audio', required=True, type=Path)
    asr.add_argument('--language')
    asr.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'submit':
        result = submit(args)
    elif args.command == 'poll':
        result = poll(args.job, once=args.once, timeout=args.timeout, interval=args.interval)
    elif args.command == 'download':
        result = download(args.job)
    elif args.command == 'models':
        code, body = Transport().request('GET', '/api/v1/models')
        if code >= 400:
            raise RuntimeError(json.dumps(body, ensure_ascii=False))
        result = [{'id': m['id'], 'input_modalities': m.get('input_modalities'), 'output_modalities': m.get('output_modalities'), 'pricings': m.get('pricings'), 'discount': 'verify against current promotion/price source'} for m in body['data'] if args.contains.lower() in m['id'].lower() and (not args.output or args.output in m.get('output_modalities', []))]
    else:
        form = args.audio.suffix.lstrip('.').lower()
        if form not in ['wav', 'mp3', 'flac', 'm4a', 'ogg', 'webm', 'aac']:
            raise ValueError('Unsupported audio container.')
        body = {'model': args.model, 'input_audio': {'data': base64.b64encode(args.audio.read_bytes()).decode(), 'format': form}}
        if args.language:
            body['language'] = args.language
        code, result = Transport().request('POST', '/api/v1/audio/transcriptions', body)
        if code >= 400:
            raise RuntimeError(json.dumps(result, ensure_ascii=False))
        write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, TimeoutError, KeyError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
