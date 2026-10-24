"""Bounded outage buffers: wait between provider rounds, never manufacture output."""
import random,time
from pathlib import Path
from .contracts import require
from .storage import load,save
from .tracking import event,heartbeat


def configuration(req):
    raw=req.get('execution_policy',{}).get('provider_outage_recovery',{})
    require(isinstance(raw,dict),'Invalid provider outage recovery')
    if not raw:return {}
    limits={'max_rounds':(1,3),'delay_seconds':(5,120),'buffer_seconds':(30,600),'extra_requests':(0,12)}
    require(set(raw)==set(limits),'Outage recovery needs explicit bounded settings')
    for key,(low,high) in limits.items():
        require(type(raw[key]) is int and low<=raw[key]<=high,'Invalid provider outage '+key)
    cap=req.get('execution_policy',{}).get('max_hosted_requests')
    require(type(cap) is int and 1<=cap<=6 and cap+raw['extra_requests']<=18,'Invalid total outage request cap')
    return raw


def transient(error):
    if getattr(error,'daily',False):return False
    text=str(error)
    return any(code in text for code in ['HTTP 408','HTTP 429','HTTP 500','HTTP 502','HTTP 503','HTTP 504','connection failed or timed out','Provider request attempt budget exhausted','MAX_TOKENS'])


def wait_to_retry(errors,folder,role,round_number,config):
    if not errors or not all(transient(e) for e in errors):return False
    # An output-only truncation is not a provider outage. Mixed 503/truncation
    # rounds may wait and retry with expanded output room; never sleep merely
    # because every healthy model returned an incomplete artifact.
    if all('MAX_TOKENS' in str(e) for e in errors):return False
    from .runtime import worker_timeout_seconds
    base=config['delay_seconds']*2**(round_number-1)
    delay=max(base,max(getattr(e,'retry_after',0) for e in errors))+random.uniform(0,5)
    path=Path(folder)/'provider-recovery.json'
    record={'role':role,'state':'waiting_for_provider','retry_round':round_number+1,
            'delay_seconds':round(delay,3),'retry_at':time.time()+delay,
            'input_checkpoint':'packets/','approval_granted':False}
    if worker_timeout_seconds()<delay+30:
        save(path,{**record,'state':'awaiting_provider_resume','reason':'Shared deadline cannot fit another delayed attempt'})
        return False
    save(path,record)
    event('provider_wait','Temporary provider outage; preserving inputs and delaying retry',role=role,seconds=round(delay,3),retry_round=round_number+1)
    with heartbeat('Waiting for provider capacity; no generation requests during backoff'):
        until=time.monotonic()+delay
        while True:
            remaining=until-time.monotonic()
            if remaining<=0:break
            worker_timeout_seconds()
            time.sleep(min(5,remaining))
    save(path,{**record,'state':'retrying'})
    return True


def finish(folder,role,success,errors):
    path=Path(folder)/'provider-recovery.json'
    previous=load(path) if path.exists() else {}
    if success:
        if previous:save(path,{**previous,'state':'provider_recovered'})
    elif previous or errors and all(transient(e) for e in errors):
        save(path,{**previous,'role':role,'state':'awaiting_provider_resume',
                   'input_checkpoint':'packets/','approval_granted':False,
                   'reason':previous.get('reason','Bounded outage buffer exhausted; exact inputs retained')})
