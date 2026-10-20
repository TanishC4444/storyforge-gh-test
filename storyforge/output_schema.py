"""Constrain syntax/identifiers; semantic and evidence validators still decide acceptance."""
def editorial_schema(packet):
    required=packet.get('required_checks')
    passages=packet.get('evidence_passages')
    if not required or not passages:return None
    evidence={'type':'array','items':{'type':'string','enum':[p['id'] for p in passages]},'minItems':1,'maxItems':3}
    check={'type':'object','properties':{'verdict':{'type':'string','enum':['pass','fail','not_applicable']},'evidence_ids':evidence,'reason':{'type':'string'}},'required':['verdict','evidence_ids','reason'],'additionalProperties':False}
    issue={'type':'object','properties':{'severity':{'type':'string','enum':['blocking','advisory']},'category':{'type':'string','enum':required},'evidence_ids':evidence,'problem':{'type':'string'},'fix':{'type':'string'}},'required':['severity','category','evidence_ids','problem','fix'],'additionalProperties':False}
    return {'type':'object','properties':{'pass':{'type':'boolean'},'checks':{'type':'object','properties':{key:check for key in required},'required':list(required),'additionalProperties':False},'issues':{'type':'array','items':issue}},'required':['pass','checks','issues'],'additionalProperties':False}
