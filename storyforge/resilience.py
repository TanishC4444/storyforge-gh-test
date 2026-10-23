"""Explicit draft-continuation policy; never turn missing verification into a pass."""
import copy
import hashlib
import json
from pathlib import Path
from . import contracts
from .evidence import passages
from .tracking import event
from .storage import save


def enabled(req):return bool(req.get('execution_policy',{}).get('continue_with_warnings'))


def warning(out,kind,error):
    path=Path(out)/'warnings.json'
    existing=json.loads(path.read_text()) if path.exists() else []
    existing.append({'kind':kind,'message':str(error)})
    save(path,existing);event('warning',str(error),kind=kind)


def unavailable(error):return {'pass':False,'checks':[],'issues':[],'unverified':True,'error':str(error)}


def salvage_memory(raw,prose,ids):
    """Lossless outer-shape recovery; quarantine unsupported facts instead of truncating evidence."""
    if isinstance(raw,list):raw={'memories':raw}
    if not isinstance(raw,dict) or not isinstance(raw.get('memories'),list):return {'memories':[],'quarantined':[{'error':'Missing memories array','raw':raw}]}
    valid=[];rejected=[]
    for item in raw['memories']:
        try:
            item=copy.deepcopy(item)
            if isinstance(item,dict) and isinstance(item.get('evidence_ids'),list):item['evidence_ids']=list(dict.fromkeys(item['evidence_ids']))
            valid.extend(contracts.delta({'memories':[item]},prose,ids)['memories'])
        except (ValueError,TypeError,KeyError) as exc:rejected.append({'error':str(exc),'raw':item})
    return {'memories':valid,'quarantined':rejected}


def memory_extract(executor,req,out,prose,packet,instruction,allow_public=True):
    ids=[c['id'] for c in req['characters']]
    from .output_schema import memory_schema
    def validate(raw):
        result=salvage_memory(raw,prose,ids) if enabled(req) else contracts.delta(raw,prose,ids)
        if not allow_public:
            retained=[]
            for item in result['memories']:
                if 'public' in item['known_by']:
                    result.setdefault('quarantined',[]).append({'error':'Public scope is not allowed; explicit witnesses required','raw':item})
                else:retained.append(item)
            result['memories']=retained
        if req.get('performance',{}).get('canon_index'):
            lookup={m['id']:m for m in packet.get('prior_canon',[])}
            for update in result['memories']:
                for old_id in update.get('supersedes',[]):
                    contracts.require(old_id in lookup,'Memory update cites unknown prior fact')
                    old=lookup[old_id]
                    contracts.require(bool(update.get('fact_key')) and update['fact_key']==old.get('fact_key') and update['kind']==old['kind'],'Memory update changed fact identity: '+old_id+' requires fact_key='+repr(old.get('fact_key'))+' and kind='+old['kind']+'; unkeyed prior facts cannot be superseded. Record a separate event with supersedes=[] instead if supported by the scene.')
        return result
    prior=None
    if req.get('performance',{}).get('canon_index'):
        prior=packet.get('prior_canon',[])
        instruction+=' For a changed resource, relationship or obligation, copy the exact fact_key and kind of the same prior fact when using its ID in supersedes. Prior facts without fact_key are immutable and cannot appear in supersedes. New events, consequences, and discoveries use a new fact_key and supersedes=[]; they do not replace the prior character or world premise. Never infer an update or erase history. Include unresolved callbacks and obligations, not only recent motion.'
    try:
        result=executor.call('memory',packet,instruction,tokens=1400 if prior is not None else 1000,validator=validate,response_schema=memory_schema(packet,ids,allow_public=allow_public,prior_memories=prior))
        if result.get('quarantined'):warning(out,'memory_quarantine','Unsupported memory entries quarantined; source prose retained.')
        return result
    except Exception as exc:
        if not enabled(req):raise
        warning(out,'memory_unavailable',exc)
        # The source scene is retained verbatim. No guessed facts or knowledge holders.
        save(Path(out)/'memory-source.txt',prose)
        return {'memories':[],'quarantined':[],'fallback':'verbatim_scene_only','error':str(exc)}


def creative_request(req):
    operational={'profile','max_repairs','max_stage_retries','context_chars','n_ctx','runner_repo','auto_approve_plan','execution_policy','performance','api_roles','medium_decision'}
    return {k:v for k,v in req.items() if k not in operational}


def load_seed(req,root):
    seed=req.get('execution_policy',{}).get('resume_seed')
    if not seed:return None
    path=(Path(root)/seed).resolve()
    contracts.require(path.is_relative_to(Path(root).resolve()),'Recovery path outside repository')
    value=json.loads((path/'snapshot.json').read_text())
    contracts.require(creative_request(value['request'])==creative_request(req),'Recovery seed has a different creative brief')
    contracts.plan(value['plan'],req);contracts.refinement(value['refinement'],req)
    value=copy.deepcopy(value);value['source_request_hash']=value.get('request_hash');value['request']=req;value['request_hash']=hashlib.sha256(json.dumps(req,sort_keys=True).encode()).hexdigest()
    value['recovery']={'source_run':39512585096,'reuse_planning':True,'scene_id':'ch01-sc01','prose':(path/'scene-01.txt').read_text(),'reviews':{key:json.loads((path/filename).read_text()) for key,filename in [('story','story-review.json'),('rhetoric','rhetoric-review.json')]}}
    return value
