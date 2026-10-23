"""Recover required descriptions without guessing facts or changing metadata."""
import copy
from pathlib import Path
from .contracts import require
from .evidence import bind
from .storage import save


def source_defaults(raw,packet,prose,out):
    result=copy.deepcopy(raw);changes=[]
    if isinstance(result,list):result={'memories':result}
    if not isinstance(result,dict) or not isinstance(result.get('memories'),list):return result
    allowed={p['id'] for p in packet.get('evidence_passages',[])}
    for i,item in enumerate(result['memories']):
        if not isinstance(item,dict):continue
        text=item.get('text')
        if text is not None and not (isinstance(text,str) and not text.strip()):continue
        ids=item.get('evidence_ids')
        if not isinstance(ids,list) or not ids or not all(isinstance(x,str) for x in ids) or not set(ids)<=allowed:continue
        try:evidence=bind(item,prose)['evidence']
        except ValueError:continue
        # Copy the entire cited span, never a truncated quote or a guessed summary.
        if not 0<len(evidence)<=600:continue
        item['text']=evidence
        changes.append({'record_index':i,'field':'text','method':'complete_verbatim_evidence','evidence_ids':ids,'text':evidence})
    if changes:save(Path(out)/'memory-field-defaults.json',{'changes':changes,'source_bound':True})
    return result


def repair_texts(executor,req,out,prose,packet,raw):
    """One small field-only request; every other record field remains immutable."""
    if not isinstance(raw,dict) or not isinstance(raw.get('memories'),list):return None
    broken=[i for i,m in enumerate(raw['memories']) if isinstance(m,dict) and (not isinstance(m.get('text'),str) or not m['text'].strip() or len(m['text'])>600)]
    if not broken:return None
    allowed={p['id'] for p in packet.get('evidence_passages',[])};ids=set()
    for i in broken:
        evidence=raw['memories'][i].get('evidence_ids')
        require(isinstance(evidence,list) and evidence and all(isinstance(x,str) for x in evidence) and set(evidence)<=allowed,'Cannot repair text without owned source evidence')
        bind(raw['memories'][i],prose);ids.update(evidence)
    from .inference import Executor
    options=copy.deepcopy(req);options['max_stage_retries']=0
    policy=options.setdefault('execution_policy',{})
    policy.setdefault('hosted_routes',{})['memory']=['flash36','flash','lite']
    policy.setdefault('hosted_role_seconds',{})['memory']=45
    policy['max_hosted_requests']=3
    selected=[{'record_index':i,'immutable_fields':{k:v for k,v in raw['memories'][i].items() if k!='text'},'invalid_text':raw['memories'][i].get('text')} for i in broken]
    prior_ids={old for i in broken for old in raw['memories'][i].get('supersedes',[])}
    data={'evidence_passages':[p for p in packet['evidence_passages'] if p['id'] in ids],
          'records_needing_text':selected,'prior_canon':[m for m in packet.get('prior_canon',[]) if m.get('id') in prior_ids]}
    item={'type':'object','properties':{'record_index':{'type':'integer','enum':broken},'text':{'type':'string','minLength':1,'maxLength':600}},'required':['record_index','text'],'additionalProperties':False}
    schema={'type':'object','properties':{'repairs':{'type':'array','items':item,'minItems':len(broken),'maxItems':len(broken)}},'required':['repairs'],'additionalProperties':False}
    def validate(value):
        require(isinstance(value,dict) and isinstance(value.get('repairs'),list),'Missing field repairs')
        fixes=value['repairs'];indices=[f.get('record_index') for f in fixes if isinstance(f,dict)]
        require(len(indices)==len(fixes)==len(broken) and set(indices)==set(broken),'Missing, duplicate or foreign field repair')
        for f in fixes:
            require(set(f)=={'record_index','text'} and type(f['record_index']) is int,'Repair may change only text')
            require(isinstance(f['text'],str) and f['text'].strip() and len(f['text'])<=600,'Invalid repaired memory text')
        return value
    result=Executor(options,Path(out)/'text-repair',executor.backend).call('memory',data,
        'Fill ONLY the missing or malformed text descriptions. Each text must describe the actual source-supported fact or unresolved obligation in 1–3 specific sentences, at most 600 characters. Preserve uncertainty. Thread metadata never replaces a required description. Immutable fields, knowledge holders and prior identities cannot be edited. Do not infer a new event, resolution or witness. Return exactly one repair per supplied record_index; no other records or fields.',
        tokens=min(2300,250*len(broken)+200),response_schema=schema,validator=validate)
    merged=copy.deepcopy(raw)
    for fix in result['repairs']:merged['memories'][fix['record_index']]['text']=fix['text']
    save(Path(out)/'memory-field-repairs.json',{'repairs':result['repairs'],'immutable_metadata_preserved':True})
    return merged
