"""Full prompt-to-story process in one resident runner, with source-bound checkpoints."""
from __future__ import annotations
import argparse,json,os,shutil,time,hashlib
from pathlib import Path
from .dag import stage
from .storage import load,save
from .inference import Executor,ROOT
from .batch_review import review as batch_review
from .tracking import tracked_stage


@tracked_stage
def audit(task,source,out,index=0,character=None,request_file=None,profile=None,backend='fixture'):
    state=load(Path(source)/'state/snapshot.json');req=state['request']
    prose=(Path(source)/'edited/prose.txt').read_text()
    batch_review(Executor(req,out,backend),req,state,state['plan']['scenes'][index],prose,out)


def run(folder,request_file='troy-full-api',profile='fast',backend='worker'):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    # All Executor instances and actor calls share a single cross-process ledger.
    quota=folder/'provider-budget';os.environ['STORY_QUOTA_DIR']=str(quota)
    timeline=[];started=time.monotonic()
    if backend=='worker':
        from .hosted import GoogleHosted
        hosted=GoogleHosted(quota);health={}
        for kind in ['gemma','flash']:
            before=time.monotonic()
            try:
                _,diag=hosted.complete(kind,'Return only OK.','Connection and output compatibility check.',128,role='health_probe')
                health[kind]={'available':True,'diagnostic':diag}
            except Exception as exc:health[kind]={'available':False,'error':str(exc)}
            health[kind]['seconds']=round(time.monotonic()-before,3)
            save(folder/'provider-health.json',health)
        print('Provider compatibility checks: '+json.dumps(health),flush=True)
    def execute(name,task,state=None,extras=(),index=0,character=None,fn=stage):
        work=folder/'stages'/name;inputs=work/'inputs';out=work/'out'
        inputs.mkdir(parents=True,exist_ok=True)
        if state:save(inputs/'state/snapshot.json',load(state/'snapshot.json'))
        for src,target in extras:shutil.copytree(src,inputs/target,dirs_exist_ok=True)
        mark=time.monotonic()
        save(folder/'progress.json',{'phase':name,'started_at':time.time(),'elapsed_seconds':round(time.monotonic()-started,3)})
        if os.getenv('GITHUB_ACTIONS')=='true':print('::group::Full process: '+name,flush=True)
        print(f'Full process: {name}',flush=True)
        try:
            fn(task,inputs,out,index,character,request_file,profile,backend)
        finally:
            if os.getenv('GITHUB_ACTIONS')=='true':print('::endgroup::',flush=True)
            timeline.append({'stage':name,'seconds':round(time.monotonic()-mark,3),'elapsed_seconds':round(time.monotonic()-started,3)})
            save(folder/'phase-timings.json',timeline)
            # Source outputs and raw calls remain in their authoritative stage folders.
            shutil.rmtree(inputs,ignore_errors=True)
        if (out/'snapshot.json').exists():save(folder/'latest-state.json',load(out/'snapshot.json'))
        return out
    state=execute('prepare','prepare')
    for kind in ['refine','plan']:
        state=execute(kind,kind,state)
        state=execute(kind+'_review',kind+'_review',state)
        state=execute(kind+'_revision',kind+'_revision',state,[(state,'design-review')])
        state=execute(kind+'_gate',kind+'_gate',state)
    req=load(state/'snapshot.json')['request']
    for i in range(req['chapters']*req['scenes_per_chapter']):
        prefix=f's{i+1:02}'
        state=execute(prefix+'_design','scene_design',state,index=i)
        card=load(state/'snapshot.json')['plan']['scenes'][i]
        proposals=[]
        for cid in card['participants']:
            actor=execute(prefix+'_actor_'+cid,'character',state,index=i,character=cid)
            proposals.append((actor,'characters/'+cid))
        direction=execute(prefix+'_direction','director',state,proposals,index=i)
        draft=execute(prefix+'_draft','writer',state,[(direction,'direction')],index=i)
        edited=execute(prefix+'_edit','edit',state,[(draft,'draft')],index=i)
        reviewed=execute(prefix+'_review','review',state,[(edited,'edited')],index=i,fn=audit)
        repaired=execute(prefix+'_repair','repair',state,[(edited,'edited'),(reviewed/'story','diagnosis'),(reviewed/'rhetoric','rhetoric')],index=i)
        repair=load(repaired/'repair.json')
        changed=repair['changed']
        actual=hashlib.sha256((repaired/'prose.txt').read_text().encode()).hexdigest()
        from .contracts import require
        require(actual==repair['candidate_sha256'],'Repair metadata does not match candidate text')
        if not changed:require(actual==repair['reviewed_sha256'],'Changed prose cannot reuse its old review')
        if changed:
            reviewed=execute(prefix+'_verify','review',state,[(repaired,'edited')],index=i,fn=audit)
        # Record all accepted-text facts, resources and changes in one delta,
        # after revision, then independently check it before committing canon.
        memory=execute(prefix+'_memory','memory',state,[(repaired,'edited')],index=i)
        verified=execute(prefix+'_memory_review','memory_review',state,[(repaired,'edited'),(memory,'memory')],index=i)
        state=execute(prefix+'_accept','accept',state,[(repaired,'edited'),(reviewed/'story','story-review'),(reviewed/'rhetoric','rhetoric-review'),(memory,'memory'),(verified,'memory-review')],index=i)
    final=load(state/'snapshot.json')
    shutil.copytree(state,folder/'final',dirs_exist_ok=True)
    if final['completion_status']=='complete':
        save(folder/'FINAL_STORY.txt',(state/'story.txt').read_text())
    else:save(folder/'PROVISIONAL_STORY.txt',(state/'story.txt').read_text())
    calls=[]
    for path in (folder/'stages').glob('*/out/calls/*.json'):
        value=load(path);calls.append({k:value.get(k) for k in ['role','model','seconds','diagnostic']})
    roles={}
    for call in calls:
        summary=roles.setdefault(call['role'],{'calls':0,'seconds':0,'models':[]})
        summary['calls']+=1;summary['seconds']+=call.get('seconds') or 0
        if call.get('model') not in summary['models']:summary['models'].append(call.get('model'))
    save(folder/'benchmark.json',{'elapsed_seconds':round(time.monotonic()-started,3),'completion_status':final['completion_status'],
        'phases':timeline,'roles':roles,'calls':calls,'provider_budget':load(quota/'quota.json') if (quota/'quota.json').exists() else {},
        'skill_bytes':{p.name:p.stat().st_size for p in (ROOT/'skills').glob('*.md')}})
    return final

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True)
    parser.add_argument('--request-file',default='troy-full-api');parser.add_argument('--backend',default='worker',choices=['worker','fixture'])
    args=parser.parse_args();run(args.out,args.request_file,backend=args.backend)
