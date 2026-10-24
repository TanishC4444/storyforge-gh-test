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
    last_raw=None
    def validate(raw,capture=True):
        nonlocal last_raw
        if req.get('performance',{}).get('pipelined_living'):
            from .memory_fields import source_defaults
            raw=source_defaults(raw,packet,prose,out)
        if capture:last_raw=copy.deepcopy(raw)
        result=salvage_memory(raw,prose,ids) if enabled(req) and not req.get('performance',{}).get('pipelined_living') else contracts.delta(raw,prose,ids)
        if req.get('performance',{}).get('pipelined_living') and 'evidence_passages' in packet:
            owned={p['id'] for p in packet['evidence_passages']}
            for fact in result['memories']:
                contracts.require(set(fact.get('evidence_ids',[]))<=owned,'Memory evidence_ids outside owned source passages')
        if not allow_public:
            retained=[]
            for item in result['memories']:
                if 'public' in item['known_by']:
                    contracts.require(not req.get('performance',{}).get('pipelined_living'),'Invalid memory knowledge holders: explicit witnesses required, not public')
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
    instruction+=' Every memory, including each thread update, MUST include a nonempty text description of at most 600 characters, evidence_ids and explicit known_by. Thread IDs and states supplement text; they never replace it. Never guess missing witnesses, outcomes or source evidence.'
    instruction+=' subject/life_state are ONLY for actual lifecycle changes with life:<character_id> keys. Do NOT attach them to arrival, location, presence or ordinary action records. thread_id/thread_state are ONLY for kind=thread with a matching thread:<id> key. Omit unrelated optional metadata entirely.'
    instruction+=' Keep facts atomic: separate private sensations, fears and inferences from observable actions. Never assign a mixed public/private sentence one broad witness list. Use character_registry and read_only_source_context to identify actual listeners, not all characters in the world. Cite ONLY owned evidence_passages in output; context may establish an arrival or listener but is not independently owned for extraction. Existing knowledge does not disappear because a later paragraph does not repeat its acquisition.'
    from .adaptive import enabled as adaptive
    schema=memory_schema(packet,ids,allow_public=allow_public,prior_memories=prior)
    if adaptive(req):
        instruction=instruction.replace('Extract at most 6 consequential updates.','Extract all material supported changes in your assigned source; do not impose a six-fact summary quota.')
        schema['properties']['memories']['maxItems']=24
    try:
        result=executor.call('memory',packet,instruction,tokens=2300 if adaptive(req) else 1400 if prior is not None else 1000,validator=validate,response_schema=schema)
        if result.get('quarantined'):warning(out,'memory_quarantine','Unsupported memory entries quarantined; source prose retained.')
        return result
    except Exception as exc:
        if req.get('performance',{}).get('pipelined_living') and isinstance(last_raw,dict) and isinstance(last_raw.get('memories'),list):
            from .memory_fields import repair_texts
            save(Path(out)/'memory-rejected-records.json',last_raw)
            save(Path(out)/'memory-source.txt',prose)
            try:
                from .memory_records import partition,repair as repair_records
                rejected=copy.deepcopy(last_raw)
                validate_record=lambda value:validate(value,capture=False)
                valid_indices,problems=partition(rejected,validate_record,req,packet)
                last_raw=rejected
                if problems and all(p['editable_fields']==['text'] for p in problems):
                    fixed=repair_texts(executor,req,out,prose,packet,rejected)
                else:fixed=repair_records(executor,req,out,prose,packet,rejected,validate_record)
                if fixed is not None:return validate(fixed)
            except Exception as repair_error:
                if isinstance(last_raw,dict) and isinstance(last_raw.get('memories'),list):
                    retained=[]
                    for record in last_raw['memories']:
                        try:retained.extend(validate({'memories':[record]},capture=False)['memories'])
                        except (ValueError,TypeError,KeyError):pass
                    save(Path(out)/'memory-partial.json',{'memories':retained,'unverified':True,'error':str(repair_error)})
                raise contracts.ContractError('Memory field-only recovery failed; source and records retained: '+str(repair_error)) from repair_error
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
