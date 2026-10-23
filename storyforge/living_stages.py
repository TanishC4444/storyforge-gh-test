"""Runner-scoped Living stages. Only artifact bookkeeping is fused; role calls stay separate."""
from __future__ import annotations
import argparse,shutil,time,os,json,re,fnmatch
from pathlib import Path
from .storage import load,save
from .contracts import require,delta
from . import batch_pipeline as b,memory_batches as m
from .dag import stage


def copy_file(source,dest):
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)


def arrange(incoming='incoming',source='inputs',manifest=None,needs=None):
    manifest=manifest if manifest is not None else json.loads(os.environ['STORY_ARTIFACT_MANIFEST'])
    needs=needs if needs is not None else json.loads(os.environ['STORY_UPSTREAM_NEEDS'])
    incoming=Path(incoming);source=Path(source)
    for spec in manifest:
        if spec.get('condition'):
            match=re.search(r"needs\.([a-zA-Z0-9_]+)\.outputs\.([a-zA-Z0-9_]+)",spec['condition'])
            require(match is not None,'Unsupported artifact condition')
            if needs.get(match[1],{}).get('outputs',{}).get(match[2])!='true':continue
        names=[p for p in incoming.iterdir() if p.is_dir() and fnmatch.fnmatch(p.name,spec['name'])]
        require(bool(names),'Missing required upstream artifact: '+spec['name'])
        for folder in names:
            target=source/spec['path']/(folder.name if spec['pattern'] else '')
            shutil.copytree(folder,target,dirs_exist_ok=True)


def execute(task,source,out,index=0,backend='fixture'):
    source=Path(source);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    state=load(source/'state/snapshot.json');card=state['plan']['scenes'][index]
    if task=='direction_plan':
        stage('director',source,out/'direction',index=index,backend=backend)
        b.plan_draft(state,card,out,out,backend)
    elif task=='draft_extract_plan':
        prose=b.merge_draft(state,source,out);save(out/'prose.txt',prose)
        save(out/'work/edited/prose.txt',prose);m.extract_plan(state,out/'work',out)
    elif task=='memory_compile_plan':
        facts=m.extract_join(state,source,out)
        save(source/'memory/memory.json',facts);m.plan(state,source,out,'preflight')
    elif task=='repair_plan':
        for kind in ['story','rhetoric']:
            work=out/'work'/kind
            copy_file(source/'edited/prose.txt',work/'edited/prose.txt')
            shutil.copytree(source/(kind+'-batches'),work/'batches',dirs_exist_ok=True)
            verdict=b.join_reviews(state,work,out/(kind+'-review'),kind)
            save(source/(kind+'-review')/'review.json',verdict)
        b.plan_repairs(state,source,out)
        copy_file(source/'memory-review/review.json',out/'memory-review/review.json')
    elif task=='repair_refresh_plan':
        prose=b.merge_repairs(state,source,out)
        work=out/'work';save(work/'edited/prose.txt',prose)
        copy_file(source/'edited/prose.txt',work/'original/prose.txt')
        copy_file(source/'initial-memory/memory.json',work/'initial-memory/memory.json')
        copy_file(source/'preflight-memory/review.json',work/'preflight-memory/review.json')
        plan=m.refresh_plan(state,work,out)
        b.output('refresh_required',any(x['ids'] for x in plan['batches']))
    elif task=='final_memory_plan':
        plan=load(source/'plan/extract-plan.json')
        if not any(x['ids'] for x in plan['batches']):
            for batch in plan['batches']:m.extract_batch(state,card,source,source/'batches'/batch['id'],backend,batch['id'])
        facts=m.extract_join(state,source,out);save(source/'memory/memory.json',facts)
        plan=m.plan(state,source,out,'final')
        reused=bool(plan.get('reused_preflight'));b.output('checks_required',not reused)
        if reused:
            save(source/'plan/memory-plan.json',plan)
            m.check(state,card,source,source/'check-batches/reuse',backend,'reuse')
            shutil.copytree(source/'check-batches',source/'batches',dirs_exist_ok=True)
            m.join(state,source,out)
    elif task=='memory_final_join':
        proof=source/'memory/review.json'
        if proof.exists():
            review=load(proof);facts=load(source/'memory/memory.json')
            require(review.get('pass') and review.get('state_sha256')==b.bind_state(state) and review.get('source_sha256')==b.digest((source/'edited/prose.txt').read_text()) and review.get('memory_sha256')==b.bind_state(facts),'Stale reused final factual proof')
            save(out/'review.json',review)
        else:m.join(state,source,out)
    elif task=='finalize':
        # The repair-plan artifact carries compiled, source-bound literary findings.
        for kind in ['story-review','rhetoric-review','memory-review']:
            copy_file(source/'findings'/kind/'review.json',source/kind/'review.json')
        b.finalize(state,card,source,out,backend)
    elif task=='accept':
        final=load(source/'edited/repair.json')['editorial_adjudication']
        save(source/'story-review/review.json',final['story']);save(source/'rhetoric-review/review.json',final['rhetoric'])
        stage('accept',source,out,index=index,backend=backend)
    else:raise ValueError('Unknown Living runner stage')


def main():
    p=argparse.ArgumentParser();p.add_argument('task');p.add_argument('--source',default='inputs');p.add_argument('--out',default='out');p.add_argument('--index',type=int,default=0);p.add_argument('--backend',choices=['fixture','worker'],default='fixture');args=p.parse_args()
    if args.task=='arrange':arrange();return
    started=time.monotonic();execute(args.task,args.source,args.out,args.index,args.backend)
    status=Path(args.out)/'status.json'
    if not status.exists():save(status,{'task':args.task,'status':'success','elapsed_seconds':round(time.monotonic()-started,3),'fixture':args.backend=='fixture'})

if __name__=='__main__':main()
