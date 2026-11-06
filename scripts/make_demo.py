"""Create synthetic clips and a short edit manifest without any API calls."""
import argparse
from pathlib import Path
import sys

from common import checked, executable, write_json


def make_demo(project):
    project = Path(project).resolve()
    if (project / 'film.json').exists():
        raise ValueError('Demo manifest already exists; choose an empty project.')
    inputs = project / 'inputs'
    inputs.mkdir(parents=True, exist_ok=True)
    for i, (color, frequency) in enumerate([('darkblue', 220), ('darkgreen', 260), ('darkred', 330)], 1):
        output = inputs / f'shot-{i:02d}.mp4'
        if output.exists():
            raise ValueError('Demo input already exists: ' + str(output))
        checked([executable('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:s=180x320:r=30:d=0.4', '-f', 'lavfi', '-i', f'sine=frequency={frequency}:sample_rate=48000:duration=0.4', '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(output)])
    manifest = {
        'schema_version': 1, 'title': 'Offline pipeline demo', 'fps': 30,
        'width': 180, 'height': 320, 'target_frames': 36, 'fit': 'cover',
        'shots': [{'id': f'S{i:02d}', 'frames': 12, 'source': f'inputs/shot-{i:02d}.mp4', 'in_seconds': 0, 'audio': 'source'} for i in range(1, 4)],
        'captions': [{'start_frame': 0, 'end_frame': 12, 'text': 'BEGIN'}, {'start_frame': 24, 'end_frame': 36, 'text': 'THE END'}],
        'titles': [], 'voiceover': None, 'music': None, 'output': 'output/final.mp4'
    }
    write_json(project / 'film.json', manifest)
    (project / '.gitignore').write_text('inputs/\noutput/\n.drama/\n.env*\n', encoding='utf-8')
    return project / 'film.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    try:
        print(make_demo(parser.parse_args().project))
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
