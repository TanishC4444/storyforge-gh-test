"""Constrain syntax/identifiers; semantic and evidence validators still decide acceptance."""
def editorial_schema(packet):
    required=packet.get('required_checks')
    passages=packet.get('evidence_passages')
    if not required or not passages:return None
    evidence={'type':'array','items':{'type':'string','enum':[p['id'] for p in passages]},'minItems':1,'maxItems':3}
    check={'type':'object','properties':{'id':{'type':'string','enum':required},'verdict':{'type':'string','enum':['pass','fail','not_applicable']},'evidence_ids':evidence,'reason':{'type':'string'}},'required':['id','verdict','evidence_ids','reason'],'additionalProperties':False}
    issue={'type':'object','properties':{'severity':{'type':'string','enum':['blocking','advisory']},'category':{'type':'string','enum':required},'evidence_ids':evidence,'problem':{'type':'string'},'fix':{'type':'string'}},'required':['severity','category','evidence_ids','problem','fix'],'additionalProperties':False}
    return {'type':'object','properties':{'pass':{'type':'boolean'},'checks':{'type':'array','items':check,'minItems':len(required),'maxItems':len(required)},'issues':{'type':'array','items':issue}},'required':['pass','checks','issues'],'additionalProperties':False}
