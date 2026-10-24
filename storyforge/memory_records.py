"""Repair invalid record fields while freezing validated sibling facts."""
import copy
from pathlib import Path
from .contracts import require
from .output_schema import memory_schema
from .storage import save


def fields_for(error,record):
    message=str(error)
    if 'knowledge holders' in message:return {'known_by'}
    if 'Belief needs holder' in message:return {'holder','known_by'}
    if 'memory text' in message:return {'text'}
    if 'memory kind' in message:return {'kind'}
    if 'supersedes' in message and 'changed fact identity' not in message:return {'supersedes'}
    if 'unknown prior fact' in message:return {'supersedes'}
    if 'changed fact identity' in message:return {'fact_key','supersedes'}
    if 'evidence' in message.lower():return {'evidence_ids'}
    if 'plot thread' in message or 'Thread needs' in message:return {'kind','thread_id','thread_state','fact_key','supersedes'}
    if 'lifecycle' in message.lower():return {'kind','subject','life_state','fact_key','supersedes'}
    return set()



def malformed_fields(record,req,packet):
    if not isinstance(record,dict):return set()
    fields=set();cast={c['id'] for c in req['characters']}|{'public'}
    kind=record.get('kind')
    if not isinstance(kind,str) or kind not in {'event','belief','claim','resource','relationship','thread'}:fields.add('kind')
    text=record.get('text')
    if not isinstance(text,str) or not text.strip() or len(text)>600:fields.add('text')
    known=record.get('known_by')
    if not isinstance(known,list) or not all(isinstance(c,str) and c in cast for c in known):fields.add('known_by')
    if record.get('kind')=='belief':
        if not isinstance(record.get('holder'),str) or record['holder'] not in cast-{'public'}:fields.add('holder')
        elif isinstance(known,list) and record['holder'] not in known:fields.add('known_by')
    links=record.get('supersedes',[])
    if not isinstance(links,list) or not all(isinstance(x,str) for x in links):fields.add('supersedes');links=[]
    elif len(links)>3 or len(links)!=len(set(links)):fields.add('supersedes')
    lookup={m['id']:m for m in packet.get('prior_canon',[])}
    for link in links:
        old=lookup.get(link)
        if old is None or not old.get('fact_key') or record.get('kind')!=old['kind']:fields.add('supersedes')
        elif record.get('fact_key')!=old['fact_key']:fields.update({'fact_key','supersedes'})
    if record.get('kind')=='thread':
        import re
        tid=record.get('thread_id')
        if not isinstance(tid,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',tid):fields.add('thread_id')
        if not isinstance(record.get('thread_state'),str) or record['thread_state'] not in {'seeded','escalating','payoff','closed'}:fields.add('thread_state')
        if not isinstance(tid,str) or record.get('fact_key')!='thread:'+tid:fields.add('fact_key')
    if 'subject' in record or 'life_state' in record:
        subject=record.get('subject')
        if not isinstance(subject,str) or subject not in cast-{'public'}:fields.add('subject')
        if not isinstance(record.get('life_state'),str) or record['life_state'] not in {'alive','dead','missing','unknown'}:fields.add('life_state')
        if kind!='event':fields.add('kind')
        if not isinstance(subject,str) or record.get('fact_key')!='life:'+subject:fields.add('fact_key')
        if fields & {'subject','life_state','fact_key','kind'}:
            fields.update({'kind','subject','life_state','fact_key','supersedes'})
    if ('thread_id' in record or 'thread_state' in record) and kind!='thread':
        fields.update({'kind','thread_id','thread_state','fact_key','supersedes'})
    evidence=record.get('evidence_ids')
    allowed={p['id'] for p in packet['evidence_passages']}
    if evidence is not None and (not isinstance(evidence,list) or not 1<=len(evidence)<=3 or not all(isinstance(p,str) and p in allowed for p in evidence) or len(set(evidence))!=len(evidence)):fields.add('evidence_ids')
    return fields


def partition(raw,validate,req=None,packet=None):
    require(isinstance(raw,dict) and isinstance(raw.get('memories'),list),'Cannot partition malformed memory wrapper')
    valid=[];problems=[]
    for i,record in enumerate(raw['memories']):
        try:validate({'memories':[record]});valid.append(i)
        except (ValueError,TypeError,KeyError) as exc:
            fields=fields_for(exc,record)
            if req is not None and packet is not None:fields.update(malformed_fields(record,req,packet))
            problems.append({'record_index':i,'error':str(exc),'editable_fields':sorted(fields)})
    return valid,problems


def repair(executor,req,out,prose,packet,raw,validate):
    """One field patch across all invalid records; no changes to valid siblings."""
    valid,problems=partition(raw,validate,req,packet)
    if not problems:return copy.deepcopy(raw)
    require(all(p['editable_fields'] for p in problems),'Unrecognized memory fault; source and valid records retained')
    options=copy.deepcopy(req);options['max_stage_retries']=0
    policy=options.setdefault('execution_policy',{})
    policy.setdefault('hosted_routes',{})['memory']=['flash36','flash','lite']
    policy.setdefault('hosted_role_seconds',{})['memory']=60;policy['max_hosted_requests']=3
    ids=[c['id'] for c in req['characters']]
    item=memory_schema(packet,ids,prior_memories=packet.get('prior_canon',[]))['properties']['memories']['items']
    properties={}
    for problem in problems:
        i=problem['record_index'];fields=problem['editable_fields']
        props={f:copy.deepcopy(item['properties'][f]) for f in fields}
        for field in {'subject','life_state','thread_id','thread_state'} & set(fields):
            props[field]={'anyOf':[props[field],{'type':'null'}]}
        properties['r'+str(i)]={'type':'object','properties':props,'required':fields,'additionalProperties':False}
    schema={'type':'object','properties':{'repairs':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}},'required':['repairs'],'additionalProperties':False}
    data={'records_needing_repair':[{**p,'record':raw['memories'][p['record_index']]} for p in problems],
          'evidence_passages':packet['evidence_passages'],'prior_canon':packet.get('prior_canon',[]),
          'character_registry':[{'id':c['id'],'name':c.get('name',c['id'])} for c in req['characters']],
          'specific_memory_findings':packet.get('specific_memory_findings',[])}
    def check(value):
        require(isinstance(value,dict) and isinstance(value.get('repairs'),dict),'Missing memory record patches')
        fixes=value['repairs'];require(set(fixes)==set(properties),'Missing or foreign record patch')
        merged=copy.deepcopy(raw)
        for problem in problems:
            i=problem['record_index'];fields=set(problem['editable_fields']);patch=fixes['r'+str(i)]
            require(isinstance(patch,dict) and set(patch)==fields,'Patch changed an immutable record field')
            apply_patch(merged['memories'][i],patch)
        validate(merged)  # Full source, cast, belief, lifecycle and identity contracts.
        return value
    from .inference import Executor
    data['optional_field_policy']='Set subject/life_state to null to REMOVE accidental lifecycle metadata from a location or ordinary event; preserve its real key and prior identity. Actual death or life-status changes must retain correct lifecycle metadata. Set thread_id/thread_state to null to REMOVE accidental thread metadata from an ordinary event or claim.'
    result=Executor(options,Path(out)/'record-repair',executor.backend).call('memory',data,
        'Repair ONLY each record’s editable_fields using actual source evidence and registered character IDs. Return repairs keyed by r plus record_index; every requested field is required. Never alter other fields or create/delete records. known_by lists actual supported witnesses or holders, not everyone present in the wider world; never guess a default witness list. Preserve uncertainty. A state update may supersede only the same prior kind and fact_key. For a new event that incorrectly replaces a resource or deadline, use supersedes=[] and retain its distinct event fact_key instead of overwriting state; this does not assert a resource reset. For an actual update of the same state, copy the exact prior key. Thread descriptions, states and knowledge holders must be supplied independently. Do not change prose to justify a memory. All patched records must pass the same original validators and later independent factual review.',
        tokens=min(4200,600*len(problems)+300),response_schema=schema,validator=check)
    merged=copy.deepcopy(raw)
    for problem in problems:
        i=problem['record_index'];apply_patch(merged['memories'][i],result['repairs']['r'+str(i)])
    save(Path(out)/'memory-record-repairs.json',{'repairs':result['repairs'],'valid_record_indices_preserved':valid,'diagnostics':problems})
    return merged


def apply_patch(record,patch):
    for key,value in patch.items():
        if key in {'subject','life_state','thread_id','thread_state'} and value is None:record.pop(key,None)
        else:record[key]=value
