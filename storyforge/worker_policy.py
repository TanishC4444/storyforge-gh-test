"""One worker policy for bounded API concurrency and conservative CPU fallback."""
from contextlib import contextmanager
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
import threading

# Provider tiers are existing configured models; no unverified model identifiers.
STAGES={
 'refiner_part':('gemma',850,60),'refiner':(None,2400,90),'architect':(None,3000,120),
 'development_editor':(None,1200,90),'scene_designer':(None,1200,90),
 'character':('gemma',220,45),'director':(None,500,60),
 'writer':(None,4200,180),'writer_beat':(None,1100,120),
 'seam':(None,700,90),'humanizer':(None,4200,180),'structural_editor':(None,4200,180),
 'repair':(None,1300,120),'global_repair':(None,3200,150),
 'story_quality':(None,1600,90),'rhetoric_quality':(None,1400,90),
 'memory':(None,1400,90),'memory_quality':('gemma',1000,90),
 'chapter_quality':(None,1800,120)}
PROFILE_TABLES={'fast':STAGES,'small':{role:(tier,min(cap,1800),min(timeout,90)) for role,(tier,cap,timeout) in STAGES.items()}}
_LOCK=threading.Lock();_SEMAPHORES={};CPU_LOCK=threading.RLock()

def enabled(req):return bool(req.get('execution_policy',{}).get('experimental'))

def policy(req,role,tokens):
    tier,cap,timeout=PROFILE_TABLES.get(req.get('profile'),STAGES).get(role,('gemma',tokens,120))
    if role=='refiner_part':tier=req.get('execution_policy',{}).get('refinement_provider','cpu')
    if tier=='cpu':tier=None
    return {'tier':tier,'thinking':'minimal' if tier=='gemma' else 'low',
            'max_tokens':min(tokens,cap),'timeout':timeout,'retries':2,
            'estimate_small_calls':req.get('execution_policy',{}).get('estimate_small_calls',False)}

@contextmanager
def permit(req):
    limit=req.get('execution_policy',{}).get('concurrency',{}).get('api',2)
    if type(limit) is not int or not 1<=limit<=4:raise ValueError('API concurrency must be 1–4')
    with _LOCK:sem=_SEMAPHORES.setdefault(limit,threading.BoundedSemaphore(limit))
    with sem:yield

def parallel(req,kind,items,fn):
    limit=req.get('execution_policy',{}).get('concurrency',{}).get(kind,2)
    if type(limit) is not int or not 1<=limit<=4:raise ValueError('Concurrency must be 1–4')
    with ThreadPoolExecutor(max_workers=limit) as pool:
        futures=[pool.submit(copy_context().run,fn,item) for item in items]
        return [future.result() for future in futures]


def validate(req):
    from .contracts import require
    knobs=req['execution_policy']
    require(knobs.get('refinement_provider','cpu') in {'cpu','gemma'},'Invalid refinement provider')
    require(knobs.get('gate_repair_threshold','blocking') in {'blocking','advisory'},'Invalid repair gate threshold')
    require(type(knobs.get('writer_beats',1)) is int and 1<=knobs.get('writer_beats',1)<=4,'Invalid writer beat count')
    require(isinstance(knobs.get('concurrency',{}),dict),'Concurrency must name API, review, writer and repair limits')
    for key,value in knobs.get('concurrency',{}).items():
        require(key in {'api','reviews','writer','repair','refinement'} and type(value) is int and 1<=value<=4,'Invalid concurrency limit')
