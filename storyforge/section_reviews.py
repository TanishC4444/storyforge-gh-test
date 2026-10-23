"""Source-linked summaries for causal review; exact passages for prose review."""
import math
from pathlib import Path
from .storage import load,save
from .contracts import require
from .evidence import passages
from .patching import digest
from .editorial import RHETORIC_CHECKS,STORY_CHECKS,editorial_review
from .editorial_transport import call_editorial
from .adaptive import enabled as adaptive,windows,repetitions


def plan(state,source,out):
    from .batch_pipeline import bind_state,output
    prose=(Path(source)/'edited/prose.txt').read_text();catalog=passages(prose)
    groups=windows(catalog,650) if adaptive(state['request']) else [catalog[i:i+2] for i in range(0,len(catalog),2)]
    sections=[{'id':str(i),'ids':[p['id'] for p in group]} for i,group in enumerate(groups)]
    value={'state_sha256':bind_state(state),'source_sha256':digest(prose),'sections':sections,'adaptive':adaptive(state['request']),'whole_scene':adaptive(state['request']) and len(prose.split())<=1000}
    save(Path(out)/'section-plan.json',value);output('characters',[s['id'] for s in sections]);output('reviews',[s['id']+'-'+str(g) for s in sections for g in range(1 if value['adaptive'] else 2)]);output('final_reviews',final_ids(value));output('story_reviews',[0] if value['adaptive'] else [0,1,2])
    return value


def inputs(state,source):
    from .batch_pipeline import bind_state
    prose=(Path(source)/'edited/prose.txt').read_text();p=load(Path(source)/'plan/section-plan.json')
    require(p['state_sha256']==bind_state(state) and p['source_sha256']==digest(prose),'Stale section plan');return p,prose


def summarize(state,card,source,out,backend,bid):
    from .batch_pipeline import scoped
    from .inference import Executor
    p,prose=inputs(state,source);section=next((s for s in p['sections'] if s['id']==bid),None);require(section is not None,'Unknown section')
    source_rows=[x for x in passages(prose) if x['id'] in section['ids']]
    previous=Path(source)/'previous-summaries/summaries.json';original=Path(source)/'original/prose.txt'
    if previous.exists() and original.exists():
        old=load(previous);old_rows={x['id']:x['text'] for x in passages(original.read_text())}
        require(old['source_sha256']==digest(original.read_text()),'Stale original summaries')
        cached=next((x for x in old['sections'] if x['ids']==section['ids'] and not x.get('unverified')),None)
        if cached and all(old_rows.get(x['id'])==x['text'] for x in source_rows):
            value={**cached,'source_sha256':digest(prose),'reused_exact_source':True}
            save(Path(out)/'summary-batch.json',value);return value
    error=None
    if backend=='fixture':text='FIXTURE source-linked summary; transport only.'
    else:
        try:
            text=Executor(scoped(state['request']),out,backend).call('director',{'original_prompt':state['request']['premise'],'source_passages':[{'id':x['id'],'text':x['text']} for x in source_rows]},
                'Summarize ONLY these actual passages in 60–100 words. Report who acts, choice, resistance, consequence, location/time, custody/resource changes and who learns what. Preserve uncertainty. Do not add planned events, interpretation or literary praise. Name source IDs beside statements. This summary is a navigation aid, not canon. Plain text.',
                tokens=260,response_schema=False,output_format='text')
        except Exception as exc:text='';error=str(exc)
    value={'id':bid,'source_sha256':digest(prose),'ids':section['ids'],'summary':text,'unverified':error is not None,'error':error}
    save(Path(out)/'summary-batch.json',value);return value


