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


class ArtifactReader(Protocol):
    def names(self) -> list[str]: ...

    def files(self, name: str) -> Files | None: ...


def unzip(data: bytes) -> Files:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}


def _json(files: Files, path: str):
    return json.loads(files[path]) if path in files else None


def _text(files: Files, path: str) -> str:
    return files[path].decode('utf-8') if path in files else ''


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


def sequential_story(run_id: int, reader: ArtifactReader) -> Story:
    files = _need(reader, 'readable-story')
    snapshot = _json(files, 'canon/snapshot.json') or {}
    status = _json(files, 'reading-status.json') or {}
    accepted = snapshot.get('accepted') or []
    if accepted:
        scenes = [SceneSummary(id=s['id'], status=s.get('quality_status', 'reviewed'), words=_words(s.get('prose', ''))) for s in accepted]
    else:
        scenes = [SceneSummary(id=s['scene_id'], status=s.get('status', 'unknown'), words=s.get('words', 0)) for s in status.get('scenes', [])]
    return Story(
        run_id=run_id, mode='sequential',
        title=(snapshot.get('request') or {}).get('title'),
        complete=bool(snapshot.get('complete')),
        completion_status=snapshot.get('completion_status'),
        text=_text(files, 'READABLE_DRAFT.txt'),
        scenes=scenes,
    )


def sequential_scene(reader: ArtifactReader, scene_id: str) -> Scene:
    snapshot = _snapshot(reader) or {}
    for s in snapshot.get('accepted') or []:
        if s['id'] == scene_id:
            reviews = {key: s[field] for key, field in [('story', 'review'), ('rhetoric', 'rhetoric_review'), ('memory', 'memory_review')] if s.get(field) is not None}
            return Scene(id=s['id'], status=s.get('quality_status', 'reviewed'), words=_words(s['prose']), prose=s['prose'], reviews=reviews)
    raise NotAvailable(f'Scene {scene_id!r} has no accepted prose in this run')


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
