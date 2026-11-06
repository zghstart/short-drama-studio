"""Render a frame-based manifest with portable, frame-complete captions."""
import argparse
from fractions import Fraction
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from common import executable, probe, read_json, resolve_path, write_json
from timeline import validate


def wrap(text, draw, font, width):
    lines = []
    for paragraph in text.split('\n'):
        current = ''
        for character in paragraph:
            if current and draw.textbbox((0, 0), current + character, font=font)[2] > width:
                lines.append(current.rstrip())
                current = ''
            current += character
        lines.append(current.rstrip())
    return lines


def draw_overlay(data, frame, font_path):
    from PIL import Image, ImageDraw, ImageFont
    width, height = data['width'], data['height']
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def face(size):
        return ImageFont.truetype(str(font_path), size) if font_path else ImageFont.load_default(size=size)

    def text_block(text, position, size, centered=False, color='white', max_lines=3):
        font = face(size)
        stroke = max(1, round(height / 480))
        lines = wrap(text, draw, font, width * .88)
        if len(lines) > max_lines:
            raise ValueError('Text needs too many lines; split the cue or use an appropriate font size.')
        line_height = round(size * 1.45)
        x, y = position
        if centered:
            y -= line_height * (len(lines) - 1)
        for line in lines:
            left = (width - draw.textbbox((0, 0), line, font=font)[2]) / 2 if centered else x
            draw.text((left, y), line, font=font, fill=color, stroke_width=stroke, stroke_fill='black')
            y += line_height

    for cue in data.get('captions', []):
        if cue['start_frame'] <= frame < cue['end_frame']:
            text_block(cue['text'], (0, height * .85), max(9, round(height * .028)), True, cue.get('color', 'white'), 2)
    for title in data.get('titles', []):
        if title['start_frame'] <= frame < title['end_frame']:
            position = title.get('position', 'top_left')
            point = {'top_left': (width * .065, height * .055), 'lower_left': (width * .065, height * .65), 'center': (0, height * .45)}[position]
            text_block(title['text'], point, max(10, round(height * .033)), position == 'center', title.get('color', 'white'))
    return image


def graphics(data, font_path, destination, ffmpeg):
    text = ''.join(c['text'] for kind in ['captions', 'titles'] for c in data.get(kind, []))
    if any(ord(c) > 255 for c in text) and not font_path:
        raise ValueError('Non-Latin captions require --font or a manifest font path with suitable glyphs.')
    if font_path and not font_path.is_file():
        raise ValueError('Font file is missing.')
    # Cache compressed PNGs by active cues, then feed exactly target_frames frames.
    cache = {}
    command = [ffmpeg, '-v', 'error', '-y', '-f', 'image2pipe', '-framerate', str(data['fps']), '-c:v', 'png', '-i', 'pipe:0', '-frames:v', str(data['target_frames']), '-c:v', 'qtrle', '-pix_fmt', 'argb', str(destination)]
    log = destination.with_suffix('.log')
    with log.open('wb') as stderr:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=stderr)
        try:
            for frame in range(data['target_frames']):
                active = tuple((kind, index) for kind in ['captions', 'titles'] for index, cue in enumerate(data.get(kind, [])) if cue['start_frame'] <= frame < cue['end_frame'])
                if active not in cache:
                    buffer = io.BytesIO()
                    draw_overlay(data, frame, font_path).save(buffer, format='PNG')
                    cache[active] = buffer.getvalue()
                process.stdin.write(cache[active])
        except BaseException:
            process.stdin.close()
            process.wait()
            raise
        process.stdin.close()
        code = process.wait()
    if code:
        raise RuntimeError('Caption render failed: ' + log.read_text(errors='replace')[-2000:])
    meta = probe(destination)
    video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
    if int(video.get('nb_frames', 0)) != data['target_frames']:
        raise RuntimeError('Caption video ended early; refusing to export an incomplete overlay.')


def srt_text(data):
    def stamp(frame):
        milliseconds = round(frame * 1000 / data['fps'])
        return f'{milliseconds//3600000:02d}:{milliseconds//60000%60:02d}:{milliseconds//1000%60:02d},{milliseconds%1000:03d}'
    return '\n\n'.join(f'{i}\n{stamp(c["start_frame"])} --> {stamp(c["end_frame"])}\n{c["text"]}' for i, c in enumerate(sorted(data.get('captions', []), key=lambda x: x['start_frame']), 1)) + '\n'


