from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.writing-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load(path):
    return json.loads(Path(path).read_text())


@contextmanager
def lock(folder):
    path = Path(folder) / '.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError('Run is locked. If its coordinator has stopped, remove .lock before resuming.') from None
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def export(folder, state, req):
    folder = Path(folder)
    prefix = 'FIXTURE / PLUMBING TEST — NOT MODEL-GENERATED FICTION\n\n' if state['backend'] == 'fixture' else ''
    chapters = []
    for chapter in range(1, req['chapters'] + 1):
        scenes = [s for s in state['accepted'] if s['chapter'] == chapter]
        if len(scenes) != req['scenes_per_chapter']:
            continue
        text = prefix + f'Chapter {chapter}\n\n' + '\n\n* * *\n\n'.join(s['prose'] for s in scenes)
        save(folder / 'chapters' / f'chapter-{chapter:02}.txt', text)
        chapters.append(text)
    if len(chapters) == req['chapters']:
        save(folder / 'story.txt', req.get('title', req['project_id']) + '\n\n' + '\n\n'.join(chapters))
    for scene in state['accepted']:
        save(folder / 'scenes' / f'{scene["id"]}.txt', prefix + scene['prose'])
