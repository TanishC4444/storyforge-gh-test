"""The three supported modes and how they map onto workflow_dispatch inputs.

Each mode wraps one workflow. tests/test_api.py checks every input here against
the workflow YAML, so a workflow change that breaks the API fails the tests.
To expose a new workflow input, add a ModeInput to the right mode.
"""
from __future__ import annotations

import re
import secrets

from .schemas import Mode, ModeInput, RecoverRun, StartRun

SEQUENTIAL_WORKFLOW = 'living-universe-pipeline.yml'
PARALLEL_WORKFLOW = 'planned-parallel.yml'
RECOVERY_WORKFLOW = 'resume-story.yml'

_REQUEST = ModeInput(name='request_file', label='Story brief', type='string', required=True,
                     description='A brief from GET /requests.')
_BACKEND = ModeInput(name='backend', label='Backend', type='choice', options=['fixture', 'live'], default='fixture',
                     description='"fixture" tests the plumbing with synthetic prose; "live" runs real models.')

MODES: dict[str, Mode] = {
    'sequential': Mode(
        id='sequential', label='Sequential',
        description='Writes scenes one at a time. Each scene is reviewed, repaired and committed to canon before the next starts.',
        workflow=SEQUENTIAL_WORKFLOW, starts_from='request',
        inputs=[
            _REQUEST, _BACKEND,
            ModeInput(name='profile', label='Model profile', type='choice', options=['balanced', 'expressive', 'fast', 'small'], default='fast'),
            ModeInput(name='scene_limit', label='Scenes this run', type='choice', options=['1', '2', '4'], default='2'),
            ModeInput(name='resume_run', label='Continue world from run', type='string', default='',
                      description='Prior run with an accepted universe-canon checkpoint. Empty starts a new world.'),
            ModeInput(name='checkpoint_artifact', label='Checkpoint artifact', type='choice', options=['universe-canon', 'quickstart'], default='universe-canon'),
            ModeInput(name='saved_draft_run', label='Reuse first-scene draft from run', type='string', default=''),
        ],
    ),
    'parallel': Mode(
        id='parallel', label='Parallel',
        description='Plans every scene in depth first, then writes all scenes at once on separate runners and checks them together.',
        workflow=PARALLEL_WORKFLOW, starts_from='request',
        inputs=[_REQUEST, _BACKEND],
    ),
    'recovery': Mode(
        id='recovery', label='Recovery',
        description='Continues a failed sequential run from its first unfinished scene, keeping approved scenes and saved drafts.',
        workflow=RECOVERY_WORKFLOW, starts_from='run',
        inputs=[
            ModeInput(name='strategy', label='Strategy', type='choice', options=['fresh', 'rerun'], default='fresh',
                      description='"fresh" starts a new sequential run from the saved prefix; "rerun" retries the failed stage inside the original run.'),
            ModeInput(name='scene', label='First unfinished scene', type='choice', options=['auto', '1', '2', '3', '4'], default='auto'),
            ModeInput(name='restart_stage', label='Restart stage', type='choice', options=['auto', 'editing', 'memory', 'scene'], default='auto',
                      description='Rerun strategy only.'),
        ],
    ),
}

# Workflow inputs the API sets itself; callers cannot pass them.
MANAGED_INPUTS = {
    SEQUENTIAL_WORKFLOW: {'queue_tag', 'fresh_run', 'recovery_probe'},
    PARALLEL_WORKFLOW: {'queue_tag'},
    RECOVERY_WORKFLOW: {'source_run'},
}

_WORKFLOW_MODES = {SEQUENTIAL_WORKFLOW: 'sequential', PARALLEL_WORKFLOW: 'parallel', RECOVERY_WORKFLOW: 'recovery'}

# Both request-driven workflows set run-name to "<Label> | <request_file> | <queue_tag or run number>".
_TITLE = re.compile(r'^(?:Living|Planned parallel) \| (?P<request>[A-Za-z0-9_-]+) \| (?P<tag>\S+)$')


def mode_for_workflow(path: str) -> str | None:
    return _WORKFLOW_MODES.get(path.rsplit('/', 1)[-1])


def parse_title(title: str) -> tuple[str | None, str | None]:
    """Return (request_file, tag) from a run's display title."""
    match = _TITLE.match(title or '')
    return (match['request'], match['tag']) if match else (None, None)


def new_tag() -> str:
    return 'api-' + secrets.token_hex(4)


def _check_choice(spec: ModeInput, value):
    if spec.type == 'choice' and str(value) not in (spec.options or []):
        raise ValueError(f'{spec.name} must be one of {spec.options}')
    if spec.type == 'boolean' and not isinstance(value, bool):
        raise ValueError(f'{spec.name} must be true or false')
    if spec.type == 'string' and not isinstance(value, str):
        raise ValueError(f'{spec.name} must be a string')


def start_inputs(body: StartRun, tag: str) -> tuple[str, dict[str, str]]:
    """Return (workflow, dispatch inputs) for a sequential or parallel start."""
    mode = MODES[body.mode]
    specs = {spec.name: spec for spec in mode.inputs}
    values: dict[str, str | bool] = {'request_file': body.request_file, 'backend': body.backend}
    for name, value in body.inputs.items():
        if name in values or name not in specs:
            allowed = sorted(set(specs) - {'request_file', 'backend'})
            raise ValueError(f'Unknown input {name!r} for {mode.id} mode; allowed: {allowed}')
        values[name] = value
    for name, value in values.items():
        _check_choice(specs[name], value)
    values['queue_tag'] = tag
    # workflow_dispatch inputs are strings on the wire, including booleans.
    return mode.workflow, {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in values.items()}


def recovery_inputs(body: RecoverRun, source_run: int, request_file: str | None, tag: str) -> tuple[str, dict[str, str]]:
    """Return (workflow, dispatch inputs) for recovering a failed sequential run."""
    if body.strategy == 'rerun':
        return RECOVERY_WORKFLOW, {'source_run': str(source_run), 'scene': body.scene, 'restart_stage': body.restart_stage}
    if not request_file:
        raise ValueError('Fresh recovery needs the original brief, which this run title does not name; use strategy "rerun"')
    # The fresh path is a new sequential run that imports the failed run's approved prefix.
    start = StartRun(mode='sequential', request_file=request_file, backend=body.backend, inputs=body.inputs)
    workflow, inputs = start_inputs(start, tag)
    inputs['fresh_run'] = str(source_run)
    return workflow, inputs