def join_summaries(state,source,out):
    p,prose=inputs(state,source);found={}
    for path in (Path(source)/'batches').rglob('summary-batch.json'):
        v=load(path);require(v['id'] not in found and v['source_sha256']==digest(prose),'Duplicate or stale summary');found[v['id']]=v
    expected={s['id'] for s in p['sections']};require(set(found)<=expected,'Foreign summary')
    for section in p['sections']:
        if section['id'] in found:require(found[section['id']]['ids']==section['ids'],'Changed summary source ownership')
    missing=sorted(expected-set(found))
    value={'source_sha256':digest(prose),'sections':[found[s['id']] for s in p['sections'] if s['id'] in found],
           'unverified':bool(missing) or any(v.get('unverified') for v in found.values()),'missing':missing}
    save(Path(out)/'summaries.json',value);return value


def review_section(state,card,source,out,backend,bid):
    from .batch_pipeline import scoped,review_context,bind_state
    section_id,group=bid.split('-');group=int(group);p,prose=inputs(state,source)
    section=next((s for s in p['sections'] if s['id']==section_id),None);require(section is not None and group in {0,1},'Unknown prose review batch')
    catalog=passages(prose);positions=[i for i,x in enumerate(catalog) if x['id'] in section['ids']]
    rows=[{'id':x['id'],'text':x['text']} for i,x in enumerate(catalog) if any(abs(i-j)<=1 for j in positions)]
    checks=RHETORIC_CHECKS if p.get('adaptive') else RHETORIC_CHECKS[group*4:(group+1)*4]
    data={**review_context(state,card),'scene_wide_repetition_candidates':repetitions(prose),'evidence_passages':rows,'owned_passages':section['ids'],'required_checks':checks}
    summaries_path=Path(source)/'summaries/summaries.json'
    if summaries_path.exists():
        summaries=load(summaries_path);require(summaries['source_sha256']==digest(prose),'Stale section summaries')
        data['section_summary']=next((x['summary'] for x in summaries['sections'] if x['id']==section_id),'')
    try:
        from .inference import Executor
        verdict=call_editorial(Executor(scoped(state['request']),out,backend),'rhetoric_quality',data,
            'Read the EXACT owned passages, using neighbors only as context. Assess every requested dimension. Anchor faults to owned IDs. Check summary faithfulness against actual source; an invented or omitted consequential event needs an instruction_leakage issue. User form and actual canon govern; summaries have no authority. Give concise specific reasons.',prose,checks,1100)
        require(all(set(i.get('evidence_ids',[])) & set(section['ids']) for i in verdict.get('issues',[])),'Issue outside owned review section')
    except Exception as exc:verdict={'pass':False,'checks':[],'issues':[],'unverified':True,'error':str(exc)}
    value={'id':bid,'kind':'rhetoric','state_sha256':bind_state(state),'source_sha256':digest(prose),'review':verdict}
    save(Path(out)/'section-review.json',value);return value


def join_reviews(state,source,out):
    from .batch_pipeline import bind_state
    p,prose=inputs(state,source);expected={s['id']+'-'+str(g) for s in p['sections'] for g in range(1 if p.get('adaptive') else 2)};found={}
    for path in (Path(source)/'batches').rglob('section-review.json'):
        v=load(path);require(v['id'] in expected and v['id'] not in found,'Foreign or duplicate section review')
        require(v['source_sha256']==digest(prose) and v['state_sha256']==bind_state(state),'Stale section review');found[v['id']]=v
    valid=[v['review'] for v in found.values() if not v['review'].get('unverified')]
    issues=[i for v in valid for i in v['issues']];checks=[]
    for key in RHETORIC_CHECKS:
        candidates=[c for v in valid for c in v['checks'] if c['id']==key]
        if candidates:checks.append(next((c for c in candidates if c['verdict']=='fail'),candidates[0]))
    missing=sorted(expected-set(found));unverified=bool(missing) or any(v['review'].get('unverified') for v in found.values())
    value={'pass':not unverified and all(v['pass'] for v in valid),'checks':checks,'issues':issues,'missing_batches':missing}
    if unverified:value.update(unverified=True,error='Incomplete prose review; valid findings preserved')
    else:value=editorial_review(value,prose,RHETORIC_CHECKS)
    save(Path(out)/'review.json',value);return value


