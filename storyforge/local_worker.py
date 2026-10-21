"""Resident inference within the job already allocated by GitHub Actions."""
from __future__ import annotations
import atexit
import importlib.util
import os
import signal
import threading
from .worker_policy import CPU_LOCK
from .runtime import JOB_TIMEOUT_MINUTES, JOB_TIMEOUT_SECONDS, DOWNLOAD_TIMEOUT_SECONDS, worker_timeout_seconds

_SESSIONS={}


def close_sessions():
    for session in _SESSIONS.values():session.close()
    _SESSIONS.clear()


atexit.register(close_sessions)


def execute(model, system, prompt, tokens, n_ctx, role, response_schema=None):
    with CPU_LOCK:
        return _execute(model,system,prompt,tokens,n_ctx,role,response_schema)

def _execute(model, system, prompt, tokens, n_ctx, role, response_schema=None):
    if importlib.util.find_spec('llama_cpp') is None:
        from .cpu_fallback import execute as remote
        return remote(model,system,prompt,tokens,n_ctx,role,response_schema)
    from gh_inference import ResidentSession, Limits
    key=(model,n_ctx)
    if key not in _SESSIONS:
        # One model resident per job; do not accumulate multiple 12B models.
        close_sessions()
        options={'chat_template_options':{'enable_thinking':False}} if model.startswith('gemma-4') else {}
        _SESSIONS[key]=ResidentSession(model,n_ctx=n_ctx,
            limits=Limits(job_timeout_minutes=JOB_TIMEOUT_MINUTES,provider_timeout_seconds=JOB_TIMEOUT_SECONDS,download_timeout_seconds=DOWNLOAD_TIMEOUT_SECONDS),
            model_options=options,runner_ram_gb=16,runner_disk_gb=14)
    def expired(*args):raise TimeoutError('Shared job time budget exhausted; preserving cleanup time.')
    main=threading.current_thread() is threading.main_thread()
    worker_timeout_seconds()
    if main:
        previous=signal.signal(signal.SIGALRM,expired)
        signal.setitimer(signal.ITIMER_REAL,worker_timeout_seconds())
    try:
        output,diagnostic=_SESSIONS[key].complete(prompt,system=system,max_tokens=tokens,
            temperature=.7 if role in {'writer','humanizer'} else .25,response_schema=response_schema)
        return output,{**diagnostic,'workflow_run_id':os.getenv('GITHUB_RUN_ID'),'workflow_job':os.getenv('GITHUB_JOB')}
    finally:
        if main:
            signal.setitimer(signal.ITIMER_REAL,0)
            signal.signal(signal.SIGALRM,previous)
