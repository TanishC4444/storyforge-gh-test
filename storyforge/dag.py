"""Artifact-driven stages for one visible Actions DAG, with a single canon writer."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from . import contracts
from .evidence import payload as evidence_payload
from .coordinator import compact, packet, visible, planning_packet, PLAN_INSTRUCTION, MEMORY_INSTRUCTION
from .inference import Executor, ROOT, parse_json
from .retrieval import retrieve, application_packet
from .brief import controls
from .editorial import STORY_CHECKS, RHETORIC_CHECKS, editorial_review, rhetoric_signals, apply_signals, merge_reviews
from .development import development_stage, validate_scene
from .storage import load, save, export
from .tracking import tracked_stage, event, heartbeat
from .resilience import enabled, warning, unavailable, memory_extract, load_seed
from .patching import repair as patch_repair
from .canon import cards as canon_cards, recording_context

REFINE = 'Develop the premise, preserving explicit user choices and marking assumptions. Return only JSON with original_prompt (exact request premise), refined_prompt, central_conflict, reader_experience (strings), and preserved_user_choices, expanded_story_elements, character_tensions, subplot_possibilities, world_constraints, suggested_techniques, retrieval_references, assumptions, open_decisions (arrays). For every supplied creative category, preserve its explicit choices and develop its practical effect: medium/length, themes/tensions, scenes, world constraints, character behavior/arcs, plots/subplots, genre, tone/mood, reference influence, and figurative style. New detail is a proposal, not a user choice. No chapters yet.'


def output(name, value):
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(name + '=' + (value if isinstance(value, str) else json.dumps(value)) + '\n')


def context(req, state, card):
    return packet(req, state, card)


def actor_packet(req, state, card, cid):
    contracts.require(cid in card['participants'], 'Character not in this scene')
    facts=compact(visible(state['memories'],cid,{s['id']:s['participants'] for s in state['accepted']}))
    if req.get('performance',{}).get('canon_index'):
        from .canon import working
        facts=working(state,cid,query=json.dumps(card),budget=None)['facts']
    return {'character': next(c for c in req['characters'] if c['id'] == cid),
            'situation': {'location': card['location'], 'time': card['time']},
            'known_facts': facts, 'knowledge_policy':'Use only supported known facts; author world rules and future scene outcomes are not character knowledge.'}


def safe_review(value,prose,required,req):
    if value.get('unverified') and (enabled(req) or req.get('execution_policy',{}).get('editorial_disagreement')=='one_strict_check'):return value
    return editorial_review(value,prose,required)


@tracked_stage
def stage(task, source, out, index=0, character=None, request_file='silent-bell-full', profile='balanced', backend='fixture'):
    source, out = Path(source), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if task == 'prepare':
        req = contracts.request(load(ROOT / 'examples' / f'{request_file}.json'))
        if os.getenv('STORY_LEAN_LIVING','').lower()=='true':req.setdefault('performance',{}).update(lean_living_checks=True,adaptive_batches=True,summary_reviews=False)
        if os.getenv('STORY_LIVING_PIPELINE','').lower()=='true':req.setdefault('performance',{})['pipelined_living']=True
        req['profile'] = profile
        if req.get('performance',{}).get('classic_expansion'):
            req.setdefault('execution_policy',{}).setdefault('editorial_disagreement','one_strict_check')
        if req.get('execution_policy',{}).get('experimental') or req.get('performance',{}).get('classic_expansion'):
            from .worker_policy import validate
            validate(req)
        contracts.require(req['chapters'] * req['scenes_per_chapter'] <= (12 if req.get('execution_policy',{}).get('experimental') else 9), 'Requested scenes exceed workflow capacity')
        contracts.require(req['auto_approve_plan'], 'This automated DAG requires explicit auto_approve_plan in the request')
        if backend=='worker' and req.get('performance',{}).get('api_batch_probes'):
            from .hosted import GoogleHosted
            probe=GoogleHosted(out/'provider-budget');health={}
            for kind in ['gemma','flash']:
                try:
                    text,diag=probe.complete(kind,'Return only JSON. Copy all four supplied items without changing them.','{"items":["a","b","c","d"]}',128,structured=True,role='batch_probe')
                    contracts.require(parse_json(text)=={'items':['a','b','c','d']},'Batch probe changed item identities')
                    health[kind]={'batch_probe':'passed','model':diag['model']}
                except Exception as exc:health[kind]={'batch_probe':'failed','error':str(exc)}
            save(out/'batch-provider-health.json',health)
            event('provider_probe','Batched API compatibility probes completed',results=health)
        seed=load_seed(req,ROOT)
        if seed is not None:
            seed['backend']=backend
            event('recovery','Reusing saved outline, refinement and scene 1; no replanning or redrafting',source_run=seed['recovery']['source_run'])
            save(out/'snapshot.json',seed);return seed
        event('retrieval','Searching literary analyses and selecting role-specific craft guidance',mode=req['retrieval_mode'])
        with heartbeat('Retrieving classical mechanisms and role-specific craft guidance'):
            retrieved=retrieve(req)
        state = {'version': 0, 'backend': backend, 'accepted': [],
                 'memories': [dict(f, kind=f.get('kind','event'), source='user_input') for f in req['initial_facts']],
                 'request_hash': hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest(),
                 'retrieval': retrieved, 'request': req}
        event('retrieval_complete','Literary references selected',sources=[s['title'] for s in state['retrieval']['sources']],stale_records=state['retrieval']['stale_embedding_records'])
        save(out / 'snapshot.json', state)
        return state
    if task == 'resume':
        from .resilience import creative_request
        state=load(source/'checkpoint/snapshot.json')
        req=contracts.request(load(ROOT/'examples'/f'{request_file}.json'))
        contracts.require(creative_request(req)==creative_request(state['request']),'Continuation brief differs from checkpoint')
        contracts.require(len(state['accepted'])==2,'Continuation requires exactly two committed scenes')
        contracts.plan(state['plan'],req)
        state['request']['performance']={**state['request'].get('performance',{}),'single_editorial_pass':True,'combine_direction':True,'targeted_edits':True}
        state['request']['profile']=profile;state['backend']=backend
        state['request_hash']=hashlib.sha256(json.dumps(state['request'],sort_keys=True).encode()).hexdigest()
        if (source/'saved-design/snapshot.json').exists() and (source/'saved-draft/draft.txt').exists():
            saved=load(source/'saved-design/snapshot.json')
            contracts.require(saved['accepted']==state['accepted'],'Saved draft has a different canon checkpoint')
            contracts.require(creative_request(saved['request'])==creative_request(req),'Saved draft brief differs')
            state['plan']['scenes'][2]=saved['plan']['scenes'][2]
            state['continuation_drafts']={'2':(source/'saved-draft/draft.txt').read_text()}
        state['continuation']={'source_run':os.getenv('CONTINUATION_RUN'),'start_scene':3}
        save(out/'snapshot.json',state);output('characters',state['plan']['scenes'][2]['participants']);return state
    state = load(source / 'state' / 'snapshot.json')
    req = state['request']
    event('state_loaded','Accepted state loaded',version=state['version'],accepted_scenes=len(state['accepted']),planned_scenes=req['chapters']*req['scenes_per_chapter'])
    if req.get('execution_policy',{}).get('experimental'):
        from .experimental import dispatch,UNHANDLED
        result=dispatch(task,source,out,state,index,profile,backend,request_file)
        if result is not UNHANDLED:return result
    executor = Executor(req, out, backend)
    if req.get('performance',{}).get('single_editorial_pass'):
        executor.req={**req,'max_stage_retries':0}
    if task=='refine' and state.get('recovery',{}).get('reuse_planning'):
        save(out/'refinement.json',state['refinement']);save(out/'snapshot.json',state);return state
    if task == 'refine' and (source / 'seed').exists():
        # Old failed attempts may have valid content rejected only for formatting.
        # Require the exact original story request; max_repairs is an execution-only setting.
        for call_path in sorted((source / 'seed').rglob('calls/refiner-*.json')):
            saved = load(call_path)
            packet_path = call_path.parent.parent / 'packets' / call_path.name
            if not packet_path.exists():
                continue
            previous = contracts.request(copy.deepcopy(load(packet_path).get('input', {}).get('request', {})))
            comparable = lambda x: {k: v for k, v in x.items() if k != 'max_repairs'}
            if comparable(previous) != comparable(req):
                continue
            try:
                recovered = contracts.refinement(parse_json(saved['output']), req)
            except contracts.ContractError:
                continue
            event('recovery','Reusing validated refinement; no model generation',source_run=os.getenv('REFINEMENT_SEED_RUN'))
            state['refinement'] = recovered
            state['refinement_recovery'] = {'source_artifact_call': call_path.name, 'source_run': os.getenv('REFINEMENT_SEED_RUN'), 'normalization': 'String-list reader experience joined; labelled objects represented as name/value entries; no story content invented.'}
            save(out / 'refinement.json', recovered)
            save(out / 'recovered-raw-call.json', saved)
            save(out / 'snapshot.json', state)
            return state
        raise contracts.ContractError('Seed artifact did not contain a compatible valid refinement; no silent replacement or fresh regeneration.')
    if task == 'refine':
        state['refinement'] = executor.call('refiner', {'request': req, 'inspiration': application_packet(req,state['retrieval'],'refiner')}, REFINE, tokens=3600, validator=lambda x: contracts.refinement(x, req))
        save(out / 'refinement.json', state['refinement'])
        save(out / 'snapshot.json', state)
        return state
    if task=='plan' and state.get('recovery',{}).get('reuse_planning'):
        save(out/'plan.json',state['plan']);save(out/'snapshot.json',state);output('characters',state['plan']['scenes'][0]['participants']);return state
    if task == 'plan':
        state['plan'] = executor.call('architect', planning_packet(req, state['refinement'], state['retrieval']), PLAN_INSTRUCTION, tokens=4200, validator=lambda x: contracts.plan(x, req), skill=(ROOT / 'skills/story_architect.md').read_text().split('TECHNIQUE LIBRARY')[0])
        state['plan_approved'] = True
        save(out / 'plan.json', state['plan'])
        save(out / 'snapshot.json', state)
        output('characters', state['plan']['scenes'][0]['participants'])
        return state
    if task in {'refine_review','refine_revision','refine_gate','plan_review','plan_revision','plan_gate'}:
        result=development_stage(task,source,out,state,executor,PLAN_INSTRUCTION,REFINE)
        if task=='plan_gate':output('characters',result['plan']['scenes'][0]['participants'])
        return result
    if task=='scene_design':
        if index>0 and req.get('performance',{}).get('verified_draft_continuity'):
            previous=state['accepted'][-1]
            if not previous.get('canon_committed',True):
                receipts=state.get('draft_continuity_receipts',[])
                contracts.require(any(r['scene']==previous['id'] and r.get('memory_verified') and r['source_sha256']==hashlib.sha256(previous['prose'].encode()).hexdigest() for r in receipts),'Previous scene has no verified memory handoff. Preserve its draft and resolve memory verification before writing the next scene; do not reset to initial facts.')
        old=state['plan']['scenes'][index]
        if str(index) in state.get('fresh_drafts',{}):
            save(out/'scene-design.json',old);save(out/'snapshot.json',state);output('characters',old['participants']);return state
        if req.get('performance',{}).get('single_editorial_pass'):
            save(out/'scene-design.json',old);save(out/'snapshot.json',state);output('characters',old['participants']);event('design','Using approved scene card; writer reconciles with latest accepted canon');return state
        if index==0 and state.get('recovery'):
            save(out/'scene-design.json',old);save(out/'snapshot.json',state);output('characters',old['participants']);return state
        living_proposal={}
        if req.get('performance',{}).get('living_bounded'):
            from .living_prepare import chapter_proposal
            living_proposal=chapter_proposal(state,out)
        from .universe_events import DIRECTOR_POLICY,extended_request,current_life
        from .canon import bridge
        from .adaptive import writing_count
        from .continuation import history as continuity_history
        beat_count=writing_count(req)
        from .narrative_context import context as narrative_context
        designed=executor.call('scene_designer',{'narrative_context':narrative_context(state,old),'living_proposal':living_proposal,'request_controls':controls(req),'world':req['world_design'],'plot':req['plot_design'],'characters':[c for c in req['characters'] if c['id'] in old['participants']] if req.get('performance',{}).get('pipelined_living') else req['characters'],'cast_registry':[{'id':c['id'],'name':c['name']} for c in req['characters']],'proposed_scene':old,'writing_batch_count':beat_count,'creative_freedom':req.get('creative_freedom',{}),'character_life_state':current_life(continuity_history(state)),'accepted_memory':bridge(state),'previous_scene':{'id':state['accepted'][-1]['id'],'quality_status':state['accepted'][-1].get('quality_status'),'canon_committed':state['accepted'][-1].get('canon_committed',True)} if state['accepted'] else None,'user_scene_design':[s for s in req['scene_designs'] if s['id']==old['id']],'inspiration':application_packet(req,state['retrieval'],'scene_designer',old['id'])},
            DIRECTOR_POLICY+' Supply writing_beats with exactly writing_batch_count entries. Each has action, entry_state and exit_state: concrete nonoverlapping proposed events, resource/custody/knowledge handoffs and a clear last exit. Allocate a revelation or action to ONE beat only; later beats cannot repeat it. The writers work in parallel against this shared contract. Reconcile the proposed scene with what ACTUALLY happened. Do not rediscover an established fact. Preserve IDs, chapter, valid participant IDs, world rules, and user choices. Return one JSON scene card with id, chapter, pov, participants, location, time, goal, obstacle, intended_change, choice, consequence, new_development, and reference_uses (array of {record_id,application}). Explain development through a new tactic, cost, commitment, leverage, or interpretation, not stronger adjectives. No new events become canon here.',
            tokens=1600,validator=lambda x:validate_scene(x,req,index,dead={cid for cid,status in current_life(continuity_history(state)).items() if status=='dead'}))
        allowed={r['id'] for r in application_packet(req,state['retrieval'],'scene_designer',old['id'])['references']}
        contracts.require(all(isinstance(r,dict) and r.get('record_id') in allowed for r in designed['reference_uses']),'Scene reference outside applicable source packet')
        dead={cid for cid,status in current_life(continuity_history(state)).items() if status=='dead'}
        contracts.require(not dead & set(designed['participants']),'Scene attempts to revive a canonically dead participant')
        expanded=extended_request(req,designed)
        req['characters']=expanded['characters']
        state['request_hash']=hashlib.sha256(json.dumps(req,sort_keys=True).encode()).hexdigest()
        state['plan']['scenes'][index]=designed
        if req.get('execution_policy',{}).get('experimental'):
            from .experimental import memory_hash
            state['design_memory_hash']=memory_hash(state)
        save(out/'scene-design.json',designed);save(out/'snapshot.json',state)
        output('characters',designed['participants'])
        return state
    card = state['plan']['scenes'][index]
    scene_packet = context(req, state, card)
    budget = min(3600, int(req['words_per_scene'] * 2.2) + 200)
    quality_skill = (ROOT / 'skills/story_quality.md').read_text()
    if task=='character' and str(index) in state.get('continuation_drafts',{}):
        save(out/'proposal.json',{'character':character,'observable_proposal':'Existing draft retained; no new proposal.','state_version':state['version']});return
    if task == 'character' and index==0 and state.get('recovery'):
        save(out/'proposal.json',{'character':character,'observable_proposal':'Recovered scene already exists; no new actions proposed.','state_version':state['version']});return
    if task == 'character' and req.get('performance',{}).get('pipelined_living') and not req.get('performance',{}).get('model_character_proposals',False):
        data=actor_packet(req,state,card,character)
        from .canon import bridge
        author={m['id']:m for m in bridge(state)['facts']}
        known=[{'fact_id':m['id'],'source':'prior_canon.facts'} if m.get('id') in author and m==author[m['id']] else m for m in data['known_facts']]
        save(out/'proposal.json',{'character':character,'state_version':state['version'],'method':'source_bound_character_context_no_inference','observable_proposal':'Use this authored character profile and knowledge allowlist to choose a tactic; no action is precommitted and no new fact is asserted.','character_profile':data['character'],'known_facts':known,'knowledge_policy':'Resolve fact_id only against prior_canon.facts. Listed historical facts remain this character’s beliefs; other author facts are not shared knowledge.'})
        return
    if task == 'character':
        result = executor.call('character', actor_packet(req, state, card, character), 'Propose one observable action or spoken line pursuing your goal in this situation. Use only known facts. Do not disclose private reasoning or secrets as commentary.', tokens=220)
        save(out / 'proposal.json', {'character': character, 'observable_proposal': result, 'state_version': state['version']})
        return
    if task == 'director':
        proposals = [load(p) for p in sorted((source / 'characters').rglob('proposal.json'))]
        contracts.require(len(proposals) == len(card['participants']) and {p['character'] for p in proposals} == set(card['participants']), 'Missing/duplicate character proposals')
        contracts.require(all(p['state_version'] == state['version'] for p in proposals), 'Stale character proposal')
        if req.get('performance',{}).get('combine_direction'):
            save(out/'direction.txt',json.dumps({'scene':card,'observable_proposals':proposals}));event('direction','Reusing scene design and character proposals; no extra director call');return
        result = executor.call('director', {'scene_context': scene_packet, 'proposals': proposals}, 'Propose 3–5 concise beats. Respect POV, knowledge, rules, and intended change. Proposals are optional and are not canon.', tokens=500)
        save(out / 'direction.txt', result)
        return
    if task=='writer' and str(index) in state.get('continuation_drafts',{}):
        save(out/'draft.txt',state['continuation_drafts'][str(index)]);event('recovery','Reusing already generated scene draft');return
    if task=='writer' and index==0 and state.get('recovery'):
        save(out/'draft.txt',state['recovery']['prose']);event('recovery','Recovered existing scene 1 prose; no drafting call');return
    if task == 'writer':
        scene_packet['direction'] = (source / 'direction/direction.txt').read_text()
        from .craft import validate_prose
        check=(lambda text:validate_prose(text,req,check_length=backend!='fixture')) if req.get('performance',{}).get('validate_scene_prose') else None
        result = executor.call('writer', scene_packet, 'Write complete scene prose at target_words. Use the selected medium format; no summary, commentary, or canon delta. Respect POV, knowledge, rules, and voices. Develop attempted action, resistance, a costly choice and its aftermath in specific detail.', tokens=budget,skill=(ROOT/'skills/distinct_writing.md').read_text(),validator=check,output_format='text')
        save(out / 'draft.txt', result)
        return
    if task == 'edit_plan':
        from .fast_edit import batches
        prose=(source/'draft/draft.txt').read_text()
        plan=batches(prose)
        contracts.require(bool(plan),'Cannot edit empty draft')
        save(out/'batches.json',plan);save(out/'draft.txt',prose)
        output('characters',[b['id'] for b in plan]);return
    if task == 'edit_batch':
        from .fast_edit import validate, schema
        batch=next(b for b in load(source/'edit-plan/batches.json') if b['id']==character)
        try:
            result=({'replacements':{}} if backend=='fixture' else executor.call('humanizer',{'owned_paragraphs':batch['owned'],'passages':batch['passages'],
                'scene':card,'style':req['style'],'world_rules':req['world_rules'],
                'pov_character':next(c for c in req['characters'] if c['id']==card['pov'])},
                'In one pass edit prose, rhetoric and distinct writing. Return JSON replacements only for owned paragraphs needing changes; empty replacements if none. Neighbors are read-only. Preserve events, knowledge, chronology, deliberate epic register and approximate length. Do not invent facts or explain obvious actions.',
                tokens=1800,validator=lambda x:validate(x,batch),response_schema=schema(batch),skill=(ROOT/'skills/distinct_writing.md').read_text()))
        except Exception as exc:
            if not enabled(req):raise
            warning(out,'passage_editor_unavailable',exc);result={'replacements':{},'unverified':True}
        save(out/'batch.json',{**result,'id':batch['id'],'source_sha256':batch['source_sha256']});return
    if task == 'edit_merge':
        from .fast_edit import merge
        prose=(source/'edit-plan/draft.txt').read_text()
        results=[load(p) for p in (source/'batches').rglob('batch.json')]
        revised=merge(prose,load(source/'edit-plan/batches.json'),results)
        save(out/'prose.txt',revised)
        save(out/'repair.json',{'changed':False,'reviewed_sha256':hashlib.sha256(revised.encode()).hexdigest(),'candidate_sha256':hashlib.sha256(revised.encode()).hexdigest()})
        save(out/'edit-report.json',{'batches':results,'source_sha256':hashlib.sha256(prose.encode()).hexdigest(),'final_sha256':hashlib.sha256(revised.encode()).hexdigest()})
        for result in results:
            if result.get('unverified'):warning(out,'passage_edit_skipped','Batch '+result['id']+' retained original prose; full-scene review still required.')
        return
    if task == 'edit':
        draft = (source / 'draft/draft.txt').read_text()
        if req.get('performance',{}).get('targeted_edits'):
            save(out/'prose.txt',draft);event('edit','Full-scene rewrite skipped; parallel reviewers will propose targeted fixes');return
        result = executor.call('humanizer', {'context':{k:scene_packet[k] for k in ['scene','characters','pov_profile','pov_visible_memory','recent_ending','style_and_controls']},'style':req['style'],'world_rules':req['world_rules'],'genre':req.get('genre'),'prose': draft, 'craft':application_packet(req,state['retrieval'],'humanizer',card['id'])}, 'Edit only what needs improvement. Preserve events, evidence, knowledge, POV, deliberate style, and approximate length. Return complete prose alone.', tokens=budget, skill=(ROOT / 'skills/distinct_writing.md').read_text())
        save(out / 'prose.txt', result)
        return
    if task == 'repair':
        prose = (source / 'edited/prose.txt').read_text()
        story_verdict=load(source / 'diagnosis/review.json');rhetoric_verdict=load(source / 'rhetoric/review.json')
        review = merge_reviews(story_verdict,rhetoric_verdict)
        from .adjudication import enabled as settle_once,decide
        if settle_once(req) and not review['pass']:
            final=decide(req,state,card,prose,[story_verdict,rhetoric_verdict],out,backend)
            save(out/'prose.txt',prose)
            save(out/'repair.json',{'changed':False,'reviewed_sha256':hashlib.sha256(prose.encode()).hexdigest(),'candidate_sha256':hashlib.sha256(prose.encode()).hexdigest(),'editorial_adjudication':final,'further_editorial_iteration':False})
            event('editorial_settled','One strict final check completed; no further editorial repair loop',passed=final['verdict']['pass'],unverified=final['unverified'])
            return
        changed = not review['pass'] and req['max_repairs'] > 0
        before = hashlib.sha256(prose.encode()).hexdigest()
        event('repair_decision','Repair required' if changed else 'Prose unchanged; forwarding existing candidate',issues=len(review['issues']))
        patch_info={}
        if changed and req.get('performance',{}).get('targeted_edits'):
            try:prose,patch_info=patch_repair(executor,req,prose,[review])
            except Exception as exc:
                if not enabled(req):raise
                warning(out,'patch_unavailable',exc)
            changed=hashlib.sha256(prose.encode()).hexdigest()!=before
        elif changed:
            prose = executor.call('writer', {'context': scene_packet, 'prose': prose, 'review': review},
                'Repair the cited violations. Preserve unaffected facts and deliberate voice. Return complete scene prose near target_words, with no commentary.', tokens=budget, skill=(ROOT / 'skills/distinct_writing.md').read_text())
        save(out / 'prose.txt', prose)
        save(out / 'repair.json', {'changed': changed, 'reviewed_sha256': before, 'candidate_sha256': hashlib.sha256(prose.encode()).hexdigest(),'patches':patch_info})
        return
    if task in {'rhetoric_review','verify_rhetoric'}:
        prose=(source/'edited/prose.txt').read_text()
        if task=='rhetoric_review' and index==0 and state.get('recovery') and prose==state['recovery']['prose']:
            save(out/'review.json',state['recovery']['reviews']['rhetoric']);event('recovery','Reusing source-matched rhetoric review and its unresolved issues');return
        if task=='verify_rhetoric' and not load(source/'edited/repair.json')['changed']:
            repair=load(source/'edited/repair.json')
            contracts.require(hashlib.sha256(prose.encode()).hexdigest()==repair['reviewed_sha256'],'Cannot reuse rhetoric review after prose changes')
            final=repair.get('editorial_adjudication')
            verdict=safe_review(final['rhetoric'] if final else load(source/'rhetoric/review.json'),prose,RHETORIC_CHECKS,req)
        else:
            verdict=executor.call('rhetoric_quality',{**evidence_payload(prose),'required_checks':RHETORIC_CHECKS,'creative_controls':controls(req),'previous_scene':state['accepted'][-1]['prose'][-3500:] if state['accepted'] else '', 'signals':rhetoric_signals(prose),'craft':application_packet(req,state['retrieval'],'rhetoric_quality',card['id'])},'Review the complete scene in evidence_passages. Return the required editorial JSON.',tokens=1600,validator=lambda x:editorial_review(x,prose,RHETORIC_CHECKS),skill=(ROOT/'skills/rhetoric_quality.md').read_text())
        verdict=apply_signals(verdict,rhetoric_signals(prose))
        save(out/'review.json',verdict)
        return
    if task in {'story_review', 'verify', 'memory', 'memory_final'}:
        prose = (source / 'edited/prose.txt').read_text()
        if task=='story_review' and index==0 and state.get('recovery') and prose==state['recovery']['prose']:
            save(out/'review.json',state['recovery']['reviews']['story']);event('recovery','Reusing source-matched story review and its unresolved issues');return
        if task in {'verify', 'memory_final'}:
            repair = load(source / 'edited/repair.json')
            contracts.require(hashlib.sha256(prose.encode()).hexdigest() == repair['candidate_sha256'], 'Candidate hash mismatch')
            if not repair['changed']:
                contracts.require(repair['candidate_sha256'] == repair['reviewed_sha256'], 'Cannot reuse review after prose changes')
                if task == 'verify':
                    final=repair.get('editorial_adjudication')
                    save(out / 'review.json', safe_review(final['story'] if final else load(source / 'diagnosis/review.json'), prose,STORY_CHECKS,req))
                else:
                    save(out / 'memory.json', contracts.delta(load(source / 'initial-memory/memory.json'), prose, [c['id'] for c in req['characters']]))
                return
        if task in {'story_review', 'verify'}:
            verdict=executor.call('story_quality',{**evidence_payload(prose),'required_checks':STORY_CHECKS,'scene':card,'creative_controls':{k:v for k,v in controls(req).items() if k!='style'},'world':req['world_design'],'plot':req['plot_design'],'characters':[c for c in req['characters'] if c['id'] in card['participants']],'world_rules':req['world_rules'],'initial_facts':req['initial_facts'],'accepted_memories':compact(state['memories'],36),'previous_scene':{'id':state['accepted'][-1]['id'],'quality_status':state['accepted'][-1].get('quality_status'),'canon_committed':state['accepted'][-1].get('canon_committed',True)} if state['accepted'] else None,'craft':application_packet(req,state['retrieval'],'story_quality',card['id'])},
                'Assess the complete scene in evidence_passages against accepted knowledge and the user brief. Return the required editorial JSON.',tokens=1600,validator=lambda x:editorial_review(x,prose,STORY_CHECKS),skill=quality_skill)
            words = len(prose.split())
            if backend != 'fixture' and req['length_policy']['scene_words']=='strict' and not req['words_per_scene'] * req['min_words_ratio'] <= words <= req['words_per_scene'] * req['max_words_ratio']:
                verdict['pass'] = False
                verdict['issues'].append({'severity': 'blocking', 'category': 'length', 'quote': prose[:80], 'problem': f'{words} words outside target tolerance', 'fix': f'Return a complete scene near {req["words_per_scene"]} words.'})
            save(out / 'review.json', verdict)
        else:
            result = memory_extract(executor,req,out,prose,{**evidence_payload(prose),'scene':card,'characters':[c['id'] for c in req['characters']],'existing':compact(state['memories']),**(recording_context(state,card) if req.get('performance',{}).get('canon_index') else {})},MEMORY_INSTRUCTION)
            save(out / 'memory.json', result)
        return
    if task == 'memory_review':
        prose = (source / 'edited/prose.txt').read_text()
        verdict = executor.call('memory_quality', {'current_prose': prose, 'proposed_memory': load(source / 'memory/memory.json'), 'prior_memory': (recording_context(state,card) if req.get('performance',{}).get('canon_index') else compact(state['memories'],36))}, 'Check proposed_memory for unsupported inference, contradiction, false knowledge acquisition, or belief/claim presented as fact. Return required review JSON with quotations from current_prose.', tokens=1200, validator=lambda x: contracts.review(x, prose), skill=(ROOT/'skills/memory_quality.md').read_text())
        save(out / 'review.json', verdict)
        return
    if task == 'accept':
        contracts.require(len(state['accepted']) == index, 'Commit does not follow accepted scene order')
        review = load(source / 'story-review/review.json')
        memory_review = load(source / 'memory-review/review.json')
        rhetoric_review=safe_review(load(source/'rhetoric-review/review.json'),(source/'edited/prose.txt').read_text(),RHETORIC_CHECKS,req)
        review=safe_review(review,(source/'edited/prose.txt').read_text(),STORY_CHECKS,req)
        save(out / 'reviews.json', {'story': review, 'rhetoric':rhetoric_review, 'memory': memory_review})
        event('acceptance','Checking story, rhetoric and memory gates',story=review['pass'],rhetoric=rhetoric_review['pass'],memory=memory_review['pass'])
        from .adjudication import enabled as settle_once,decide,chapter_text,digest as source_digest
        final=load(source/'edited/repair.json').get('editorial_adjudication') if (source/'edited/repair.json').exists() else None
        prose=(source/'edited/prose.txt').read_text()
        if settle_once(req) and not final and not (review['pass'] and rhetoric_review['pass'] and memory_review['pass']):
            final=decide(req,state,card,prose,[review,rhetoric_review,memory_review],out,backend)
            review,rhetoric_review=final['story'],final['rhetoric']
        if final:
            contracts.require(final['prose_sha256']==source_digest(prose),'Final adjudication targets stale prose')
            save(out/'editorial-adjudication.json',final)
        move_on=settle_once(req) and final is not None
        unresolved=not (review['pass'] and rhetoric_review['pass'] and memory_review['pass'])
        if unresolved and move_on:
            warning(out,'final_editorial_decision','Final check did not verify all requirements. Preserve this provisional scene, withhold its canon updates, and continue without another editorial loop.')
        elif unresolved and enabled(req):warning(out,'provisional_scene','Quality or verification remains unresolved; retaining an explicitly provisional draft.')
        else:contracts.require(not unresolved, 'Review rejected scene or memory; no canon commit. Inspect saved review artifacts.')
        prose = (source / 'edited/prose.txt').read_text()
        memory = contracts.delta(load(source / 'memory/memory.json'), prose, [c['id'] for c in req['characters']])
        final_patch=None
        if unresolved and enabled(req) and not move_on and req.get('performance',{}).get('targeted_edits') and not req.get('performance',{}).get('single_editorial_pass'):
            try:
                revised,final_patch=patch_repair(executor,req,prose,[review,rhetoric_review])
                if revised!=prose:
                    reviewed_hash=hashlib.sha256(prose.encode()).hexdigest();prose=revised
                    for verdict in [review,rhetoric_review]:verdict['reviewed_prose_sha256']=reviewed_hash;verdict['post_review_patch']=True
                    save(out/'final-prose.txt',prose)
                    memory=memory_extract(executor,req,out,prose,{**evidence_payload(prose),'scene':card,'characters':[c['id'] for c in req['characters']],'existing':compact(state['memories']),**(recording_context(state,card) if req.get('performance',{}).get('canon_index') else {})},MEMORY_INSTRUCTION)
                    memory_review=executor.call('memory_quality',{'current_prose':prose,'proposed_memory':memory,'prior_memory':compact(state['memories'])},'Check supported facts and knowledge holders; return pass and issues with exact source quotations.',tokens=900,validator=lambda x:contracts.review(x,prose),skill=(ROOT/'skills/memory_quality.md').read_text())
                    warning(out,'final_targeted_edit','Final cited issues patched; literary re-verification remains pending and the draft is provisional.')
            except Exception as exc:warning(out,'final_patch_unavailable',exc)
        save(out/'final-edit.json',{'patch':final_patch,'quality_reverification_pending':bool(final_patch and final_patch.get('changed'))})
        save(out/'reviews.json',{'story':review,'rhetoric':rhetoric_review,'memory':memory_review})
        if enabled(req) and (memory.get('quarantined') or memory.get('fallback')):
            unresolved=True;warning(out,'memory_incomplete','Some memory could not be safely extracted; consult source prose.')
        memory_status={'quarantined_count':len(memory.get('quarantined',[])),'fallback':memory.get('fallback'),'verified':memory_review['pass']}
        if not memory_review['pass'] and enabled(req):
            save(out/'quarantined-memory.json',memory);memory={'memories':[]};warning(out,'memory_quarantine','Memory verifier did not approve extracted facts; prose retained, facts withheld.')
        if (index + 1) % req['scenes_per_chapter'] == 0:
            chapter_prose = '\n\n'.join([s['prose'] for s in state['accepted'] if s['chapter'] == card['chapter']] + [prose])
            if final:
                contracts.require(final['chapter_sha256']==source_digest(chapter_prose),'Final adjudication targets stale chapter; no second debate')
                chapter_review=final['story']
            else:
                chapter_review=executor.call('chapter_quality',{**evidence_payload(chapter_prose),'required_checks':STORY_CHECKS,'chapter':card['chapter'],'rules':req['world_rules'],'chapter_plan':[s for s in state['plan']['scenes'] if s['chapter']==card['chapter']], 'nonnegotiable_form':req.get('pov'), 'quality_contract':req.get('quality_contract',[]), 'chapter_contract':req.get('chapter_contract',{}), 'creative_controls':controls(req)},'Review the full chapter in evidence_passages under the author form and chapter contract. For a no-dialogue brief, assess dialogue_tactics through narrated offers, refusals, commitments and leverage; absence of quoted speech is not itself a defect. Never propose direct dialogue against the brief. Other causal or character failures still need concrete evidence. Return editorial JSON.',tokens=1600,validator=lambda x:editorial_review(x,chapter_prose,STORY_CHECKS),skill=quality_skill)
            save(out / 'chapter-review.json', chapter_review)
            if not chapter_review['pass'] and settle_once(req) and not final:
                final=decide(req,state,card,prose,[review,rhetoric_review,chapter_review],out,backend)
                review,rhetoric_review=final['story'],final['rhetoric'];chapter_review=final['story'];move_on=True
                save(out/'editorial-adjudication.json',final);save(out/'chapter-review.json',chapter_review)
                unresolved=not (review['pass'] and rhetoric_review['pass'] and memory_review['pass'])
            if (not chapter_review['pass'] or unresolved) and move_on:
                unresolved=True;warning(out,'provisional_final_decision','Strict check finished; retain draft without canon updates or further debate.')
            elif not chapter_review['pass'] and enabled(req):
                unresolved=True;warning(out,'chapter_needs_review','Chapter audit did not pass; exported as provisional draft.')
            else:contracts.require(chapter_review['pass'], 'Chapter review rejected; no final scene commit')
        save(out/'reviews.json',{'story':review,'rhetoric':rhetoric_review,'memory':memory_review})
        canon_allowed=not unresolved and all(s.get('canon_committed',True) for s in state['accepted'])
        if not canon_allowed and (move_on or settle_once(req)):
            save(out/'withheld-memory.json',memory);memory={'memories':[]}
        result = copy.deepcopy(state)
        result['version'] += 1
        result['accepted'].append({'id': card['id'], 'chapter': card['chapter'], 'pov': card['pov'], 'participants': card['participants'], 'prose': prose, 'review': review, 'rhetoric_review':rhetoric_review, 'memory_review': memory_review, 'reference_uses':card.get('reference_uses',[]), 'state_version': result['version'],'quality_status':'needs_review' if unresolved else 'reviewed','memory_extraction':memory_status,'canon_committed':canon_allowed})
        summary_path=source/'edited/scene-summary.json'
        if summary_path.exists():
            summary=load(summary_path)
            contracts.require(summary['source_sha256']==source_digest(prose),'Stale accepted scene summary')
            result['accepted'][-1]['source_summary']=summary
        if req.get('performance',{}).get('canon_index'):
            from .canon import append,index as canon_index
            result.setdefault('canon',canon_index(result['memories']))
            if canon_allowed or not settle_once(req):
                append(result,memory['memories'],f'episode-{state["universe_episode"]:06}/'+card['id'] if state.get('universe_episode') else card['id'])
            save(out/'canon.json',result['canon'])
        else:result['memories'].extend(dict(m, source=card['id']) for m in memory['memories'])
        if not canon_allowed and req.get('performance',{}).get('verified_draft_continuity') and memory_review.get('pass') and not memory_review.get('unverified') and memory_review.get('source_sha256')==source_digest(prose) and memory_review.get('memory_sha256') and not memory.get('unverified'):
            from .continuation import append_verified_branch
            from .batch_pipeline import bind_state as continuity_binding
            branch_memory=load(source/'memory/memory.json')
            if not branch_memory.get('unverified'):
                append_verified_branch(result,branch_memory,card['id'],prose,memory_review,expected_state_sha256=continuity_binding(state))
                save(out/'draft-continuity.json',{'scope':'draft_branch','memory_verified':True,'literary_approved':False,'facts':result['draft_memories']})
        result['complete'] = len(result['accepted']) == len(result['plan']['scenes'])
        result['completion_status']='complete_with_warnings' if result['complete'] and any(s.get('quality_status')=='needs_review' for s in result['accepted']) else ('complete' if result['complete'] else 'in_progress')
        if canon_allowed:
            for c in result['request']['characters']:
                if c.get('cast_status')=='proposed' and c['id'] in card['participants']:c['cast_status']='introduced'
        result['request_hash']=hashlib.sha256(json.dumps(result['request'],sort_keys=True).encode()).hexdigest()
        save(out / 'snapshot.json', result)
        export(out, result, result['request'])
        event('draft_retained' if not canon_allowed and settle_once(req) else 'canon_committed','Scene checkpoint saved'+(' — provisional draft' if unresolved else ' — reviewed'),scene=card['id'],quality_status='needs_review' if unresolved else 'reviewed',words=len(prose.split()),accepted_scenes=len(result['accepted']),state_version=result['version'])
        output('characters', result['plan']['scenes'][index + 1]['participants'] if not result['complete'] else [])
        return result
    raise ValueError(f'Unknown DAG task: {task}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('task')
    parser.add_argument('--source', default='inputs')
    parser.add_argument('--out', default='out')
    parser.add_argument('--index', type=int, default=0)
    parser.add_argument('--character')
    parser.add_argument('--request-file', default='silent-bell-full')
    parser.add_argument('--profile', default='balanced')
    parser.add_argument('--backend', choices=['fixture', 'worker'], default='fixture')
    args = parser.parse_args()
    stage(args.task, args.source, args.out, args.index, args.character, args.request_file, args.profile, args.backend)

if __name__ == '__main__':
    main()
