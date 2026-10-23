"""Independent passage editors; one source-bound, deterministic merge."""
from .contracts import require
from .evidence import passages
from .patching import apply, digest


def batches(prose, count=4):
    catalog=passages(prose);count=min(count,len(catalog));result=[]
    for i in range(count):
        start=i*len(catalog)//count;end=(i+1)*len(catalog)//count
        result.append({'id':str(i),'source_sha256':digest(prose),'owned':[p['id'] for p in catalog[start:end]],'passages':[{'id':p['id'],'text':p['text']} for p in catalog[max(0,start-1):min(len(catalog),end+1)]]})
    return result


def validate(value, batch):
    require(isinstance(value,dict) and isinstance(value.get('replacements'),dict),'Editor requires replacements')
    require(set(value['replacements'])<=set(batch['owned']),'Editor changed an unowned paragraph')
    require(all(isinstance(v,str) and (batch.get('allow_deletions') or v.strip()) for v in value['replacements'].values()),'Editors cannot delete paragraphs')
    return value


def merge(prose, plan, results):
    require(plan and all(b['source_sha256']==digest(prose) for b in plan),'Stale edit plan')
    require(len(results)==len(plan) and {r['id'] for r in results}=={b['id'] for b in plan},'Missing or duplicate editor batch')
    edits={}
    for batch in plan:
        result=next(r for r in results if r['id']==batch['id'])
        require(result['source_sha256']==digest(prose),'Stale editor result');validate(result,batch)
        require(not set(edits)&set(result['replacements']),'Conflicting edit ownership')
        edits.update(result['replacements'])
    return apply(prose,edits,digest(prose))


def schema(batch):
    return {'type':'object','properties':{'replacements':{'type':'object','properties':{p:{'type':'string'} for p in batch['owned']},'additionalProperties':False}},'required':['replacements'],'additionalProperties':False}
