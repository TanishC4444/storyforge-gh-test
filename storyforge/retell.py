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
from .narrative_gate import defects,change_metrics

CORE='''Strict third-person past-tense narrative, no dialogue, no quoted speech, no invocation, no direct address. Preserve ancient social imagination, material causality and earned epic cadence. Every passage must perform a function: action, orientation, perception, characterization, tension, or an earned image. Do not announce feelings, significance, scene functions or moral lessons already clear from action. No summaries standing in for the promised scene. No recycled gestures or replay of an earlier bargain or acquisition. Show resistance, a costly decision, and its actual consequence. Characters act differently under pressure, with mixed motives and imperfect knowledge. No technical weapon construction instructions.'''
AUDIT='''Return JSON {"pass":boolean,"issues":[{"quote":exact short quote from candidate,"problem":string,"fix":specific change}],"scene_progression":string,"depth_assessment":string}. Be skeptical. Fail for repetition, duplicated beats, unearned outcome, summary replacing action, generic emotional labels, explaining obvious acts, cosmetic ancient diction, failure of scene-specific goals, broken inventory, knowledge leak, or no-dialogue/third-person violations. A claim that a review passed is not evidence of literary quality. Examine the actual complete prose. An issue must quote the candidate exactly. Do not fail just to satisfy an issue quota; do not praise vague themes as proof of depth.'''

def review(value,prose):
    contracts.require(isinstance(value,dict) and type(value.get('pass')) is bool and isinstance(value.get('issues'),list),'Invalid narrative audit')
    for issue in value['issues']:
        contracts.require(isinstance(issue,dict) and all(isinstance(issue.get(k),str) and issue[k].strip() for k in ['quote','problem','fix']),'Invalid narrative issue')
        contracts.require(issue['quote'] in prose,'Audit quote absent from candidate')
    contracts.require(not(value['pass'] and value['issues']),'Passing audit contains unresolved issues')
    return value

