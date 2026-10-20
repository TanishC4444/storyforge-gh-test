"""Run the existing GH-INFERENCE worker on this already-allocated Actions runner.

No GitHub API, no workflow dispatch, and no nested runner allocation.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from .inference import ROOT


def execute(model, system, prompt, tokens, n_ctx, role):
    sys.path.insert(0, str(ROOT / 'vendor/gh-inference'))
    from gh_ai_runner.runner import INFERENCE_SCRIPT
    from gh_ai_runner.limits import Limits
    from gh_ai_runner.validation import _validate
    from gh_ai_runner.models import MODELS
    limits = Limits()
    _validate(model, tokens, .7, n_ctx, runner_ram_gb=16, runner_disk_gb=14, cache=False, limits=limits)
    config = {'model': model, 'n_ctx': n_ctx, 'max_tokens': tokens,
              'temperature': .7 if role in {'writer', 'humanizer'} else .25,
              'cache_weights': False, 'limits': limits.to_dict(),
              'agent': {'remember': False, 'history': [], 'tasks': [], 'refine_prompt': False, 'track_time': True},
              'model_options': {'chat_template_options': {'enable_thinking': False}} if model.startswith('gemma-4') else {}}
    with tempfile.TemporaryDirectory(prefix='story-worker-') as temp:
        path = Path(temp)
        (path / 'worker.py').write_text(INFERENCE_SCRIPT)
        # Reuse downloaded files only within this job. No model cache artifact upload.
        (path / 'model_cache').symlink_to((ROOT / 'model_cache').resolve(), target_is_directory=True)
        (ROOT / 'model_cache').mkdir(exist_ok=True)
        env = {**os.environ, 'JOB_ID': role, 'ATTEMPT': '1', 'BACKEND': 'local',
               'LOCAL_MODEL': model, 'CACHE': 'false', 'SYSTEM': system, 'PROMPT': prompt,
               'CONFIG_JSON': json.dumps(config)}
        process = subprocess.run([sys.executable, str(path / 'worker.py')], cwd=path, env=env, timeout=2100)
        result_path = path / 'result.json'
        result = json.loads(result_path.read_text()) if result_path.exists() else {}
        if process.returncode:
            raise RuntimeError('Worker failed: ' + str(result.get('error', f'exit {process.returncode}')))
        item = result['agent']['results'][-1]
        return item['output'], {**item, 'workflow_run_id': os.getenv('GITHUB_RUN_ID'),
                               'workflow_job': os.getenv('GITHUB_JOB'), 'model_revision': MODELS[model].get('revision', 'main')}
