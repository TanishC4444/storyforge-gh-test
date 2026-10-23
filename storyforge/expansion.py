"""Fast author-brief preparation and readable drafts for the classic runner graph."""
import argparse,copy,hashlib,json,os,re,time
from pathlib import Path
from .contracts import require
from .storage import load,save
from .craft import compile_brief,compile_scene_plan
from .canon import index
from .flow_common import fingerprint

BASELINE_RUN='39552359292'

def bible(req):return fingerprint({'universe_id':req.get('universe_id',req['project_id']),'world_rules':req['world_rules'],'setting':req.get('world_design',{}).get('setting','')})

def prepare(source,out,checkpoint=None):
    """Normalize explicit choices without LLM expansion or invented canon."""
    state=load(source);req=state['request'];out=Path(out)
    require(req.get('performance',{}).get('classic_expansion'),'This preparation requires an explicit expansion request')
    require(not req.get('execution_policy',{}).get('experimental'),'Classic expansion uses the established runner stages')
    started=time.monotonic();foundation=bible(req);episode=1;history=[]
    if checkpoint:
        prior=load(checkpoint)
        require(prior.get('backend')==state['backend'],'Cannot mix fixture and live universe canon')
        require(prior.get('universe_bible_hash')==foundation,'Universe bible differs; author a deliberate new universe instead')
        from .universe_events import resume_cast
        resume_cast(req,prior)
        require(prior.get('complete') and prior.get('accepted'),'Checkpoint must contain completed accepted scenes')
        require(all(s.get('quality_status')=='reviewed' and all(s.get(k,{}).get('pass') for k in ['review','rhetoric_review','memory_review']) for s in prior['accepted']),'Unreviewed prose cannot be imported as accepted universe canon')
        require(prior['request']['premise']!=req['premise'],'A resumed universe needs a new episode brief, not the same opening again')
        episode=prior['universe_episode']+1
        state['memories']=copy.deepcopy(prior['memories'])
        history=copy.deepcopy(prior.get('universe_history',[]))+[dict(s,universe_episode=prior['universe_episode']) for s in prior['accepted']]
    state['request_hash']=fingerprint(req)
    state.update(universe_bible_hash=foundation,universe_episode=episode,universe_history=history)
    state['canon']=index(state['memories'])
    state['refinement']=compile_brief(req)
    state['refinement_method']='application_compiled_author_brief_no_model_calls'
    state['plan']=compile_scene_plan(req);state['plan_approved']=True
    state['planning_provenance']={'method':'compiled_explicit_author_layout','model_development_review':False,'baseline_run':BASELINE_RUN,'note':'These remain proposed scene outcomes. Characters do not know future plans. Scene, prose and memory reviews follow.'}
    save(out/'refinement.json',state['refinement']);save(out/'plan.json',state['plan']);save(out/'snapshot.json',state)
    save(out/'status.json',{'task':'compile_author_brief','status':'success','phase':'success','elapsed_seconds':round(time.monotonic()-started,3),'model_calls_started':0,'refinement_method':state['refinement_method']})
    return state


def preview(source,label='Writer draft'):
    """Publish actual prose independently of eventual acceptance."""
    folder=Path(source);prose=None;status='unreviewed';origin=None
    for filename in ['final-prose.txt','prose.txt','draft.txt']:
        p=folder/filename
        if p.exists() and p.read_text().strip():prose=p.read_text();origin=filename;break
    if prose is None:
        # Even a rejected writer response is useful to inspect. It is never canon.
        calls=[]
        for p in (folder/'calls').glob('writer-*.json'):
            c=load(p)
            if isinstance(c.get('output'),str):calls.append((p.stat().st_mtime,p,c))
        if calls:
            _,p,c=max(calls);prose=c['output'];origin=str(p.relative_to(folder));status='rejected_or_incomplete_model_response'
    if prose is None:return None
    value={'label':label,'status':status,'source':origin,'sha256':hashlib.sha256(prose.encode()).hexdigest(),'words':len(prose.split()),'prose':prose}
    save(folder/'readable-draft.txt',label+'\n\nUNREVIEWED MODEL OUTPUT - NOT ACCEPTED CANON\n\n'+prose)
    save(folder/'preview.json',value)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        fence='`'*(max([len(s) for s in re.findall(r'`+',prose)]+[2])+1)
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('\n### '+label+'\n\nUnreviewed model output; '+str(value['words'])+' words. Review status is separate.\n\n'+fence+'text\n'+prose+'\n'+fence+'\n')
    return value


def collect(source,out):
    root=Path(source);out=Path(out);accepted=[];episodes=[]
    for p in root.glob('s*_accept/snapshot.json'):
        s=load(p)
        if s.get('accepted') and all(x.get('quality_status')=='reviewed' for x in s['accepted']):episodes.append(s)
    if episodes:
        best=max(episodes,key=lambda s:len(s['accepted']));accepted=best['accepted']
        save(out/'canon/snapshot.json',best)
    final_decisions={}
    for path in root.glob('s*_final_check/editorial-adjudication.json'):
        final_decisions[path.parent.name.split('_')[0]]=load(path)
    drafted=max([load(p) for p in root.glob('s*_accept/snapshot.json')],key=lambda s:len(s.get('accepted',[])),default={}).get('accepted',[])
    previews={}
    for p in root.rglob('preview.json'):
        # Only top-level scene jobs, not their repeated upstream input artifacts.
        job=p.relative_to(root).parts[0]
        if re.fullmatch(r's\d+_(draft|edit|repair)',job):previews[job]=load(p)
    ids=sorted({j.split('_')[0] for j in previews})
    sections=[]
    for sid in ids:
        item=next(previews[sid+'_'+phase] for phase in ['repair','edit','draft'] if sid+'_'+phase in previews)
        position=int(sid[1:])-1
        known=accepted[position] if position<len(accepted) else None
        reviewed=known is not None and hashlib.sha256(known['prose'].encode()).hexdigest()==item['sha256']
        status='reviewed' if reviewed else item['status']
        if not reviewed:
            decision=final_decisions.get(sid)
            if decision and (not decision['verdict'].get('pass') or decision.get('unverified')):status='provisional - final check unresolved'
            elif position<len(drafted) and drafted[position].get('quality_status')=='needs_review':status='provisional - verification unresolved'
        sections.append((sid,known['prose'] if reviewed else item['prose'],status))
    save(out/'READABLE_DRAFT.txt','CLASSIC UNIVERSE EXPANSION\nStatus applies separately to each scene. Unreviewed prose is not accepted canon.\n\n'+'\n\n* * *\n\n'.join(sid+' | '+status+'\n\n'+prose for sid,prose,status in sections))
    save(out/'reading-status.json',{'baseline_run':BASELINE_RUN,'scenes':[{'scene_id':sid,'status':status,'words':len(p.split())} for sid,p,status in sections],'accepted_scenes':len(accepted),'prose_available':bool(sections)})
    return sections


def main():
    p=argparse.ArgumentParser();p.add_argument('task',choices=['prepare','preview','collect']);p.add_argument('--source',default='inputs/state/snapshot.json');p.add_argument('--out',default='out');p.add_argument('--checkpoint');p.add_argument('--label',default='Writer draft');a=p.parse_args()
    if a.task=='prepare':prepare(a.source,a.out,a.checkpoint)
    elif a.task=='preview':preview(a.source,a.label)
    else:collect(a.source,a.out)

if __name__=='__main__':main()
