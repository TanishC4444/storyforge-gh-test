"""Bounded development loops and author-only scene re-design."""
from __future__ import annotations
from pathlib import Path
from . import contracts
from .brief import controls
from .editorial import DESIGN_CHECKS, design_review
from .inference import ROOT
from .retrieval import application_packet
from .storage import save, load


def document(state,kind):
    return {'request':state['request'],'candidate':state['refinement'] if kind=='refine' else state['plan']}


def source_paths(document):
    """Supply real navigable paths, never guessed aliases for normalized fields."""
    paths=[]
    def visit(value,path,depth):
        paths.append(path)
        if depth>=2:return
        if isinstance(value,dict):
            for key,item in value.items():visit(item,path+'.'+key,depth+1)
        elif isinstance(value,list):
            for index,item in enumerate(value[:6]):visit(item,path+'.'+str(index),depth+1)
    visit(document['candidate'],'candidate',0)
    return paths


def assess(executor,state,kind):
    data=document(state,kind)
    return executor.call('development_editor',{'review_document':data,'required_checks':DESIGN_CHECKS,'valid_candidate_paths':source_paths(data)},
                         'Assess every required category against the actual candidate, compared with the user request. Select paths from valid_candidate_paths. Normalized lists use numeric indexes, not invented named keys. User-request fields are requirements, not evidence that the candidate satisfies them. Return the required design-review JSON. Set pass=true if all checks pass and issues are advisory only; pass=false requires a failed check or blocking issue.',
                         tokens=2700,validator=lambda x:design_review(x,data),skill=(ROOT/'skills/design_review.md').read_text())


def development_stage(task,source,out,state,executor,plan_instruction,refine_instruction):
    kind='refine' if task.startswith('refine_') else 'plan'
    if task.endswith('_review'):
        verdict=assess(executor,state,kind)
        save(out/'review.json',verdict);save(out/'snapshot.json',state)
        return state
    if task.endswith('_revision'):
        verdict=load(source/'design-review/review.json')
        state.setdefault('development_history',[]).append({'kind':kind,'review':verdict})
        if not verdict['pass']:
            if kind=='refine':
                candidate=executor.call('refiner',{'request':state['request'],'candidate':state['refinement'],'revision_requests':verdict['issues']},
                    refine_instruction+' Revise the candidate to address the development review; preserve explicit user choices and identify assumptions.',tokens=3600,validator=lambda x:contracts.refinement(x,state['request']))
                state['refinement']=candidate
            else:
                candidate=executor.call('architect',{'request':state['request'],'candidate':state['plan'],'revision_requests':verdict['issues']},
                    plan_instruction+' Revise the actual causal sequence and scene functions, not just phrasing.',tokens=4200,validator=lambda x:contracts.plan(x,state['request']))
                state['plan']=candidate
        save(out/('refinement.json' if kind=='refine' else 'plan.json'),state['refinement'] if kind=='refine' else state['plan'])
        save(out/'snapshot.json',state)
        return state
    if task.endswith('_gate'):
        verdict=assess(executor,state,kind)
        save(out/'review.json',verdict)
        contracts.require(verdict['pass'],kind+' development review rejected after one revision; no story generation starts')
        state.setdefault('development_gates',{})[kind]=verdict
        save(out/'snapshot.json',state)
        return state
    raise ValueError('Unknown development stage')


def validate_scene(scene,req,index):
    expected=f'ch{index//req["scenes_per_chapter"]+1:02}-sc{index%req["scenes_per_chapter"]+1:02}'
    ids={c['id'] for c in req['characters']}
    contracts.require(isinstance(scene,dict) and scene.get('id')==expected,'Scene design must keep scene ID')
    contracts.require(scene.get('chapter')==index//req['scenes_per_chapter']+1 and scene.get('pov') in ids,'Invalid scene design chapter/POV')
    participants=scene.get('participants',[])
    contracts.require(isinstance(participants,list) and bool(participants) and all(isinstance(x,str) for x in participants) and len(set(participants))==len(participants) and set(participants)<=ids and scene['pov'] in participants,'Invalid scene participants')
    for key in ['goal','obstacle','intended_change','location','time','choice','consequence','new_development']:
        contracts.require(isinstance(scene.get(key),str) and bool(scene[key].strip()),'Scene design needs '+key)
    contracts.require(isinstance(scene.get('reference_uses'),list),'Scene design needs reference_uses')
    return scene
