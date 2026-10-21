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
    if any(s.get('quality_status')=='needs_review' for s in state['accepted']):prefix+='PROVISIONAL DRAFT — unresolved quality or verification warnings; see editorial-report.json.\n\n'
    save(folder/'editorial-report.json',{'completion_status':state.get('completion_status','in_progress'),'scenes':[{'id':s['id'],'quality_status':s.get('quality_status','reviewed'),'story':s.get('review'),'rhetoric':s.get('rhetoric_review'),'memory':s.get('memory_review'),'memory_extraction':s.get('memory_extraction')} for s in state['accepted']]})
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
    save(folder / 'reference-usage.json', [{'scene_id':s['id'],'planned_uses':s.get('reference_uses',[]),'model_assessment':next((c for c in s.get('review',{}).get('checks',[]) if c['id']=='reference_application'),None)} for s in state['accepted']])
    complete = len(state['accepted']) == req['chapters'] * req['scenes_per_chapter']
    provisional = any(s.get('quality_status') == 'needs_review' for s in state['accepted'])
    label = 'PARTIAL_DRAFT' if not complete else ('PROVISIONAL_STORY' if provisional else 'FINAL_STORY')
    text = req.get('title', req['project_id']) + '\n\n' + prefix + '\n\n* * *\n\n'.join(s['prose'] for s in state['accepted'])
    save(folder / (label + '.txt'), text)
    save(folder / 'READ_ME.txt', f'{len(state["accepted"])} of {req["chapters"] * req["scenes_per_chapter"]} scenes. Read {label}.txt.\nComplete: {complete}. Quality warnings: {provisional}.\n')
    for scene in state['accepted']:
        save(folder / 'scenes' / f'{scene["id"]}.txt', prefix + scene['prose'])
