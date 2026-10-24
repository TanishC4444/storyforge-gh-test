"""Turn workflow artifacts into API responses.

Both the GitHub backend and the demo backend implement ArtifactReader, so the
parsing below is shared. Artifact layouts are produced by the workflows:

- sequential: readable-story (READABLE_DRAFT.txt, reading-status.json,
  canon/snapshot.json) and universe-canon (snapshot.json)
- parallel: parallel-readable-story (STORY-DRAFT.txt, report.json) and
  planned-{write,check,patch}-<scene id> (scene.json, prose.txt)
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Protocol

from .schemas import Canon, Job, Progress, Scene, SceneSummary, Story

Files = dict[str, bytes]


class NotAvailable(Exception):
    """The run has not produced (or no longer has) the artifact needed."""


class InvalidArtifact(ValueError):
    """An upstream archive or saved record is corrupt, not a bad user request."""


class ArtifactReader(Protocol):
    def names(self) -> list[str]: ...

    def files(self, name: str) -> Files | None: ...


def unzip(data: bytes) -> Files:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}
    except (zipfile.BadZipFile,RuntimeError,NotImplementedError):
        raise InvalidArtifact('The saved artifact archive could not be read; try fetching it again') from None


def _json(files: Files, path: str):
    if path not in files:return None
    try:value=json.loads(files[path])
    except (ValueError,UnicodeError):raise InvalidArtifact('The saved artifact contains invalid JSON') from None
    if value is not None and not isinstance(value,dict):raise InvalidArtifact('The saved artifact record must be an object')
    return value


def _text(files: Files, path: str) -> str:
    try:return files[path].decode('utf-8') if path in files else ''
    except UnicodeError:raise InvalidArtifact('The saved artifact contains invalid text') from None


def _words(text: str) -> int:
    return len(text.split())


def _need(reader: ArtifactReader, name: str) -> Files:
    files = reader.files(name)
    if files is None:
        raise NotAvailable(f'Artifact {name!r} is not available for this run yet (or has expired)')
    return files


# Sequential mode

def _snapshot(reader: ArtifactReader) -> dict | None:
    files = reader.files('readable-story')
    return _json(files, 'canon/snapshot.json') if files else None


def _sequential_sections(files: Files, snapshot: dict) -> list[dict]:
    """Overlay the intact approved checkpoint on legacy/partial text exports."""
    text=_text(files,'READABLE_DRAFT.txt')
    markers=list(re.finditer(r'(?m)^s(\d+) \| ([^\n]+)\n\n',text))
    sections={}
    accepted=snapshot.get('accepted') or []
    plan=(snapshot.get('plan') or {}).get('scenes') or []
    for i,match in enumerate(markers):
        position=int(match[1])-1
        end=markers[i+1].start() if i+1<len(markers) else len(text)
        prose=text[match.end():end].removesuffix('\n\n* * *\n\n').strip()
        sid=plan[position]['id'] if 0<=position<len(plan) else f's{position+1:02}'
        sections[position]={'id':sid,'status':match[2],'prose':prose}
    for i,scene in enumerate(accepted):
        sections[i]={'id':scene['id'],'status':scene.get('quality_status','reviewed'),'prose':scene.get('prose',''),'reviews':{key:scene[field] for key,field in [('story','review'),('rhetoric','rhetoric_review'),('memory','memory_review')] if scene.get(field) is not None}}
    return [sections[i] for i in sorted(sections)]


def sequential_story(run_id: int, reader: ArtifactReader) -> Story:
    files = _need(reader, 'readable-story')
    snapshot = _json(files, 'canon/snapshot.json') or {}
    status = _json(files, 'reading-status.json') or {}
    sections=_sequential_sections(files,snapshot)
    text=_text(files,'READABLE_DRAFT.txt')
    # Rebuild only incomplete legacy exports; retain all saved unapproved sections.
    if any(s.get('prose') and s['prose'] not in text for s in snapshot.get('accepted') or []):
        text='CLASSIC UNIVERSE EXPANSION\nStatus applies separately to each scene. Unreviewed prose is not accepted canon.\n\n'+'\n\n* * *\n\n'.join(s['id']+' | '+s['status']+'\n\n'+s['prose'] for s in sections)
    scenes=[SceneSummary(id=s['id'],status=s['status'],words=_words(s['prose'])) for s in sections] if sections else [SceneSummary(id=s['scene_id'],status=s.get('status','unknown'),words=s.get('words',0)) for s in status.get('scenes',[])]
    return Story(run_id=run_id, mode='sequential',title=(snapshot.get('request') or {}).get('title'),complete=bool(snapshot.get('complete')),completion_status=snapshot.get('completion_status'),text=text,scenes=scenes)


def sequential_scene(reader: ArtifactReader, scene_id: str) -> Scene:
    files=_need(reader,'readable-story');snapshot=_json(files,'canon/snapshot.json') or {}
    for scene in _sequential_sections(files,snapshot):
        if scene['id']==scene_id:
            return Scene(id=scene_id,status=scene['status'],words=_words(scene['prose']),prose=scene['prose'],reviews=scene.get('reviews',{}))
    raise NotAvailable(f'Scene {scene_id!r} has no saved prose in this run')


def sequential_canon(run_id: int, reader: ArtifactReader) -> Canon:
    files = reader.files('universe-canon')
    snapshot = _json(files, 'snapshot.json') if files else _snapshot(reader)
    if not snapshot:
        raise NotAvailable('This run has not committed any canon yet')
    return Canon(run_id=run_id, version=snapshot.get('version'), completion_status=snapshot.get('completion_status'),
                 memories=snapshot.get('memories') or [], canon=snapshot.get('canon'))


def sequential_recovery(reader: ArtifactReader) -> dict | None:
    """The failed run's own resume summary: completed_scenes, total_scenes, resume_scene."""
    files = reader.files('story-recovery')
    return _json(files, 'recovery.json') if files else None


