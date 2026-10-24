"""Report manuscript approval independently of Actions job completion."""
import argparse,json,os
from pathlib import Path
from .storage import load,save
from .patching import digest
from .batch_pipeline import bind_state
from .canon import index


def audit(source,out,expected):
    source=Path(source);snapshots=[load(p) for p in source.glob('s*_accept/snapshot.json')]
    state=max(snapshots,key=lambda x:len(x.get('accepted',[])),default={});scenes=state.get('accepted',[])
    target=min(expected,len(state.get('plan',{}).get('scenes',[]))) if state else expected
    errors=[];rows=[]
    if len(scenes)!=target:errors.append(f'Expected {target} scenes; found {len(scenes)}')
    for i,scene in enumerate(scenes):
        p=f's{i+1:02}';proof_path=source/(p+'_memory_review/review.json');facts_path=source/(p+'_final_memory/memory.json');state_path=source/(p+'_design/snapshot.json')
        recovered=source/(p+'_memory_recovery_join')
        if recovered.exists():
            # Acceptance consumes this exact pair after bounded recovery. Never
            # fall back to an older passing ledger if recovered proof is invalid.
            proof_path=recovered/'review.json';facts_path=recovered/'memory.json'
        receipt=source/(p+'_accept')
        if (receipt/'acceptance-binding.json').exists():
            proof_path=receipt/'consumed-proof.json';facts_path=receipt/'consumed-memory.json';state_path=receipt/'acceptance-state.json'
        bound=False
        if all(p.exists() for p in [proof_path,facts_path,state_path]):
            proof=load(proof_path)
            bound=bool(proof.get('pass') and not proof.get('unverified') and proof.get('source_sha256')==digest(scene['prose']) and proof.get('state_sha256')==bind_state(load(state_path)) and proof.get('memory_sha256')==bind_state(load(facts_path)))
        approved=bool(scene.get('canon_committed') and scene.get('quality_status')=='reviewed' and all(scene.get(k,{}).get('pass') and not scene.get(k,{}).get('unverified') for k in ['review','rhetoric_review','memory_review']))
        rows.append({'scene':scene['id'],'approved':approved,'factual_proof_bound':bound,'words':len(scene['prose'].split())})
        if not approved:errors.append(scene['id']+': literary or factual approval unresolved')
        if not bound:errors.append(scene['id']+': final factual proof is absent or stale')
    history=state.get('memories',[]);initial=state.get('request',{}).get('initial_facts',[])
    retained=[m for m in history if m.get('source')=='user_input']
    for fact in initial:
        if not any(all(record.get(k)==v for k,v in fact.items()) for record in retained):errors.append('A source initial fact was dropped or altered')
    try:view=index(history)
    except ValueError as exc:view={'current':[]};errors.append(str(exc))
    result={'pass':not errors,'errors':errors,'scenes':rows,'expected_scenes':target,'cast':len(state.get('request',{}).get('characters',[])),'rules':len(state.get('request',{}).get('world_rules',[])),'initial_memory_facts':len(initial),'retained_initial_facts':len(retained),'memory_history_facts':len(history),'current_memory_facts':len(view['current']),'note':'Approvals and source bindings are checked separately from job success. Runtime is measured from GitHub run timestamps; automated approval is not a guarantee of literary excellence.'}
    save(Path(out)/'episode-audit.json',result)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('\n### Episode approval audit\n\n'+json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',default='results');p.add_argument('--out',default='audit');p.add_argument('--expected',type=int,required=True);args=p.parse_args()
    result=audit(args.source,args.out,args.expected)
    if not result['pass']:raise SystemExit('Episode not approved; inspect episode-audit.json and preserved drafts')
