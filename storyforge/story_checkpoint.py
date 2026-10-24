"""Preserve a resumable episode boundary independently of its eventual approval."""
import argparse,hashlib,json,re,shutil
from pathlib import Path
from .storage import load,save


def approved(scene):
    return bool(scene.get('canon_committed') and scene.get('quality_status')=='reviewed' and all(scene.get(k,{}).get('pass') and not scene.get(k,{}).get('unverified') for k in ['review','rhetoric_review','memory_review']))


def preserve(source,out,expected=None):
    source=Path(source);out=Path(out)
    seed=source/'quickstart/seed-results'
    if seed.exists():
        for folder in seed.iterdir():
            if folder.is_dir() and not (source/folder.name).exists():shutil.copytree(folder,source/folder.name)
    candidates=[]
    for path in source.glob('s*_accept/snapshot.json'):
        state=load(path)
        valid=all(approved(s) for s in state.get('accepted',[]))
        # If source proof artifacts are present, flags alone cannot establish a
        # safe recovery boundary. Old native reruns may leave stale proofs.
        if valid:
            from .episode_audit import audit
            has_proofs=any(source.glob('s*_memory_review/review.json')) or any(source.glob('s*_accept/consumed-proof.json'))
            if has_proofs:
                import tempfile
                with tempfile.TemporaryDirectory() as d:
                    assessment=audit(source,Path(d),len(state['accepted']))
                valid=all(r['approved'] and r['factual_proof_bound'] for r in assessment['scenes'][:len(state['accepted'])])
        if valid:candidates.append((len(state['accepted']),path,state))
    if candidates:
        count,path,state=max(candidates,key=lambda x:x[0])
    else:
        path=source/'quickstart/snapshot.json';state=load(path) if path.exists() else None;count=0
    if state is not None:save(out/'checkpoint/snapshot.json',state)
    total=len(state.get('plan',{}).get('scenes',[])) if state else 0
    if expected is not None:total=min(total,expected)
    drafts=[];partial_batches=[]
    for number in range(1,5):
        prefix=f's{number:02}';chosen=None
        for suffix in ['final_check','repair','draft']:
            folder=source/(prefix+'_'+suffix);text=folder/'prose.txt'
            if text.exists():chosen=(folder,text);break
        if chosen:
            folder,text=chosen;prose=text.read_text();target=out/'drafts'/prefix
            save(target/'prose.txt',prose)
            for name in ['repair.json','editorial-adjudication.json']:
                if (folder/name).exists():shutil.copy2(folder/name,target/name)
            drafts.append({'scene':number,'source_artifact':folder.name,'words':len(prose.split()),'sha256':hashlib.sha256(prose.encode()).hexdigest(),'approved':number<=count})
        for folder in sorted(source.glob(prefix+'_write_batches-*')):
            batch=folder/'draft-batch.json';texts=[]
            if batch.exists():
                text=load(batch).get('prose','')
                if isinstance(text,str) and text.strip():texts.append(('draft.txt',text))
            for i,path in enumerate(sorted(folder.rglob('incomplete-generation.json'))):
                item=load(path)
                if item.get('role') in {'writer','writer_beat','repair','humanizer'} and isinstance(item.get('text'),str) and item['text'].strip():texts.append((f'incomplete-{i}.txt',item['text']))
            for name,text in texts:
                save(out/'partial-batches'/folder.name/name,text)
                partial_batches.append({'scene':number,'source_artifact':folder.name,'file':name,'words':len(text.split()),'approved':False})
    result={'version':1,'mode':'retry_same_episode','completed_scenes':count,'completed_scene_ids':[s['id'] for s in state.get('accepted',[])] if state else [],'total_scenes':total,'resume_scene':count+1 if count<total or not total else None,'drafts':drafts,'partial_batches':partial_batches,'checkpoint_available':state is not None,'policy':'Completed approved scenes and full memory are retained. Failed scene prose is saved separately and never promoted to canon. Resume saved story can restart the unfinished scene, editing, or memory stage using the original run artifacts.'}
    save(out/'recovery.json',result)
    save(out/'RECOVERY.md',f'# Saved story recovery\n\n{count} completed scene(s) retained. '+(f'Resume at scene {result["resume_scene"]}.' if result['resume_scene'] else 'This episode is complete.')+'\n\nUse **Resume saved story** in Actions with the original run ID. Choose **editing** to keep the written draft, **memory** to retry factual processing, or **scene** to rebuild only the unfinished scene and its dependents. Completed earlier scenes are reused. The backup is uploaded before any retry. GitHub retries use the original run revision. The universe continuation input is separate; it starts a new episode.\n')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default='results');p.add_argument('--out',default='recovery');p.add_argument('--expected',type=int);a=p.parse_args();preserve(a.source,a.out,a.expected)

if __name__=='__main__':main()