def final_ids(plan):
    if plan.get('whole_scene'):return ['scene-0']
    if plan.get('adaptive'):return ['story-0']+['local-'+s['id']+'-0' for s in plan['sections']]
    return ['story-'+str(g) for g in range(3)]+['local-'+s['id']+'-'+str(g) for s in plan['sections'] for g in range(2)]


def final_review(state,card,source,out,backend,bid):
    from .batch_pipeline import scoped,review_context,bind_state
    from .adjudication import CHECKS
    from .inference import Executor
    prose=(Path(source)/'edited/prose.txt').read_text();catalog=passages(prose)
    hybrid='-' in str(bid);data=review_context(state,card)
    if bid=='scene-0':
        p,_=inputs(state,source);require(p.get('whole_scene'),'Whole-scene review not allocated')
        checks=CHECKS;rows=catalog
        instruction='Read this complete scene as one coherent batch. Check repeated dialogue or revelations anywhere in it, tense changes, planning language, resource counts, custody, chronology and earned knowledge. A stylistic/API warning in an earlier scene never permits resetting its verified draft facts. Check every author constraint; do not invent flaws or demand extra characters/events.'
        original=Path(source)/'original/prose.txt'
        prior_paths=[Path(source)/k/'review.json' for k in ['story-review','rhetoric-review']]
        if original.exists() and original.read_text()==prose and all(x.exists() for x in prior_paths):
            previous=[load(x) for x in prior_paths]
            memory_proof=Path(source)/'preflight-memory/review.json'
            proof=load(memory_proof) if memory_proof.exists() else None
            memory_clear=proof is None or (proof.get('pass') and not proof.get('unverified') and proof.get('source_sha256')==digest(prose))
            if memory_clear and all(v.get('pass') and not v.get('unverified') for v in previous):
                verdict=editorial_review({'pass':True,'checks':[c for v in previous for c in v['checks']],'issues':[i for v in previous for i in v['issues']]},prose,CHECKS)
                value={'group':bid,'state_sha256':bind_state(state),'source_sha256':digest(prose),'review':verdict,'reused_unchanged_passing_checks':True}
                save(Path(out)/'final-review-batch.json',value);return value
    elif hybrid:
        p,_=inputs(state,source);require(bid in final_ids(p),'Unknown final batch')
        if bid.startswith('local-'):
            _,sid,g=bid.split('-');section=next(s for s in p['sections'] if s['id']==sid)
            checks=RHETORIC_CHECKS if p.get('adaptive') else RHETORIC_CHECKS[int(g)*4:(int(g)+1)*4]
            positions=[i for i,x in enumerate(catalog) if x['id'] in section['ids']]
            rows=[x for i,x in enumerate(catalog) if any(abs(i-j)<=1 for j in positions)]
            data['owned_passages']=section['ids']
            instruction='Judge only your owned passages, using adjacent passages as read-only context. Detect repetitive wording, duplicated actions, POV/style/medium drift and instruction leakage. Anchor issues to owned IDs.'
        else:
            g=int(bid.split('-')[1]);checks=STORY_CHECKS if p.get('adaptive') else STORY_CHECKS[g*3:(g+1)*3]
            summaries=load(Path(source)/'summaries/summaries.json')
            require(summaries['source_sha256']==digest(prose),'Stale final summaries')
            if summaries.get('unverified'):
                value={'group':bid,'state_sha256':bind_state(state),'source_sha256':digest(prose),'review':{'pass':False,'checks':[],'issues':[],'unverified':True,'error':'Incomplete final summaries'}}
                save(Path(out)/'final-review-batch.json',value);return value
            data['current_scene_summaries']=summaries['sections']
            # Exact changed text and joins support summary-based judgments. Never use old summaries after repair.
            original=Path(source)/'original/prose.txt'
            old_texts={x['text'] for x in passages(original.read_text())} if original.exists() else set()
            selected={i for i,x in enumerate(catalog) if x['text'] not in old_texts} if original.exists() else set(range(len(catalog)))
            selected.update({0,len(catalog)-1})
            rows=[x for i,x in enumerate(catalog) if i in selected]
            memory_path=Path(source)/'memory/memory.json'
            if memory_path.exists():data['proposed_memory_changes']=load(memory_path)
            data['prior_scene_outcomes']=[{k:s.get(k) for k in ['id','pov','quality_status','canon_committed','intended_change']} for s in state.get('universe_history',[])+state['accepted']]
            instruction='Assess causal cohesion across the source-linked summaries, full current canon, proposed memory changes and exact supplied passages. Summaries and intended changes are navigation/proposals, never accepted facts. Catch repeated completed events, incompatible chronology, knowledge leaks, abandoned consequences, unearned twists and missing setups. Prior provisional outcomes cannot override canon. Cite exact evidence, not an invented quote.'
    else:
        group=int(bid);checks=CHECKS[group*3:(group+1)*3];require(bool(checks),'Unknown final review group');rows=catalog
        instruction='Independently assess the actual candidate against the original prompt and canon.'
    data['scene_wide_repetition_candidates']=repetitions(prose)
    preflight=Path(source)/'preflight-memory/review.json'
    if preflight.exists():
        proof=load(preflight);require(proof['source_sha256']==digest((Path(source)/'original/prose.txt').read_text()),'Stale preflight evidence')
        data['memory_findings_to_independently_verify']=proof.get('issues',[])
    data.update(evidence_passages=[{'id':x['id'],'text':x['text']} for x in rows],required_checks=checks)
    try:
        verdict=call_editorial(Executor(scoped(state['request']),out,backend),'chapter_quality',data,
            'ONE final strict judgment round; no debate or rewrite loop. '+instruction+' Author medium, knowledge, style and explicit constraints govern. Give concise source-bound judgments; never approve merely to finish.',prose,checks,2300 if adaptive(state['request']) else 1000)
        if data.get('owned_passages'):require(all(set(i.get('evidence_ids',[])) & set(data['owned_passages']) for i in verdict.get('issues',[])),'Final issue outside owned section')
    except Exception as exc:verdict={'pass':False,'checks':[],'issues':[],'unverified':True,'error':str(exc)}
    value={'group':str(bid) if hybrid else int(bid),'state_sha256':bind_state(state),'source_sha256':digest(prose),'review':verdict}
    save(Path(out)/'final-review-batch.json',value);return value