def sequential_warnings(reader: ArtifactReader) -> list[str]:
    snapshot = _snapshot(reader) or {}
    return [f'{s["id"]} is a provisional draft ({s["quality_status"]})' for s in snapshot.get('accepted') or [] if s.get('quality_status') not in (None, 'reviewed')]


# Parallel mode

_PLANNED = re.compile(r'^planned-(write|check|patch)-(.+)$')


def _parallel_scenes(reader: ArtifactReader) -> dict[str, dict[str, str]]:
    """Map scene ID to its latest stage artifacts, e.g. {'ch01-sc01': {'write': ..., 'check': ...}}."""
    scenes: dict[str, dict[str, str]] = {}
    for name in reader.names():
        match = _PLANNED.match(name)
        if match:
            scenes.setdefault(match[2], {})[match[1]] = name
    return dict(sorted(scenes.items()))


def _parallel_scene_record(reader: ArtifactReader, stages: dict[str, str]) -> tuple[str, str, dict]:
    """Return (prose, status, reviews) using the latest stage that produced prose."""
    prose, status, reviews = '', 'unreviewed', {}
    for stage in ('write', 'patch'):
        files = reader.files(stages[stage]) if stage in stages else None
        if files:
            record = _json(files, 'scene.json') or {}
            prose = _text(files, 'prose.txt') or record.get('prose', prose)
            status = record.get('status', status)
    check = reader.files(stages['check']) if 'check' in stages else None
    if check:
        record = _json(check, 'scene.json') or {}
        status = record.get('status', status)
        reviews['check'] = {k: v for k, v in record.items() if k != 'prose'}
    return prose, status, reviews


def parallel_story(run_id: int, reader: ArtifactReader) -> Story:
    files = _need(reader, 'parallel-readable-story')
    report = _json(files, 'report.json') or {}
    scenes = []
    for scene_id, stages in _parallel_scenes(reader).items():
        prose, status, _ = _parallel_scene_record(reader, stages)
        scenes.append(SceneSummary(id=scene_id, status=status, words=_words(prose)))
    return Story(run_id=run_id, mode='parallel', title=report.get('title'), complete=bool(report.get('pass')),
                 completion_status=report.get('status'), text=_text(files, 'STORY-DRAFT.txt'), scenes=scenes)


def parallel_scene(reader: ArtifactReader, scene_id: str) -> Scene:
    stages = _parallel_scenes(reader).get(scene_id)
    if not stages:
        raise NotAvailable(f'Scene {scene_id!r} has no saved prose in this run')
    prose, status, reviews = _parallel_scene_record(reader, stages)
    return Scene(id=scene_id, status=status, words=_words(prose), prose=prose, reviews=reviews)


# Progress from job names (available while a run is still going)

_COMMIT = re.compile(r'^Scene (\d+) / Commit scene')


def progress(mode: str, jobs: list[Job]) -> Progress:
    done = [j for j in jobs if j.status in {'succeeded', 'failed', 'cancelled', 'skipped'}]
    result = Progress(jobs_total=len(jobs), jobs_done=len(done))
    if mode == 'sequential':
        result.accepted_scenes = sum(1 for j in jobs if _COMMIT.match(j.name) and j.status == 'succeeded')
    elif mode == 'parallel':
        writes = [j for j in jobs if j.name.startswith('write (')]
        result.total_scenes = len(writes) or None
        result.accepted_scenes = sum(1 for j in jobs if j.name.startswith('check (') and j.status == 'succeeded')
    return result
