"""Shared time policy for CPU inference and its enclosing Actions job."""
import os
import time

JOB_TIMEOUT_MINUTES = 360
JOB_TIMEOUT_SECONDS = JOB_TIMEOUT_MINUTES * 60
CLEANUP_RESERVE_SECONDS = 300
WORKER_TIMEOUT_SECONDS = JOB_TIMEOUT_SECONDS - CLEANUP_RESERVE_SECONDS
DOWNLOAD_TIMEOUT_SECONDS = 600


def worker_timeout_seconds():
    """Share the job's remaining time across validation retries; preserve cleanup time."""
    deadline = os.getenv('STORY_JOB_DEADLINE')
    if deadline is None:
        return WORKER_TIMEOUT_SECONDS
    remaining = int(float(deadline) - time.time())
    if remaining <= 0:
        raise TimeoutError('Six-hour job budget exhausted; stopping before cleanup reserve.')
    return min(WORKER_TIMEOUT_SECONDS, remaining)


REVIEW_ROLES={'development_editor','story_quality','rhetoric_quality','chapter_quality','memory_quality'}
REVIEW_CALL_TIMEOUT_SECONDS=600


def inference_timeout_seconds(role):
    remaining=worker_timeout_seconds()
    return min(remaining,REVIEW_CALL_TIMEOUT_SECONDS) if role in REVIEW_ROLES else remaining
