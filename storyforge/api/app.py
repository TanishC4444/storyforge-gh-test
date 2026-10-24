"""FastAPI application. Run with:

    uvicorn storyforge.api.app:app --reload

Interactive docs are served at /docs. Every route except /health, /modes and
/requests needs `Authorization: Bearer <GitHub token>` (or `Bearer demo`).
"""
from __future__ import annotations

import asyncio
import copy
import json
import time
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, Path as RoutePath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ..contracts import ContractError, request as validate_request
from .artifacts import NotAvailable, InvalidArtifact
from .config import Settings, get_settings
from .demo import DemoBackend
from .github import GitHubError
from .modes import MODES
from .schemas import (ArtifactList, AuthCheck, Canon, ErrorBody, Health, Mode, RecoverRun, RequestSummary,
                      RunDetail, RunList, RunStatus, Scene, StartedRun, StartRun, Story, ValidationResult)
from .service import Backend, Conflict, GitHubBackend, NotFound, request_files, supported_modes

API_VERSION = '0.1.0'
PREFIX = '/api/v1'
RunId = Annotated[int, RoutePath(gt=0)]

app = FastAPI(
    title='Storyforge API',
    version=API_VERSION,
    description='Start and read Storyforge story runs on GitHub Actions. Authenticate with your own GitHub token, or `demo` for sample data.',
    responses={401: {'model': ErrorBody}, 404: {'model': ErrorBody}, 409: {'model': ErrorBody}, 422: {'model': ErrorBody}, 502: {'model': ErrorBody}},
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_settings.cors_origins),
    allow_methods=['GET', 'POST'],
    allow_headers=['Authorization', 'Content-Type'],
)


@app.middleware('http')
async def allow_private_network(request: Request, call_next):
    # Lets a hosted frontend (e.g. GitHub Pages) call an API running on localhost in Chromium browsers.
    response = await call_next(request)
    if request.method == 'OPTIONS' and request.headers.get('access-control-request-private-network'):
        response.headers['Access-Control-Allow-Private-Network'] = 'true'
    return response


# Error mapping: backends raise plain exceptions; HTTP codes are decided here only.

@app.exception_handler(NotFound)
async def _not_found(_, exc):
    return JSONResponse({'detail': str(exc)}, status_code=404)


@app.exception_handler(NotAvailable)
async def _not_available(_, exc):
    return JSONResponse({'detail': str(exc)}, status_code=404)


@app.exception_handler(Conflict)
async def _conflict(_, exc):
    return JSONResponse({'detail': str(exc)}, status_code=409)


@app.exception_handler(InvalidArtifact)
async def _invalid_artifact(_, exc):
    return JSONResponse({'detail':str(exc)},status_code=502)


@app.exception_handler(ValueError)
async def _invalid(_, exc):
    return JSONResponse({'detail': str(exc)}, status_code=422)


@app.exception_handler(GitHubError)
async def _github(_, exc: GitHubError):
    # Pass auth and permission errors through; anything else is an upstream failure.
    status = exc.status if exc.status in {401, 403, 404, 409, 422} else 502
    return JSONResponse({'detail': exc.message}, status_code=status)


# Dependencies

def settings() -> Settings:
    return _settings


def make_backend(authorization: str | None, config: Settings) -> Backend:
    scheme, _, token = (authorization or '').partition(' ')
    token = token.strip()
    if scheme.lower() != 'bearer' or not token:
        raise HTTPException(401, 'Send your GitHub token as "Authorization: Bearer <token>"', headers={'WWW-Authenticate': 'Bearer'})
    if token == 'demo':
        if not config.allow_demo:
            raise HTTPException(401, 'Demo mode is disabled on this server')
        return DemoBackend(config)
    return GitHubBackend(config, token)


AuthHeader = Annotated[str | None, Header(description='Bearer <GitHub token>, or Bearer demo')]


def backend(authorization: AuthHeader = None, config: Settings = Depends(settings)) -> Iterator[Backend]:
    instance = make_backend(authorization, config)
    try:
        yield instance
    finally:
        instance.close()


BackendDep = Annotated[Backend, Depends(backend)]


# Public

@app.get(f'{PREFIX}/health', response_model=Health, tags=['meta'])
def health(config: Settings = Depends(settings)):
    return Health(version=API_VERSION, repo=config.repo, ref=config.ref, demo_available=config.allow_demo)


@app.get(f'{PREFIX}/modes', response_model=list[Mode], tags=['meta'])
def list_modes():
    """The three modes and every input each accepts. Build start forms from this."""
    return list(MODES.values())


def _load_request(config: Settings, name: str) -> dict:
    if name not in request_files(config):
        raise NotFound(f'No story brief named {name!r}')
    return json.loads((config.examples_dir / f'{name}.json').read_text())


@app.get(f'{PREFIX}/requests', response_model=list[RequestSummary], tags=['requests'])
def list_requests(config: Settings = Depends(settings)):
    """Story briefs available to start runs with (examples/*.json on the server)."""
    out = []
    for name in request_files(config):
        value = _load_request(config, name)
        out.append(RequestSummary(
            supported_modes=supported_modes(value), id=name, title=value.get('title') or name, medium=value.get('medium'), genre=value.get('genre'),
            chapters=value.get('chapters', 3), scenes_per_chapter=value.get('scenes_per_chapter', 3),
            words_per_scene=value.get('words_per_scene', 850), characters=len(value.get('characters') or []), premise=value['premise'],
        ))
    return out


