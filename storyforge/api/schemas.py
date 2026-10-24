"""Request and response models. These define the public API contract.

Add fields rather than renaming or removing them, so existing frontend code
keeps working. Regenerate web/openapi.json after any change here
(python -m scripts.export_openapi).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ModeId = Literal['sequential', 'parallel', 'recovery']

# One vocabulary for every run, whatever GitHub reports underneath.
RunStatus = Literal['queued', 'running', 'succeeded', 'succeeded_with_warnings', 'failed', 'cancelled']

JobStatus = Literal['queued', 'running', 'succeeded', 'failed', 'cancelled', 'skipped']


class ErrorBody(BaseModel):
    detail: str


class Health(BaseModel):
    ok: bool = True
    version: str
    repo: str
    ref: str
    demo_available: bool


class AuthCheck(BaseModel):
    login: str
    repo: str
    can_dispatch: bool = Field(description='True when the token can start workflows on the repo.')
    demo: bool = False


class ModeInput(BaseModel):
    name: str
    label: str
    type: Literal['choice', 'string', 'boolean']
    options: list[str] | None = None
    default: str | bool | None = None
    required: bool = False
    description: str = ''


class Mode(BaseModel):
    id: ModeId
    label: str
    description: str
    workflow: str
    starts_from: Literal['request', 'run'] = Field(description='"request" modes start from a story brief; "run" modes act on an earlier run.')
    inputs: list[ModeInput]


class RequestSummary(BaseModel):
    id: str
    title: str
    medium: str | None = None
    genre: str | None = None
    chapters: int
    scenes_per_chapter: int
    words_per_scene: int
    characters: int
    premise: str


class ValidationResult(BaseModel):
    valid: bool
    error: str | None = None
    normalized: dict[str, Any] | None = None


class StartRun(BaseModel):
    mode: Literal['sequential', 'parallel']
    request_file: str = Field(description='Name of a brief in examples/ without .json, from GET /requests.')
    backend: Literal['fixture', 'live'] = 'fixture'
    inputs: dict[str, str | bool] = Field(default_factory=dict, description='Other mode inputs listed by GET /modes, e.g. profile or scene_limit.')


class RecoverRun(BaseModel):
    strategy: Literal['fresh', 'rerun'] = Field(
        'fresh',
        description='"fresh" starts a new run that reuses the approved prefix; "rerun" re-executes the failed stage inside the original run.',
    )
    scene: Literal['auto', '1', '2', '3', '4'] = 'auto'
    restart_stage: Literal['auto', 'editing', 'memory', 'scene'] = Field('auto', description='Used by the "rerun" strategy only.')
    backend: Literal['fixture', 'live'] = Field('live', description='Fresh strategy only. Must match the original run.')
    inputs: dict[str, str | bool] = Field(default_factory=dict, description='Fresh strategy only: sequential-mode inputs such as profile or scene_limit.')


class StartedRun(BaseModel):
    mode: ModeId
    workflow: str
    run_id: int | None = Field(None, description='Null when GitHub has not listed the run yet; poll GET /runs?tag=<tracking_tag>.')
    tracking_tag: str | None = None
    tracks_run_id: int | None = Field(None, description='For in-place recovery: the original run whose progress to watch.')
    html_url: str | None = None


class Job(BaseModel):
    id: int
    name: str
    status: JobStatus
    started_at: str | None = None
    completed_at: str | None = None
    html_url: str | None = None


class Progress(BaseModel):
    jobs_total: int = 0
    jobs_done: int = 0
    accepted_scenes: int | None = None
    total_scenes: int | None = None


class RunSummary(BaseModel):
    id: int
    mode: ModeId
    workflow: str
    title: str
    status: RunStatus
    request_file: str | None = None
    tracking_tag: str | None = None
    attempt: int = 1
    created_at: str
    updated_at: str
    html_url: str | None = None


class RunList(BaseModel):
    runs: list[RunSummary]


class RunDetail(RunSummary):
    jobs: list[Job] = []
    progress: Progress = Progress()
    recoverable: bool = Field(False, description='True when POST /runs/{id}/recover can continue this run.')
    warnings: list[str] = []


class SceneSummary(BaseModel):
    id: str
    status: str = Field(description='"reviewed", "needs_review", "unreviewed" or a pipeline-specific label.')
    words: int


class Story(BaseModel):
    run_id: int
    mode: ModeId
    title: str | None = None
    complete: bool
    completion_status: str | None = None
    text: str
    scenes: list[SceneSummary]


class Scene(SceneSummary):
    prose: str
    reviews: dict[str, Any] = Field(default_factory=dict, description='Raw review records keyed by reviewer (story, rhetoric, memory, check).')


class Canon(BaseModel):
    run_id: int
    version: int | None = None
    completion_status: str | None = None
    memories: list[dict[str, Any]] = []
    canon: Any = None


class Artifact(BaseModel):
    id: int
    name: str
    size_bytes: int
    expired: bool
    created_at: str | None = None


class ArtifactList(BaseModel):
    artifacts: list[Artifact]
