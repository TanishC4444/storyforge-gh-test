"""Source-bound parallel memory checks before repairs and after fact refresh."""
import math
from pathlib import Path
from .storage import load,save
from .continuation import history as continuity_history
from .contracts import require,review
from .evidence import passages
from .patching import digest
from .output_schema import memory_review_schema
from .adaptive import enabled as adaptive,windows


def memory_canon(state):
    from .canon import index
    from .continuation import history
    view=index(history(state));current={m['id'] for m in view['current']}
    keys={'id','kind','text','known_by','holder','claim_source','source','state_version','continuity_scope','literary_status','subject','life_state','thread_id','thread_state','fact_key','supersedes','evidence_prose_sha256'}
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
        prior=memory_canon(state);prior_size=32 if state['request'].get('performance',{}).get('pipelined_living') else 20 if adaptive(state['request']) else 8;fact_size=8 if adaptive(state['request']) else 2
        prior_groups=[list(range(i,min(i+prior_size,len(prior)))) for i in range(0,len(prior),prior_size)] or [[]]
        candidates=[{'task':'facts','owned_passages':[],'fact_indices':list(range(i,min(i+fact_size,len(facts))))} for i in range(0,len(facts),fact_size)]
        groups=windows(catalog,450) if adaptive(state['request']) else [catalog[i:i+2] for i in range(0,len(catalog),2)]
        candidates += [{'task':'continuity' if phase=='preflight' else 'coverage','owned_passages':[p['id'] for p in group],'fact_indices':[]} for group in groups]
        if not candidates:candidates=[{'task':'facts','owned_passages':[],'fact_indices':[]}]
        batches=[dict(c,id=str(i*len(prior_groups)+j),prior_indices=group) for i,c in enumerate(candidates) for j,group in enumerate(prior_groups)]
    previous=Path(source)/'preflight-memory/review.json'
    reuse=None
    if phase=='final' and adaptive(state['request']) and previous.exists():
        v=load(previous)
        if v.get('pass') and not v.get('unverified') and v.get('state_sha256')==bind_state(state) and v.get('source_sha256')==digest(prose) and v.get('memory_sha256')==bind_state(memory):
            reuse=v;batches=[{'id':'reuse','owned_passages':[],'fact_indices':[]}]
    if memory.get('unverified'):
        # No model can verify incomplete extraction. Preserve the full ledger and
        # report one blocked check instead of launching identical failing workers.
        reuse=None;batches=[{'id':'0','owned_passages':[],'fact_indices':[]}]
    require(len(batches)<=256,'Memory coverage exceeds one Actions matrix; split the episode or use continuation without dropping facts')
    value={'phase':phase,'state_sha256':bind_state(state),'source_sha256':digest(prose),
           'memory_sha256':bind_state(memory),'batches':batches,'reused_preflight':reuse}
    save(Path(out)/'memory-plan.json',value);output('characters',[b['id'] for b in batches]);return value


def inputs(state,source):
    from .batch_pipeline import bind_state
    source=Path(source);p=load(source/'plan/memory-plan.json')
    prose=(source/'edited/prose.txt').read_text();memory=load(source/'memory/memory.json')
    require(p['state_sha256']==bind_state(state) and p['source_sha256']==digest(prose)
            and p['memory_sha256']==bind_state(memory),'Stale memory-check inputs')
    return p,prose,memory


def validate(value,prose,batch,phase,allowed=None):
    value=review(value,prose);catalog=passages(prose)
    for issue in value['issues']:
        require(issue.get('target') in {'memory','prose'},'Memory issue requires target')
        if issue['target']=='prose':
            ids=issue.get('evidence_ids') or [p['id'] for p in catalog if issue['quote'] in p['text']]
            owned=set(batch['owned_passages']) if phase=='preflight' else set(allowed or batch['owned_passages'])
            require(bool(set(ids)&owned),'Prose issue outside owned memory batch')
            issue['evidence_ids']=[pid for pid in ids if pid in owned]
            if phase=='final':
                # Preserve late findings and their original verdict rather than
                # losing them as a transport error or silently granting approval.
                issue['outside_requested_scope']=True
    return value


def evidence_context(catalog,owned,facts):
    ids=set(owned)|{pid for f in facts for pid in f.get('evidence_ids',[])}
    # Fact quotations alone omit entrances and listeners established earlier in
    # the conversation. Supply their coherent source window as read-only context;
    # factual ownership and canon partitions remain unchanged.
    for group in windows(catalog,450):
        if any(p['id'] in ids for p in group):
            ids.update(p['id'] for p in group)
    positions=[i for i,p in enumerate(catalog) if p['id'] in ids]
    return [p for i,p in enumerate(catalog) if any(abs(i-j)<=1 for j in positions)]


