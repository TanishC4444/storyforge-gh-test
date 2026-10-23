"""Manually resumed local world simulation. Random proposals never become canon by fiat."""
import argparse,copy,json,random,time,os
from pathlib import Path
from .contracts import require,plan
from .storage import save,load,lock
from .flow_common import fingerprint,example_path,object_schema,strings,generated
from .inference import Executor
from .canon import append,index,working,recording_context
from .evidence import payload
from .coordinator import MEMORY_INSTRUCTION
from .resilience import memory_extract
from .experimental import review_memory
from .experimental_parts import review,repair,needs_repair
from .editorial import STORY_CHECKS,RHETORIC_CHECKS
from .craft import validate_prose,compile_scene_plan

SHOCKS=['A resource becomes scarce','A neglected obligation is called in','An ally refuses the expected help','A rival moves first','Weather closes a route','An accident destroys a convenience','A hidden cost of an earlier choice emerges','A stranger brings an uncertain claim','An apparent opportunity creates a competing duty','An old grievance acquires a new witness','Two incompatible loyalties demand action','A discovery changes the value of an ordinary object','A trusted ally betrays a promise to save someone else','A successful rescue exposes a larger catastrophe','A faction splits over the cost of victory','A supposedly safe institution conceals an active conspiracy','A necessary sacrifice threatens a valued character','A planted clue reveals a dangerous second meaning','Two opponents must cooperate against a consequence they caused','A public revelation destroys the legitimacy of a leader','An apparent death leaves contradictory evidence','A debt comes due at the worst possible moment','An enemy protects someone the protagonists abandoned']


def foundation(name):
    spec=load(example_path(name));require(isinstance(spec.get('beginning'),str) and bool(spec['beginning'].strip()),'Universe needs a beginning')
    req=load(example_path(spec['author_brief']))
    require(type(spec.get('seed')) is int and 0<=spec['seed']<2**63,'Seed must be a nonnegative 63-bit integer')
    require(type(spec.get('chaos')) in {float,int} and 0<=spec['chaos']<=1,'Chaos must be 0–1')
    require(type(spec.get('episode_words')) is int and 100<=spec['episode_words']<=1600,'Episode output budget must be 100–1600 words')
    req.update(premise=spec['beginning'],words_per_scene=spec['episode_words'],profile='expressive',api_roles={})
    req['ending_tendency']='Leave consequential open threads; the world has no predetermined final ending.'
    req['execution_policy']={'experimental':False,'literary_quality':True,'continue_with_warnings':False,
        'cpu_models':{r:'qwen7b' for r in ['director','scene_designer','memory','memory_quality','story_quality','rhetoric_quality','chapter_quality','development_editor','global_repair','repair']}}
    req['performance']={**req.get('performance',{}),'inherit_provider_budget':False,'compact_packets':True}
    return spec,req


def tuple_tree(x):return tuple(tuple_tree(v) for v in x) if isinstance(x,list) else x

def propose(state,spec,req):
    rng=random.Random();rng.setstate(tuple_tree(state['rng_state']))
    from .universe_events import freedom,current_life
    f=freedom(req);dead={cid for cid,status in current_life(state.get('memories',[])).items() if status=='dead'}
    ids=[c['id'] for c in req['characters'] if c['id'] not in dead]
    intensity=f['intensity'] if f['enabled'] else spec['chaos']
    shocks=rng.sample(SHOCKS,min(len(SHOCKS),1+int(intensity*4)))
    actors=rng.sample(ids,min(2,len(ids)))
    proposal={'shocks':shocks,'actors':actors,'intensity':round(rng.uniform(.3,.6)+spec['chaos']*.4,3),'roll':rng.getrandbits(32),
              'creative_freedom':f,'causal_budget':1+int(intensity*2),'policy':'Proposals only. Adapt to immutable world rules and current consequences. Reject incompatible shocks rather than overriding canon. Claims need not be true.'}
    state['rng_state']=rng.getstate();state['attempts']+=1
    return proposal


def scene_card(req,state,proposal,out,backend):
    ids=[c['id'] for c in req['characters']]
    schema=object_schema({**{k:{'type':'string'} for k in ['goal','obstacle','intended_change','location','time']},'pov':{'type':'string','enum':ids},'participants':{'type':'array','items':{'type':'string','enum':ids},'minItems':1,'maxItems':len(ids)}})
    def validate(v):
        require(all(isinstance(v.get(k),str) and v[k].strip() for k in ['goal','obstacle','intended_change','location','time']),'Incomplete event contract')
        require(v.get('pov') in ids and isinstance(v.get('participants'),list) and v['pov'] in v['participants'] and set(v['participants'])<=set(ids),'Unknown event participants')
        return {**v,'id':f'world-{state["version"]+1:06}','chapter':state['version']+1}
    fixture={k:v for k,v in compile_scene_plan(req)['scenes'][0].items() if k not in {'id','chapter'}}
    return generated(req,out,backend,'director',{'beginning':req['premise'],'world_rules':req['world_rules'],'cast':req['characters'],
         'actual_current_state':working(state,query=str(proposal),budget=6500),'proposal':proposal},
        'Develop one consequential next event. Deeply specify an attempted solution, resistance, choice, time and location. Grow an existing conflict before adding an unrelated one. The beginning applies only before the first accepted event. Do not repeat completed events. Planned outcomes remain proposals. Do not guarantee success or a plot twist.',schema,validate,fixture,tokens=1200)


