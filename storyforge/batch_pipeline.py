"""Gemini-first small writing/repair batches with deterministic source-bound merges."""
import argparse,copy,json,math,os,time
from pathlib import Path
from .adaptive import enabled as adaptive,repetitions
from .continuation import history as continuity_history
from .contracts import require,delta
from .storage import load,save
from .inference import Executor,ROOT
from .evidence import payload,passages
from .canon import working,recording_context,cards,bridge
from .coordinator import packet,MEMORY_INSTRUCTION
from .craft import validate_prose
from .fast_edit import validate as validate_patch,schema as patch_schema
from .patching import apply,digest,targets
from .editorial import STORY_CHECKS,RHETORIC_CHECKS,editorial_review
from .output_schema import editorial_schema
from .resilience import memory_extract
from .experimental import bind_memory
from .adjudication import decide,chapter_text
from .expansion import preview
from .retrieval import application_packet
from .review_policy import contract


def output(name,value):
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write(name+'='+json.dumps(value)+'\n')

def bind_state(state):return digest(json.dumps(state,sort_keys=True))
def scoped(req):
    req=copy.deepcopy(req);req['max_stage_retries']=0;return req

def scene_context(state,card,role='writer'):
    req=state['request']
    from .narrative_context import context
    return {'narrative_context':context(state,card),'scene':card,'original_prompt':req['premise'],'world_rules':req['world_rules'],
        'author_contract':contract(req),
        'scene_contract':next((c for c in req['scene_designs'] if c['id']==card['id']),{}),
        'literary_application':application_packet(req,state['retrieval'],role,card['id']),
        'prior_canon':bridge(state),
        'pov_known_facts':bridge(state,card['pov']),
        'prior_story_context':[{'id':s['id'],'quality_status':s.get('quality_status','reviewed'),'canon_committed':s.get('canon_committed',True),'intended_change_is_plan_only':s.get('intended_change')} for s in (state.get('universe_history',[])+state['accepted'])[-2:]],
        'participants':[{k:c.get(k) for k in ['id','name','goal','fear','contradiction']} for c in req['characters'] if c['id'] in card['participants']],
        'prior_scene_exit':state['accepted'][-1]['prose'][-1200:] if state['accepted'] else '',
        'author_policy':'Plans and author continuity are not automatically shared character knowledge.'}

def review_context(state,card,include_policy=False):
    # No duplicate style/world/contract copies; review_policy injects the exact
    # immutable author contract once. Summaries never become canonical facts.
    req=state['request']
    from .narrative_context import context
    return {'narrative_context':context(state,card),'original_prompt':req['premise'],'scene':card,
            'scene_contract':next((c for c in req['scene_designs'] if c['id']==card['id']),{}),
            'prior_canon':cards(continuity_history(state)),
            'prior_scene_summaries':[{'id':s['id'],'quality_status':s.get('quality_status'),'canon_committed':s.get('canon_committed',True),'source_summary':s['source_summary']} for s in state.get('universe_history',[])+state['accepted'] if s.get('source_summary') and s['source_summary'].get('source_sha256')==digest(s['prose'])],
            'reference_applications':application_packet(req,state['retrieval'],'story_quality',card['id'])}


