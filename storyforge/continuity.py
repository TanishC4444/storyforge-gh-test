"""Conservative controller normalization; keep rejected metadata without inventing facts."""
from .contracts import require
from .evidence import passages
import re


def validate(value,count):
    require(isinstance(value,dict),'Continuity must be an object')
    result=dict(value);raw=result.get('approved_memory_indices',[])
    require(isinstance(raw,list),'Approval indices must be an array')
    approved=[];invalid=[]
    for index in raw:
        if isinstance(index,str) and index.isdecimal():index=int(index)
        if type(index) is int and 0<=index<count:approved.append(index)
        else:invalid.append(index)
    result['approved_memory_indices']=sorted(set(approved))
    if invalid:result['quarantined_approval_indices']=invalid
    for field in ['charges_remaining','charges_used_this_scene']:
        number=result.get(field)
        if isinstance(number,str) and number.isdecimal():number=int(number)
        if number is not None and (type(number) is not int or number<0):
            result.setdefault('quarantined_counts',{})[field]=number;number=None
        result[field]=number
    return result


def source_notes(prose):
    selected=[p for p in passages(prose) if re.search(r'(?i)\b(?:burn\w*|blister\w*|damp\w*|suspect|remaining|seal|pledge|injur\w*|bandag\w*)\b',p['text'])]
    return [{'id':p['id'],'text':p['text']} for p in selected[-3:]]


def reconcile(ledger,prior,scene_index):
    result=dict(ledger)
    previous=prior.get('charges_remaining') if prior else None
    current=result.get('charges_remaining');reported=result.get('charges_used_this_scene')
    if scene_index>1 and type(previous) is int and type(current) is int and current<=previous:
        result['net_charge_count_reduction']=previous-current
        if reported is not None and reported!=previous-current:
            result['quarantined_reported_usage']=reported
            result['charges_used_this_scene']=None
            result['count_warning']='Reported usage conflicts with remaining counts; consult source passages. Net count reduction is a projection, not an invented firing event.'
    return result
