"""Reuse the classic runner DAG with fast preparation and parallel passage editors."""
from pathlib import Path
import copy,yaml
from scripts.build_workflow import build
ROOT=Path(__file__).resolve().parents[1]

def build_expansion(total=9,per_chapter=3):
    # Quote the YAML on key while preserving real numeric/boolean workflow values.
    x=yaml.safe_load(build(total=total,per_chapter=per_chapter,troy=True,full_api=True,resident=False).replace('\non:\n',"\n'on':\n"))
    x['name']='Cinematic universe expansion / classic runners'
    x['concurrency']={'group':'classic-universe-expansion','cancel-in-progress':False}
    inputs=x['on']['workflow_dispatch']['inputs'];inputs['request_file']={'type':'string','default':'classic-universe-practice','description':'Author universe bible and explicit next-scene layout in examples/'}
    inputs['profile']['default']='fast';inputs['scene_limit']={'type':'choice','options':['1'] if total==1 else ['1','3','9'],'default':'1'}
    inputs.pop('refinement_seed_run',None)
    inputs['canon_run']={'type':'string','default':'','description':'Optional prior accepted universe-canon checkpoint; requires a new episode brief'}
    jobs=x['jobs'];prepare=jobs['prepare']
    # No model calls in prepare or quickstart; lexical retrieval needs no encoder install.
    prepare['steps']=[s for s in prepare['steps'] if s.get('name')!='Install local RAG encoder when requested']
    quick=copy.deepcopy(jobs['refine']);quick['name']='Compile author brief and scene layout without inference';quick['needs']=['prepare']
    quick['steps']=[s for s in quick['steps'] if s.get('uses')!='actions/download-artifact@v4' or s.get('with',{}).get('name')=='prepare']
    for s in quick['steps']:
        if s.get('uses')=='./.github/actions/setup-worker':s['with']['backend']='fixture'
        if s.get('id')=='task':
            s['env']['CANON_RUN']='${{ inputs.canon_run }}'
            s['run']='extra=()\nif [ -n "$CANON_RUN" ]; then extra=(--checkpoint inputs/canon/snapshot.json); fi\npython -m storyforge.expansion prepare --source inputs/state/snapshot.json --out out "${extra[@]}"'
        if s.get('uses')=='actions/upload-artifact@v4':s['with']['name']='quickstart'
    quick['steps'].insert(3,{'uses':'actions/download-artifact@v4','if':"${{ inputs.canon_run != '' }}",'with':{'name':'universe-canon','path':'inputs/canon','run-id':'${{ inputs.canon_run }}','github-token':'${{ github.token }}'}})
    for name in ['refine','refine_review','refine_revision','refine_gate','plan','plan_review','plan_revision','plan_gate']:jobs.pop(name,None)
    new={'prepare':prepare,'quickstart':quick}
    for k,v in jobs.items():
        if k=='prepare':continue
        text=yaml.safe_dump(v,sort_keys=False).replace('plan_gate','quickstart')
        new[k]=yaml.safe_load(text)
    jobs=new;x['jobs']=jobs
    # Parallel passage ownership/merge is taken directly from the baseline's graph.
    old=yaml.safe_load(build(total=3,per_chapter=1,troy=True,continuation=True).replace('\non:\n',"\n'on':\n"))['jobs']
    for i in range(total):
        prefix=f's{i+1:02}'
        for suffix in ['edit_plan','edit_batches','edit']:
            text=yaml.safe_dump(old['s03_'+suffix],sort_keys=False).replace('s03',prefix).replace('--index 2',f'--index {i}').replace('resume','quickstart')
            v=yaml.safe_load(text)
            v['if']='${{ '+str(i)+' < fromJSON(inputs.scene_limit) }}'
            for step in v['steps']:
                if step.get('id')=='task':step.setdefault('env',{}).update(GEMINI_API_KEY='${{ secrets.GEMINI_API_KEY }}',GEMINI_API_KEYS='${{ secrets.GEMINI_API_KEYS }}')
            jobs[prefix+'_'+suffix]=v
    for k,v in jobs.items():
        v['env']={'STORY_REVIEW_TIMEOUT_SECONDS':'1800'}
        if k=='s01_design':v.pop('if',None)
        for s in v.get('steps',[]):
            if s.get('id')=='task':
                s.get('env',{}).pop('REFINEMENT_SEED_RUN',None);s.get('env',{}).pop('CONTINUATION_RUN',None)
            if s.get('uses')=='actions/upload-artifact@v4':s['with']['retention-days']=30
        if k.startswith('s') and k.rsplit('_',1)[-1] in {'draft','edit','repair'}:
            idx=next(i for i,s in enumerate(v['steps']) if s.get('uses')=='actions/upload-artifact@v4')
            v['steps'].insert(idx,{'name':'Show generated prose before final acceptance','if':'always()','run':'python -m storyforge.expansion preview --source out --label "'+{'draft':'Writer draft','edit':'Passage-edited draft','repair':'Review-repaired draft'}[k.rsplit('_',1)[-1]]+'"'})
    results=jobs['results'];results['needs']=[k for k in jobs if k!='results']
    # Collect readable text even if a later reviewer or validator failed.
    results['steps'].insert(2,{'name':'Collect readable prose independently of canon acceptance','if':'always()','run':'python -m storyforge.expansion collect --source results --out reading'})
    results['steps'].insert(3,{'uses':'actions/upload-artifact@v4','if':'always()','with':{'name':'readable-story','path':'reading/','retention-days':30}})
    results['steps'].insert(4,{'uses':'actions/upload-artifact@v4','if':'always()','with':{'name':'universe-canon','path':'reading/canon/','retention-days':30,'if-no-files-found':'ignore'}})
    return yaml.safe_dump(x,sort_keys=False,width=120)



