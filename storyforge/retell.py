"""One coordinated hosted run, isolated role packets, durable checkpoints, CPU fallback."""
from __future__ import annotations
import argparse,copy,hashlib,json,time,re
from pathlib import Path
from . import contracts
from .inference import Executor,ROOT
from .storage import save,load
from .coordinator import PLAN_INSTRUCTION,planning_packet,compact,visible,MEMORY_INSTRUCTION
from .dag import REFINE
from .retrieval import application_packet
from .evidence import payload
from .resilience import memory_extract
from .narrative_gate import defects,change_metrics,rhetorical_signals

CORE='''Strict third-person past-tense narrative, no dialogue, no quoted speech, no invocation, no direct address. Preserve ancient social imagination, material causality and earned epic cadence. Every passage must perform a function: action, orientation, perception, characterization, tension, or an earned image. Do not announce feelings, significance, scene functions or moral lessons already clear from action. No summaries standing in for the promised scene. No-dialogue does not require silence or pantomime: briefly narrate offers, refusals and orders, then their physical consequences, without reproducing speeches or explaining meaningful looks. Keep one primary focal anchor, but an epic narrator may supply another character's history or inner attention in a clearly separated paragraph. Narratorial knowledge is never automatically available to characters; do not infer inner calculations merely from a look. No recycled gestures or replay of an earlier bargain or acquisition. Show resistance, a costly decision, and its actual consequence. Characters act differently under pressure, with mixed motives and imperfect knowledge. Build each scene around an attempted solution that meets specific resistance and changes the next available choice. Let a supporting relationship or obligation complicate that solution; carry its consequence into a later scene. Earn reversals through established actions rather than new accidents. Epic comparisons must sharpen a particular action, social relation or perception; ornamental archaism alone is insufficient. Vary pace: develop decisive choices in full, compress routine movement. No technical weapon construction instructions.'''
AUDIT='''Return JSON {"pass":boolean,"issues":[{"quote":exact short quote from candidate,"problem":string,"fix":specific change}],"scene_progression":string,"depth_assessment":string}. Third-person epic omniscience in separate paragraphs is permitted; distinguish that from characters acquiring private knowledge without evidence. Enforce every cast identity; Thestor the smith and the unnamed keeper are different people. Be skeptical. Fail for repetition, duplicated beats, unearned outcome, summary replacing action, generic emotional labels, explaining obvious acts, cosmetic ancient diction, failure of scene-specific goals, broken inventory, knowledge leak, or no-dialogue/third-person violations. Assess whether the focal character actually attempts a tactic, has a meaningful alternative, pays a particular cost and changes the material situation; passive reaction is not enough. Proposed fixes must not substitute stock body language for emotional labels. A claim that a review passed is not evidence of literary quality. Examine the actual complete prose. An issue must quote the candidate exactly. Do not fail just to satisfy an issue quota; do not praise vague themes as proof of depth.'''

def review(value,prose):
    contracts.require(isinstance(value,dict) and type(value.get('pass')) is bool and isinstance(value.get('issues'),list),'Invalid narrative audit')
    for issue in value['issues']:
        contracts.require(isinstance(issue,dict) and all(isinstance(issue.get(k),str) and issue[k].strip() for k in ['quote','problem','fix']),'Invalid narrative issue')
        if issue['quote'] not in prose:
            from .evidence import quote_span,EvidenceError
            try:
                start,end,_=quote_span(issue['quote'],prose);issue['quote']=prose[start:end]
            except EvidenceError:
                matches=list(re.finditer(re.escape(issue['quote']),prose,re.I))
                contracts.require(len(matches)==1,'Audit quote absent or ambiguous in candidate')
                issue['quote']=matches[0].group()
        contracts.require(issue['quote'] in prose,'Audit quote absent from candidate')
    contracts.require(not(value['pass'] and value['issues']),'Passing audit contains unresolved issues')
    return value

