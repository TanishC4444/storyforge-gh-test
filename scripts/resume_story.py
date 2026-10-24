"""Back up saved scene checkpoints, then request one native partial Actions rerun."""
import argparse,concurrent.futures,json,os,re
from pathlib import Path
from scripts.stress_queue import GitHub
from storyforge.story_checkpoint import preserve


def pages(api,path,key):
    items=[]
    for page in range(1,101):
        value=api.api(path+('&' if '?' in path else '?')+f'per_page=100&page={page}')
        rows=value[key];items+=rows
        if not rows or len(items)>=value['total_count']:return items
    raise ValueError('Too many saved jobs or artifacts')


def select_job(jobs,scene,stage):
    labels={'scene':f'Reconcile scene {scene} with verified prior memory','editing':'Compile literary findings and allocate targeted edits','memory':'Allocate one targeted final-memory correction'}
    def matches(label):
        scoped=[j for j in jobs if j['name'].startswith(f'Scene {scene} / ') and label in j['name'] and j.get('conclusion')!='skipped']
        if scoped:return scoped
        # Original scene-boundary titles were unique before names gained prefixes.
        if stage=='scene':return [j for j in jobs if j['name']==label and j.get('conclusion')!='skipped']
        return []
    if stage=='memory':
        found=matches(labels['memory'])
        if not found:found=matches('Compile full memory and allocate exhaustive checks')
    else:found=matches(labels[stage])
    if not found and stage!='scene':return select_job(jobs,scene,'scene')
    if len(found)!=1:raise ValueError('Could not identify one resumable scene job; use a run containing that scene boundary')
    return found[0]


def plan(api,run_id,scene,stage,out):
    if not str(run_id).isdigit() or int(run_id)<=0:raise ValueError('A positive source run ID is required')
    if stage not in {'scene','editing','memory'}:raise ValueError('Unknown restart stage')
    out=Path(out);run=api.api(f'actions/runs/{run_id}')
    if run['status']!='completed':raise ValueError('Wait until the source run finishes or is cancelled before resuming it')
    if run.get('conclusion')=='success':raise ValueError('This run succeeded; use universe continuation for a new episode')
    if run['path'].split('@')[0]!='.github/workflows/living-universe-pipeline.yml':raise ValueError('Resume requires a full living pipeline run, not the stress controller')
    artifacts=pages(api,f'actions/runs/{run_id}/artifacts','artifacts')
    selected=[a for a in artifacts if not a.get('expired') and (a['name'] in {'quickstart','readable-story','universe-canon'} or re.fullmatch(r's\d+_(accept|draft|repair|final_check|final_memory|memory_review|memory_recovery_join|design|write_batches-[0-9]+)',a['name']))]
    if not selected:raise ValueError('No saved checkpoints remain; download recovery artifacts before their 30-day expiry')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda a:api.artifact(a,out/'backup'/a['name']),selected))
    recovery=preserve(out/'backup',out/'saved-story')
    first=recovery['resume_scene']
    if first is None:raise ValueError('All authored scenes are already approved; use universe continuation for a new episode')
    number=first if scene=='auto' else int(scene)
    if not first<=number<=min(4,recovery['total_scenes'] or 4):raise ValueError('Cannot overwrite completed scenes or resume outside this episode')
    if number!=first:raise ValueError('Resume the first unfinished scene so no missing boundary is skipped')
    jobs=pages(api,f'actions/runs/{run_id}/jobs?filter=latest','jobs');job=select_job(jobs,number,stage)
    value={'run_id':int(run_id),'run_attempt':run['run_attempt'],'head_sha':run['head_sha'],'job_id':job['id'],'job_name':job['name'],'scene':number,'requested_stage':stage,'completed_scenes_preserved':recovery['completed_scenes'],'backup_artifacts':[a['name'] for a in selected],'url':run['html_url']}
    (out/'resume-plan.json').write_text(json.dumps(value,indent=2)+'\n')
    return value


def apply(api,out):
    value=json.loads((Path(out)/'resume-plan.json').read_text());run=api.api(f'actions/runs/{value["run_id"]}')
    if run['status']!='completed' or run['run_attempt']!=value['run_attempt'] or run['head_sha']!=value['head_sha']:raise ValueError('Source run changed since backup; inspect its current attempt')
    # This POST is deliberately not retried: an ambiguous response may already
    # have launched the partial rerun. Saved upstream artifacts remain reusable.
    api.api(f'actions/jobs/{value["job_id"]}/rerun','POST',{})
    return value


def main():
    p=argparse.ArgumentParser();p.add_argument('task',choices=['plan','apply']);p.add_argument('--out',default='resume');a=p.parse_args()
    api=GitHub(os.environ['GITHUB_REPOSITORY'],os.environ['GH_TOKEN'])
    result=plan(api,os.environ['SOURCE_RUN'],os.environ.get('SCENE','auto'),os.environ.get('RESTART_STAGE','editing'),a.out) if a.task=='plan' else apply(api,a.out)
    print(json.dumps(result,indent=2))
    if a.task=='apply' and os.getenv('GITHUB_STEP_SUMMARY'):
        Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(f'Resumed scene {result["scene"]}; {result["completed_scenes_preserved"]} completed scenes preserved. Original draft/checkpoint backup was uploaded first. [Open resumed run]({result["url"]}).\n')

if __name__=='__main__':main()