def check(state,card,source,out,backend,bid):
    from .batch_pipeline import scoped,scene_context,bind_state
    from .canon import cards
    from .editorial_transport import factual,factual_ids
    from .inference import Executor
    p,prose,memory=inputs(state,source);batch=next((b for b in p['batches'] if b['id']==bid),None)
    require(batch is not None,'Unknown memory batch')
    if p.get('reused_preflight'):
        verdict={'pass':True,'issues':p['reused_preflight']['issues'],'reused_unchanged_verified_memory':True}
    elif memory.get('unverified'):
        verdict={'pass':False,'issues':[],'unverified':True,'error':memory.get('error','Memory extraction unavailable')}
    else:
        facts=[{'index':i,**{k:v for k,v in memory['memories'][i].items() if k in {'kind','text','known_by','holder','claim_source','continuity_scope','literary_status','subject','life_state','thread_id','thread_state','fact_key','supersedes','evidence_ids'}}} for i in batch['fact_indices']]
        mode=('Also check continuity ONLY in owned_passages: character arrival before action, acquired knowledge, custody, resources and causal joins. Quote the affected owned paragraph and target prose for a demonstrated continuity fault. '
              if p['phase']=='preflight' else 'Assess ONLY the supplied extracted facts and knowledge holders. Do not report prose, entrances, style, similes or editorial preferences; those were assessed in the final editorial check. Issues must target memory. ')
        data={**scene_context(state,card,'memory_quality'),'current_prose':prose,'owned_passages':batch['owned_passages'],
              'proposed_memory':{'memories':facts},'check_phase':p['phase']}
        text_mode=state['request'].get('performance',{}).get('memory_pair_batches')
        if text_mode:
            catalog=passages(prose)
            prior=memory_canon(state)
            identity_index=[{k:f[k] for k in ['id','kind','fact_key','known_by','canonical_status'] if k in f} for f in prior]
            if batch['task'] in {'continuity','coverage'}:
                facts=[{'index':i,**{k:v for k,v in f.items() if k in {'kind','text','known_by','holder','claim_source','continuity_scope','literary_status','subject','life_state','thread_id','thread_state','fact_key','supersedes','evidence_ids'}}} for i,f in enumerate(memory['memories']) if set(f.get('evidence_ids',[])) & set(batch['owned_passages'])]
            # Select owned facts first, then include EVERY cited anchor, even
            # when the other end falls outside this paragraph window.
            evidence=evidence_context(catalog,batch['owned_passages'],facts)
            prior_lookup={f['id']:f for f in prior}
            references=[{'fact_index':f['index'],'prior_id':old,'exists':old in prior_lookup,
                         'same_key_and_kind':old in prior_lookup and f.get('fact_key')==prior_lookup[old].get('fact_key') and f['kind']==prior_lookup[old]['kind']}
                        for f in facts for old in f.get('supersedes',[])]
            linked_ids={old for f in facts for old in f.get('supersedes',[])}
            from .narrative_context import context
            narrative=context(state,card,include_policy=False)
            data={'reading_order':narrative['reading_order'],'original_prompt':state['request']['premise'],'scene_contract':next((c for c in state['request']['scene_designs'] if c['id']==card['id']),{}),
                  'current_prose':'\n\n'.join(x['text'] for x in evidence),'evidence_passages':[{'id':x['id'],'text':x['text']} for x in evidence],
                  'owned_passages':batch['owned_passages'],'proposed_memory':{'memories':facts},
                  'prior_canon':[prior[i] for i in batch['prior_indices']],'check_phase':p['phase'],'task':batch['task'],
                  'canon_identity_index':identity_index,
                  'character_registry':[{'id':c['id'],'name':c['name']} for c in state['request']['characters']],
                  'application_reference_checks':references,
                  'linked_prior_facts':[f for f in prior if f['id'] in linked_ids],
                  'previous_findings_to_verify':p.get('recovery_findings',[]),
                  'coverage_policy':'owned_passages defines responsibility for completeness and prose findings, not a limit on fact evidence. Judge each supplied fact against ALL its evidence_ids in evidence_passages; a multi-anchor fact may be supported outside owned_passages. This is one exhaustive continuity partition, not a summary. character_registry is the complete authored cast and the authority for character ID existence. canon_identity_index enumerates fact IDs, NOT characters; absence of a character from it is not an identity error. canon_identity_index contains ALL prior fact IDs, exact keys and knowledge holders; linked_prior_facts supplies full referenced records, even outside this partition. application_reference_checks deterministically verifies exact ID existence and key/kind matching; judge semantic replacement validity, not a contradictory guess about those verified bytes. An ID absent from prior_canon is NOT nonexistent. Never renumber an ID or substitute an older fact with a different key. Records tagged draft_branch are source-verified facts of this provisional manuscript, not published universe canon. Other partitions are checked separately. Do not invent omitted facts. Historical_superseded facts describe earlier states. Previously acquired knowledge persists, but public observation of an action never grants access to private feelings. Check each atomic claim separately.'}
            mode = ((mode+' Also check extraction completeness: material facts, resource changes, obligations and knowledge acquired in owned passages must appear accurately in proposed_memory. Missing facts target memory, never rewrite prose to justify them. ') if batch['task']=='continuity' else 'Check completeness of proposed_memory against owned passages. Missing material facts or unsupported knowledge target memory. No prose or style judgments. ' if batch['task']=='coverage' else 'Check ONLY supplied facts, their source evidence and knowledge holders against this canon partition. Issues target memory; no prose or style judgment. ')
        id_mode=adaptive(state['request'])
        options={'tokens':1200 if id_mode else 650 if text_mode else 1200,'response_schema':memory_review_schema()}
        if text_mode and backend!='fixture':options.update(response_schema=False,output_format='text',skill='Verify source-supported facts and knowledge; do not edit prose.')
        try:
            verdict=Executor(scoped(state['request']),out,backend).call('memory_quality',
                data,
                'Verify every supplied fact, uncertainty, chronology and knowledge holder against actual prose and established canon. Other paragraphs are read-only context. Never rewrite prose to make a false extraction true. '+mode+
                'Do not flag stylistic repetition or require changes contrary to the author brief. A passing result may contain advisory issues only. '+
                (('Return PASS or FAIL, followed only when necessary by lines: ISSUE blocking/advisory | memory/prose | category | p001,p002 source IDs | specific problem | specific fix. Use existing supplied IDs, never write quotes. No JSON.' if id_mode else 'Return PASS or FAIL, followed only when necessary by lines: ISSUE blocking/advisory | memory/prose | category | exact source quote | specific problem | specific fix. No JSON.') if text_mode and backend!='fixture' else 'Return pass and issues with exact source quotations, target memory or prose, and specific fixes.'),
                validator=lambda v:validate(factual_ids(v,prose,{x['id'] for x in evidence}) if id_mode and text_mode and backend!='fixture' else factual(v,prose),prose,batch,p['phase'],{x['id'] for x in evidence} if text_mode else None),**options)
        except Exception as exc:verdict={'pass':False,'issues':[],'unverified':True,'error':str(exc)}
    value={'id':bid,'plan_sha256':bind_state(p),'review':verdict}
    save(Path(out)/'memory-check-batch.json',value);return value


