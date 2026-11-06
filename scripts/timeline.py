"""Create and validate frame-based edit manifests. No API calls."""
import argparse
from decimal import Decimal
from pathlib import Path
import shutil
import sys

from common import positive_integer, read_json, resolve_path, write_json


def validate(data, base=None, check_files=False):
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('schema_version must be 1.')
    if not isinstance(data.get('title'), str) or not data['title'].strip():
        raise ValueError('title must be a nonempty string.')
    for name in ['output', 'font']:
        if name in data and (not isinstance(data[name], str) or not data[name]):
            raise ValueError(name + ' must be a nonempty path string.')
    fps = positive_integer(data.get('fps'), 'fps')
    if fps > 120:
        raise ValueError('fps must not exceed 120.')
    for name in ['width', 'height']:
        if positive_integer(data.get(name), name) % 2:
            raise ValueError(f'{name} must be even for H.264 export.')
    if data.get('fit', 'cover') not in ['cover', 'contain']:
        raise ValueError('fit must be cover or contain.')
    shots = data.get('shots')
    if not isinstance(shots, list) or not shots:
        raise ValueError('At least one shot is required.')
    ids, total = set(), 0
    for shot in shots:
        if not isinstance(shot, dict):
            raise ValueError('Every shot must be an object.')
        sid = shot.get('id')
        if not isinstance(sid, str) or not sid or sid in ids:
            raise ValueError('Shot ids must be nonempty and unique.')
        ids.add(sid)
        total += positive_integer(shot.get('frames'), sid + '.frames')
        start = shot.get('in_seconds', 0)
        if isinstance(start, bool) or not isinstance(start, (int, float)) or not Decimal(str(start)).is_finite() or start < 0:
            raise ValueError(sid + '.in_seconds must be finite and nonnegative.')
        if shot.get('audio', 'source') not in ['source', 'silent']:
            raise ValueError(sid + '.audio must be source or silent.')
        if check_files:
            source = shot.get('source')
            if not isinstance(source, str) or not source or not resolve_path(base, source).is_file():
                raise ValueError(sid + ': source media is missing.')
    if positive_integer(data.get('target_frames'), 'target_frames') != total:
        raise ValueError(f'Shot total {total} does not match target_frames.')
    for field in ['captions', 'titles']:
        rows = data.get(field, [])
        if not isinstance(rows, list):
            raise ValueError(field + ' must be an array.')
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(field + ': every cue must be an object.')
            a, b = row.get('start_frame'), row.get('end_frame')
            if any(isinstance(x, bool) or not isinstance(x, int) for x in [a, b]) or not 0 <= a < b <= total:
                raise ValueError(field + ': frame interval is outside the film.')
            if not isinstance(row.get('text'), str) or not row['text'].strip():
                raise ValueError(field + ': text must not be empty.')
            if field == 'titles' and row.get('position', 'top_left') not in ['top_left', 'lower_left', 'center']:
                raise ValueError('Unknown title position.')
        if field == 'captions':
            ordered = sorted(rows, key=lambda row: row['start_frame'])
            if any(a['end_frame'] > b['start_frame'] for a, b in zip(ordered, ordered[1:])):
                raise ValueError('Caption intervals overlap; combine lines in one cue.')
    for name in ['music', 'voiceover']:
        track = data.get(name)
        if track is None:
            continue
        if not isinstance(track, dict) or not isinstance(track.get('file'), str):
            raise ValueError(name + ' requires file and optional gain.')
        gain = track.get('gain', .15 if name == 'music' else 1)
        if isinstance(gain, bool) or not isinstance(gain, (int, float)) or not Decimal(str(gain)).is_finite() or gain < 0:
            raise ValueError(name + '.gain must be finite and nonnegative.')
        if check_files and not resolve_path(base, track['file']).is_file():
            raise ValueError(name + ': audio file is missing.')
    return {'shots': len(shots), 'frames': total, 'fps': fps, 'duration_seconds': total / fps}


def initialize(project, title, duration, shots, fps=30, width=1080, height=1920):
    project = Path(project).expanduser().resolve()
    total_decimal = Decimal(str(duration)) * fps
    if not total_decimal.is_finite() or total_decimal != int(total_decimal):
        raise ValueError('Duration must map to whole frames at the selected fps.')
    total = positive_integer(int(total_decimal), 'total frames')
    positive_integer(shots, 'shots')
    if total < shots:
        raise ValueError('Each shot needs at least one frame.')
    manifest = project / 'film.json'
    if manifest.exists():
        raise ValueError('film.json already exists; refusing to replace it.')
    for name in ['brief.md', 'screenplay.md', 'continuity.json']:
        if (project / name).exists():
            raise ValueError(f'{name} already exists; refusing to replace it.')
    q, r = divmod(total, shots)
    data = {
        'schema_version': 1, 'title': title, 'fps': fps, 'width': width, 'height': height,
        'target_frames': total, 'fit': 'cover',
        'shots': [{'id': f'S{i+1:02d}', 'frames': q + (i < r), 'source': f'inputs/shot-{i+1:02d}.mp4', 'in_seconds': 0, 'audio': 'source', 'purpose': ''} for i in range(shots)],
        'captions': [], 'titles': [], 'music': None, 'voiceover': None,
        'output': 'output/final.mp4'
    }
    validate(data)
    project.mkdir(parents=True, exist_ok=True)
    runtime = project / '.drama'
    runtime.mkdir(exist_ok=True)
    (runtime / '.gitignore').write_text('*\n', encoding='utf-8')
    ignore = project / '.gitignore'
    additions = ['.drama/', 'inputs/', 'output/', '.env', '.env.*', '!.env.example']
    old = ignore.read_text(encoding='utf-8') if ignore.exists() else ''
    missing = [line for line in additions if line not in old.splitlines()]
    if missing:
        ignore.write_text(old + ('\n' if old and not old.endswith('\n') else '') + '\n'.join(missing) + '\n', encoding='utf-8')
    assets = Path(__file__).resolve().parents[1] / 'assets'
    for source, target in [('brief-template.md', 'brief.md'), ('screenplay-template.md', 'screenplay.md'), ('continuity-template.json', 'continuity.json')]:
        shutil.copyfile(assets / source, project / target)
    write_json(manifest, data)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('project', type=Path)
    init.add_argument('--title', required=True)
    init.add_argument('--duration', type=Decimal, default=Decimal(30))
    init.add_argument('--shots', type=int, default=3)
    init.add_argument('--fps', type=int, default=30)
    init.add_argument('--width', type=int, default=1080)
    init.add_argument('--height', type=int, default=1920)
    check = sub.add_parser('validate')
    check.add_argument('manifest', type=Path)
    check.add_argument('--check-files', action='store_true')
    args = parser.parse_args()
    if args.command == 'init':
        print(initialize(args.project, args.title, args.duration, args.shots, args.fps, args.width, args.height))
    else:
        import json
        print(json.dumps(validate(read_json(args.manifest), args.manifest.resolve().parent, args.check_files), ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
