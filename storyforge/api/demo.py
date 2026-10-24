"""Demo backend: the full API over bundled sample runs, with no GitHub calls.

Send `Authorization: Bearer demo` to use it. Started runs advance through
simulated jobs over DEMO_SECONDS, then expose the bundled story artifacts.
State is in memory and resets when the server restarts.

Sample content comes from real live runs of this repo:
sequential from run 40108148721 (hard-adapt-comic), parallel from run
40119904662 (hard-chronology, failed its final publish gate).
"""
from __future__ import annotations

import copy
import io
import json
import threading
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import artifacts as parse
from .artifacts import Files
from .config import Settings
from .modes import MODES, new_tag, recovery_inputs, start_inputs
from .schemas import Artifact, AuthCheck, Job, RecoverRun, RunDetail, RunSummary, StartedRun, StartRun
from .service import Backend, Conflict, NotFound, check_request_file

DATA = Path(__file__).with_name('demo_data')
DEMO_SECONDS = 90.0

_SEQUENTIAL_JOBS = ['Prepare request and literary retrieval', 'Compile universe beginning or bounded episode layout'] + [
    name for n in (1, 2) for name in (
        f'Scene {n} / Reconcile scene {n} with verified prior memory',
        f'Scene {n} / Write coherent scene / batch 0',
        f'Scene {n} / Full-scene story checks / batch 0',
        f'Scene {n} / Commit scene {n} only after literary and factual gates',
    )
] + ['Collect outputs and checkpoints']

_SCENES = ['ch01-sc01', 'ch02-sc01', 'ch03-sc01', 'ch04-sc01']
_PARALLEL_JOBS = (['prepare', 'outline'] + [f'description ({s})' for s in _SCENES] + ['lock'] + [f'write ({s})' for s in _SCENES]
                  + [f'check ({s})' for s in _SCENES] + ['audit', 'patch', 'publish', 'results'])

_RECOVERY_JOBS = ['resume']


def _load_dir(folder: Path) -> dict[str, Files]:
    return {child.name: {p.relative_to(child).as_posix(): p.read_bytes() for p in child.rglob('*') if p.is_file()}
            for child in sorted(folder.iterdir()) if child.is_dir()}


def _partial_sequential(full: dict[str, Files]) -> dict[str, Files]:
    """A failed sequential run that committed only its first scene."""
    files = copy.deepcopy(full)
    story = files['readable-story']
    snapshot = json.loads(story['canon/snapshot.json'])
    snapshot['accepted'] = snapshot['accepted'][:1]
    snapshot.update(complete=False, completion_status='in_progress')
    story['canon/snapshot.json'] = json.dumps(snapshot).encode()
    first = snapshot['accepted'][0]['prose']
    story['READABLE_DRAFT.txt'] = first.encode()
    story['reading-status.json'] = json.dumps({'scenes': [{'scene_id': 's01', 'status': 'reviewed', 'words': len(first.split())}], 'accepted_scenes': 1}).encode()
    files['quickstart'] = {'snapshot.json': b'{}'}
    files['story-recovery'] = {'recovery.json': json.dumps({'mode': 'retry_same_episode', 'completed_scenes': 1, 'total_scenes': 2, 'resume_scene': 2}).encode()}
    return files


@dataclass
class DemoRun:
    id: int
    mode: str
    request_file: str | None
    outcome: str  # final status once the simulated duration has passed
    data: str  # key into DemoStore.datasets
    started: float
    duration: float = DEMO_SECONDS
    tag: str | None = None
    attempt: int = 1
    cancelled_at: float | None = None
    tracks: int | None = None
    # Job index the failure is attributed to, when outcome is "failed".
    fail_at: int | None = None
    jobs: list[str] = field(default_factory=list)


class DemoStore:
    def __init__(self):
        self.lock = threading.Lock()
        sequential = _load_dir(DATA / 'sequential')
        self.datasets = {
            'sequential': sequential,
            'sequential-partial': _partial_sequential(sequential),
            'parallel': _load_dir(DATA / 'parallel'),
            'none': {},
        }
        now = time.time()
        self.runs: dict[int, DemoRun] = {}
        self.next_id = 9100
        self._add(DemoRun(9001, 'sequential', 'hard-adapt-comic', 'succeeded', 'sequential', now - 7200, jobs=_SEQUENTIAL_JOBS))
        self._add(DemoRun(9002, 'parallel', 'hard-chronology', 'failed', 'parallel', now - 5400, jobs=_PARALLEL_JOBS, fail_at=len(_PARALLEL_JOBS) - 2))
        self._add(DemoRun(9003, 'sequential', 'hard-chronology', 'failed', 'sequential-partial', now - 3600, jobs=_SEQUENTIAL_JOBS, fail_at=6))

    def _add(self, run: DemoRun):
        self.runs[run.id] = run

    def create(self, **kwargs) -> DemoRun:
        with self.lock:
            run = DemoRun(self.next_id, started=time.time(), **kwargs)
            self.next_id += 1
            self._add(run)
            return run


_STORE: DemoStore | None = None


def store() -> DemoStore:
    global _STORE
    if _STORE is None:
        _STORE = DemoStore()
    return _STORE


def reset():
    """Forget started runs (used by tests)."""
    global _STORE
    _STORE = None


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class DemoReader:
    def __init__(self, files: dict[str, Files]):
        self._files = files

    def names(self) -> list[str]:
        return sorted(self._files)

    def files(self, name: str) -> Files | None:
        return self._files.get(name)


