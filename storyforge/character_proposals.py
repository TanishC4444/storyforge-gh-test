"""Concurrent, isolated actor requests; coordinator alone handles CPU fallback."""
import hashlib,json,copy
from concurrent.futures import ThreadPoolExecutor
from .coordinator import compact,visible
from .storage import save,load
from .inference import Executor
from .hosted import MODELS

INSTRUCTION='Propose one observable tactic and a concrete risk in at most 100 words, consistent with this character. Use only supplied known facts; future arc possibilities are character design, not events that have happened. Conceal private facts when motivated. No dialogue or hidden reasoning. This proposal is not canon.'

def actor_input(character,state,card,setting):
    return {'character_design':character,'visible_situation':{'location':card['location'],'time':card['time'],'setting':setting},'known_facts':compact(visible(state['memories'],character['id']))}

def propose(executor,req,state,card,setting,cast):
    kind=req.get('api_roles',{}).get('character')
    def hosted(character):
        data=actor_input(character,state,card,setting)
        digest=hashlib.sha256(json.dumps([kind,INSTRUCTION,data],sort_keys=True).encode()).hexdigest()[:20]
        path=executor.folder/'calls'/f'actor-{digest}.json'
        if path.exists():return character['id'],load(path)['output'],None
        save(executor.folder/'packets'/f'actor-{digest}.json',{'role':'character','input':data,'system':INSTRUCTION,'model':MODELS[kind]})
        try:
            print('Character '+character['id']+': independent API context',flush=True)
            text,diag=executor.hosted.complete(kind,INSTRUCTION,json.dumps(data,ensure_ascii=False),220,role='character')
            save(path,{'role':'character','model':diag['model'],'output':text,'diagnostic':diag})
            return character['id'],text,None
        except Exception as exc:return character['id'],None,str(exc)
    results=[]
    if executor.hosted and kind in MODELS:
        with ThreadPoolExecutor(max_workers=min(4,len(cast))) as pool:
            results=list(pool.map(hosted,cast))
    else:results=[(c['id'],None,None) for c in cast]
    proposals=[]
    for cid,text,error in results:
        if text is None:
            c=next(c for c in cast if c['id']==cid)
            local=copy.deepcopy(req);local['api_roles'].pop('character',None)
            if error:save(executor.folder/'actor-failures'/f'{cid}.json',{'error':error,'fallback':'existing_cpu_worker'})
            text=Executor(local,executor.folder/'actor-cpu'/cid,executor.backend).call('character',actor_input(c,state,card,setting),INSTRUCTION,tokens=220)
        proposal={'character':cid,'proposal':text,'source_scene_count':len(state['accepted'])}
        save(executor.folder/'characters'/card['id']/cid/'proposal.json',proposal)
        proposals.append(proposal)
    return proposals
