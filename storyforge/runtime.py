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
        raise TimeoutError('Inference/job time budget exhausted; preserving artifacts and cleanup time.')
    return min(WORKER_TIMEOUT_SECONDS, remaining)


REVIEW_ROLES={'development_editor','story_quality','rhetoric_quality','chapter_quality','memory_quality'}
REVIEW_CALL_TIMEOUT_SECONDS=600


def review_call_timeout_seconds():
    value=int(os.getenv('STORY_REVIEW_TIMEOUT_SECONDS',str(REVIEW_CALL_TIMEOUT_SECONDS)))
    if not 60<=value<=3600:raise ValueError('Review call budget must be 60–3600 seconds')
    return value


def inference_timeout_seconds(role):
    remaining=worker_timeout_seconds()
    if role in REVIEW_ROLES:return min(remaining,review_call_timeout_seconds())
    if os.getenv('STORY_BATCH_TIMEOUT_SECONDS') and role in {'writer_beat','humanizer','repair','director'}:
        cap=int(os.environ['STORY_BATCH_TIMEOUT_SECONDS'])
        if not 60<=cap<=1800:raise ValueError('Batch inference budget must be 60–1800 seconds')
        return min(remaining,cap)
    return remaining


def scoped_call_budget(fn):
    """One elapsed-time allowance shared by hosted routes and CPU fallback."""
    from functools import wraps
    @wraps(fn)
    def wrapped(self,role,*args,**kwargs):
        budgets=self.req.get('execution_policy',{}).get('total_call_seconds',{})
        if role not in budgets or self.backend=='fixture':return fn(self,role,*args,**kwargs)
        seconds=budgets[role]
        if type(seconds) is not int or not 30<=seconds<=1800:raise ValueError('Invalid total call budget')
        from .provider_recovery import configuration
        recovery=configuration(self.req)
        seconds+=recovery.get('buffer_seconds',0)
        previous=os.getenv('STORY_JOB_DEADLINE');deadline=time.time()+seconds
        if previous:deadline=min(deadline,float(previous))
        os.environ['STORY_JOB_DEADLINE']=str(deadline)
        try:return fn(self,role,*args,**kwargs)
        finally:
            if previous is None:os.environ.pop('STORY_JOB_DEADLINE',None)
            else:os.environ['STORY_JOB_DEADLINE']=previous
    return wrapped