def plan_draft(state,card,source,out,backend):
    from .adaptive import writing_count
    req=state['request'];count=writing_count(req)
    goals=[('Develop the attempted task and immediate resistance. Do not make the decisive choice yet.',card['goal']),
           ('Develop the competing alternative and decisive choice. Preserve the initial pressure.',card['obstacle']),
           ('Render the material consequence and aftermath. End at the planned exit; no moral summary.',card['intended_change'])]
    beats=[]
    for i in range(count):
        phase=2 if count==1 else 0 if i==0 else 2 if i==count-1 else 1
        beats.append({'id':str(i),'position':i,'count':count,'purpose':goals[phase][0],'scene_anchor':goals[phase][1],
            'entry':'Actual initial scene conditions.' if i==0 else 'Continue the preceding planned beat without repeating its setup.',
            'exit':card['intended_change'] if i==count-1 else 'Hand off causally to the next planned beat; its later outcome must not happen early.',
            'target_words':req['words_per_scene']//count+(1 if i<req['words_per_scene']%count else 0)})
    if count==1:beats[0].update(purpose='Write the complete scene once: attempted action, resistance, consequential choice, aftermath and planned exit. No recap or outline commentary.',entry='Continue actual current memory and the previous exact exit, if any.')
    concrete=card.get('writing_beats',[])
    if concrete:
        require(len(concrete)==count,'Scene writing contract has wrong beat count')
        for beat,defined in zip(beats,concrete):beat.update(purpose=defined['action'],entry=defined['entry_state'],exit=defined['exit_state'])
    plan={'scene_id':card['id'],'state_sha256':bind_state(state),'beats':beats,'direction':(Path(source)/'direction/direction.txt').read_text()}
    plan['plan_sha256']=digest(json.dumps(plan,sort_keys=True));save(Path(out)/'draft-plan.json',plan);output('characters',[b['id'] for b in beats]);return plan

def cached_prose(folder):
    calls=[]
    for p in Path(folder).rglob('incomplete-generation.json'):
        try:c=load(p)
        except (ValueError,OSError):continue
        if c.get('role') in {'writer','writer_beat','humanizer','repair'} and c.get('text'):calls.append((p.stat().st_mtime,c['text']))
    for p in Path(folder).rglob('calls/*.json'):
        try:c=load(p)
        except (ValueError,OSError):continue
        if isinstance(c.get('output'),str) and c.get('role') in {'writer_beat','humanizer','repair'}:calls.append((p.stat().st_mtime,c['output']))
    return max(calls)[1] if calls else ''

def write_batch(state,card,source,out,backend,bid):
    req=scoped(state['request']);out=Path(out);plan=load(Path(source)/'plan/draft-plan.json')
    require(plan['state_sha256']==bind_state(state),'Stale writing plan')
    beat=next((b for b in plan['beats'] if b['id']==bid),None);require(beat is not None,'Unknown writing batch')
    local=copy.deepcopy(req);local['words_per_scene']=beat['target_words']
    data={**scene_context(state,card),'ordered_beat_plan':plan['beats'],'your_beat':beat,'direction':plan['direction'],
        'instruction':'Write only your assigned contiguous part. Other batches supply other parts. Never repeat the scene opening or narrate a later beat early.'}
    data['author_contract']['length'].update(target_scene_words=beat['target_words'],complete_scene_target_words=req['words_per_scene'])
    errors=[];text=''
    minimum=math.ceil(beat['target_words']*local.get('min_words_ratio',.75))
    maximum=math.floor(beat['target_words']*local.get('max_words_ratio',1.3))
    length_instruction=(f' Length is mandatory: write {beat["target_words"]} words, within {minimum}–{maximum} words. Do not stop at a synopsis. Expand actual resistance, concrete action, competing motives and consequences; do not add repetitive explanation or change canon.' if local.get('length_policy',{}).get('scene_words')=='strict' else '')
    if local.get('length_policy',{}).get('overflow')=='advisory':
        length_instruction=f' Aim near {beat["target_words"]} words with at least {minimum} words of developed action. Longer is acceptable when the detail serves the scene. Do not trim necessary action or rewrite solely to meet a maximum. Maintain pacing, coherence and specificity; padding and repetition remain faults.'
    reuse=Path(source)/'reused'
    reused=None
    if reuse.exists():
        require(len(plan['beats'])==1 and beat['position']==0 and card['id']==state['plan']['scenes'][0]['id'],'Saved draft import requires one complete first-scene batch')
        old_state=load(reuse/'s01_design/snapshot.json');old=load(reuse/'s01_write_batches-0/draft-batch.json')
        from .resilience import creative_request
        before=creative_request(old_state['request']);after=creative_request(req)
        before.pop('length_policy',None);after.pop('length_policy',None)
        require(before==after,'Saved draft creative brief differs beyond length policy')
        require(old_state.get('backend')==state.get('backend') and old_state['memories']==state['memories'] and old_state['accepted']==state['accepted']==[],'Saved draft has a different initial canon or backend')
        require(old['state_sha256']==bind_state(old_state) and old['scene_id']==card['id'] and old['id']==bid,'Saved draft provenance does not match its checkpoint')
        text=old['prose'];validate_prose(text,local,check_length=True)
        require(old.get('verified_form') or bool(old.get('errors')),'Saved draft has no verified form or explained rejection')
        if old.get('errors'):
            try:validate_prose(text,old_state['request'],check_length=True)
            except ValueError as exc:old_error=str(exc)
            else:old_error=''
            require(bool(old_error) and all(e in {old_error,'repair failed after bounded retries: '+old_error} for e in old['errors']),'Saved draft rejection was not solely the validated length error')
        reused={'source_sha256':digest(text),'original_verified_form':old.get('verified_form',False),'policy':'Imported verbatim as unreviewed prose; all current literary and memory gates still run.'}
    fresh=state.get('fresh_drafts',{}).get(str(state['plan']['scenes'].index(card)))
    if fresh and len(plan['beats'])==1:
        text=fresh['prose'];require(digest(text)==fresh['source_sha256'],'Fresh draft hash mismatch')
        validate_prose(text,local,check_length=backend!='fixture')
        reused={'source_sha256':digest(text),'policy':'Fresh-run draft import, with all current reviews rebuilt.'}
    for attempt in range(0 if backend=='fixture' or reused is not None else 2):
        role='writer_beat' if attempt==0 else 'repair'
        folder=out/str(attempt);executor=Executor(req,folder,backend)
        inserting=bool(attempt and req.get('performance',{}).get('strict_draft_handoff') and local.get('length_policy',{}).get('scene_words')=='strict' and 0<len(text.split())<minimum and len(passages(text))>1)
        try:
            if inserting:
                from .length_expansion import expand
                text=expand(executor,local,text,data,folder)
                errors=[];break
            text=executor.call(role,{**data,'rejected_batch':text or None,'specific_errors':errors},
                'Return ONLY this assigned beat near its target_words, in the application-owned medium. Preserve the shared chronology, POV, voice and author form. Use a scene heading only in the first batch if the medium requires it. No quoted dialogue against a no-dialogue brief, plot-summary substitutes or neighboring beats. If correcting a rejected batch, return the complete corrected assigned batch; when count is one this is the complete scene. Preserve its events and expand its dramatization to the required length.'+length_instruction,
                tokens=min(4200 if adaptive(req) else 1500,int(beat['target_words']*3.2)+400),output_format='text',validator=lambda t:validate_prose(t,local,check_length=backend!='fixture'))
            validate_prose(text,local,check_length=backend!='fixture')
            errors=[];break
        except Exception as exc:
            if not inserting:text=cached_prose(folder) or text
            errors=[str(exc)]
            if not text:break
    if backend=='fixture' and reused is None:text=f'FIXTURE writing batch {bid}: the assigned planned beat is a transport test only.'
    result={'id':bid,'scene_id':card['id'],'state_sha256':plan['state_sha256'],'plan_sha256':plan['plan_sha256'],'prose':text,'verified_form':bool(text) and not errors,'errors':errors}
    from .craft import length_status
    result['length_status']=length_status(text,local)
    if reused:result['reused_draft']=reused
    save(out/'draft-batch.json',result)
    if text:save(out/'draft.txt',text);preview(out,'Writing batch '+bid+' - unreviewed')
    return result

def merge_draft(state,source,out):
    plan=load(Path(source)/'plan/draft-plan.json');require(plan['state_sha256']==bind_state(state),'Stale writing plan')
    values=[load(p) for p in (Path(source)/'batches').rglob('draft-batch.json')];found={}
    allowed={b['id'] for b in plan['beats']}
    for v in values:
        require(v['id'] in allowed and v['id'] not in found,'Duplicate or foreign writing batch')
        require(v['state_sha256']==plan['state_sha256'] and v['plan_sha256']==plan['plan_sha256'],'Stale writing batch')
        found[v['id']]=v
    prose='\n\n'.join(found[b['id']]['prose'].strip() for b in plan['beats'] if b['id'] in found and found[b['id']]['prose'].strip())
    require(bool(prose),'No writing batch produced readable prose')
    if state['request'].get('performance',{}).get('strict_draft_handoff'):
        require(set(found)==allowed,'Missing writing batch; cannot hand off partial prose')
        require(all(v.get('verified_form') and not v.get('errors') for v in found.values()),'Unverified writing batch; retain draft but do not advance')
        validate_prose(prose,state['request'],check_length=state.get('backend')!='fixture')
    save(Path(out)/'draft.txt',prose);save(Path(out)/'writing-report.json',{'missing':[b['id'] for b in plan['beats'] if b['id'] not in found],'batches':[{k:v for k,v in x.items() if k!='prose'} for x in found.values()],'unreviewed':True})
    preview(out,'Compiled writing batches - unreviewed');return prose

def review_batch(state,card,source,out,backend,kind,group):
    prose=(Path(source)/'edited/prose.txt').read_text();all_checks=STORY_CHECKS if kind=='story' else RHETORIC_CHECKS
    from .adaptive import enabled as adaptive
    checks=all_checks if adaptive(state['request']) and group==0 else all_checks[group*3:(group+1)*3];require(bool(checks),'Unknown review group')
    req=scoped(state['request']);req['execution_policy'].setdefault('cpu_models',{})[kind+'_quality']='qwen7b'
    data={**payload(prose),'scene_wide_repetition_candidates':repetitions(prose),**scene_context(state,card,kind+'_quality'),'required_checks':checks,'prior_scene':state['accepted'][-1]['prose'][-1800:] if state['accepted'] else None}
    if adaptive(req):data={**review_context(state,card),**payload(prose),'scene_wide_repetition_candidates':repetitions(prose),'required_checks':checks}
    summary_path=Path(source)/'summaries/summaries.json'
    if kind=='story' and not adaptive(req) and req.get('performance',{}).get('summary_reviews') and summary_path.exists():
        summaries=load(summary_path);require(summaries['source_sha256']==digest(prose),'Stale story summaries')
        if summaries.get('unverified'):
            result={'kind':kind,'group':group,'state_sha256':bind_state(state),'source_sha256':digest(prose),
                    'review':{'pass':False,'checks':[],'issues':[],'unverified':True,'error':'Incomplete summary coverage'}}
            save(Path(out)/'review-batch.json',result);return result
        data={**review_context(state,card),'required_checks':checks,
              'section_summaries':[{'source_ids':v['ids'],'summary':v['summary']} for v in summaries['sections']],
              'evidence_passages':[{'id':pid,'text':'See source-linked section '+v['id']+' summary.'} for v in summaries['sections'] for pid in v['ids']],
              'summary_policy':'These are provisional source-linked summaries. Judge causal progression, not sentence quality. Never infer author compliance from a summary; exact prose is separately reviewed and read by the final adjudicator.'}
    try:
        from .editorial_transport import call_editorial
        verdict=call_editorial(Executor(req,out,backend),kind+'_quality',data,
            'Assess ONLY the requested dimensions against the actual source and author brief. Cite the exact affected paragraph IDs for every issue; do not request a whole-scene rewrite. Do not invent a preceding scene. Suggestions that contradict the author POV or no-dialogue form are invalid. Give a concrete correction and keep reasons concise.',prose,checks,2000 if adaptive(req) else 1200)
    except Exception as exc:verdict={'pass':False,'checks':[],'issues':[],'unverified':True,'error':str(exc)}
    result={'kind':kind,'group':group,'state_sha256':bind_state(state),'source_sha256':digest(prose),'review':verdict}
    save(Path(out)/'review-batch.json',result);return result

def join_reviews(state,source,out,kind):
    prose=(Path(source)/'edited/prose.txt').read_text();required=STORY_CHECKS if kind=='story' else RHETORIC_CHECKS
    values=[load(p) for p in (Path(source)/'batches').rglob('review-batch.json')];expected={0} if adaptive(state['request']) else set(range(math.ceil(len(required)/3)))
    require(len({v['group'] for v in values})==len(values),'Duplicate review batch')
    require(all(v['kind']==kind and v['state_sha256']==bind_state(state) and v['source_sha256']==digest(prose) for v in values),'Stale or foreign review batch')
    if {v['group'] for v in values}!=expected or any(v['review'].get('unverified') for v in values):verdict={'pass':False,'checks':[c for v in values if not v['review'].get('unverified') for c in v['review'].get('checks',[])],'issues':[i for v in values if not v['review'].get('unverified') for i in v['review'].get('issues',[])],'unverified':True,'error':'Missing or unverified review group; valid findings preserved'}
    else:
        reviews=[v['review'] for v in sorted(values,key=lambda v:v['group'])]
        verdict=editorial_review({'pass':all(v['pass'] for v in reviews),'checks':[c for v in reviews for c in v['checks']],'issues':[i for v in reviews for i in v['issues']]},prose,required)
    verdict.update(state_sha256=bind_state(state),source_sha256=digest(prose))
    save(Path(out)/'review.json',verdict);return verdict

def plan_repairs(state,source,out):
    prose=(Path(source)/'edited/prose.txt').read_text();reviews=[load(Path(source)/p/'review.json') for p in ['story-review','rhetoric-review']]
    memory_path=Path(source)/'memory-review/review.json'
    if memory_path.exists():
        memory_review=load(memory_path)
        require(memory_review['source_sha256']==digest(prose),'Stale preflight memory review')
        reviews.append({'issues':[i for i in memory_review['issues'] if i.get('target')=='prose']})
    selected,_=targets(prose,reviews);catalog=passages(prose);ids=[p['id'] for p in catalog if p['id'] in selected];batches=[]
    groups=[[pid] for pid in ids]
    if state['request'].get('performance',{}).get('empowered_editors'):
        # Relational findings own every linked passage together; independent
        # corrections stay in small parallel batches.
        for review in reviews:
            for issue in review.get('issues',[]):
                # One relational or structural finding needs one editor owning
                # its linked passages, not a competing rewrite for every line.
                linked=set(issue.get('evidence_ids',[]))&set(ids)
                if len(linked)>3 and issue.get('category') in {'scene_change','climax','reference_application','style_fidelity','quality_contract','category'}:
                    # A missing premise/attempt spanning a scene needs one
                    # structural solution, not one new attempt per source window.
                    linked=set(ids)
                related=[g for g in groups if set(g)&linked]
                if len(related)>1:
                    combined=[pid for pid in ids if any(pid in g for g in related)]
                    groups=[g for g in groups if g not in related]+[combined]
        groups.sort(key=lambda g:ids.index(g[0]))
    else:groups=[ids[i:i+2] for i in range(0,len(ids),2)]
    for own in groups:
        positions=[i for i,p in enumerate(catalog) if p['id'] in own]
        context=[{'id':p['id'],'text':p['text']} for i,p in enumerate(catalog) if any(abs(i-j)<=1 for j in positions)]
        owned_words=sum(len(p['text'].split()) for p in catalog if p['id'] in own)
        unowned_words=len(prose.split())-owned_words
        batches.append({'id':str(len(batches)),'source_sha256':digest(prose),'owned':own,'passages':context,
                        'allow_deletions':bool(state['request'].get('performance',{}).get('empowered_editors')),
                        'original_scene_words':len(prose.split()),
                        'owned_word_budget':max(1,min(owned_words,state['request']['words_per_scene']-unowned_words)),
                        'findings':{pid:selected[pid]['issues'] for pid in own}})
    if not batches:batches=[{'id':'noop','source_sha256':digest(prose),'owned':[],'passages':[],'findings':{}}]
    plan={'state_sha256':bind_state(state),'source_sha256':digest(prose),'batches':batches};save(Path(out)/'repair-plan.json',plan);save(Path(out)/'prose.txt',prose);output('characters',[b['id'] for b in batches]);return plan

def repair_batch(state,card,source,out,backend,bid):
    plan=load(Path(source)/'plan/repair-plan.json');require(plan['state_sha256']==bind_state(state),'Stale repair plan')
    batch=next((b for b in plan['batches'] if b['id']==bid),None);require(batch is not None,'Unknown repair batch')
    req=scoped(state['request']);result={'replacements':{}};error=None
    if batch['owned'] and backend!='fixture':
        try:
            from .editorial_transport import patches
            empowered=req.get('performance',{}).get('empowered_editors')
            options={'tokens':min(4200,1400*max(1,len(batch['owned']))),'response_schema':patch_schema(batch),'validator':lambda v:patches(v,batch)}
            if empowered:options.update(response_schema=False,output_format='text')
            data={**review_context(state,card),'batch':batch,'immutable_world_rules':req['world_rules']}
            instruction='Check allegations against the original author prompt and actual canon. Repair ONLY owned passages. Neighbors are read-only. Dismiss criticism that conflicts with the brief. Preserve required events, knowledge and voice. Keep near owned_word_budget by replacing redundant action rather than appending a second climax. Maintain the requested narrative tense across all owned passages. '
            instruction+=('You may delete redundant passages, combine owned passages, restructure, shorten or replace them. Keep each necessary event once. For a merge put the complete combined text under one owned ID and delete the redundant owned IDs. Never move events into unowned passages. Return plain blocks: REPLACE p001 followed by the replacement on new lines, then END_REPLACE. Use DELETE p002 for deletion, or NO_CHANGES. No JSON or commentary.' if empowered else 'Return JSON replacements keyed only by owned IDs. No whole-scene rewrite.')
            try:result=Executor(req,out,backend).call('repair',data,instruction,**options)
            except ValueError as exc:
                raw=[load(p).get('output') for p in (Path(out)/'calls').glob('repair-*.json')]
                if not adaptive(req) or not raw or not any(x in str(exc) for x in ['Duplicate deletion','Duplicate replacement','unowned paragraph','No valid edit blocks']):raise
                result=Executor(req,Path(out)/'patch-clarification',backend).call('repair',{**data,'rejected_patch':raw[-1],'specific_protocol_error':str(exc)},instruction+' Correct only this returned patch once. Use exactly one operation per owned paragraph; never both REPLACE and DELETE. Do not echo paragraph IDs into story text. Do not add NO_CHANGES beside edits.',allow_cpu_fallback=False,**options)
            if empowered and result['replacements']:
                original={x['id']:x['text'] for x in batch['passages'] if x['id'] in batch['owned']}
                candidate={pid:result['replacements'].get(pid,text) for pid,text in original.items()}
                source_prose=Path(source)/'plan/prose.txt'
                compiled=apply(source_prose.read_text(),result['replacements'],plan['source_sha256']) if source_prose.exists() else None
                if compiled is not None:validate_prose(compiled,req,check_length=False)
                def assess(value):
                    if isinstance(value,dict):require(type(value.get('pass')) is bool,'Missing edit assessment');return value
                    require(isinstance(value,str) and value.strip().split('|',1)[0].strip() in {'PASS','FAIL'},'Missing edit assessment')
                    return {'pass':value.strip().startswith('PASS'),'reason':value.strip()}
                assessment=Executor(req,Path(out)/'candidate-check',backend).call('story_quality',
                    {**review_context(state,card),'assessment_scope':'paragraph_patch','original_passages':original,'candidate_patch':candidate,'context_passages':batch['passages'],'compiled_scene_words':len(compiled.split()) if compiled is not None else None,'findings':batch['findings']},
                    'Compare the original with this proposed paragraph edit against the actual author prompt and canon. Candidate_patch is ONLY the owned excerpt, not the whole scene; do not apply the scene word target to it. Check that the specific faults are resolved and no new repetition, contradictions, missing necessary action, forbidden form or knowledge leaks are introduced. Deletion and consolidation are allowed. Do not demand dialogue against a no-dialogue brief. Return PASS or FAIL | one concrete reason. No JSON; do not rewrite.',
                    tokens=250,response_schema=False,output_format='text',skill='Independently judge whether the proposed edit is an improvement grounded in the author brief and actual facts.',validator=assess)
                require(assessment['pass'],'Candidate edit rejected: '+assessment.get('reason','Unresolved editorial faults'))
                save(Path(out)/'candidate-assessment.json',assessment)
        except Exception as exc:error=str(exc)
    save(Path(out)/'repair-batch.json',{'id':bid,'source_sha256':plan['source_sha256'],'replacements':result['replacements'],'unverified':error is not None,'error':error});return result

def merge_repairs(state,source,out):
    plan=load(Path(source)/'plan/repair-plan.json');prose=(Path(source)/'edited/prose.txt').read_text()
    require(plan['state_sha256']==bind_state(state) and plan['source_sha256']==digest(prose),'Stale repair merge')
    values=[load(p) for p in (Path(source)/'batches').rglob('repair-batch.json')];lookup={};edits={}
    for v in values:
        require(v['id'] not in lookup,'Duplicate repair result');lookup[v['id']]=v
    allowed={b['id'] for b in plan['batches']};require(set(lookup)<=allowed,'Foreign repair result')
    missing=[]
    for b in plan['batches']:
        v=lookup.get(b['id'])
        if v is None:missing.append(b['id']);continue
        require(v['source_sha256']==digest(prose),'Stale repair result');validate_patch(v,b)
        require(not set(edits)&set(v['replacements']),'Conflicting edit ownership')
        if not v.get('unverified'):edits.update(v['replacements'])
    merge_error=None
    try:revised=apply(prose,edits,digest(prose))
    except ValueError as exc:revised=prose;edits={};merge_error=str(exc)
    save(Path(out)/'prose.txt',revised)
    save(Path(out)/'repair.json',{'changed':prose!=revised,'reviewed_sha256':digest(prose),'candidate_sha256':digest(revised),'batched_repair':True,'merge_error':merge_error,'changed_paragraphs':list(edits),'missing_batches':missing,'unverified_batches':[v['id'] for v in values if v.get('unverified')]})
    preview(out,'Compiled targeted repairs - unreviewed');return revised

def finalize(state,card,source,out,backend):
    prose=(Path(source)/'edited/prose.txt').read_text();info=load(Path(source)/'edited/repair.json')
    reviews=[load(Path(source)/k/'review.json') for k in ['story-review','rhetoric-review']]
    memory_path=Path(source)/'memory-review/review.json'
    if memory_path.exists():reviews.append(load(memory_path))
    batch_verdict=None
    if (Path(source)/'final-batches').exists():
        from .section_reviews import final_join
        batch_verdict=final_join(state,source)
    elif state['request'].get('performance',{}).get('lean_living_checks'):
        original=Path(source)/'original/prose.txt';facts=Path(source)/'initial-memory/memory.json'
        proof=reviews[2] if len(reviews)>2 else {}
        if original.exists() and original.read_text()==prose and facts.exists() and proof.get('pass') and not proof.get('unverified') and proof.get('source_sha256')==digest(prose) and proof.get('state_sha256')==bind_state(state) and proof.get('memory_sha256')==bind_state(load(facts)) and all(r.get('pass') and not r.get('unverified') and r.get('source_sha256')==digest(prose) and r.get('state_sha256')==bind_state(state) for r in reviews[:2]):
            batch_verdict=editorial_review({'pass':True,'checks':[c for r in reviews[:2] for c in r['checks']],'issues':[i for r in reviews[:2] for i in r['issues']]},prose,STORY_CHECKS+RHETORIC_CHECKS)
            batch_verdict.update(batch_count=0,reused_unchanged_passing_checks=True)
    final=decide(state['request'],state,card,prose,reviews,out,backend,batch_verdict=batch_verdict)
    summaries=Path(source)/'summaries/summaries.json'
    if summaries.exists():
        summary=load(summaries);require(summary['source_sha256']==digest(prose),'Stale summary handoff')
        save(Path(out)/'scene-summary.json',summary)
    save(Path(out)/'prose.txt',prose);save(Path(out)/'repair.json',{**info,'editorial_adjudication':final,'further_editorial_iteration':False});preview(out,'Final checked text - see verification status');return final

def refresh_memory(state,card,source,out,backend):
    prose=(Path(source)/'edited/prose.txt').read_text();before=(Path(source)/'original/prose.txt').read_text();initial=load(Path(source)/'initial-memory/memory.json')
    if prose==before:save(Path(out)/'memory.json',initial);return initial
    retained,diff=bind_memory(initial,before,prose);changed={p['id'] for p in diff['changed']}
    req=scoped(state['request']);data=payload(prose);data['evidence_passages']=[p for p in data['evidence_passages'] if p['id'] in changed]
    additions={'memories':[]}
    if data['evidence_passages']:
        try:additions=memory_extract(Executor(req,out,backend),req,out,prose,{**data,'characters':[c['id'] for c in req['characters']],'prior_canon':cards(continuity_history(state))},MEMORY_INSTRUCTION+' Extract ONLY changed passages; unchanged facts are retained separately.')
        except Exception as exc:additions={'memories':[],'unverified':True,'error':str(exc)}
    result=delta({'memories':retained+additions['memories']},prose,[c['id'] for c in req['characters']])
    if additions.get('unverified') or initial.get('unverified'):result.update(unverified=True,error=additions.get('error',initial.get('error','Unverified original facts remain')))
    save(Path(out)/'memory.json',result);return result

def extract_initial(state,card,source,out,backend):
    prose=(Path(source)/'edited/prose.txt').read_text();req=scoped(state['request'])
    try:
        result=memory_extract(Executor(req,out,backend),req,out,prose,{**payload(prose),'characters':[c['id'] for c in req['characters']],'prior_canon':cards(continuity_history(state))},MEMORY_INSTRUCTION)
    except Exception as exc:result={'memories':[],'unverified':True,'error':str(exc)}
    save(Path(out)/'memory.json',result);return result


def verify_memory(state,card,source,out,backend):
    from .contracts import review as memory_review
    prose=(Path(source)/'edited/prose.txt').read_text();memory=load(Path(source)/'memory/memory.json')
    if memory.get('unverified'):
        verdict={'pass':False,'issues':[],'unverified':True,'error':memory.get('error','Extraction unverified')}
    else:
        req=scoped(state['request'])
        facts=[{k:v for k,v in m.items() if k in {'kind','text','known_by','holder','claim_source','subject','life_state','thread_id','thread_state','fact_key','supersedes','evidence_ids'}} for m in memory['memories']]
        try:
            verdict=Executor(req,out,backend).call('memory_quality',{'current_prose':prose,'proposed_memory':{'memories':facts},'prior_canon':working(state,query=str(card),budget=3500)},
                'Verify every extracted fact and knowledge holder against current_prose and prior canon. Do not treat a prose problem as a memory extraction error. Unsupported facts must fail. Return pass and source-quoted issues with target memory or prose.',tokens=1000,validator=lambda v:memory_review(v,prose))
        except Exception as exc:verdict={'pass':False,'issues':[],'unverified':True,'error':str(exc)}
    save(Path(out)/'review.json',verdict);return verdict


def main():
    p=argparse.ArgumentParser();p.add_argument('task');p.add_argument('--source',default='inputs');p.add_argument('--out',default='out');p.add_argument('--backend',choices=['fixture','worker'],default='fixture');p.add_argument('--index',type=int,default=0);p.add_argument('--batch');p.add_argument('--kind',choices=['story','rhetoric']);p.add_argument('--group',type=int);p.add_argument('--phase',choices=['preflight','final'],default='preflight');a=p.parse_args()
    started=time.monotonic()
    source=Path(a.source);out=Path(a.out);state=load(source/'state/snapshot.json');card=state['plan']['scenes'][a.index]
    if a.task.startswith('section_'):
        from . import section_reviews
        if a.task=='section_plan':section_reviews.plan(state,source,out)
        elif a.task=='section_summary':section_reviews.summarize(state,card,source,out,a.backend,a.batch)
        elif a.task=='section_summaries_join':section_reviews.join_summaries(state,source,out)
        elif a.task=='section_review':section_reviews.review_section(state,card,source,out,a.backend,a.batch)
        elif a.task=='section_reviews_join':section_reviews.join_reviews(state,source,out)
        elif a.task=='section_final_review':section_reviews.final_review(state,card,source,out,a.backend,a.batch)
        else:raise ValueError('Unknown section task')
    elif a.task=='memory_refresh_plan':
        from . import memory_batches
        memory_batches.refresh_plan(state,source,out)
    elif a.task.startswith('memory_extract_'):
        from . import memory_batches
        if a.task=='memory_extract_plan':memory_batches.extract_plan(state,source,out)
        elif a.task=='memory_extract_batch':memory_batches.extract_batch(state,card,source,out,a.backend,a.batch)
        elif a.task=='memory_extract_join':memory_batches.extract_join(state,source,out)
        else:raise ValueError('Unknown memory extraction task')
    elif a.task.startswith('memory_check_'):
        from . import memory_batches
        if a.task=='memory_check_plan':memory_batches.plan(state,source,out,a.phase)
        elif a.task=='memory_check_batch':memory_batches.check(state,card,source,out,a.backend,a.batch)
        elif a.task=='memory_check_join':memory_batches.join(state,source,out)
        else:raise ValueError('Unknown memory-check task')
    elif a.task=='draft_plan':plan_draft(state,card,source,out,a.backend)
    elif a.task=='write_batch':
        result=write_batch(state,card,source,out,a.backend,a.batch)
        if not result.get('prose','').strip() or (state['request'].get('performance',{}).get('strict_draft_handoff') and not result.get('verified_form')):
            save(out/'status.json',{'task':a.task,'status':'failure','phase':'writer_form_rejected' if result.get('prose') else 'writer_unavailable','elapsed_seconds':round(time.monotonic()-started,3),'warning_artifacts':['draft-batch.json']})
            raise SystemExit('No verified writer output; artifacts preserved and job marked failed for targeted retry')
    elif a.task=='merge_draft':merge_draft(state,source,out)
    elif a.task=='forward':save(out/'prose.txt',(source/'draft/draft.txt').read_text())
    elif a.task=='review_batch':review_batch(state,card,source,out,a.backend,a.kind,a.group)
    elif a.task=='join_reviews':join_reviews(state,source,out,a.kind)
    elif a.task=='repair_plan':plan_repairs(state,source,out)
    elif a.task=='repair_batch':repair_batch(state,card,source,out,a.backend,a.batch)
    elif a.task=='merge_repairs':merge_repairs(state,source,out)
    elif a.task=='finalize':finalize(state,card,source,out,a.backend)
    elif a.task=='verdict_view':save(out/'review.json',load(source/'edited/repair.json')['editorial_adjudication'][a.kind])
    elif a.task=='refresh_memory':refresh_memory(state,card,source,out,a.backend)
    elif a.task=='extract_initial':extract_initial(state,card,source,out,a.backend)
    elif a.task=='verify_memory':verify_memory(state,card,source,out,a.backend)
    else:raise ValueError('Unknown batch task')
    warnings=[];judgments=[]
    for filename in ['draft-batch.json','review-batch.json','repair-batch.json','writing-report.json','repair.json','memory.json','memory-check-batch.json','review.json','final-review-batch.json','section-review.json','summary-batch.json']:
        path=out/filename
        if path.exists():
            value=load(path)
            assessment=value.get('review',value.get('editorial_adjudication',{}).get('verdict',value))
            if 'pass' in assessment:judgments.append(assessment)
            if assessment.get('pass') is False or value.get('unverified') or value.get('merge_error') or value.get('errors') or value.get('missing') or value.get('missing_batches') or value.get('unverified_batches') or value.get('review',{}).get('unverified'):
                warnings.append(filename)
    if warnings:print('::warning::'+a.task+': unresolved checks; inspect '+', '.join(warnings),flush=True)
    approval='unverified' if any(v.get('unverified') for v in judgments) else 'changes_requested' if any(v.get('pass') is False for v in judgments) else 'checks_passed' if judgments else 'not_assessed'
    save(out/'status.json',{'approval_status':approval,'task':a.task,'status':'success','phase':'complete_with_warnings' if warnings else 'success','elapsed_seconds':round(time.monotonic()-started,3),'warning_artifacts':warnings,'fixture':a.backend=='fixture'})

if __name__=='__main__':main()
