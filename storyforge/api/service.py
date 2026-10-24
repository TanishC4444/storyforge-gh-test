"""Backends behind the routes. GitHubBackend uses real Actions runs; demo.py
provides the same interface over bundled sample data.

Routes only call Backend methods, so a new data source (another repo, a local
runner) only needs a new subclass.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

from . import artifacts as parse
from .artifacts import ArtifactReader, Files, NotAvailable
from .config import Settings
from .github import GitHubClient, GitHubError
from .modes import MODES, mode_for_workflow, new_tag, parse_title, recovery_inputs, start_inputs
from .schemas import (Artifact, AuthCheck, Canon, Job, JobStatus, RecoverRun, RunDetail, RunStatus,
                      RunSummary, Scene, StartedRun, StartRun, Story)


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def run_status(status: str, conclusion: str | None) -> RunStatus:
    if status != 'completed':
        return 'running' if status == 'in_progress' else 'queued'
    if conclusion == 'success':
        return 'succeeded'
    if conclusion in {'cancelled', 'skipped'}:
        return 'cancelled'
    return 'failed'


def job_status(status: str, conclusion: str | None) -> JobStatus:
    if status != 'completed':
        return 'running' if status == 'in_progress' else 'queued'
    return {'success': 'succeeded', 'cancelled': 'cancelled', 'skipped': 'skipped'}.get(conclusion or '', 'failed')


def request_files(settings: Settings) -> list[str]:
    names = []
    for path in sorted(settings.examples_dir.glob('*.json')):
        try:
            value = json.loads(path.read_text())
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get('premise'), str):
            names.append(path.stem)
    return names


def check_request_file(settings: Settings, name: str):
    if name not in request_files(settings):
        raise NotFound(f'No story brief named {name!r}; see GET /requests')


class Backend:
    """Shared behaviour. Subclasses supply runs, jobs and artifact readers."""

    def __init__(self, settings: Settings):
        self.settings = settings

    # Subclass interface

    def auth_check(self) -> AuthCheck: raise NotImplementedError
    def list_runs(self, mode: str | None, tag: str | None, limit: int) -> list[RunSummary]: raise NotImplementedError
    def get_run(self, run_id: int) -> RunDetail: raise NotImplementedError
    def start_run(self, body: StartRun) -> StartedRun: raise NotImplementedError
    def recover_run(self, run_id: int, body: RecoverRun) -> StartedRun: raise NotImplementedError
    def cancel_run(self, run_id: int) -> None: raise NotImplementedError
    def list_artifacts(self, run_id: int) -> list[Artifact]: raise NotImplementedError
    def artifact_zip(self, run_id: int, name: str) -> bytes: raise NotImplementedError
    def reader(self, run_id: int) -> ArtifactReader: raise NotImplementedError
    def mode_of(self, run_id: int) -> str: raise NotImplementedError
    def request_file_of(self, run_id: int) -> str | None: raise NotImplementedError

    # Shared

    def close(self):
        pass

    def refresh(self, run_id: int):
        """Drop anything cached about a run so the next read is current."""

    def finish_detail(self, detail: RunDetail, done: bool) -> RunDetail:
        """Fill status details that need jobs or artifacts. Both backends call this from get_run."""
        # GitHub reports a started run as "queued" again while new jobs wait for runners.
        if detail.status == 'queued' and any(j.status != 'queued' for j in detail.jobs):
            detail.status = 'running'
        if not done or detail.mode != 'sequential':
            return detail
        reader = self.reader(detail.id)
        names = set(reader.names())
        detail.recoverable = detail.status == 'failed' and 'quickstart' in names
        snapshot = parse._snapshot(reader) or {}
        request = snapshot.get('request') or {}
        if snapshot:
            detail.progress.accepted_scenes = len(snapshot.get('accepted') or [])
            if request.get('chapters') and request.get('scenes_per_chapter'):
                detail.progress.total_scenes = request['chapters'] * request['scenes_per_chapter']
        recovery = parse.sequential_recovery(reader) if detail.status == 'failed' else None
        if recovery:
            detail.progress.accepted_scenes = recovery.get('completed_scenes', detail.progress.accepted_scenes)
            detail.progress.total_scenes = recovery.get('total_scenes') or detail.progress.total_scenes
            detail.resume_scene = recovery.get('resume_scene')
        detail.warnings = parse.sequential_warnings(reader)
        if detail.status == 'succeeded' and detail.warnings:
            detail.status = 'succeeded_with_warnings'
        return detail

    def story(self, run_id: int) -> Story:
        mode = self._content_mode(run_id)
        reader = self.reader(run_id)
        story = parse.sequential_story(run_id, reader) if mode == 'sequential' else parse.parallel_story(run_id, reader)
        if not story.title:
            request_file = self.request_file_of(run_id)
            if request_file and request_file in request_files(self.settings):
                story.title = json.loads((self.settings.examples_dir / f'{request_file}.json').read_text()).get('title')
        return story

    def scene(self, run_id: int, scene_id: str) -> Scene:
        mode = self._content_mode(run_id)
        reader = self.reader(run_id)
        return parse.sequential_scene(reader, scene_id) if mode == 'sequential' else parse.parallel_scene(reader, scene_id)

    def canon(self, run_id: int) -> Canon:
        if self._content_mode(run_id) != 'sequential':
            raise Conflict('Only sequential runs commit canon')
        return parse.sequential_canon(run_id, self.reader(run_id))

    def _content_mode(self, run_id: int) -> str:
        mode = self.mode_of(run_id)
        if mode == 'recovery':
            raise Conflict('In-place recovery writes into the original run; read the story from tracks_run_id')
        return mode


class GitHubReader:
    """Reads one run's artifacts, caching downloaded zips on disk by artifact ID."""

    def __init__(self, client: GitHubClient, run_id: int, cache_dir: Path):
        self.client, self.run_id, self.cache_dir = client, run_id, cache_dir
        self._latest: dict[str, dict] | None = None
        self._files: dict[str, Files | None] = {}

    def latest(self) -> dict[str, dict]:
        if self._latest is None:
            latest: dict[str, dict] = {}
            # Reruns can upload a new artifact under the same name; the newest wins.
            for item in sorted(self.client.artifacts(self.run_id), key=lambda a: a['id']):
                if not item['expired']:
                    latest[item['name']] = item
            self._latest = latest
        return self._latest

    def names(self) -> list[str]:
        return sorted(self.latest())

    def zip_bytes(self, name: str) -> bytes | None:
        item = self.latest().get(name)
        if item is None:
            return None
        path = self.cache_dir / f'{item["id"]}.zip'
        if path.exists():
            return path.read_bytes()
        data = self.client.artifact_zip(item['id'])
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.download-')
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(temp, path)
        return data

    def files(self, name: str) -> Files | None:
        if name not in self._files:
            data = self.zip_bytes(name)
            self._files[name] = parse.unzip(data) if data is not None else None
        return self._files[name]


