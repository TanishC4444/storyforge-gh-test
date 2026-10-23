"""Constrain syntax/identifiers; semantic and evidence validators still decide acceptance."""
import copy
def editorial_schema(packet):
    required=packet.get('required_checks')
    passages=packet.get('evidence_passages')
    if not required or not passages:return None
    evidence={'type':'array','items':{'type':'string','enum':[p['id'] for p in passages]},'minItems':1,'maxItems':3}
    check={'type':'object','properties':{'verdict':{'type':'string','enum':['pass','fail','not_applicable']},'evidence_ids':evidence,'reason':{'type':'string'}},'required':['verdict','evidence_ids','reason'],'additionalProperties':False}
    issue={'type':'object','properties':{'severity':{'type':'string','enum':['blocking','advisory']},'category':{'type':'string','enum':required},'evidence_ids':evidence,'problem':{'type':'string'},'fix':{'type':'string'},'replacement':{'type':'string'}},'required':['severity','category','evidence_ids','problem','fix','replacement'],'additionalProperties':False}
    checks={key:copy.deepcopy(check) for key in required}
    for key,spec in checks.items():
        if key not in {'subplot_function','reference_application'}:
            spec['properties']['verdict']['enum']=['pass','fail']
    return {'type':'object','properties':{'pass':{'type':'boolean'},'checks':{'type':'object','properties':checks,'required':list(required),'additionalProperties':False},'issues':{'type':'array','items':issue}},'required':['pass','checks','issues'],'additionalProperties':False}


def memory_schema(packet,character_ids,allow_public=True,prior_memories=None):
    ids=[p['id'] for p in packet['evidence_passages']]
    item={'type':'object','properties':{'kind':{'type':'string','enum':['event','belief','claim','resource','relationship','thread']},'text':{'type':'string','minLength':1,'maxLength':600},'evidence_ids':{'type':'array','items':{'type':'string','enum':ids},'minItems':1,'maxItems':3},'known_by':{'type':'array','items':{'type':'string','enum':character_ids+(['public'] if allow_public else [])}},'holder':{'type':'string','enum':character_ids},'claim_source':{'type':'string','enum':character_ids}},'required':['kind','text','evidence_ids','known_by'],'additionalProperties':False}
    item['properties'].update(subject={'type':'string','enum':character_ids},life_state={'type':'string','enum':['alive','dead','missing','unknown']},thread_id={'type':'string'},thread_state={'type':'string','enum':['seeded','escalating','payoff','closed']})
    if prior_memories is not None:
        item['properties']['fact_key']={'type':'string'}
        item['required']+=['fact_key','supersedes']
        updatable=[m['id'] for m in prior_memories if m.get('fact_key')]
        item['properties']['supersedes']={'type':'array','items':{'type':'string','enum':updatable} if updatable else {'type':'string'},'maxItems':3 if updatable else 0}
    return {'type':'object','properties':{'memories':{'type':'array','items':item,'maxItems':12 if prior_memories is not None else 6}},'required':['memories'],'additionalProperties':False}


def continuity_schema(memory_count):
    properties={k:{'type':'string'} for k in ['location','elapsed_time','weapon_custody','obligations','irreversible_changes']}
    properties.update({k:{'type':['integer','null'],'minimum':0,'maximum':1000} for k in ['charges_remaining','charges_used_this_scene']})
    indices={'type':'array','items':{'type':'integer'},'maxItems':memory_count}
    if memory_count:indices['items']['enum']=list(range(memory_count))
    properties['approved_memory_indices']=indices
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def refinement_schema():
    """Match contracts.refinement; never fill missing creative content ourselves."""
    strings = ['original_prompt', 'refined_prompt', 'central_conflict', 'reader_experience']
    arrays = ['preserved_user_choices', 'expanded_story_elements', 'character_tensions',
              'subplot_possibilities', 'world_constraints', 'suggested_techniques',
              'retrieval_references', 'assumptions', 'open_decisions']
    properties = {key: {'type': 'string', 'minLength': 1} for key in strings}
    properties.update({key: {'type': 'array', 'items': {'type': 'string'},'maxItems':12} for key in arrays})
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def plan_schema(req):
    """Constrain the complete outline, including fields required after scenes."""
    ids=[c['id'] for c in req['characters']]
    total=req['chapters']*req['scenes_per_chapter']
    scene_ids=[f'ch{i // req["scenes_per_chapter"] + 1:02}-sc{i % req["scenes_per_chapter"] + 1:02}' for i in range(total)]
    properties={key:{'type':'string','minLength':1} for key in ['goal','obstacle','intended_change','location','time']}
    properties.update({'id':{'type':'string','enum':scene_ids},
                       'chapter':{'type':'integer','enum':list(range(1,req['chapters']+1))},
                       'pov':{'type':'string','enum':ids},
                       'participants':{'type':'array','items':{'type':'string','enum':ids},'minItems':1,'maxItems':len(ids)}})
    if req.get('performance',{}).get('application_plan_binding'):
        properties.pop('id');properties.pop('chapter')
    scene={'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    return {'type':'object','properties':{
        'scenes':{'type':'array','items':scene,'minItems':total,'maxItems':total},
        'threads':{'type':'array','items':{'type':'string'},'maxItems':12}},
        'required':['scenes','threads'],'additionalProperties':False}


def scene_schema(req,packet):
    scene=plan_schema(req)['properties']['scenes']['items']
    card=packet.get('proposed_scene',{})
    scene['properties'].update({'id':{'type':'string','enum':[card['id']]} if 'id' in card else {'type':'string'},'chapter':{'type':'integer','enum':[card['chapter']]} if 'chapter' in card else {'type':'integer'}})
    scene['properties'].update({key:{'type':'string','minLength':1} for key in ['choice','consequence','new_development']})
    refs=packet.get('inspiration',{}).get('references',[])
    item={'type':'object','properties':{'record_id':{'type':'string','enum':[r['id'] for r in refs]} if refs else {'type':'string'},'application':{'type':'string'}},'required':['record_id','application'],'additionalProperties':False}
    scene['properties']['reference_uses']={'type':'array','items':item,'maxItems':len(refs)}
    scene['required']=list(scene['properties'])
    count=packet.get('writing_batch_count')
    if count:
        fields={k:{'type':'string','minLength':1} for k in ['action','entry_state','exit_state']}
        scene['properties']['writing_beats']={'type':'array','items':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False},'minItems':count,'maxItems':count}
        scene['required'].append('writing_beats')
    from .universe_events import freedom
    f=freedom(req)
    if f['enabled'] and f['new_characters']:
        # IDs may refer to profiles declared in this same atomic scene proposal.
        scene['properties']['participants']['maxItems']=min(8,len(req['characters'])+f['max_new_per_scene'])
        scene['properties']['participants']['items']={'type':'string'}
        scene['properties']['pov']={'type':'string'}
        fields={k:{'type':'string'} for k in ['id','name','goal','voice','introduction_cause']}
        scene['properties']['new_characters']={'type':'array','items':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False},'maxItems':f['max_new_per_scene']}
    return scene


def memory_review_schema():
    issue={'type':'object','properties':{k:{'type':'string'} for k in ['category','quote','problem','fix']},'required':['severity','category','quote','problem','fix'],'additionalProperties':False}
    issue['properties']['severity']={'type':'string','enum':['blocking','advisory']}
    issue['properties']['target']={'type':'string','enum':['memory','prose']}
    issue['required'].append('target')
    return {'type':'object','properties':{'pass':{'type':'boolean'},'issues':{'type':'array','items':issue}},'required':['pass','issues'],'additionalProperties':False}
