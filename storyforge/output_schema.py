"""Constrain syntax/identifiers; semantic and evidence validators still decide acceptance."""
def editorial_schema(packet):
    required=packet.get('required_checks')
    passages=packet.get('evidence_passages')
    if not required or not passages:return None
    evidence={'type':'array','items':{'type':'string','enum':[p['id'] for p in passages]},'minItems':1,'maxItems':3}
    check={'type':'object','properties':{'verdict':{'type':'string','enum':['pass','fail','not_applicable']},'evidence_ids':evidence,'reason':{'type':'string'}},'required':['verdict','evidence_ids','reason'],'additionalProperties':False}
    issue={'type':'object','properties':{'severity':{'type':'string','enum':['blocking','advisory']},'category':{'type':'string','enum':required},'evidence_ids':evidence,'problem':{'type':'string'},'fix':{'type':'string'},'replacement':{'type':'string'}},'required':['severity','category','evidence_ids','problem','fix','replacement'],'additionalProperties':False}
    return {'type':'object','properties':{'pass':{'type':'boolean'},'checks':{'type':'object','properties':{key:check for key in required},'required':list(required),'additionalProperties':False},'issues':{'type':'array','items':issue}},'required':['pass','checks','issues'],'additionalProperties':False}


def memory_schema(packet,character_ids):
    ids=[p['id'] for p in packet['evidence_passages']]
    item={'type':'object','properties':{'kind':{'type':'string','enum':['event','belief','claim','resource','relationship','thread']},'text':{'type':'string'},'evidence_ids':{'type':'array','items':{'type':'string','enum':ids},'minItems':1,'maxItems':3},'known_by':{'type':'array','items':{'type':'string','enum':character_ids+['public']}},'holder':{'type':'string','enum':character_ids},'claim_source':{'type':'string','enum':character_ids}},'required':['kind','text','evidence_ids','known_by'],'additionalProperties':False}
    return {'type':'object','properties':{'memories':{'type':'array','items':item,'maxItems':6}},'required':['memories'],'additionalProperties':False}