def tick(state,spec,req,out,backend):
    out=Path(out);proposal=propose(state,spec,req)
    # Persist the random draw before inference, including draws that later fail.
    save(out/'proposal.json',proposal);save(out.parent/'checkpoint.json',state)
    card=scene_card(req,state,proposal,out/'direction',backend)
    executor=Executor(req,out/'calls',backend)
    context=recording_context(state,card)
    packet={'scene':card,'beginning':req['premise'] if not state['accepted'] else None,'world_rules':req['world_rules'],
            'cast':req['characters'],'author_canon':context,'pov_visible_memory':working(state,character=card['pov'],query=str(card),budget=4500),
            'recent_prose':[s['prose'] for s in state['accepted'][-1:]],'random_proposal':proposal,'target_words':req['words_per_scene'],
            'knowledge_rule':'Author canon is not shared character knowledge. Show acquisition before using a private fact. New conflicts and twists must have material causes.'}
    prose=executor.call('writer',packet,'Write one developed scene from this proposed event, in the author style. Show a consequential action and its cost. Do not summarize the outline. Do not resolve the entire world. Prose alone.',tokens=2600,validator=lambda t:validate_prose(t,req,check_length=backend!='fixture'),output_format='text')
    save(out/'prose.txt',prose)
    for attempt in range(2):
        facts=memory_extract(executor,req,out/'memory'/str(attempt),prose,{**payload(prose),'characters':[c['id'] for c in req['characters']],**context},MEMORY_INSTRUCTION)
        info={'scene':card,'world_rules':req['world_rules'],'actual_canon':context,'references':[], 'episode_policy':'An open-ended universe episode, not the end of a story.'}
        reviews=[review(executor,req,prose,info,STORY_CHECKS,'story_quality','story'),review(executor,req,prose,info,RHETORIC_CHECKS,'rhetoric_quality','rhetoric'),review_memory(executor,req,prose,facts['memories'])]
        save(out/f'reviews-{attempt}.json',reviews)
        if all(r.get('pass') and not r.get('unverified') for r in reviews):break
        if attempt==1:raise ValueError('Universe event not accepted; checkpoint and provisional prose preserved')
        # Memory errors are re-extracted, never made true by rewriting the story.
        literary=[r for r in reviews[:2] if needs_repair(r,req)]
        if literary:
            prose,_=repair(executor,req,prose,literary);save(out/'prose.txt',prose)
    candidate=copy.deepcopy(state);candidate['version']+=1
    append(candidate,facts['memories'],card['id'])
    candidate['accepted'].append({**card,'prose':prose,'source_sha256':payload(prose)['prose_sha256'],'quality_status':'fixture' if backend=='fixture' else 'reviewed'})
    candidate['last_event_status']='accepted';save(out/'accepted.json',candidate['accepted'][-1])
    save(out.parent/'checkpoint.json',candidate)
    save(out.parent/('FIXTURE_UNIVERSE.txt' if backend=='fixture' else 'UNIVERSE.txt'),'\n\n* * *\n\n'.join(s['prose'] for s in candidate['accepted'])+'\n')
    return candidate


def run(name,out,backend='fixture',steps=None,minutes=45,resume=None):
    require(type(minutes) is int and 1<=minutes<=300,'Runtime budget must be 1–300 minutes')
    require(steps is None or type(steps) is int and 1<=steps<=100,'Practice event limit must be 1–100')
    spec,req=foundation(name);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    fid=fingerprint({'spec':spec,'author_brief':req});mode='fixture' if backend=='fixture' else 'local'
    checkpoint=Path(resume) if resume else out/'checkpoint.json'
    if checkpoint.exists():
        state=load(checkpoint);require(state['foundation_hash']==fid,'Immutable universe foundation changed; start a new universe')
        require(state['mode']==mode,'Fixture checkpoints cannot resume into a live universe')
    else:
        facts=[dict(m,id=f'm{i:05}',kind=m.get('kind','event'),source='user_input') for i,m in enumerate(req['initial_facts'])]
        state={'foundation_hash':fid,'mode':mode,'version':0,'attempts':0,'rng_state':random.Random(spec['seed']).getstate(),'accepted':[],'memories':facts,'canon':index(facts)}
    with lock(out):
        save(out/'checkpoint.json',state);started=time.monotonic();count=0
        while (steps is None or count<steps) and time.monotonic()-started<minutes*60:
            remaining=minutes*60-(time.monotonic()-started)
            # Share the manual run budget with all existing inference calls.
            previous=os.environ.get('STORY_JOB_DEADLINE');deadline=time.time()+remaining
            if previous:deadline=min(deadline,float(previous))
            os.environ['STORY_JOB_DEADLINE']=str(deadline)
            try:state=tick(state,spec,req,out/f'attempt-{state["attempts"]+1:06}',backend)
            finally:
                if previous is None:os.environ.pop('STORY_JOB_DEADLINE',None)
                else:os.environ['STORY_JOB_DEADLINE']=previous
            count+=1
        return state


def main():
    p=argparse.ArgumentParser();p.add_argument('--request-file',default='troy-universe');p.add_argument('--out',default='out');p.add_argument('--backend',choices=['fixture','worker'],default='fixture');p.add_argument('--steps',type=int);p.add_argument('--minutes',type=int,default=45);p.add_argument('--resume')
    a=p.parse_args();run(a.request_file,a.out,a.backend,a.steps,a.minutes,a.resume)

if __name__=='__main__':main()
