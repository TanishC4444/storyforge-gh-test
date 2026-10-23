"""Source-linked summaries for causal review; exact passages for prose review."""
import math
from pathlib import Path
from .storage import load,save
from .contracts import require
from .evidence import passages
from .patching import digest
from .editorial import RHETORIC_CHECKS,editorial_review
from .editorial_transport import call_editorial


def plan(state,source,out):
    from .batch_pipeline import bind_state,output
    prose=(Path(source)/'edited/prose.txt').read_text();catalog=passages(prose)
    sections=[{'id':str(i//2),'ids':[p['id'] for p in catalog[i:i+2]]} for i in range(0,len(catalog),2)]
    value={'state_sha256':bind_state(state),'source_sha256':digest(prose),'sections':sections}
    save(Path(out)/'section-plan.json',value);output('characters',[s['id'] for s in sections]);output('reviews',[s['id']+'-'+str(g) for s in sections for g in range(2)])
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
    checks=RHETORIC_CHECKS[group*4:(group+1)*4]
    data={**review_context(state,card),'evidence_passages':rows,'owned_passages':section['ids'],'required_checks':checks}
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
    p,prose=inputs(state,source);expected={s['id']+'-'+str(g) for s in p['sections'] for g in range(2)};found={}
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


def final_review(state,card,source,out,backend,bid):
    from .batch_pipeline import scoped,review_context,bind_state
    from .adjudication import CHECKS
    from .inference import Executor
    prose=(Path(source)/'edited/prose.txt').read_text();group=int(bid);checks=CHECKS[group*3:(group+1)*3]
    require(bool(checks),'Unknown final review group')
    data={**review_context(state,card),'evidence_passages':[{'id':p['id'],'text':p['text']} for p in passages(prose)],
          'required_checks':checks,'prior_scenes_in_current_chapter':[{'id':s['id'],'prose':s['prose'],'quality_status':s.get('quality_status','reviewed')} for s in state['accepted'] if s['chapter']==card['chapter']]}
    try:
        verdict=call_editorial(Executor(scoped(state['request']),out,backend),'chapter_quality',data,
            'This is the ONE final judgment round for your requested dimensions. Independently read the complete actual candidate, original prompt, immutable author contract, source-bound canon and supplied prior chapter scenes. Check actual results of editing, not earlier reviewer opinions. Preserve POV, knowledge, form, style, chronology and source influence. Do not require forbidden dialogue or approve to finish. Return concise source-bound judgments and actionable author-consistent issues; no further rewrite cycle.',prose,checks,1000)
    except Exception as exc:verdict={'pass':False,'checks':[],'issues':[],'unverified':True,'error':str(exc)}
    value={'group':group,'state_sha256':bind_state(state),'source_sha256':digest(prose),'review':verdict}
    save(Path(out)/'final-review-batch.json',value);return value


def final_join(state,source):
    from .batch_pipeline import bind_state
    from .adjudication import CHECKS
    prose=(Path(source)/'edited/prose.txt').read_text();expected=set(range(math.ceil(len(CHECKS)/3)));found={}
    for path in (Path(source)/'final-batches').rglob('final-review-batch.json'):
        v=load(path);require(v['group'] in expected and v['group'] not in found,'Foreign or duplicate final review')
        require(v['state_sha256']==bind_state(state) and v['source_sha256']==digest(prose),'Stale final review')
        found[v['group']]=v['review']
    valid=[v for _,v in sorted(found.items()) if not v.get('unverified')]
    value={'pass':all(v['pass'] for v in valid),'checks':[c for v in valid for c in v['checks']],'issues':[i for v in valid for i in v['issues']]}
    if set(found)!=expected or any(v.get('unverified') for v in found.values()):
        value.update(unverified=True,error='Missing or unverified final dimension batch');value['pass']=False
        return value
    return editorial_review(value,prose,CHECKS)
