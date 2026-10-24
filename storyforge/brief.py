"""Explicit creative controls, distinct from execution settings."""
from __future__ import annotations
import copy
import re

CATEGORIES = ['medium_length','themes_tensions','scene_design','world_rules','character_depth','plot_subplots','genre','tone_mood','references_adaptation','figurative_language']


def validate(req, require):
    from .media import choose
    choose(req,require)
    req.setdefault('brief_version',1)
    require(req['brief_version'] in {1,2},'Unknown creative brief version')
    req.setdefault('keywords',[{'term':x,'kind':'theme','priority':2} for x in req.get('theme_keywords',[])])
    require(isinstance(req['keywords'],list),'keywords must be an array')
    for keyword in req['keywords']:
        require(isinstance(keyword,dict) and isinstance(keyword.get('term'),str) and keyword['term'].strip(),'Keyword needs term')
        require(keyword.get('kind') in {'theme','tension','conflict','technique','relationship'},'Invalid keyword kind')
        require(type(keyword.get('priority',2)) is int and 1<=keyword.get('priority',2)<=3,'Keyword priority must be 1–3')
    defaults={
      'scene_designs':[], 'world_design':{}, 'plot_design':{}, 'references':[],
      'adaptation':{'strength':.35,'mode':'mechanisms','max_active_sources_per_scene':2,'preserve_user_choices':True},
      'style':{'figurative_language':{'density':'moderate','devices':['metaphor'],'image_domains':[]},'interiority':'selective','dialogue':'tactical and character-specific','explanation':'Do not explain already legible actions.'},
      'length_policy':{'scene_words':'guidance','chapter_words':'target'},
    }
    for key,value in defaults.items():req.setdefault(key,copy.deepcopy(value))
    for key in ['world_design','plot_design','adaptation','style','length_policy']:
        require(isinstance(req[key],dict),f'{key} must be an object')
    require(isinstance(req['scene_designs'],list),'scene_designs must be an array')
    valid_ids={c['id'] for c in req['characters']}
    for design in req['scene_designs']:
        require(isinstance(design,dict) and isinstance(design.get('id'),str),'Scene design needs ID')
        for key in ['location','setting','dramatic_function']:
            require(isinstance(design.get(key),str) and bool(design[key].strip()),f'Scene design needs {key}')
    for character in req['characters']:
        for key in ['goal','voice']:
            require(isinstance(character.get(key),str) and bool(character[key].strip()),f'Character needs {key}')
        if req['brief_version']==2 and character.get('profile_origin')!='scene_director':
            for key in ['value','fear','habitual_strategy','limits']:
                require(isinstance(character.get(key),str) and bool(character[key].strip()),f'Deep character needs {key}')
            for key in ['arc','contradiction','emotional_behavior','voice_design']:
                require(isinstance(character.get(key),dict) and bool(character[key]),f'Deep character needs {key}')
            for key in ['starting_belief','old_strategy','pressure_test','costly_choice','possible_change']:
                require(isinstance(character['arc'].get(key),str) and bool(character['arc'][key].strip()),f'Character arc needs {key}')
            require(isinstance(character['voice_design'].get('examples'),list) and len(character['voice_design']['examples'])>=2,'Voice design needs at least two examples')
    references=req['references']
    require(isinstance(references,list),'references must be an array')
    for ref in references:
        require(isinstance(ref,dict) and isinstance(ref.get('record_id'),str),'Reference needs record_id')
        require(ref.get('scope') in {'story','chapter','scene'},'Invalid reference scope')
        require(isinstance(ref.get('purpose'),str) and bool(ref['purpose'].strip()),'Reference needs purpose')
        if ref['scope']!='story':
            require(isinstance(ref.get('target'),str),'Scoped reference needs target')
            pattern=r'ch\d{2}' if ref['scope']=='chapter' else r'ch\d{2}-sc\d{2}'
            require(bool(re.fullmatch(pattern,ref['target'])),'Invalid reference target format')
            require(1<=int(ref['target'][2:4])<=req['chapters'],'Reference chapter outside requested length')
            if ref['scope']=='scene':require(1<=int(ref['target'][-2:])<=req['scenes_per_chapter'],'Reference scene outside requested length')
    if 'retrieval_weights' in req:
        weights=req['retrieval_weights']
        require(isinstance(weights,dict) and set(weights)=={'semantic_similarity','keyword_match','narrative_mechanism_match'},'Invalid retrieval weight keys')
        require(all(type(v) in (int,float) and 0<=v<=1 for v in weights.values()),'Retrieval weights must be 0–1')
        require(abs(sum(weights.values())-1)<1e-6,'Retrieval weights must sum to one')
        require(req['retrieval_mode']=='hybrid' or weights['semantic_similarity']==0,'Semantic weighting requires hybrid retrieval')
    adaptation=req['adaptation']
    require(type(adaptation.get('strength')) in (int,float) and 0<=adaptation['strength']<=1,'Adaptation strength must be 0–1')
    require(adaptation.get('mode') in {'mechanisms','structural_echo','comparative'},'Invalid adaptation mode')
    require(type(adaptation.get('max_active_sources_per_scene')) is int and 0<=adaptation['max_active_sources_per_scene']<=3,'Reference budget must be 0–3')
    figures=req['style'].get('figurative_language')
    require(isinstance(figures,dict) and figures.get('density') in {'sparse','moderate','lyrical'},'Invalid figurative language density')
    require(all(isinstance(figures.get(k,[]),list) and all(isinstance(x,str) for x in figures.get(k,[])) for k in ['devices','image_domains']),'Figurative devices/domains must be string arrays')
    require(req['length_policy'].get('scene_words') in {'guidance','strict'},'Invalid scene length policy')
    require(req['length_policy'].get('overflow','strict') in {'strict','advisory'},'Invalid length overflow policy')
    if req['brief_version']==2:
        require(bool(req['keywords']) and bool(req['scene_designs']),'Deep brief requires keywords and scene designs')
        for key in ['technology','institutions','physical_systems','deadlines']:
            require(bool(req['world_design'].get(key)),f'World design needs {key}')
        for key in ['central_question','causal_dependencies','subplots','alternatives_and_costs']:
            require(bool(req['plot_design'].get(key)),f'Plot design needs {key}')
        for subplot in req['plot_design']['subplots']:
            require(isinstance(subplot,dict) and subplot.get('owner') in valid_ids,'Subplot needs a valid owner')
            for key in ['id','question','intersection','removal_cost']:
                require(isinstance(subplot.get(key),str) and bool(subplot[key].strip()),f'Subplot needs {key}')
    require(isinstance(req.get('api_roles',{}),dict) and all(isinstance(role,str) and provider in {'gemma','flash','flash36','lite'} for role,provider in req.get('api_roles',{}).items()),'API role routing must map role names to supported Google tiers')
    for field in ['execution_policy','performance']:
        require(isinstance(req.get(field,{}),dict),field+' must be an object')
    if 'continue_with_warnings' in req.get('execution_policy',{}):require(type(req['execution_policy']['continue_with_warnings']) is bool,'Continuation policy must be boolean')
    return req


def controls(req):
    return {k:req.get(k) for k in ['medium','chapters','reader_experience','genre','tone_mood','keywords','adaptation','style','length_policy']}


def scene_controls(req, scene_id):
    return {**controls(req),'world_design':req['world_design'],
            'central_question':req['plot_design'].get('central_question'),
            'subplots':req['plot_design'].get('subplots',[]),
            'scene_designs':[s for s in req['scene_designs'] if s['id']==scene_id]}