def run(folder,source,backend='worker'):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    req=contracts.request(load(ROOT/'examples/troy-narrative-api.json'))
    seed=load(source);retrieval=seed['retrieval']
    state_path=folder/'state.json'
    fingerprint=hashlib.sha256(json.dumps(req,sort_keys=True).encode()).hexdigest()
    state=load(state_path) if state_path.exists() else {'request_hash':fingerprint,'accepted':[],'memories':[dict(x,kind='event',source='user_input') for x in req['initial_facts']]}
    contracts.require(state['request_hash']==fingerprint,'Run brief changed; choose a new output directory')
    executor=Executor(req,folder,backend)
    skill=(ROOT/'skills/distinct_writing.md').read_text()
    def status(phase):
        save(folder/'progress.json',{'phase':phase,'accepted_scenes':len(state['accepted']),'total_scenes':4,'time':time.time()});print(phase,flush=True)
    def checkpoint():save(state_path,state)
    def prose_call(role,data,instruction,tokens=2200):
        return executor.call(role,data,CORE+'\n'+instruction,tokens=tokens,skill=skill)
    if 'refinement' not in state:
        status('Flash: refine the full creative brief')
        state['refinement']=executor.call('refiner',{'request':req,'inspiration':application_packet(req,retrieval,'refiner')},REFINE+'\n'+CORE+' Specify causal costs and distinct material developments for all four scenes, and avoid generic advice.',tokens=4000,validator=lambda x:contracts.refinement({**x,'original_prompt':req['premise'],'original_prompt_binding':'Application copies immutable user brief; raw model response retained in calls.'},req));checkpoint()
    if 'plan' not in state:
        status('Flash: outline four distinct causal scenes')
        state['plan']=executor.call('architect',{'premise':req['premise'],'world_rules':req['world_rules'],'characters':[{'id':c['id'],'goal':c['goal'],'arc':c['arc']} for c in req['characters']],'required_scenes':req['scene_designs'],'chapters':1,'scenes_per_chapter':4,'development':state['refinement']['central_conflict']},PLAN_INSTRUCTION+'\n'+CORE+' Include an exact finite inventory schedule inside scene intended_change: choose a fixed charge count at acquisition and track expenditures. Make journey, resistance, acquisition, trial, battle and aftermath actual action in their assigned scenes. Never stage acquisition again. Resolve the local conflict only; Hector and Achilles survive.',tokens=2200,validator=lambda x:contracts.plan(x,req));checkpoint()
    for i,card in enumerate(state['plan']['scenes']):
        if len(state['accepted'])>i:continue
        sf=folder/'scenes'/f'{i+1:02}';sf.mkdir(parents=True,exist_ok=True)
        expected=req['scene_designs'][i]
        cast=[c for c in req['characters'] if c['id'] in card['participants']]
        proposals=[]
        for c in cast:
            status('Scene '+str(i+1)+': isolated character '+c['id'])
            proposal=executor.call('character',{'character':c,'scene':card,'known_facts':compact(visible(state['memories'],c['id'])),'rules':req['world_rules']},'Return up to 100 words: an observable tactic, an immediate risk, and a self-protective action consistent with this character. No spoken lines or hidden reasoning. This is a noncanonical proposal, not a new event.',tokens=220)
            proposals.append({'character':c['id'],'proposal':proposal})
        context={'scene':card,'required_scene':expected,'characters':cast,'proposals':proposals,'world_rules':req['world_rules'],'style':req['style'],'literary_mechanisms':application_packet(req,retrieval,'writer',card['id']),
                 'author_record':[{'id':x['id'],'ending':x['prose'][-1000:],'continuity':x['continuity']} for x in state['accepted']],
                 'knowledge_boundaries':compact(state['memories']),'target_words':850}
        status('Scene '+str(i+1)+': Gemma first draft')
        draft=prose_call('writer',context,'Write one complete 750–1000 word scene. No headings, labels, commentary, or outline. Begin where the previous accepted scene leaves the material situation; do not recap it. End on an action that causes the next scene. For the final scene show a developed local climax and aftermath.',2600)
        save(sf/'draft.txt',draft)
        status('Scene '+str(i+1)+': restrained revision experiment')
        light=prose_call('humanizer',{'prose':draft,'scene':card,'style':req['style']},'Restrained revision: remove redundant explanation, stock gestures, repetitions and vague imagery; preserve causal structure and substantive length. Return the full scene only.',2600)
        save(sf/'restrained.txt',light)
        status('Scene '+str(i+1)+': deep revision experiment')
        deep=prose_call('humanizer',{'prose':draft,'brief':context,'mechanical_defects':defects(draft,'\n'.join(x['prose'] for x in state['accepted']))},'Deep revision: rebuild weak causal sequences, resistance and decisions. Develop omitted action rather than summarizing it. Make details specific to the focal character and their obligations. Preserve established canon and required events, but allow meaningful structural change. Remove repeated beats. Return a complete 750–1000 word scene, no headings or explanation.',2800)
        save(sf/'deep.txt',deep)
        candidates={'restrained':light,'deep':deep}
        # Both candidates are audited; edit distance is diagnostic, never the selection score.
        audits={}
        for name,text in candidates.items():
            status('Scene '+str(i+1)+': evaluate '+name+' candidate')
            audits[name]=executor.call('story_quality',{'candidate':text,'scene_requirements':expected,'scene':card,'prior_material_state':[x['continuity'] for x in state['accepted']],'world_rules':req['world_rules'],'mechanical_defects':defects(text)},AUDIT,tokens=1500,validator=lambda x,t=text:review(x,t))
        clean=[name for name in candidates if audits[name]['pass'] and not defects(candidates[name])]
        selected='deep' if 'deep' in clean else ('restrained' if 'restrained' in clean else min(candidates,key=lambda n:len(audits[n]['issues'])+len(defects(candidates[n]))))
        prose=candidates[selected];audit=audits[selected]
        repairs=[]
        for attempt in range(2):
            problems=defects(prose,'\n'.join(x['prose'] for x in state['accepted']))
            if audit['pass'] and not problems:break
            status('Scene '+str(i+1)+': repair concrete faults '+str(attempt+1))
            revised=prose_call('humanizer',{'prose':prose,'scene_requirements':expected,'context':context,'review':audit,'blocking_mechanical_faults':problems},'Repair every cited fault, developing missing causal action as needed. Do not shrink the scene into summary. Preserve continuity, concrete cost and third-person no-dialogue form. Return complete scene prose only.',2800)
            repairs.append(change_metrics(prose,revised));prose=revised
            audit=executor.call('story_quality',{'candidate':prose,'scene_requirements':expected,'previous_material_state':[x['continuity'] for x in state['accepted']],'world_rules':req['world_rules'],'mechanical_defects':defects(prose)},AUDIT,tokens=1500,validator=lambda x:review(x,prose))
        save(sf/'reviewed-candidate.txt',prose)
        save(sf/'comparison.json',{'selected':selected,'restrained':change_metrics(draft,light),'deep':change_metrics(draft,deep),'audits':audits,'repair_changes':repairs,'final_review':audit,'mechanical_faults':defects(prose)})
        contracts.require(not defects(prose),'Mechanical prose gate failed; candidate retained, no final export')
        contracts.require(audit['pass'],'Scene quality gate failed; candidate retained, no final export')
        save(sf/'accepted.txt',prose)
        status('Scene '+str(i+1)+': extract source-bound continuity')
        memory=memory_extract(executor,req,sf,prose,{**payload(prose),'characters':[c['id'] for c in req['characters']],'existing':compact(state['memories'])},MEMORY_INSTRUCTION)
        # Keep uncertain memory out of actor knowledge; full prose remains authoritative author record.
        continuity=executor.call('memory_quality',{'prose':prose,'proposed_memories':memory['memories'],'prior_material_state':[x['continuity'] for x in state['accepted']]},'Return a short JSON author ledger with location, elapsed_time, weapon_custody, charges_remaining, charges_used_this_scene, obligations, irreversible_changes, and approved_memory_indices (zero-based). Approve a memory ONLY if its fact and every knowledge holder are explicitly supported in current prose; quarantine uncertain knowledge. Use explicit facts; unknown ledger values null. This ledger is author continuity, not knowledge automatically given to characters.',tokens=900,validator=lambda x:x if isinstance(x,dict) else (_ for _ in ()).throw(contracts.ContractError('Ledger must be object')))
        approved=continuity.get('approved_memory_indices',[])
        contracts.require(isinstance(approved,list) and all(type(j) is int and 0<=j<len(memory['memories']) for j in approved),'Invalid memory approval indices')
        for j in sorted(set(approved)):state['memories'].append(dict(memory['memories'][j],source=card['id']))
        save(sf/'memory-approval.json',{'approved_indices':approved,'quarantined_count':len(memory['memories'])-len(set(approved))})
        state['accepted'].append({'id':card['id'],'prose':prose,'continuity':continuity,'audit':audit});checkpoint()
    status('Flash: audit complete four-scene progression')
    story='\n\n* * *\n\n'.join(x['prose'] for x in state['accepted'])
    audit=executor.call('chapter_quality',{'candidate':story,'required_scene_progression':req['scene_designs'],'world_rules':req['world_rules'],'ledgers':[x['continuity'] for x in state['accepted']]},AUDIT+' Verify progression across all four scenes, charge arithmetic, nonrepetition, developed journey and battle, consistent custody and an earned local climax.',tokens=2000,validator=lambda x:review(x,story))
    save(folder/'whole-story-review.json',audit)
    if not audit['pass']:
        status('Gemma: repair whole-story transitions and causal faults')
        revised=prose_call('humanizer',{'prose':story,'review':audit,'scene_requirements':req['scene_designs'],'world_rules':req['world_rules']},'Repair the whole four-scene story against the exact cited faults. Keep all four developed scenes and 2800–4000 words. Return prose alone, separating scenes with * * *. Do not add a title.',7500)
        save(folder/'whole-story-revision-candidate.txt',revised)
        contracts.require(len(revised.split())>=2600,'Whole-story revision collapsed developed scenes')
        story=revised
        audit=executor.call('chapter_quality',{'candidate':story,'required_scene_progression':req['scene_designs'],'world_rules':req['world_rules']},AUDIT,tokens=2000,validator=lambda x:review(x,story))
        save(folder/'whole-story-review-final.json',audit)
    save(folder/'whole-story-candidate.txt',story)
    contracts.require(len(re.split(r'\n\s*\* \* \*\s*\n',story))==4,'Final export must contain four scenes')
    contracts.require(not defects(story),'Final mechanical gate failed')
    contracts.require(audit['pass'],'Whole-story audit failed; reviewed draft retained without final label')
    save(folder/'FINAL_STORY.txt',req['title']+'\n\n'+story.strip()+'\n')
    save(folder/'manifest.json',{'final_text':'FINAL_STORY.txt','words':len(story.split()),'scenes':4,'whole_story_audit_pass':audit['pass'],'request_hash':fingerprint,'provider_budget':load(folder/'provider-budget/quota.json') if (folder/'provider-budget/quota.json').exists() else {}})
    status('Complete: FINAL_STORY.txt saved')
    return folder/'FINAL_STORY.txt'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--source',required=True);p.add_argument('--backend',default='worker',choices=['worker','fixture']);args=p.parse_args();run(args.out,args.source,args.backend)
