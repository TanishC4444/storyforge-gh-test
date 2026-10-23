"""One local universe event prepared for the full visible classic-runner DAG."""
import argparse,copy,json,random
from pathlib import Path
from .storage import save,load
from .contracts import require,plan
from .canon import index
from .craft import compile_brief,compile_scene_plan
from .expansion import bible
from .universe import propose,scene_card


def prepare(source,out,checkpoint=None,backend='fixture'):
    state=load(source);req=state['request'];out=Path(out)
    require(req.get('performance',{}).get('classic_expansion') and req.get('performance',{}).get('living_universe'),'Living runner graph requires an explicit universe-event request')
    bounded=req.get('performance',{}).get('living_bounded',False)
    require(req['scenes_per_chapter']==1 and (1<=req['chapters']<=4 if bounded else req['chapters']==1),'Living runs support one event or an explicit bounded episode of up to four chapters')
    fid=bible(req);history=[];episode=1;rng=random.Random(104729).getstate();attempts=0
    if checkpoint:
        old=load(checkpoint)
        require(old.get('backend')==state['backend'],'Cannot mix fixture and live universe canon')
        require(old.get('universe_bible_hash')==fid,'Cannot silently replace universe foundation')
        require(all(s.get('quality_status')=='reviewed' and all(s.get(k,{}).get('pass') for k in ['review','rhetoric_review','memory_review']) for s in old.get('accepted',[])),'Unreviewed events cannot enter universe canon')
        from .universe_events import resume_cast
        resume_cast(req,old)
        history=copy.deepcopy(old.get('universe_history',[]))+[dict(s,universe_episode=old['universe_episode']) for s in old.get('accepted',[])]
        state['memories']=copy.deepcopy(old['memories']);episode=old['universe_episode']+bool(old.get('accepted'))
        rng=old['universe_rng_state'];attempts=old['universe_attempts']
    from .flow_common import fingerprint
    state['request_hash']=fingerprint(req)
    if bounded:
        state.update(universe_bible_hash=fid,universe_episode=episode,universe_history=history,universe_rng_state=rng,universe_attempts=attempts,canon=index(state['memories']))
        state['refinement']=compile_brief(req);state['refinement_method']='application_compiled_author_brief_no_model_calls'
        state['plan']=compile_scene_plan(req);state['plan_approved']=True
        state['planning_provenance']={'method':'bounded_living_episode_with_per_chapter_random_proposals','accepted_history':False,'refinement_model_calls':0}
        save(out/'plan.json',state['plan']);save(out/'refinement.json',state['refinement']);save(out/'snapshot.json',state)
        save(out/'status.json',{'task':'bounded_episode_layout','status':'success','phase':'success','refinement_model_calls':0,'chapters':req['chapters']})
        return state
    world={'version':len(history),'accepted':history,'memories':state['memories'],'rng_state':rng,'attempts':attempts}
    proposal=propose(world,{'chaos':.95},req)
    state.update(universe_bible_hash=fid,universe_episode=episode,universe_history=history,universe_rng_state=world['rng_state'],universe_attempts=world['attempts'],canon=index(state['memories']))
    state['refinement']=compile_brief(req);state['refinement_method']='application_compiled_author_brief_no_model_calls'
    # Preserve the draw and all prior canon before asking the local director.
    save(out/'proposal.json',proposal);save(out/'snapshot.json',state)
    card=scene_card(req,world,proposal,out/'event-direction',backend);card.update(id='ch01-sc01',chapter=1)
    req['scene_designs']=[{'id':card['id'],'pov':card['pov'],'participants':card['participants'],'location':card['location'],'time':card['time'],
        'dramatic_function':card['goal'],'development':card['intended_change'],'choice_and_consequence':card['intended_change'],
        'restrictions':'Preserve established canon, individual knowledge and immutable world rules. The proposed change is not yet an accepted event.'}]
    state['plan']=plan({'scenes':[card],'threads':[s['question'] for s in req['plot_design'].get('subplots',[])]},req)
    from .flow_common import fingerprint
    state['request_hash']=fingerprint(req)
    state['plan_approved']=True;state['planning_provenance']={'method':'seeded_random_proposal_then_local_director','accepted_history':False,'refinement_model_calls':0}
    save(out/'plan.json',state['plan']);save(out/'refinement.json',state['refinement']);save(out/'snapshot.json',state)
    save(out/'status.json',{'task':'local_event_direction','status':'success','phase':'success','refinement_model_calls':0,'event_planning':'local director; proposal only'})
    return state


def chapter_proposal(state,out):
    """Draw against actual prior canon at each chapter; never precommit future events."""
    world={'version':len(state.get('universe_history',[]))+len(state['accepted']),
           'accepted':state.get('universe_history',[])+state['accepted'],'memories':state['memories'],
           'rng_state':state['universe_rng_state'],'attempts':state['universe_attempts']}
    proposal=propose(world,{'chaos':.6},state['request'])
    state['universe_rng_state']=world['rng_state'];state['universe_attempts']=world['attempts']
    proposal['policy']+=' Bounded episode: the author chapter arc governs. Select up to causal_budget connected complications only when earned. Preserve fixed resources, identities, travel time and deadlines. Foreshadow later shocks and carry their consequences through memory.'
    save(Path(out)/'proposal.json',proposal);save(Path(out)/'snapshot.json',state)
    return proposal


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default='inputs/state/snapshot.json');p.add_argument('--out',default='out');p.add_argument('--checkpoint');p.add_argument('--backend',choices=['fixture','worker'],default='fixture');a=p.parse_args();prepare(a.source,a.out,a.checkpoint,a.backend)

if __name__=='__main__':main()