@app.get(f'{PREFIX}/requests/{{request_id}}', tags=['requests'])
def get_request(request_id: str, config: Settings = Depends(settings)) -> dict[str, Any]:
    return _load_request(config, request_id)


@app.post(f'{PREFIX}/requests/validate', response_model=ValidationResult, tags=['requests'])
def validate(brief: dict[str, Any] = Body(...)):
    """Check a brief against the pipeline contract without starting anything."""
    try:
        return ValidationResult(valid=True, normalized=validate_request(copy.deepcopy(brief)))
    except (ContractError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return ValidationResult(valid=False, error=str(exc))


# Authenticated

@app.get(f'{PREFIX}/auth/check', response_model=AuthCheck, tags=['auth'])
def auth_check(api: BackendDep):
    """Confirm the token works and whether it can start runs."""
    return api.auth_check()


@app.get(f'{PREFIX}/runs', response_model=RunList, tags=['runs'])
def list_runs(api: BackendDep,
              mode: Annotated[str | None, Query(pattern='^(sequential|parallel|recovery)$')] = None,
              status: Annotated[RunStatus | None, Query(description='Filter by RunStatus')] = None,
              tag: Annotated[str | None, Query(description='tracking_tag returned by POST /runs')] = None,
              limit: Annotated[int, Query(ge=1, le=50)] = 20):
    runs = api.list_runs(mode, tag, limit)
    if status:
        runs = [r for r in runs if r.status == status]
    return RunList(runs=runs)


@app.post(f'{PREFIX}/runs', response_model=StartedRun, status_code=202, tags=['runs'])
def start_run(body: StartRun, api: BackendDep):
    """Start a sequential or parallel run. Returns immediately; follow it with GET /runs/{id}/events."""
    return api.start_run(body)


@app.get(f'{PREFIX}/runs/{{run_id}}', response_model=RunDetail, tags=['runs'])
def get_run(run_id: RunId, api: BackendDep):
    return api.get_run(run_id)


@app.post(f'{PREFIX}/runs/{{run_id}}/recover', response_model=StartedRun, status_code=202, tags=['runs'])
def recover_run(run_id: RunId, api: BackendDep, body: RecoverRun = Body(default_factory=RecoverRun)):
    """Recovery mode: continue a failed sequential run."""
    return api.recover_run(run_id, body)


@app.post(f'{PREFIX}/runs/{{run_id}}/cancel', status_code=202, tags=['runs'])
def cancel_run(run_id: RunId, api: BackendDep) -> dict[str, bool]:
    api.cancel_run(run_id)
    return {'cancel_requested': True}


@app.get(f'{PREFIX}/runs/{{run_id}}/events', tags=['runs'], response_class=StreamingResponse,
         responses={200: {'content': {'text/event-stream': {}}, 'description': 'Server-sent events: "run" carries a RunDetail; "end" closes the stream.'}})
async def run_events(run_id: RunId, authorization: AuthHeader = None, config: Settings = Depends(settings)):
    """Stream run updates. Browsers must read this with fetch() (EventSource cannot send the token)."""
    # The stream owns its backend, so the client stays open for the stream's whole life.
    api = make_backend(authorization, config)
    try:
        first = await asyncio.to_thread(api.get_run, run_id)  # errors return before the stream opens
    except Exception:
        api.close()
        raise
    poll = 1.0 if isinstance(api, DemoBackend) else config.poll_seconds

    async def stream():
        detail, last, deadline = first, None, time.monotonic() + config.stream_seconds
        try:
            while True:
                payload = detail.model_dump_json()
                if payload != last:
                    yield f'event: run\ndata: {payload}\n\n'
                    last = payload
                else:
                    yield ': keep-alive\n\n'
                if detail.status not in {'queued', 'running'} or time.monotonic() > deadline:
                    yield 'event: end\ndata: {}\n\n'
                    return
                await asyncio.sleep(poll)
                api.refresh(run_id)
                detail = await asyncio.to_thread(api.get_run, run_id)
        finally:
            api.close()

    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.get(f'{PREFIX}/runs/{{run_id}}/story', response_model=Story, tags=['content'])
def get_story(run_id: RunId, api: BackendDep):
    """The readable manuscript and per-scene status. 404 until the run uploads it."""
    return api.story(run_id)


@app.get(f'{PREFIX}/runs/{{run_id}}/scenes/{{scene_id}}', response_model=Scene, tags=['content'])
def get_scene(run_id: RunId, scene_id: str, api: BackendDep):
    return api.scene(run_id, scene_id)


@app.get(f'{PREFIX}/runs/{{run_id}}/canon', response_model=Canon, tags=['content'])
def get_canon(run_id: RunId, api: BackendDep):
    """Committed facts and memory (sequential runs)."""
    return api.canon(run_id)


@app.get(f'{PREFIX}/runs/{{run_id}}/artifacts', response_model=ArtifactList, tags=['content'])
def list_artifacts(run_id: RunId, api: BackendDep):
    return ArtifactList(artifacts=api.list_artifacts(run_id))


@app.get(f'{PREFIX}/runs/{{run_id}}/artifacts/{{name}}', tags=['content'], response_class=Response,
         responses={200: {'content': {'application/zip': {}}}})
def download_artifact(run_id: RunId, name: str, api: BackendDep):
    return Response(api.artifact_zip(run_id, name), media_type='application/zip',
                    headers={'Content-Disposition': f'attachment; filename="{name}.zip"'})