def join(state,source,out):
    from .batch_pipeline import bind_state
    p,prose,memory=inputs(state,source);expected={b['id'] for b in p['batches']};found={}
    for path in (Path(source)/'batches').rglob('memory-check-batch.json'):
        v=load(path)
        # Native reruns leave surplus matrix artifacts from previous plans.
        # They are not evidence for this plan; missing CURRENT batches still fail.
        if v.get('plan_sha256')!=bind_state(p):continue
        require(v['id'] in expected and v['id'] not in found,'Duplicate or foreign current memory batch');found[v['id']]=v
    issues=[issue for b in p['batches'] if b['id'] in found for issue in found[b['id']]['review'].get('issues',[])]
    missing=sorted(expected-set(found));unverified=memory.get('unverified',False) or bool(missing) or any(v['review'].get('unverified') for v in found.values())
    verdict={'pass':not unverified and all(v['review']['pass'] for v in found.values()),'issues':issues,
             'source_sha256':digest(prose),'state_sha256':bind_state(state),'memory_sha256':bind_state(memory),'phase':p['phase'],'missing_batches':missing,'reused_preflight':bool(p.get('reused_preflight'))}
    if unverified:verdict.update(unverified=True,error='Missing or unverified memory-check batch',batch_errors={key:v['review'].get('error') for key,v in found.items() if v['review'].get('unverified')})
    save(Path(out)/'review.json',verdict);return verdict