def render(manifest, output=None, font=None, overwrite=False):
    manifest = Path(manifest).resolve()
    base = manifest.parent
    data = read_json(manifest)
    summary = validate(data, base, check_files=True)
    ffmpeg = executable('ffmpeg')
    output = Path(output).resolve() if output else resolve_path(base, data.get('output', 'output/final.mp4'))
    sources = [resolve_path(base, shot['source']) for shot in data['shots']]
    tracks = {name: resolve_path(base, data[name]['file']) for name in ['voiceover', 'music'] if data.get(name)}
    if output in sources or output in tracks.values() or output == manifest:
        raise ValueError('Output must not replace a source asset or manifest.')
    if output.exists() and not overwrite:
        raise ValueError('Output already exists; use --overwrite only for an intended replacement.')
    metadata = [probe(source) for source in sources]
    fps, width, height = data['fps'], data['width'], data['height']
    duration = data['target_frames'] / fps
    for shot, meta in zip(data['shots'], metadata):
        video = next((s for s in meta['streams'] if s['codec_type'] == 'video'), None)
        if video is None:
            raise ValueError(shot['id'] + ': source has no video stream.')
        available = float(video.get('duration') or meta['format'].get('duration', 0))
        try:
            tolerance = 1 / float(Fraction(video.get('r_frame_rate', str(fps))))
        except (ValueError, ZeroDivisionError):
            tolerance = 1 / fps
        if shot.get('in_seconds', 0) + shot['frames'] / fps > available + tolerance:
            raise ValueError(shot['id'] + ': source is too short; revise the edit instead of stretching it.')
        if shot.get('audio', 'source') == 'source' and not any(s['codec_type'] == 'audio' for s in meta['streams']):
            raise ValueError(shot['id'] + ': expected source audio is missing; select silent intentionally or supply voiceover.')
    for name, path in tracks.items():
        if not any(s['codec_type'] == 'audio' for s in probe(path)['streams']):
            raise ValueError(name + ': no audio stream.')
    font_path = Path(font).expanduser().resolve() if font else resolve_path(base, data['font']) if data.get('font') else None
    runtime = base / '.drama' / 'render' / uuid.uuid4().hex
    runtime.mkdir(parents=True)
    has_graphics = bool(data.get('captions') or data.get('titles'))
    if has_graphics:
        graphics(data, font_path, runtime / 'captions.mov', ffmpeg)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name('.' + output.stem + '-' + uuid.uuid4().hex + '.part.mp4')
    command = [ffmpeg, '-hide_banner', '-y']
    for source in sources:
        command += ['-i', str(source)]
    indexes = {}
    next_index = len(sources)
    for name in ['voiceover', 'music']:
        if name in tracks:
            command += ['-i', str(tracks[name])]
            indexes[name] = next_index
            next_index += 1
    if has_graphics:
        command += ['-i', str(runtime / 'captions.mov')]
        indexes['graphics'] = next_index
    filters = []
    for i, shot in enumerate(data['shots']):
        start, length = shot.get('in_seconds', 0), shot['frames'] / fps
        scale = f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}' if data.get('fit', 'cover') == 'cover' else f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2'
        filters.append(f'[{i}:v]trim=start={start}:duration={length:.9f},setpts=PTS-STARTPTS,{scale},fps={fps},tpad=stop_mode=clone:stop_duration={1/fps:.9f},trim=end_frame={shot["frames"]},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{i}]')
        if shot.get('audio', 'source') == 'silent':
            filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={length:.9f},asetpts=PTS-STARTPTS[a{i}]')
        else:
            filters.append(f'[{i}:a]atrim=start={start}:duration={length:.9f},asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.8:LRA=7,aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={length:.9f},afade=t=in:d=0.008,afade=t=out:st={max(0,length-.015):.9f}:d=0.015[a{i}]')
    inputs = ''.join(f'[v{i}][a{i}]' for i in range(len(sources)))
    filters.append(inputs + f'concat=n={len(sources)}:v=1:a=1[basev][basea]')
    if has_graphics:
        filters.append(f'[{indexes["graphics"]}:v]setpts=PTS-STARTPTS,format=rgba[graphic]')
        filters.append('[basev][graphic]overlay=0:0:format=auto:eof_action=pass[vout]')
    else:
        filters.append('[basev]null[vout]')
    audio_labels = ['[basea]']
    for name, index in indexes.items():
        if name == 'graphics':
            continue
        gain = data[name].get('gain', .15 if name == 'music' else 1)
        filters.append(f'[{index}:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain},apad,atrim=duration={duration:.9f}[{name}]')
        audio_labels.append('[' + name + ']')
    filters.append(''.join(audio_labels) + f'amix=inputs={len(audio_labels)}:duration=first:normalize=0,alimiter=limit=0.94:level=false[aout]')
    graph = ';\n'.join(filters)
    (runtime / 'filters.txt').write_text(graph, encoding='utf-8')
    command += ['-filter_complex', graph, '-map', '[vout]', '-map', '[aout]', '-frames:v', str(data['target_frames']), '-t', f'{duration:.9f}', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-b:a', '192k', '-movflags', '+faststart', str(temporary)]
    log = runtime / 'render.log'
    with log.open('w', encoding='utf-8') as handle:
        result = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(log.read_text(errors='replace')[-4000:])
    meta = probe(temporary)
    video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
    if int(video.get('nb_frames', 0)) != data['target_frames']:
        raise RuntimeError('Rendered frame count does not match the manifest.')
    if overwrite:
        os.replace(temporary, output)
    else:
        os.link(temporary, output)  # Atomic no-clobber commit on the same volume.
        temporary.unlink()
    subtitle = output.with_suffix('.srt')
    if not subtitle.exists() or overwrite:
        subtitle.write_text(srt_text(data), encoding='utf-8')
    report = {**summary, 'output': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'source_media': metadata, 'export_media': meta}
    write_json(runtime / 'report.json', report)
    return {k: v for k, v in report.items() if k not in ['source_media', 'export_media']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--font', type=Path)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    print(json.dumps(render(args.manifest, args.output, args.font, args.overwrite), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError, StopIteration) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