def final_join(state,source):
    from .batch_pipeline import bind_state
    from .adjudication import CHECKS
    prose=(Path(source)/'edited/prose.txt').read_text();plan_path=Path(source)/'plan/section-plan.json'
    expected=set(final_ids(inputs(state,source)[0])) if plan_path.exists() else set(range(math.ceil(len(CHECKS)/3)));found={}
    for path in (Path(source)/'final-batches').rglob('final-review-batch.json'):
        v=load(path);require(v['group'] in expected and v['group'] not in found,'Foreign or duplicate final review')
        require(v['state_sha256']==bind_state(state) and v['source_sha256']==digest(prose),'Stale final review');found[v['group']]=v['review']
    valid=[v for v in found.values() if not v.get('unverified')];checks=[]
    for key in CHECKS:
        candidates=[c for v in valid for c in v['checks'] if c['id']==key]
        if candidates:checks.append(next((c for c in candidates if c['verdict']=='fail'),candidates[0]))
    value={'pass':bool(valid) and all(v['pass'] for v in valid),'checks':checks,'issues':[i for v in valid for i in v['issues']],'batch_count':len(expected)}
    if set(found)!=expected or any(v.get('unverified') for v in found.values()):
        value.update(unverified=True,error='Missing or unverified final batch; valid findings preserved',missing_batches=sorted(expected-set(found),key=str),batch_errors={str(k):v.get('error') for k,v in found.items() if v.get('unverified')});value['pass']=False;return value
    return {**editorial_review(value,prose,CHECKS),'batch_count':len(expected)}
