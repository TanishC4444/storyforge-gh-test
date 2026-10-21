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
        facts=working(state,cid,query=json.dumps(card))['facts']
    return {'character': next(c for c in req['characters'] if c['id'] == cid),
            'situation': {'location': card['location'], 'time': card['time']},
            'known_facts': facts, 'knowledge_policy':'Use only supported known facts; author world rules and future scene outcomes are not character knowledge.'}


def safe_review(value,prose,required,req):
    if value.get('unverified') and enabled(req):return value
    return editorial_review(value,prose,required)


@tracked_stage
def stage(task, source, out, index=0, character=None, request_file='silent-bell-full', profile='balanced', backend='fixture'):
    source, out = Path(source), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if task == 'prepare':
        req = contracts.request(load(ROOT / 'examples' / f'{request_file}.json'))
        req['profile'] = profile
        contracts.require(req['chapters'] * req['scenes_per_chapter'] <= 9, 'This workflow supports at most nine scene slots')
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
                 'memories': [dict(f, kind='event', source='user_input') for f in req['initial_facts']],
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
        old=state['plan']['scenes'][index]
        if req.get('performance',{}).get('single_editorial_pass'):
            save(out/'scene-design.json',old);save(out/'snapshot.json',state);output('characters',old['participants']);event('design','Using approved scene card; writer reconciles with latest accepted canon');return state
        if index==0 and state.get('recovery'):
            save(out/'scene-design.json',old);save(out/'snapshot.json',state);output('characters',old['participants']);return state
        designed=executor.call('scene_designer',{'request_controls':controls(req),'world':req['world_design'],'plot':req['plot_design'],'characters':req['characters'],'proposed_scene':old,'accepted_memory':compact(state['memories'],36),'previous_scene':{'id':state['accepted'][-1]['id'],'prose_excerpt':state['accepted'][-1]['prose'][-4500:]} if state['accepted'] else None,'user_scene_design':[s for s in req['scene_designs'] if s['id']==old['id']],'inspiration':application_packet(req,state['retrieval'],'scene_designer',old['id'])},
            'Reconcile the proposed scene with what ACTUALLY happened. Do not rediscover an established fact. Preserve IDs, chapter, valid participant IDs, world rules, and user choices. Return one JSON scene card with id, chapter, pov, participants, location, time, goal, obstacle, intended_change, choice, consequence, new_development, and reference_uses (array of {record_id,application}). Explain development through a new tactic, cost, commitment, leverage, or interpretation, not stronger adjectives. No new events become canon here.',
            tokens=1600,validator=lambda x:validate_scene(x,req,index))
        allowed={r['id'] for r in application_packet(req,state['retrieval'],'scene_designer',old['id'])['references']}
        contracts.require(all(isinstance(r,dict) and r.get('record_id') in allowed for r in designed['reference_uses']),'Scene reference outside applicable source packet')
        state['plan']['scenes'][index]=designed
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
        result = executor.call('writer', scene_packet, 'Write complete scene prose at target_words. No summary, heading, commentary, or canon delta. Respect POV, knowledge, rules, and voices. Give choices consequences.', tokens=budget,skill=(ROOT/'skills/distinct_writing.md').read_text())
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
        review = merge_reviews(load(source / 'diagnosis/review.json'),load(source / 'rhetoric/review.json'))
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
            verdict=safe_review(load(source/'rhetoric/review.json'),prose,RHETORIC_CHECKS,req)
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
                    save(out / 'review.json', safe_review(load(source / 'diagnosis/review.json'), prose,STORY_CHECKS,req))
                else:
                    save(out / 'memory.json', contracts.delta(load(source / 'initial-memory/memory.json'), prose, [c['id'] for c in req['characters']]))
                return
        if task in {'story_review', 'verify'}:
            verdict=executor.call('story_quality',{**evidence_payload(prose),'required_checks':STORY_CHECKS,'scene':card,'creative_controls':{k:v for k,v in controls(req).items() if k!='style'},'world':req['world_design'],'plot':req['plot_design'],'characters':[c for c in req['characters'] if c['id'] in card['participants']],'world_rules':req['world_rules'],'initial_facts':req['initial_facts'],'accepted_memories':compact(state['memories'],36),'previous_scene':{'id':state['accepted'][-1]['id'],'prose_excerpt':state['accepted'][-1]['prose'][-4500:]} if state['accepted'] else None,'craft':application_packet(req,state['retrieval'],'story_quality',card['id'])},
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
        unresolved=not (review['pass'] and rhetoric_review['pass'] and memory_review['pass'])
        if unresolved and enabled(req):warning(out,'provisional_scene','Quality or verification remains unresolved; retaining an explicitly provisional draft.')
        else:contracts.require(not unresolved, 'Review rejected scene or memory; no canon commit. Inspect saved review artifacts.')
        prose = (source / 'edited/prose.txt').read_text()
        memory = contracts.delta(load(source / 'memory/memory.json'), prose, [c['id'] for c in req['characters']])
        final_patch=None
        if unresolved and enabled(req) and req.get('performance',{}).get('targeted_edits') and not req.get('performance',{}).get('single_editorial_pass'):
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
            chapter_review=executor.call('chapter_quality',{**evidence_payload(chapter_prose),'required_checks':STORY_CHECKS,'chapter':card['chapter'],'rules':req['world_rules'],'chapter_plan':[s for s in state['plan']['scenes'] if s['chapter']==card['chapter']]},'Review the full chapter in evidence_passages. Return editorial JSON.',tokens=1600,validator=lambda x:editorial_review(x,chapter_prose,STORY_CHECKS),skill=quality_skill)
            save(out / 'chapter-review.json', chapter_review)
            if not chapter_review['pass'] and enabled(req):
                unresolved=True;warning(out,'chapter_needs_review','Chapter audit did not pass; exported as provisional draft.')
            else:contracts.require(chapter_review['pass'], 'Chapter review rejected; no final scene commit')
        result = copy.deepcopy(state)
        result['version'] += 1
        result['accepted'].append({'id': card['id'], 'chapter': card['chapter'], 'pov': card['pov'], 'participants': card['participants'], 'prose': prose, 'review': review, 'rhetoric_review':rhetoric_review, 'memory_review': memory_review, 'reference_uses':card.get('reference_uses',[]), 'state_version': result['version'],'quality_status':'needs_review' if unresolved else 'reviewed','memory_extraction':memory_status})
        if req.get('performance',{}).get('canon_index'):
            from .canon import append
            append(result,memory['memories'],card['id'])
            save(out/'canon.json',result['canon'])
        else:result['memories'].extend(dict(m, source=card['id']) for m in memory['memories'])
        result['complete'] = len(result['accepted']) == len(result['plan']['scenes'])
        result['completion_status']='complete_with_warnings' if result['complete'] and any(s.get('quality_status')=='needs_review' for s in result['accepted']) else ('complete' if result['complete'] else 'in_progress')
        save(out / 'snapshot.json', result)
        export(out, result, req)
        event('canon_committed','Scene checkpoint saved'+(' — provisional draft' if unresolved else ' — reviewed'),scene=card['id'],quality_status='needs_review' if unresolved else 'reviewed',words=len(prose.split()),accepted_scenes=len(result['accepted']),state_version=result['version'])
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
