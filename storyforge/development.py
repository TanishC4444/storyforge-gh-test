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
    data=document(state,kind);cards=evidence_cards(data)
    requirements=compact_requirements(state['request'])
    groups=[['medium_length','themes_tensions','genre','tone_mood'],['scene_design','information_order','causal_alternatives'],['world_rules','character_depth'],['plot_subplots','references_adaptation','figurative_language']]
    results=[]
    for group in groups:
        wanted=set(group)
        for key in group:wanted.update(ALIASES.get(key,[]))
        selected=[c for c in cards if c['label'] in wanted or (kind=='plan' and c['path'].startswith('candidate.scenes.'))]
        if not selected:selected=[c for c in cards if c['path']=='candidate.refined_prompt'] or cards
        reqs={k:requirements[k] for k in group if k in requirements}
        if 'causal_alternatives' in group:reqs['causal_alternatives']=state['request']['plot_design'].get('alternatives_and_costs',[])
        if 'information_order' in group:reqs['information_order']=requirements['scene_design']
        result=executor.call('development_editor',{'requirements':reqs,'candidate_evidence':selected,'required_checks':group},
            'Compare candidate evidence with requirements. Return JSON pass, checks (one per required ID: id, verdict pass/fail, evidence_id, reason), issues (severity, category, evidence_id, problem, fix). Select evidence IDs; NEVER invent paths. Check what is actually developed, not just promised. Missing development fails with an actionable matching issue. Advisory issues alone do not require failure.',
            tokens=1100,validator=lambda x,c=selected,g=group:resolve_review(x,data,c,g),response_schema=review_schema(selected,group))
        results.append(result)
    return design_review({'pass':all(r['pass'] for r in results),'checks':[c for r in results for c in r['checks']],'issues':[i for r in results for i in r['issues']]},data)


def development_stage(task,source,out,state,executor,plan_instruction,refine_instruction):
    kind='refine' if task.startswith('refine_') else 'plan'
    if task.endswith('_review'):
        verdict=assess(executor,state,kind)
        import hashlib,json
        state.setdefault('development_assessments',{})[kind]={'sha256':hashlib.sha256(json.dumps(document(state,kind),sort_keys=True).encode()).hexdigest(),'review':verdict}
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
        import hashlib, json
        digest=hashlib.sha256(json.dumps(document(state,kind),sort_keys=True).encode()).hexdigest()
        prior=state.get('development_assessments',{}).get(kind,{})
        verdict=prior['review'] if prior.get('sha256')==digest and prior.get('review',{}).get('pass') else assess(executor,state,kind)
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


CATEGORY_FIELDS = {
    'medium_length':['medium','chapters','scenes_per_chapter','words_per_scene','length_policy'],
    'themes_tensions':['keywords'], 'scene_design':['scene_designs'],
    'world_rules':['world_rules'], 'character_depth':['characters'],
    'plot_subplots':['plot_design'], 'genre':['genre'], 'tone_mood':['tone_mood'],
    'references_adaptation':['references','adaptation'], 'figurative_language':['style'],
    'causal_alternatives':['plot_design'], 'information_order':['scene_designs'],
}
ALIASES = {'character_depth':['character_behavior_arcs'], 'plot_subplots':['plots_subplots'],
           'tone_mood':['genre_tone_mood'], 'genre':['genre_tone_mood'],
           'references_adaptation':['reference_influence'], 'figurative_language':['figurative_style'],
           'scene_design':['scenes'], 'world_rules':['world_constraints'],
           'causal_alternatives':['plots_subplots'], 'information_order':['scenes']}


def evidence_cards(data):
    """Actual source values, stable IDs and paths; no model-generated navigation."""
    import hashlib, json
    candidate=data['candidate'];cards=[]
    def add(path,value,label):
        text=json.dumps(value,ensure_ascii=False,separators=(',',':'))
        cards.append({'id':'e'+hashlib.sha256(path.encode()).hexdigest()[:10],
                      'path':path,'label':label,'value':value,'source_sha256':hashlib.sha256(text.encode()).hexdigest()})
    for key,value in candidate.items():
        if key in {'original_prompt','preserved_user_choices'}:continue
        if isinstance(value,list) and value:
            for i,item in enumerate(value):
                label=item.get('name',item.get('id',key)) if isinstance(item,dict) else key
                add('candidate.'+key+'.'+str(i),item,label)
        else:add('candidate.'+key,value,key)
    return cards


def review_schema(cards,required=DESIGN_CHECKS):
    ids=[c['id'] for c in cards]
    check={'type':'object','properties':{'id':{'type':'string','enum':required},'verdict':{'type':'string','enum':['pass','fail']},'evidence_id':{'type':'string','enum':ids},'reason':{'type':'string'}},'required':['id','verdict','evidence_id','reason'],'additionalProperties':False}
    issue={'type':'object','properties':{'severity':{'type':'string','enum':['blocking','advisory']},'category':{'type':'string','enum':required},'evidence_id':{'type':'string','enum':ids},'problem':{'type':'string'},'fix':{'type':'string'}},'required':['severity','category','evidence_id','problem','fix'],'additionalProperties':False}
    return {'type':'object','properties':{'pass':{'type':'boolean'},'checks':{'type':'array','items':check,'minItems':len(required),'maxItems':len(required)},'issues':{'type':'array','items':issue}},'required':['pass','checks','issues'],'additionalProperties':False}


def resolve_review(value,data,cards,required=DESIGN_CHECKS):
    import copy
    value=copy.deepcopy(value);lookup={c['id']:c for c in cards}
    for item in value.get('checks',[])+value.get('issues',[]):
        evidence_id=item.get('evidence_id')
        contracts.require(evidence_id in lookup,'Unknown design evidence ID')
        item['path']=lookup[evidence_id]['path']
    return design_review(value,data,required)


def compact_requirements(req):
    return {
        'medium_length':{k:req.get(k) for k in CATEGORY_FIELDS['medium_length']},
        'themes_tensions':req.get('keywords',[]),
        'scene_design':[{'id':s['id'],'function':s['dramatic_function'],'development':s.get('development'),'restrictions':s.get('restrictions')} for s in req['scene_designs']],
        'world_rules':req['world_rules'],
        'character_depth':[{'id':c['id'],'goal':c['goal'],'arc':c.get('arc'),'contradiction':c.get('contradiction')} for c in req['characters']],
        'plot_subplots':req['plot_design'],
        'genre':req.get('genre'),'tone_mood':req.get('tone_mood'),
        'references_adaptation':{'references':req['references'],'adaptation':req['adaptation']},
        'figurative_language':req['style'],
    }
