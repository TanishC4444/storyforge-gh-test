"""Source-bound parallel memory checks before repairs and after fact refresh."""
import math
from pathlib import Path
from .storage import load,save
from .contracts import require,review
from .evidence import passages
from .patching import digest
from .output_schema import memory_review_schema


def plan(state,source,out,phase):
    from .batch_pipeline import bind_state,output
    prose=(Path(source)/'edited/prose.txt').read_text();memory=load(Path(source)/'memory/memory.json')
    catalog=passages(prose);facts=memory['memories']
    # Every paragraph and fact is owned exactly once. Cross-batch context is read-only.
    count=max(1,math.ceil(len(catalog)/3),math.ceil(len(facts)/4))
    batches=[{'id':str(i),'owned_passages':[p['id'] for p in catalog[i*3:(i+1)*3]],
              'fact_indices':list(range(i*4,min(len(facts),(i+1)*4)))} for i in range(count)]
    value={'phase':phase,'state_sha256':bind_state(state),'source_sha256':digest(prose),
           'memory_sha256':bind_state(memory),'batches':batches}
    save(Path(out)/'memory-plan.json',value);output('characters',[b['id'] for b in batches]);return value


def inputs(state,source):
    from .batch_pipeline import bind_state
    source=Path(source);p=load(source/'plan/memory-plan.json')
    prose=(source/'edited/prose.txt').read_text();memory=load(source/'memory/memory.json')
    require(p['state_sha256']==bind_state(state) and p['source_sha256']==digest(prose)
            and p['memory_sha256']==bind_state(memory),'Stale memory-check inputs')
    return p,prose,memory


def validate(value,prose,batch,phase):
    value=review(value,prose);catalog=passages(prose)
    for issue in value['issues']:
        require(issue.get('target') in {'memory','prose'},'Memory issue requires target')
        require(phase=='preflight' or issue['target']=='memory','Final memory check assesses facts only; prose belongs to final adjudication')
        if issue['target']=='prose':
            ids=[p['id'] for p in catalog if issue['quote'] in p['text']]
            require(bool(set(ids)&set(batch['owned_passages'])),'Prose issue outside owned memory batch')
            issue['evidence_ids']=[pid for pid in ids if pid in batch['owned_passages']]
    return value


def check(state,card,source,out,backend,bid):
    from .batch_pipeline import scoped,scene_context,bind_state
    from .inference import Executor
    p,prose,memory=inputs(state,source);batch=next((b for b in p['batches'] if b['id']==bid),None)
    require(batch is not None,'Unknown memory batch')
    if memory.get('unverified'):
        verdict={'pass':False,'issues':[],'unverified':True,'error':'Memory extraction unavailable'}
    else:
        facts=[{'index':i,**{k:v for k,v in memory['memories'][i].items() if k in {'kind','text','known_by','holder','claim_source','fact_key','supersedes','evidence_ids'}}} for i in batch['fact_indices']]
        mode=('Also check continuity ONLY in owned_passages: character arrival before action, acquired knowledge, custody, resources and causal joins. Quote the affected owned paragraph and target prose for a demonstrated continuity fault. '
              if p['phase']=='preflight' else 'Assess ONLY the supplied extracted facts and knowledge holders. Do not report prose, entrances, style, similes or editorial preferences; those were assessed in the final editorial check. Issues must target memory. ')
        try:
            verdict=Executor(scoped(state['request']),out,backend).call('memory_quality',
                {**scene_context(state,card,'memory_quality'),'current_prose':prose,'owned_passages':batch['owned_passages'],
                 'proposed_memory':{'memories':facts},'check_phase':p['phase']},
                'Verify every supplied fact, uncertainty, chronology and knowledge holder against actual prose and established canon. Other paragraphs are read-only context. Never rewrite prose to make a false extraction true. '+mode+
                'Do not flag stylistic repetition or require changes contrary to the author brief. Return pass and issues with exact source quotations, target memory or prose, and specific fixes. A passing result may contain advisory issues only.',
                tokens=1200,response_schema=memory_review_schema(),validator=lambda v:validate(v,prose,batch,p['phase']))
        except Exception as exc:verdict={'pass':False,'issues':[],'unverified':True,'error':str(exc)}
    value={'id':bid,'plan_sha256':bind_state(p),'review':verdict}
    save(Path(out)/'memory-check-batch.json',value);return value


def join(state,source,out):
    from .batch_pipeline import bind_state
    p,prose,memory=inputs(state,source);expected={b['id'] for b in p['batches']};found={}
    for path in (Path(source)/'batches').rglob('memory-check-batch.json'):
        v=load(path);require(v['id'] in expected and v['id'] not in found,'Duplicate or foreign memory batch')
        require(v['plan_sha256']==bind_state(p),'Stale memory batch');found[v['id']]=v
    issues=[issue for b in p['batches'] if b['id'] in found for issue in found[b['id']]['review'].get('issues',[])]
    missing=sorted(expected-set(found));unverified=memory.get('unverified',False) or bool(missing) or any(v['review'].get('unverified') for v in found.values())
    verdict={'pass':not unverified and all(v['review']['pass'] for v in found.values()),'issues':issues,
             'source_sha256':digest(prose),'memory_sha256':bind_state(memory),'phase':p['phase'],'missing_batches':missing}
    if unverified:verdict.update(unverified=True,error='Missing or unverified memory-check batch')
    save(Path(out)/'review.json',verdict);return verdict
