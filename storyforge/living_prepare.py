"""One local universe event prepared for the full visible classic-runner DAG."""
import argparse,copy,json,random
from pathlib import Path
from .storage import save,load
from .contracts import require,plan
from .canon import index
from .craft import compile_brief
from .expansion import bible
from .universe import propose,scene_card


def prepare(source,out,checkpoint=None,backend='fixture'):
    state=load(source);req=state['request'];out=Path(out)
    require(req.get('performance',{}).get('classic_expansion') and not req.get('api_roles'),'Living runner graph requires an explicit local-only universe request')
    require(req['chapters']==1 and req['scenes_per_chapter']==1,'One universe event per manually resumed run')
    fid=bible(req);history=[];episode=1;rng=random.Random(104729).getstate();attempts=0
    if checkpoint:
        old=load(checkpoint)
        require(old.get('backend')==state['backend'],'Cannot mix fixture and live universe canon')
        require(old.get('universe_bible_hash')==fid,'Cannot silently replace universe foundation')
        require(all(s.get('quality_status')=='reviewed' and all(s.get(k,{}).get('pass') for k in ['review','rhetoric_review','memory_review']) for s in old.get('accepted',[])),'Unreviewed events cannot enter universe canon')
        old_cast={c['id']:c['name'] for c in old['request']['characters']};new_cast={c['id']:c['name'] for c in req['characters']}
        require(all(new_cast.get(cid)==name for cid,name in old_cast.items()),'Existing character identities must remain stable')
        history=copy.deepcopy(old.get('universe_history',[]))+[dict(s,universe_episode=old['universe_episode']) for s in old.get('accepted',[])]
        state['memories']=copy.deepcopy(old['memories']);episode=old['universe_episode']+bool(old.get('accepted'))
        rng=old['universe_rng_state'];attempts=old['universe_attempts']
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


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default='inputs/state/snapshot.json');p.add_argument('--out',default='out');p.add_argument('--checkpoint');p.add_argument('--backend',choices=['fixture','worker'],default='fixture');a=p.parse_args();prepare(a.source,a.out,a.checkpoint,a.backend)

if __name__=='__main__':main()
