"""Source-bound parallel memory checks before repairs and after fact refresh."""
import math
from pathlib import Path
from .storage import load,save
from .contracts import require,review
from .evidence import passages
from .patching import digest
from .output_schema import memory_review_schema


def memory_canon(state):
    from .canon import index
    view=index(state['memories']);current={m['id'] for m in view['current']}
    keys={'id','kind','text','known_by','holder','claim_source','source','state_version','fact_key','supersedes','evidence_prose_sha256'}
    return [{**{k:v for k,v in m.items() if k in keys},'canonical_status':'current' if m['id'] in current else 'historical_superseded'} for m in view['history']]


def plan(state,source,out,phase):
    from .batch_pipeline import bind_state,output
    prose=(Path(source)/'edited/prose.txt').read_text();memory=load(Path(source)/'memory/memory.json')
    catalog=passages(prose);facts=memory['memories']
    # Every paragraph and fact is owned exactly once. Cross-batch context is read-only.
    count=max(1,math.ceil(len(catalog)/3),math.ceil(len(facts)/4))
    batches=[{'id':str(i),'owned_passages':[p['id'] for p in catalog[i*3:(i+1)*3]],
              'fact_indices':list(range(i*4,min(len(facts),(i+1)*4)))} for i in range(count)]
    if state['request'].get('performance',{}).get('memory_pair_batches'):
        from .canon import cards
        prior=memory_canon(state);prior_groups=[list(range(i,min(i+8,len(prior)))) for i in range(0,len(prior),8)] or [[]]
        candidates=[{'task':'facts','owned_passages':[],'fact_indices':list(range(i,min(i+2,len(facts))))} for i in range(0,len(facts),2)]
        candidates += [{'task':'continuity' if phase=='preflight' else 'coverage','owned_passages':[p['id'] for p in catalog[i:i+2]],'fact_indices':[]} for i in range(0,len(catalog),2)]
        if not candidates:candidates=[{'task':'facts','owned_passages':[],'fact_indices':[]}]
        batches=[dict(c,id=str(i*len(prior_groups)+j),prior_indices=group) for i,c in enumerate(candidates) for j,group in enumerate(prior_groups)]
    require(len(batches)<=256,'Memory coverage exceeds one Actions matrix; split the episode or use continuation without dropping facts')
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
    from .canon import cards
    from .editorial_transport import factual
    from .inference import Executor
    p,prose,memory=inputs(state,source);batch=next((b for b in p['batches'] if b['id']==bid),None)
    require(batch is not None,'Unknown memory batch')
    if memory.get('unverified'):
        verdict={'pass':False,'issues':[],'unverified':True,'error':'Memory extraction unavailable'}
    else:
        facts=[{'index':i,**{k:v for k,v in memory['memories'][i].items() if k in {'kind','text','known_by','holder','claim_source','fact_key','supersedes','evidence_ids'}}} for i in batch['fact_indices']]
        mode=('Also check continuity ONLY in owned_passages: character arrival before action, acquired knowledge, custody, resources and causal joins. Quote the affected owned paragraph and target prose for a demonstrated continuity fault. '
              if p['phase']=='preflight' else 'Assess ONLY the supplied extracted facts and knowledge holders. Do not report prose, entrances, style, similes or editorial preferences; those were assessed in the final editorial check. Issues must target memory. ')
        data={**scene_context(state,card,'memory_quality'),'current_prose':prose,'owned_passages':batch['owned_passages'],
              'proposed_memory':{'memories':facts},'check_phase':p['phase']}
        text_mode=state['request'].get('performance',{}).get('memory_pair_batches')
        if text_mode:
            catalog=passages(prose);ids={pid for f in facts for pid in f.get('evidence_ids',[])}|set(batch['owned_passages'])
            positions=[i for i,x in enumerate(catalog) if x['id'] in batch['owned_passages']]
            evidence=[x for i,x in enumerate(catalog) if x['id'] in ids or any(abs(i-j)<=1 for j in positions)]
            prior=memory_canon(state)
            if batch['task'] in {'continuity','coverage'}:
                facts=[{'index':i,**{k:v for k,v in f.items() if k in {'kind','text','known_by','holder','claim_source','fact_key','supersedes','evidence_ids'}}} for i,f in enumerate(memory['memories']) if set(f.get('evidence_ids',[])) & set(batch['owned_passages'])]
            data={'original_prompt':state['request']['premise'],'scene_contract':next((c for c in state['request']['scene_designs'] if c['id']==card['id']),{}),
                  'current_prose':'\n\n'.join(x['text'] for x in evidence),'evidence_passages':[{'id':x['id'],'text':x['text']} for x in evidence],
                  'owned_passages':batch['owned_passages'],'proposed_memory':{'memories':facts},
                  'prior_canon':[prior[i] for i in batch['prior_indices']],'check_phase':p['phase'],'task':batch['task'],
                  'coverage_policy':'This is one exhaustive canon partition, not a summary. Other partitions are checked separately. Do not invent omitted facts. Canon knowledge holders, uncertainty and supersession govern. Historical_superseded facts describe earlier states; do not mistake them for current contradictions. A private update does not automatically grant knowledge to previous holders.'}
            mode = ((mode+' Also check extraction completeness: material facts, resource changes, obligations and knowledge acquired in owned passages must appear accurately in proposed_memory. Missing facts target memory, never rewrite prose to justify them. ') if batch['task']=='continuity' else 'Check completeness of proposed_memory against owned passages. Missing material facts or unsupported knowledge target memory. No prose or style judgments. ' if batch['task']=='coverage' else 'Check ONLY supplied facts, their source evidence and knowledge holders against this canon partition. Issues target memory; no prose or style judgment. ')
        options={'tokens':650 if text_mode else 1200,'response_schema':memory_review_schema()}
        if text_mode and backend!='fixture':options.update(response_schema=False,output_format='text',skill='Verify source-supported facts and knowledge; do not edit prose.')
        try:
            verdict=Executor(scoped(state['request']),out,backend).call('memory_quality',
                data,
                'Verify every supplied fact, uncertainty, chronology and knowledge holder against actual prose and established canon. Other paragraphs are read-only context. Never rewrite prose to make a false extraction true. '+mode+
                'Do not flag stylistic repetition or require changes contrary to the author brief. A passing result may contain advisory issues only. '+
                ('Return PASS or FAIL, followed only when necessary by lines: ISSUE blocking/advisory | memory/prose | category | exact source quote | specific problem | specific fix. No JSON.' if text_mode and backend!='fixture' else 'Return pass and issues with exact source quotations, target memory or prose, and specific fixes.'),
                validator=lambda v:validate(factual(v,prose),prose,batch,p['phase']),**options)
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