class GitHubBackend(Backend):
    def __init__(self, settings: Settings, token: str, client: GitHubClient | None = None):
        super().__init__(settings)
        self.client = client or GitHubClient(token, settings.repo, settings.github_api)
        self._runs: dict[int, dict] = {}
        self._readers: dict[int, GitHubReader] = {}

    def close(self):
        self.client.close()

    def refresh(self, run_id: int):
        self._runs.pop(run_id, None)
        self._readers.pop(run_id, None)

    def auth_check(self) -> AuthCheck:
        user = self.client.user()
        permissions = self.client.repository().get('permissions') or {}
        return AuthCheck(login=user['login'], repo=self.settings.repo, can_dispatch=bool(permissions.get('push')))

    def _raw_run(self, run_id: int) -> dict:
        if run_id not in self._runs:
            try:
                self._runs[run_id] = self.client.run(run_id)
            except GitHubError as exc:
                if exc.status == 404:
                    raise NotFound(f'Run {run_id} not found in {self.settings.repo}') from None
                raise
        return self._runs[run_id]

    def mode_of(self, run_id: int) -> str:
        mode = mode_for_workflow(self._raw_run(run_id)['path'])
        if mode is None:
            raise NotFound(f'Run {run_id} is not a sequential, parallel or recovery run')
        return mode

    def reader(self, run_id: int) -> GitHubReader:
        if run_id not in self._readers:
            self._readers[run_id] = GitHubReader(self.client, run_id, self.settings.cache_dir)
        return self._readers[run_id]

    def _summary(self, run: dict) -> RunSummary:
        request_file, tag = parse_title(run.get('display_title', ''))
        return RunSummary(
            id=run['id'], mode=mode_for_workflow(run['path']), workflow=run['path'].rsplit('/', 1)[-1],
            title=run.get('display_title') or run.get('name') or '', status=run_status(run['status'], run.get('conclusion')),
            request_file=request_file, tracking_tag=tag if tag and tag.startswith('api-') else None,
            attempt=run.get('run_attempt', 1), created_at=run['created_at'], updated_at=run['updated_at'], html_url=run.get('html_url'),
        )

    def list_runs(self, mode: str | None, tag: str | None, limit: int) -> list[RunSummary]:
        workflows = [MODES[mode].workflow] if mode else [m.workflow for m in MODES.values()]
        runs = [self._summary(r) for w in workflows for r in self.client.workflow_runs(w, per_page=limit)]
        if tag:
            runs = [r for r in runs if r.tracking_tag == tag]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)[:limit]

    def get_run(self, run_id: int) -> RunDetail:
        mode = self.mode_of(run_id)
        run = self._raw_run(run_id)
        summary = self._summary(run)
        jobs = [Job(id=j['id'], name=j['name'], status=job_status(j['status'], j.get('conclusion')),
                    started_at=j.get('started_at'), completed_at=j.get('completed_at'), html_url=j.get('html_url'))
                for j in self.client.jobs(run_id)]
        detail = RunDetail(**summary.model_dump(), jobs=jobs, progress=parse.progress(mode, jobs))
        return self.finish_detail(detail, done=run['status'] == 'completed')

    def request_file_of(self, run_id: int) -> str | None:
        return parse_title(self._raw_run(run_id).get('display_title', ''))[0]

    def _find_run(self, workflow: str, tag: str | None, since: float) -> int | None:
        """Find a just-dispatched run: by tag when the workflow shows one, else by creation time."""
        for _ in range(5):
            for run in self.client.workflow_runs(workflow, per_page=10):
                created = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00')).timestamp()
                if tag and parse_title(run.get('display_title', ''))[1] == tag:
                    return run['id']
                if not tag and created >= since - 5:
                    return run['id']
            time.sleep(2)
        return None

    def _dispatch(self, mode: str, workflow: str, inputs: dict[str, str], tag: str | None) -> StartedRun:
        since = time.time()
        run_id = self.client.dispatch(workflow, self.settings.ref, inputs)
        if run_id is None:
            run_id = self._find_run(workflow, tag, since)
        html = f'https://github.com/{self.settings.repo}/actions/runs/{run_id}' if run_id else None
        return StartedRun(mode=mode, workflow=workflow, run_id=run_id, tracking_tag=tag, html_url=html)

    def start_run(self, body: StartRun) -> StartedRun:
        check_request_file(self.settings, body.request_file)
        tag = new_tag()
        workflow, inputs = start_inputs(body, tag)
        return self._dispatch(body.mode, workflow, inputs, tag)

    def recover_run(self, run_id: int, body: RecoverRun) -> StartedRun:
        if self.mode_of(run_id) != 'sequential':
            raise Conflict('Recovery supports sequential runs only')
        summary = self._summary(self._raw_run(run_id))
        if summary.status != 'failed':
            raise Conflict(f'Run {run_id} is {summary.status}; only failed runs can be recovered')
        tag = new_tag() if body.strategy == 'fresh' else None
        workflow, inputs = recovery_inputs(body, run_id, summary.request_file, tag)
        if body.strategy == 'fresh':
            check_request_file(self.settings, summary.request_file)
        started = self._dispatch('sequential' if body.strategy == 'fresh' else 'recovery', workflow, inputs, tag)
        if body.strategy == 'rerun':
            started.tracks_run_id = run_id
        return started

    def cancel_run(self, run_id: int) -> None:
        self.mode_of(run_id)
        if self._raw_run(run_id)['status'] == 'completed':
            raise Conflict(f'Run {run_id} has already finished')
        self.client.cancel(run_id)

    def list_artifacts(self, run_id: int) -> list[Artifact]:
        self.mode_of(run_id)
        return [Artifact(id=a['id'], name=a['name'], size_bytes=a['size_in_bytes'], expired=a['expired'], created_at=a.get('created_at'))
                for a in self.client.artifacts(run_id)]

    def artifact_zip(self, run_id: int, name: str) -> bytes:
        self.mode_of(run_id)
        data = self.reader(run_id).zip_bytes(name)
        if data is None:
            raise NotFound(f'Run {run_id} has no unexpired artifact named {name!r}')
        return data
