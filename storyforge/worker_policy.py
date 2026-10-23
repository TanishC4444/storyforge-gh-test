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
    if role in {'writer','humanizer','structural_editor'} and req.get('execution_policy',{}).get('hosted_prose'):
        tier=req['execution_policy']['hosted_prose']
    quality=req.get('execution_policy',{}).get('model_routing')=='quality'
    if quality:
        tier={'writer':'flash','writer_beat':'flash','global_repair':'flash',
              'structural_editor':'flash36','chapter_quality':'flash36',
              'memory_quality':'gemma'}.get(role,'lite')
    literary=req.get('execution_policy',{}).get('literary_quality',False)
    if literary:
        if role in {'humanizer','repair','seam','rhetoric_quality','chapter_quality','development_editor'}:tier='flash36'
        if role=='story_quality':tier='gemma'
        timeout=180 if role in {'writer','writer_beat','global_repair','humanizer','structural_editor'} else 120
        if role in {'writer','humanizer','structural_editor','global_repair'}:cap=4200
    if tier=='cpu':tier=None
    return {'tier':tier,'thinking':'minimal' if tier=='gemma' else 'medium' if literary and role in {'writer','humanizer','structural_editor','global_repair'} else 'low',
            'max_tokens':min(tokens,cap),'timeout':timeout,'retries':2,
            'quality_routing':quality,'literary_quality':literary,
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
    from .provider_recovery import configuration
    configuration(req)
    require(knobs.get('editorial_disagreement') in {None,'one_strict_check'},'Invalid editorial disagreement policy')
    hosted=knobs.get('hosted_routes',{})
    require(isinstance(hosted,dict) and all(k in STAGES and isinstance(v,list) and 1<=len(v)<=3 and all(t in {'flash','flash36','lite','gemma'} for t in v) for k,v in hosted.items()),'Invalid hosted routing policy')
    role_seconds=knobs.get('hosted_role_seconds',{})
    require(isinstance(role_seconds,dict) and all(k in STAGES and type(v) is int and 10<=v<=300 for k,v in role_seconds.items()),'Invalid hosted role timeout')
    required=knobs.get('hosted_required_roles',[])
    require(isinstance(required,list) and all(r in STAGES for r in required),'Invalid hosted quality floor')
    require(type(knobs.get('max_hosted_requests',2)) is int and 1<=knobs.get('max_hosted_requests',2)<=6,'Invalid provider request cap')
    models=knobs.get('cpu_models',{})
    require(isinstance(models,dict) and all(k in STAGES and v in {'qwen3b','qwen7b','gemma-4-12b','glitter-12b'} for k,v in models.items()),'Invalid local role model map')
    require(type(knobs.get('literary_quality',False)) is bool,'Invalid literary quality policy')
    require(knobs.get('model_routing') in {None,'quality'},'Invalid model routing profile')
    require(knobs.get('hosted_prose') in {None,'gemma','flash'},'Invalid hosted prose provider')
    require(knobs.get('refinement_provider','cpu') in {'cpu','gemma'},'Invalid refinement provider')
    require(knobs.get('gate_repair_threshold','blocking') in {'blocking','advisory'},'Invalid repair gate threshold')
    require(type(knobs.get('writer_beats',1)) is int and 1<=knobs.get('writer_beats',1)<=4,'Invalid writer beat count')
    require(isinstance(knobs.get('concurrency',{}),dict),'Concurrency must name API, review, writer and repair limits')
    for key,value in knobs.get('concurrency',{}).items():
        require(key in {'api','reviews','writer','repair','refinement'} and type(value) is int and 1<=value<=4,'Invalid concurrency limit')