def build_living():
    x=yaml.safe_load(build_expansion(total=1,per_chapter=1))
    x['name']='Living universe / local models / full runner graph'
    x['concurrency']['group']='living-universe'
    inputs=x['on']['workflow_dispatch']['inputs'];inputs['request_file']['default']='local-universe-massive';inputs['profile']['default']='expressive'
    inputs['resume_run']=inputs.pop('canon_run');inputs['resume_run']['description']='Prior accepted universe-canon run; empty starts a world'
    inputs['checkpoint_artifact']={'type':'choice','options':['universe-canon','quickstart'],'default':'universe-canon','description':'Use quickstart only to retry a failed event while retaining its saved random draw'}
    for key,job in x['jobs'].items():
        for s in job.get('steps',[]):
            env=s.get('env',{});env.pop('GEMINI_API_KEY',None);env.pop('GEMINI_API_KEYS',None)
            if s.get('id')=='task' and key=='quickstart':
                env['CANON_RUN']='${{ inputs.resume_run }}'
                s['run']='backend=fixture\nif [ "$STORY_BACKEND" = live ]; then backend=worker; fi\nextra=()\nif [ -n "$CANON_RUN" ]; then extra=(--checkpoint inputs/canon/snapshot.json); fi\npython -m storyforge.living_prepare --backend "$backend" --source inputs/state/snapshot.json --out out "${extra[@]}"'
            if key=='quickstart' and s.get('uses')=='./.github/actions/setup-worker':s['with']['backend']='${{ inputs.backend }}'
            if key=='quickstart' and s.get('uses')=='actions/download-artifact@v4' and s['with'].get('name')=='universe-canon':
                s['if']="${{ inputs.resume_run != '' }}";s['with']['run-id']='${{ inputs.resume_run }}';s['with']['name']='${{ inputs.checkpoint_artifact }}'
        if key=='quickstart':job['name']='Compile beginning quickly and propose one local world event'
    return yaml.safe_dump(x,sort_keys=False,width=120)


if __name__=='__main__':
    (ROOT/'.github/workflows/cinematic-expansion.yml').write_text(build_expansion())
    (ROOT/'.github/workflows/living-universe.yml').write_text(build_living())