class DemoBackend(Backend):
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.store = store()

    def _run(self, run_id: int) -> DemoRun:
        run = self.store.runs.get(run_id)
        if run is None:
            raise NotFound(f'Demo run {run_id} not found')
        return run

    def _state(self, run: DemoRun) -> tuple[str, list[Job], float]:
        now = run.cancelled_at or time.time()
        fraction = min(1.0, max(0.0, (now - run.started) / run.duration))
        total = len(run.jobs)
        finished = int(fraction * total)
        jobs = []
        for i, name in enumerate(run.jobs):
            if run.outcome == 'failed' and run.fail_at is not None and fraction >= 1 and i >= run.fail_at:
                status = 'failed' if i == run.fail_at else 'skipped'
            elif i < finished:
                status = 'succeeded'
            elif i == finished and fraction < 1:
                status = 'cancelled' if run.cancelled_at else 'running'
            else:
                status = 'cancelled' if run.cancelled_at else 'queued'
            jobs.append(Job(id=run.id * 1000 + i, name=name, status=status))
        if run.cancelled_at:
            status = 'cancelled'
        elif fraction >= 1:
            status = run.outcome
        else:
            status = 'running' if fraction > 0 else 'queued'
        return status, jobs, now

    def _summary(self, run: DemoRun) -> RunSummary:
        status, _, now = self._state(run)
        label = {'sequential': 'Living', 'parallel': 'Planned parallel'}.get(run.mode)
        title = f'{label} | {run.request_file} | {run.tag or run.id}' if label else f'Resume saved story | {run.tracks}'
        return RunSummary(id=run.id, mode=run.mode, workflow=MODES[run.mode].workflow, title=title, status=status,
                          request_file=run.request_file, tracking_tag=run.tag, attempt=run.attempt,
                          created_at=_iso(run.started), updated_at=_iso(min(now, run.started + run.duration)), html_url=None)

    def _done(self, run: DemoRun) -> bool:
        return self._state(run)[0] not in {'queued', 'running'}

    def auth_check(self) -> AuthCheck:
        return AuthCheck(login='demo', repo=self.settings.repo, can_dispatch=True, demo=True)

    def mode_of(self, run_id: int) -> str:
        return self._run(run_id).mode

    def reader(self, run_id: int) -> DemoReader:
        run = self._run(run_id)
        return DemoReader(self.store.datasets[run.data] if self._done(run) and not run.cancelled_at else {})

    def list_runs(self, mode, tag, limit):
        runs = [self._summary(r) for r in self.store.runs.values() if (not mode or r.mode == mode) and (not tag or r.tag == tag)]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)[:limit]

    def get_run(self, run_id: int) -> RunDetail:
        run = self._run(run_id)
        status, jobs, _ = self._state(run)
        detail = RunDetail(**self._summary(run).model_dump(), jobs=jobs, progress=parse.progress(run.mode, jobs))
        return self.finish_detail(detail, done=self._done(run))

    def request_file_of(self, run_id: int) -> str | None:
        return self._run(run_id).request_file

    def start_run(self, body: StartRun) -> StartedRun:
        check_request_file(self.settings, body.request_file)
        tag = new_tag()
        workflow, _ = start_inputs(body, tag)  # same validation as the real backend
        jobs = _SEQUENTIAL_JOBS if body.mode == 'sequential' else _PARALLEL_JOBS
        run = self.store.create(mode=body.mode, request_file=body.request_file, outcome='succeeded', data=body.mode, tag=tag, jobs=jobs)
        return StartedRun(mode=body.mode, workflow=workflow, run_id=run.id, tracking_tag=tag)

    def recover_run(self, run_id: int, body: RecoverRun) -> StartedRun:
        source = self._run(run_id)
        if source.mode != 'sequential':
            raise Conflict('Recovery supports sequential runs only')
        status = self._state(source)[0]
        if status != 'failed':
            raise Conflict(f'Run {run_id} is {status}; only failed runs can be recovered')
        tag = new_tag() if body.strategy == 'fresh' else None
        workflow, _ = recovery_inputs(body, run_id, source.request_file, tag)
        if body.strategy == 'fresh':
            run = self.store.create(mode='sequential', request_file=source.request_file, outcome='succeeded', data='sequential', tag=tag, jobs=_SEQUENTIAL_JOBS)
            return StartedRun(mode='sequential', workflow=workflow, run_id=run.id, tracking_tag=tag)
        # In-place rerun: a short resume run, and the original run restarts as a new attempt.
        resume = self.store.create(mode='recovery', request_file=None, outcome='succeeded', data='none', jobs=_RECOVERY_JOBS, duration=10.0, tracks=run_id)
        with self.store.lock:
            source.started, source.attempt, source.outcome, source.data, source.fail_at = time.time(), source.attempt + 1, 'succeeded', 'sequential', None
        return StartedRun(mode='recovery', workflow=workflow, run_id=resume.id, tracks_run_id=run_id)

    def cancel_run(self, run_id: int) -> None:
        run = self._run(run_id)
        if self._done(run):
            raise Conflict(f'Run {run_id} has already finished')
        run.cancelled_at = time.time()

    def list_artifacts(self, run_id: int) -> list[Artifact]:
        reader = self.reader(run_id)
        run = self._run(run_id)
        return [Artifact(id=run_id * 100 + i, name=name, size_bytes=sum(len(v) for v in reader.files(name).values()),
                         expired=False, created_at=_iso(run.started + run.duration)) for i, name in enumerate(reader.names())]

    def artifact_zip(self, run_id: int, name: str) -> bytes:
        files = self.reader(run_id).files(name)
        if files is None:
            raise NotFound(f'Run {run_id} has no artifact named {name!r}')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path, content in sorted(files.items()):
                archive.writestr(path, content)
        return buffer.getvalue()