def extract_plan(state,source,out):
    from .batch_pipeline import bind_state,output
    prose=(Path(source)/'edited/prose.txt').read_text();catalog=passages(prose)
    groups=windows(catalog,350) if adaptive(state['request']) else [catalog[i:i+2] for i in range(0,len(catalog),2)]
    batches=[{'id':str(i),'ids':[p['id'] for p in group]} for i,group in enumerate(groups)]
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
    catalog=passages(prose)
    packet={'evidence_passages':[{'id':x['id'],'text':x['text']} for x in catalog if x['id'] in batch['ids']],
            'read_only_source_context':[{'id':x['id'],'text':x['text']} for x in evidence_context(catalog,batch['ids'],[]) if x['id'] not in batch['ids']],
            'character_registry':[{'id':c['id'],'name':c['name']} for c in state['request']['characters']],
            'characters':[c['id'] for c in state['request']['characters']],'prior_canon':cards(continuity_history(state)),
            'original_prompt':state['request']['premise'],'scene':card,
            'specific_memory_findings':[f for f in p.get('memory_corrections',[]) if affected_passages([f],prose)&set(batch['ids'])]}
    instruction=MEMORY_INSTRUCTION+' Extract all material supported changes and obligations in these owned passages; do not invent or summarize away facts. Other batches cover other passages. Preserve uncertainty and individual knowledge. Findings describe alleged problems, NOT source facts. Never copy an event from a finding or read-only context into an owned passage that does not establish it. Use global passage IDs exactly as supplied; never renumber them.'
    result=None;last=None;req=scoped(state['request'])
    if not batch['ids']:result={'memories':[]}
    for attempt in range(0 if result is not None else 2):
        folder=Path(out)/str(attempt)
        try:
            result=memory_extract(Executor(req,folder,backend),req,folder,prose,packet,instruction);break
        except Exception as exc:
            last=str(exc);raw=[]
            if 'Memory field-only recovery failed' in last:
                partial=folder/'memory-partial.json'
                if partial.exists():result=load(partial)
                break
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
        v=load(path)
        if v.get('plan_sha256')!=bind_state(p):continue
        require(v['id'] in expected and v['id'] not in found,'Foreign or duplicate current extraction batch');found[v['id']]=v['memory']
    memories=list(p.get('retained',[]));seen={bind_state(fact) for fact in memories}
    for b in p['batches']:
        for fact in found.get(b['id'],{}).get('memories',[]):
            key=bind_state(fact)
            if key not in seen:memories.append(fact);seen.add(key)
    value=delta({'memories':memories},prose,[c['id'] for c in state['request']['characters']])
    from .universe_events import validate_lifecycle
    try:validate_lifecycle(state,value['memories'])
    except ValueError as exc:value.update(unverified=True,error=str(exc))
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
        affected=affected_passages(corrections,before)
        changed.update(diff['unchanged'][pid] for pid in affected if pid in diff['unchanged'])
        # A retained fact may cite several paragraphs. Re-extract all its source
        # anchors if any anchor is invalidated, so the other half is not lost.
        while True:
            linked={pid for f in retained if set(f.get('evidence_ids',[]))&changed for pid in f.get('evidence_ids',[])}
            if linked<=changed:break
            changed.update(linked)
        retained=[f for f in retained if not set(f.get('evidence_ids',[]))&changed]
    if initial.get('unverified'):
        changed={p['id'] for p in passages(prose)};retained=[]
    ids=[p['id'] for p in passages(prose) if p['id'] in changed]
    groups=windows([p for p in passages(prose) if p['id'] in changed],350) if adaptive(state['request']) else [[{'id':pid} for pid in ids[i:i+2]] for i in range(0,len(ids),2)]
    batches=[{'id':str(i),'ids':[p['id'] for p in group]} for i,group in enumerate(groups)] or [{'id':'noop','ids':[]}]
    value={'state_sha256':bind_state(state),'source_sha256':digest(prose),'batches':batches,
           'retained':retained,'memory_corrections':corrections,'upstream_unverified':False,'full_reextraction':initial.get('unverified',False)}
    save(Path(out)/'extract-plan.json',value);output('characters',[b['id'] for b in batches]);return value


def affected_passages(issues,prose):
    from .evidence import quote_span
    catalog=passages(prose);known={p['id'] for p in catalog};affected=set()
    for issue in issues:
        ids=issue.get('evidence_ids') or [s['id'] for s in issue.get('evidence_spans',[]) if s.get('id')]
        if ids:
            require(set(ids)<=known,'Memory correction cites unknown source');affected.update(ids)
        elif issue.get('quote'):
            start,end,_=quote_span(issue['quote'],prose)
            affected.update(p['id'] for p in catalog if p['start']<end and p['end']>start)
    return affected