def extract_plan(state,source,out):
    from .batch_pipeline import bind_state,output
    prose=(Path(source)/'edited/prose.txt').read_text();catalog=passages(prose)
    batches=[{'id':str(i//2),'ids':[p['id'] for p in catalog[i:i+2]]} for i in range(0,len(catalog),2)]
    value={'state_sha256':bind_state(state),'source_sha256':digest(prose),'batches':batches}
    save(Path(out)/'extract-plan.json',value);output('characters',[b['id'] for b in batches]);return value


def extract_batch(state,card,source,out,backend,bid):
    from .batch_pipeline import bind_state,scoped
    from .inference import Executor
    from .canon import cards
    from .resilience import memory_extract
    from .coordinator import MEMORY_INSTRUCTION
    p=load(Path(source)/'plan/extract-plan.json');prose=(Path(source)/'edited/prose.txt').read_text()
    require(p['state_sha256']==bind_state(state) and p['source_sha256']==digest(prose),'Stale extraction plan')
    batch=next((b for b in p['batches'] if b['id']==bid),None);require(batch is not None,'Unknown extraction batch')
    packet={'evidence_passages':[{'id':x['id'],'text':x['text']} for x in passages(prose) if x['id'] in batch['ids']],
            'characters':[c['id'] for c in state['request']['characters']],'prior_canon':cards(state['memories']),
            'original_prompt':state['request']['premise'],'scene':card,'specific_memory_findings':p.get('memory_corrections',[])}
    instruction=MEMORY_INSTRUCTION+' Extract all material supported changes and obligations in these owned passages; do not invent or summarize away facts. Other batches cover other passages. Preserve uncertainty and individual knowledge.'
    result=None;last=None;req=scoped(state['request'])
    if not batch['ids']:result={'memories':[]}
    for attempt in range(0 if result is not None else 2):
        folder=Path(out)/str(attempt)
        try:
            result=memory_extract(Executor(req,folder,backend),req,folder,prose,packet,instruction);break
        except Exception as exc:
            last=str(exc);raw=[]
            for path in folder.glob('calls/memory-*.json'):raw.append(load(path).get('output'))
            if not raw:break
            packet={**packet,'rejected_memory_output':raw[-1],'specific_validation_error':last}
            instruction+=' Correct only this extraction failure using the exact prior identity, kind, known_by and source evidence. New events must not overwrite immutable prior premises. Preserve valid facts.'
    if result is None:result={'memories':[],'unverified':True,'error':last}
    value={'id':bid,'plan_sha256':bind_state(p),'memory':result};save(Path(out)/'memory-extract-batch.json',value);return value


def extract_join(state,source,out):
    from .batch_pipeline import bind_state
    from .contracts import delta
    p=load(Path(source)/'plan/extract-plan.json');prose=(Path(source)/'edited/prose.txt').read_text()
    require(p['state_sha256']==bind_state(state) and p['source_sha256']==digest(prose),'Stale extraction merge')
    expected={b['id'] for b in p['batches']};found={}
    for path in (Path(source)/'batches').rglob('memory-extract-batch.json'):
        v=load(path);require(v['id'] in expected and v['id'] not in found,'Foreign or duplicate extraction batch')
        require(v['plan_sha256']==bind_state(p),'Stale extraction batch');found[v['id']]=v['memory']
    memories=list(p.get('retained',[]));seen={bind_state(fact) for fact in memories}
    for b in p['batches']:
        for fact in found.get(b['id'],{}).get('memories',[]):
            key=bind_state(fact)
            if key not in seen:memories.append(fact);seen.add(key)
    value=delta({'memories':memories},prose,[c['id'] for c in state['request']['characters']])
    missing=sorted(expected-set(found));failed=[key for key,v in found.items() if v.get('unverified') or v.get('fallback')]
    if missing or failed or p.get('upstream_unverified'):value.update(unverified=True,error='Incomplete extraction; verified facts retained',missing_batches=missing,unverified_batches=failed)
    save(Path(out)/'memory.json',value);return value


def refresh_plan(state,source,out):
    from .batch_pipeline import bind_state,output
    from .experimental import bind_memory
    before=(Path(source)/'original/prose.txt').read_text();prose=(Path(source)/'edited/prose.txt').read_text()
    initial=load(Path(source)/'initial-memory/memory.json')
    retained,diff=bind_memory(initial,before,prose);changed={x['id'] for x in diff['changed']}
    corrections=[];review_path=Path(source)/'preflight-memory/review.json'
    if review_path.exists():
        findings=load(review_path)
        require(findings['source_sha256']==digest(before),'Stale memory repair findings')
        corrections=[i for i in findings.get('issues',[]) if i.get('target')=='memory']
        affected={p['id'] for p in passages(before) if any(i.get('quote') and i['quote'] in p['text'] for i in corrections)}
        changed.update(diff['unchanged'][pid] for pid in affected if pid in diff['unchanged'])
        retained=[f for f in retained if not set(f.get('evidence_ids',[]))&changed]
    if initial.get('unverified'):
        changed={p['id'] for p in passages(prose)};retained=[]
    ids=[p['id'] for p in passages(prose) if p['id'] in changed]
    batches=[{'id':str(i//2),'ids':ids[i:i+2]} for i in range(0,len(ids),2)] or [{'id':'noop','ids':[]}]
    value={'state_sha256':bind_state(state),'source_sha256':digest(prose),'batches':batches,
           'retained':retained,'memory_corrections':corrections,'upstream_unverified':False,'full_reextraction':initial.get('unverified',False)}
    save(Path(out)/'extract-plan.json',value);output('characters',[b['id'] for b in batches]);return value
