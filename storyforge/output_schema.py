"""Constrain syntax/identifiers; semantic and evidence validators still decide acceptance."""
def editorial_schema(packet):
    required=packet.get('required_checks')
    passages=packet.get('evidence_passages')
    if not required or not passages:return None
    evidence={'type':'array','items':{'type':'string','enum':[p['id'] for p in passages]},'minItems':1,'maxItems':3}
    check={'type':'object','properties':{'verdict':{'type':'string','enum':['pass','fail','not_applicable']},'evidence_ids':evidence,'reason':{'type':'string'}},'required':['verdict','evidence_ids','reason'],'additionalProperties':False}
    issue={'type':'object','properties':{'severity':{'type':'string','enum':['blocking','advisory']},'category':{'type':'string','enum':required},'evidence_ids':evidence,'problem':{'type':'string'},'fix':{'type':'string'},'replacement':{'type':'string'}},'required':['severity','category','evidence_ids','problem','fix','replacement'],'additionalProperties':False}
    return {'type':'object','properties':{'pass':{'type':'boolean'},'checks':{'type':'object','properties':{key:check for key in required},'required':list(required),'additionalProperties':False},'issues':{'type':'array','items':issue}},'required':['pass','checks','issues'],'additionalProperties':False}


def memory_schema(packet,character_ids,allow_public=True):
    ids=[p['id'] for p in packet['evidence_passages']]
    item={'type':'object','properties':{'kind':{'type':'string','enum':['event','belief','claim','resource','relationship','thread']},'text':{'type':'string'},'evidence_ids':{'type':'array','items':{'type':'string','enum':ids},'minItems':1,'maxItems':3},'known_by':{'type':'array','items':{'type':'string','enum':character_ids+(['public'] if allow_public else [])}},'holder':{'type':'string','enum':character_ids},'claim_source':{'type':'string','enum':character_ids}},'required':['kind','text','evidence_ids','known_by'],'additionalProperties':False}
    return {'type':'object','properties':{'memories':{'type':'array','items':item,'maxItems':6}},'required':['memories'],'additionalProperties':False}


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
    properties.update({key: {'type': 'array', 'items': {'type': 'string'}} for key in arrays})
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def plan_schema(req):
    """Constrain the complete outline, including fields required after scenes."""
    ids=[c['id'] for c in req['characters']]
    total=req['chapters']*req['scenes_per_chapter']
    scene_ids=[f'ch{i // req["scenes_per_chapter"] + 1:02}-sc{i % req["scenes_per_chapter"] + 1:02}' for i in range(total)]
    properties={key:{'type':'string','minLength':1} for key in ['goal','obstacle','intended_change','location','time']}
    properties.update({'id':{'type':'string','enum':scene_ids},
                       'chapter':{'type':'integer','minimum':1,'maximum':req['chapters']},
                       'pov':{'type':'string','enum':ids},
                       'participants':{'type':'array','items':{'type':'string','enum':ids},'minItems':1,'maxItems':len(ids)}})
    scene={'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    return {'type':'object','properties':{
        'scenes':{'type':'array','items':scene,'minItems':total,'maxItems':total},
        'threads':{'type':'array','items':{'type':'string'},'maxItems':12}},
        'required':['scenes','threads'],'additionalProperties':False}
