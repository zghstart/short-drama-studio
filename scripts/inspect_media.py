"""Inspect actual media, optionally decode it and extract review frames."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

from common import checked, executable, probe


def inspect(path, expected_duration=None, expected_fps=None, require_audio=False, decode=False, frames_dir=None):
    meta = probe(path)
    videos = [s for s in meta['streams'] if s['codec_type'] == 'video']
    audios = [s for s in meta['streams'] if s['codec_type'] == 'audio']
    if not videos:
        raise ValueError('No video stream.')
    video = videos[0]
    duration = float(meta['format']['duration'])
    fps = float(Fraction(video['r_frame_rate']))
    if expected_duration is not None and abs(duration - expected_duration) > max(1 / fps, .005):
        raise ValueError('Actual duration does not match the target within one frame.')
    if expected_fps is not None and abs(fps - expected_fps) > .001:
        raise ValueError('Actual fps does not match the target.')
    if require_audio and not audios:
        raise ValueError('Expected audio stream is missing.')
    result = {'duration_seconds': duration, 'fps': fps, 'width': video['width'], 'height': video['height'], 'video_codec': video['codec_name'], 'audio_streams': len(audios), 'frame_count': video.get('nb_frames'), 'decode_checked': False}
    if decode:
        checked([executable('ffmpeg'), '-v', 'error', '-i', str(path), '-f', 'null', '-'])
        result['decode_checked'] = True
    if audios:
        result['decoded_audio_hash'] = checked([executable('ffmpeg'), '-v', 'error', '-i', str(path), '-map', '0:a:0', '-f', 'hash', '-hash', 'sha256', '-']).strip()
    if frames_dir:
        frames_dir.mkdir(parents=True, exist_ok=True)
        result['review_frames'] = []
        for i, timestamp in enumerate([0, duration / 2, max(0, duration - 1 / fps)], 1):
            output = frames_dir / f'frame-{i:02d}.png'
            if output.exists():
                raise ValueError('Review frame already exists: ' + str(output))
            checked([executable('ffmpeg'), '-v', 'error', '-ss', str(timestamp), '-i', str(path), '-frames:v', '1', str(output)])
            if not output.exists():
                raise RuntimeError('Could not extract a review frame.')
            result['review_frames'].append(str(output))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--expected-duration', type=float)
    parser.add_argument('--expected-fps', type=float)
    parser.add_argument('--require-audio', action='store_true')
    parser.add_argument('--decode', action='store_true')
    parser.add_argument('--frames-dir', type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.video, args.expected_duration, args.expected_fps, args.require_audio, args.decode, args.frames_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError, ZeroDivisionError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
