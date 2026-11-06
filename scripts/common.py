"""Small, dependency-free helpers shared by the command-line tools."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def read_json(path):
    with Path(path).open(encoding='utf-8') as handle:
        return json.load(handle)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def executable(name):
    value = os.environ.get('DRAMA_' + name.upper()) or shutil.which(name)
    if not value:
        raise RuntimeError(f'{name} is required; install it or set DRAMA_{name.upper()}.')
    return value


def checked(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:] or f'Command failed: {command[0]}')
    return result.stdout


def probe(path):
    return json.loads(checked([executable('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def resolve_path(base, value):
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def positive_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f'{name} must be a positive integer.')
    return value