def run(folder,source,backend='worker',final_candidate=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    req=contracts.request(load(ROOT/'examples/troy-narrative-api.json'))
    source_path=Path(source)
    if not source_path.exists():source_path=ROOT/'recovery/troy-39512585096/snapshot.json'
    seed=load(source_path);retrieval=seed['retrieval']
    save(folder/'retrieval-provenance.json',{'mode':'replay_selected_classical_analysis','source':'run_artifact' if Path(source).exists() else 'committed_literary_cache','source_request_hash':seed.get('request_hash')})
    state_path=folder/'state.json'
    fingerprint=hashlib.sha256(json.dumps(req,sort_keys=True).encode()).hexdigest()
    state=load(state_path) if state_path.exists() else {'request_hash':fingerprint,'accepted':[],'memories':[dict(x,kind=x.get('kind','event'),source='user_input') for x in req['initial_facts']]}
    contracts.require(state['request_hash']==fingerprint,'Run brief changed; choose a new output directory')
    executor=Executor(req,folder,backend)
    skill_path=ROOT/'skills/distinct_writing.md'
    phase_clock=time.monotonic()
    previous_phase=None
    def status(phase):
        nonlocal phase_clock,previous_phase
        now=time.monotonic()
        if previous_phase is not None:
            with (folder/'phase-timings.jsonl').open('a') as timing:
                timing.write(json.dumps({'phase':previous_phase,'seconds':round(now-phase_clock,3),'ended_at':time.time()})+'\n')
        previous_phase=phase;phase_clock=now
        import os
        if os.getenv('GITHUB_ACTIONS')=='true':
            if getattr(status,'started',False):print('::endgroup::',flush=True)
            print('::group::'+phase,flush=True);status.started=True
            if os.getenv('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as summary:summary.write('\n- '+phase+' ('+str(len(state['accepted']))+'/4 scenes checkpointed)\n')
        save(folder/'progress.json',{'phase':phase,'accepted_scenes':len(state['accepted']),'total_scenes':4,'time':time.time()});print(phase,flush=True)
    def checkpoint():save(state_path,state)
    def prose_call(role,data,instruction,tokens=2200):
        data={'cast_registry':development['cast_registry'],**data}
        if isinstance(data,dict) and 'prose' in data:data={**data,'contextual_rhetoric_signals':rhetorical_signals(data['prose'])}
        if role=='humanizer':instruction+=' Reviewer fixes are suggestions, not commands: do not replace an emotional label with wide eyes, a tightened grip or another stock gesture. Repair the underlying function with a specific arrangement, material consequence, act of concealment, refusal or commitment. Keep necessary direct statements of emotion when earned. Make the focal character take a tactic with an alternative and a cost, rather than merely being moved around by a ruler.'
        return executor.call(role,data,CORE+'\n'+instruction,tokens=tokens,skill=skill_path.read_text())
    if 'refinement' not in state:
        status('Flash: refine the full creative brief')
        state['refinement']=executor.call('refiner',{'request':req,'inspiration':application_packet(req,retrieval,'refiner')},REFINE+'\n'+CORE+' Specify causal costs and distinct material developments for all four scenes, and avoid generic advice.',tokens=4000,validator=lambda x:contracts.refinement({**x,'original_prompt':req['premise'],'original_prompt_binding':'Application copies immutable user brief; raw model response retained in calls.'},req));checkpoint()
    if 'plan' not in state:
        status('Flash: outline four distinct causal scenes')
        state['plan']=executor.call('architect',{'premise':req['premise'],'world_rules':req['world_rules'],'characters':[{'id':c['id'],'goal':c['goal'],'arc':c['arc']} for c in req['characters']],'required_scenes':req['scene_designs'],'chapters':1,'scenes_per_chapter':4,'development':state['refinement']['central_conflict']},PLAN_INSTRUCTION+'\n'+CORE+' Include an exact finite inventory schedule inside scene intended_change: choose a fixed charge count at acquisition and track expenditures. Make journey, resistance, acquisition, trial, battle and aftermath actual action in their assigned scenes. Never stage acquisition again. Resolve the local conflict only; Hector and Achilles survive.',tokens=2200,validator=lambda x:contracts.plan(x,req));checkpoint()
    development=load(ROOT/'examples/troy-development-notes.json')
    if not state.get('development_overlay'):
        contracts.require(not state['accepted'],'Development overlay must precede accepted canon')
        for j,scene in enumerate(state['plan']['scenes']):
            scene['intended_change']=development['scenes'][j]['change']
        state['plan']['scenes'][0]['goal']='Secure passage for Meles with completed ship repairs and a deliberately revealed cult-marked fragment.'
        state['plan']['scenes'][1]['obstacle']='The keeper demands return of a specific sacred basin now held by Agamemnon; Odysseus risks his personal seal and standing to pledge restitution.'
        state['plan']['scenes'][2]['goal']='Make command share the exposure of the operators and secure a concrete protection bargain without surrendering martial standing.'
        state['plan']['scenes'][2]['time']='Midday after the expedition returns, before the Trojan advance'
        state['plan']['threads']=['Meles and Thestor: grain, passage, apprenticeship and bodily cost','Odysseus: his surrendered seal and the stolen sacred basin','Achilles: martial standing and the operators entrusted to him','Finite cache: six tubes and 24 charges after demonstration; 23 after trial; five usable tubes and 19 charges after battle']
        state['development_overlay']=development;checkpoint()
    for i,card in enumerate(state['plan']['scenes']):
        if len(state['accepted'])>i:continue
        sf=folder/'scenes'/f'{i+1:02}';sf.mkdir(parents=True,exist_ok=True)
        expected=req['scene_designs'][i]
        cast=[{**c,'role_identity':development['cast_registry'][c['id']]} for c in req['characters'] if c['id'] in card['participants']]
        from .character_proposals import propose
        status('Scene '+str(i+1)+': concurrent isolated character proposals')
        proposals=propose(executor,req,state,card,expected['setting'],cast)
        context={'development_notes':development['scenes'][i],'material_register':development['recurring_details'],'scene':card,'required_scene':expected,'characters':[{k:c.get(k) for k in ['id','name','role_identity','goal','value','fear','arc','contradiction']} for c in cast],'proposals':proposals,'world_rules':req['world_rules'],'style':req['style'],'literary_mechanisms':application_packet(req,retrieval,'writer',card['id']),
                 'author_record':[{'id':x['id'],'ending':x['prose'][-1000:],'continuity':x['continuity']} for x in state['accepted']],
                 'knowledge_boundaries':compact(state['memories']),'target_words':850}
        status('Scene '+str(i+1)+(': Gemma first draft' if i==0 else ': combined writer and structural editor'))
        draft='' if i>0 else (sf/'draft.txt').read_text() if (sf/'draft.txt').exists() else prose_call('writer',context,'Write one complete 750–1000 word scene. No headings, labels, commentary, or outline. Begin where the previous accepted scene leaves the material situation; do not recap it. End on an action that causes the next scene. For the final scene show a developed local climax and aftermath.',2600)
        if i==0:save(sf/'draft.txt',draft)
        status('Scene '+str(i+1)+': restrained revision experiment')
        light=draft if i>0 else ((sf/'restrained.txt').read_text() if (sf/'restrained.txt').exists() else prose_call('humanizer',{'prose':draft,'scene':card,'style':req['style']},'Restrained revision: remove redundant explanation, stock gestures, repetitions and vague imagery; preserve causal structure and substantive length. Return the full scene only.',2600))
        if i==0:save(sf/'restrained.txt',light)
        status('Scene '+str(i+1)+': deep revision experiment')
        deep=(sf/'deep.txt').read_text() if (sf/'deep.txt').exists() else prose_call('humanizer',{'literary_mechanisms':{k:v for k,v in application_packet(req,retrieval,'humanizer',card['id']).items() if k!='craft'},'character_proposals':proposals,'focal_character':next(c for c in cast if c['id']==card['pov']),'development_notes':development['scenes'][i],'material_register':development['recurring_details'],'source_event_summary':card['intended_change'],'style':req['style'],'prior_draft_faults':rhetorical_signals(draft),'brief':{'scene':card,'requirements':expected,'accepted_memory':compact(state['memories'],36),'prior_material_state':[x['continuity'] for x in state['accepted']],'world_rules':req['world_rules']},'mechanical_defects':defects(draft,'\n'.join(x['prose'] for x in state['accepted'])) if draft else []},'Write a complete new scene directly from these developed events and character proposals, applying the distinct-writing guidance as the prose is composed. Build resistance and decisions. Briefly narrate offers and refusals instead of pantomime. Do not copy phrasing from earlier scenes. Develop omitted action rather than summarizing it. Make details specific to the focal character and their obligations. Preserve established canon and required events, but allow meaningful structural change. Remove repeated beats. Return a complete 750–1000 word scene, no headings or explanation.',2200)
        save(sf/'deep.txt',deep)
        candidates={'restrained':light,'deep':deep} if i==0 else {'deep':deep}
        # Both candidates are audited; edit distance is diagnostic, never the selection score.
        audits={}
        for name,text in candidates.items():
            status('Scene '+str(i+1)+': evaluate '+name+' candidate')
            audits[name]=executor.call('story_quality',{'candidate':text,'cast_registry':development['cast_registry'],'contextual_rhetoric_signals':rhetorical_signals(text),'scene_requirements':expected,'scene':card,'prior_material_state':[x['continuity'] for x in state['accepted']],'world_rules':req['world_rules'],'mechanical_defects':defects(text)},AUDIT,tokens=1500,validator=lambda x,t=text:review(x,t))
        clean=[name for name in candidates if audits[name]['pass'] and not defects(candidates[name])]
        selected='deep' if 'deep' in clean else ('restrained' if 'restrained' in clean else min(candidates,key=lambda n:len(audits[n]['issues'])+len(defects(candidates[n]))))
        prose=candidates[selected];audit=audits[selected]
        repairs=[]
        for attempt in range(2):
            problems=defects(prose,'\n'.join(x['prose'] for x in state['accepted']))
            if audit['pass'] and not problems:break
            status('Scene '+str(i+1)+': repair concrete faults '+str(attempt+1))
            revised=prose_call('humanizer',{'prose':prose,'scene_requirements':expected,'context':{'scene':card,'prior_material_state':[x['continuity'] for x in state['accepted']],'world_rules':req['world_rules']},'review':audit,'blocking_mechanical_faults':problems},'Repair every cited fault, developing missing causal action as needed. Do not shrink the scene into summary. Preserve continuity, concrete cost and third-person no-dialogue form. Return complete scene prose only.',2200)
            repairs.append(change_metrics(prose,revised));prose=revised
            audit=executor.call('story_quality',{'candidate':prose,'cast_registry':development['cast_registry'],'contextual_rhetoric_signals':rhetorical_signals(prose),'scene_requirements':expected,'previous_material_state':[x['continuity'] for x in state['accepted']],'world_rules':req['world_rules'],'mechanical_defects':defects(prose)},AUDIT,tokens=1500,validator=lambda x:review(x,prose))
        save(sf/'reviewed-candidate.txt',prose)
        save(sf/'comparison.json',{'guidance_sha256':hashlib.sha256(skill_path.read_bytes()).hexdigest(),'selected':selected,'mode':'revision_comparison' if i==0 else 'combined_authoring','restrained':change_metrics(draft,light) if i==0 else None,'deep':change_metrics(draft,deep) if i==0 else None,'audits':audits,'repair_changes':repairs,'final_review':audit,'mechanical_faults':defects(prose)})
        contracts.require(not defects(prose),'Mechanical prose gate failed; candidate retained, no final export')
        contracts.require(audit['pass'],'Scene quality gate failed; candidate retained, no final export')
        save(sf/'accepted.txt',prose)
        status('Scene '+str(i+1)+': extract source-bound continuity')
        memory=memory_extract(executor,req,sf,prose,{**payload(prose),'characters':[c['id'] for c in req['characters']],'existing':compact(state['memories'])},MEMORY_INSTRUCTION+' For this run public is forbidden: use only explicitly supported character witness IDs. A Greek council does not make its facts known to Hector.',allow_public=False)
        # Keep uncertain memory out of actor knowledge; full prose remains authoritative author record.
        save(sf/'memory.json',memory)
        from .output_schema import continuity_schema
        from .continuity import validate as validate_continuity,source_notes,reconcile
        continuity=executor.call('memory_quality',{'prose':prose,'memory_count':len(memory['memories']),'proposed_memories':memory['memories'],'prior_material_state':[x['continuity'] for x in state['accepted']]},'Return a short JSON author ledger with location, elapsed_time, weapon_custody, charges_remaining, charges_used_this_scene, obligations, irreversible_changes, and approved_memory_indices (zero-based memory entries, never paragraph numbers; empty if memory_count is zero). Approve a memory ONLY if its fact and every knowledge holder are explicitly supported in current prose; quarantine uncertain knowledge. Use explicit facts; unknown ledger values null. This ledger is author continuity, not knowledge automatically given to characters.',tokens=700,response_schema=continuity_schema(len(memory['memories'])),validator=lambda x:validate_continuity(x,len(memory['memories'])))
        continuity=reconcile(continuity,state['accepted'][-1]['continuity'] if state['accepted'] else None,i)
        continuity['source_condition_passages']=source_notes(prose)
        approved=continuity.get('approved_memory_indices',[])
        contracts.require(isinstance(approved,list) and all(type(j) is int and 0<=j<len(memory['memories']) for j in approved),'Invalid memory approval indices')
        for j in sorted(set(approved)):state['memories'].append(dict(memory['memories'][j],source=card['id']))
        save(sf/'memory-approval.json',{'approved_indices':approved,'quarantined_count':len(memory['memories'])-len(set(approved))})
        state['accepted'].append({'id':card['id'],'prose':prose,'continuity':continuity,'audit':audit});checkpoint()
    status(('Gemma' if final_candidate else 'Flash')+': audit complete four-scene progression')
    story='\n\n* * *\n\n'.join(x['prose'] for x in state['accepted'])
    if final_candidate:
        story=Path(final_candidate).read_text().strip()
        # Preserve the Flash ceiling; editorial rechecks can use Gemma.
        executor.req={**req,'api_roles':{**req['api_roles'],'chapter_quality':'gemma'}}
        sections=re.split(r'\n\s*\* \* \*\s*\n',story)
        contracts.require(len(sections)==4 and all(not defects(p) for p in sections),'Editorial candidate must contain four mechanically valid scenes')
        save(folder/'editorial-input.json',{'source':'explicit_editorial_candidate','sha256':hashlib.sha256(story.encode()).hexdigest(),'original_scene_hashes':[hashlib.sha256(x['prose'].encode()).hexdigest() for x in state['accepted']]})
    save(folder/'whole-story-candidate.txt',story)
    final_packet={'candidate':story,'cast_registry':development['cast_registry'],'required_scene_progression':req['scene_designs'],'world_rules':req['world_rules'],'ledgers':[x['continuity'] for x in state['accepted']]}
    if final_candidate:
        final_packet={'candidate':story,'cast_registry':development['cast_registry'],'requirements':['Four developed scenes: discovery, costly acquisition, trial and counsel, battle and local aftermath.','Third-person epic narration; no dialogue, invocation, first-person narrator or quoted speech.','Six weapons and 24 charges acquired after a demonstration consumes one of 25. Trial consumes one, leaving 23 including one suspect charge. Three shots and one failed charge leave 19; five usable weapons remain.','Thestor is the mortal smith, Meles his nephew; the unnamed shrine keeper is a different man.','Burned hand and wet conditions must causally affect the climax; no unsupported wet-powder pressure explanation.','Achilles and Hector survive; Troy is not taken. Hector observes effects, not private Greek counts.','No duplicated events or passages, explanatory moral ending or raw serialization.','Personal seal and sacred basin obligation remain consequential.']}
    audit=executor.call('chapter_quality',final_packet,AUDIT+' Verify the complete current candidate, not earlier drafts. Check resource arithmetic, earned choices, continuity and unnecessary explanation.',tokens=1200 if final_candidate else 2000,validator=lambda x:review(x,story))
    save(folder/'whole-story-review.json',audit)
    if not audit['pass']:
        status('Gemma: repair whole-story transitions and causal faults')
        parts=[x['prose'] for x in state['accepted']]
        targets=set()
        for issue in audit['issues']:
            for j,text in enumerate(parts):
                if issue['quote'] in text:targets.add(j)
        if not targets:targets=set(range(4))
        for j in sorted(targets):
            local_issues=[issue for issue in audit['issues'] if issue['quote'] in parts[j]]
            revised=prose_call('humanizer',{'prose':parts[j],'review':local_issues,'scene_requirements':req['scene_designs'][j],'neighboring_material_states':[x['continuity'] for x in state['accepted']],'world_rules':req['world_rules']},'Repair this scene against the whole-story audit. Keep 750–1000 words and its causal position. Preserve all unaffected established events. Return scene prose only.',2200)
            contracts.require(not defects(revised),'Whole-story repair introduced mechanical faults')
            parts[j]=revised
        story='\n\n* * *\n\n'.join(parts)
        save(folder/'whole-story-revision-candidate.txt',story)
        audit=executor.call('story_quality',{'candidate':story,'cast_registry':development['cast_registry'],'required_scene_progression':req['scene_designs'],'world_rules':req['world_rules']},AUDIT,tokens=2000,validator=lambda x:review(x,story))
        save(folder/'whole-story-review-final.json',audit)
    save(folder/'whole-story-candidate.txt',story)
    contracts.require(len(re.split(r'\n\s*\* \* \*\s*\n',story))==4,'Final export must contain four scenes')
    contracts.require(not defects(story),'Final mechanical gate failed')
    contracts.require(audit['pass'],'Whole-story audit failed; reviewed draft retained without final label')
    save(folder/'FINAL_STORY.txt',req['title']+'\n\n'+story.strip()+'\n')
    save(folder/'manifest.json',{'final_text':'FINAL_STORY.txt','words':len(story.split()),'scenes':4,'whole_story_audit_pass':audit['pass'],'editorial_candidate':bool(final_candidate),'final_body_sha256':hashlib.sha256(story.encode()).hexdigest(),'request_hash':fingerprint,'provider_budget':load(folder/'provider-budget/quota.json') if (folder/'provider-budget/quota.json').exists() else {}})
    status('Complete: FINAL_STORY.txt saved')
    return folder/'FINAL_STORY.txt'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--source',required=True);p.add_argument('--backend',default='worker',choices=['worker','fixture']);p.add_argument('--final-candidate');args=p.parse_args();run(args.out,args.source,args.backend,args.final_candidate)
