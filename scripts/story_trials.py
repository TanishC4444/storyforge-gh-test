"""Bounded fresh-run recovery and the separately scheduled parallel experiment."""
import argparse,datetime,json,os,time
from pathlib import Path
from scripts.stress_queue import GitHub,Queue


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['recovery','parallel'],required=True);p.add_argument('--source-run',default='40103398653');p.add_argument('--out',default='trial');a=p.parse_args()
    api=GitHub(os.environ['GITHUB_REPOSITORY'],os.environ['GH_TOKEN']);out=Path(a.out);out.mkdir(exist_ok=True)
    rows=[];source=a.source_run
    workflow='living-universe-pipeline.yml' if a.mode=='recovery' else 'planned-parallel.yml'
    active=None
    try:
        for attempt in range(2 if a.mode=='recovery' else 1):
            tag=f'trial-{os.environ["GITHUB_RUN_ID"]}-{a.mode}-{attempt+1}'
            inputs={'backend':'live','request_file':'hard-chronology','queue_tag':tag}
            if a.mode=='recovery':inputs.update(profile='fast',scene_limit='4',fresh_run=str(source))
            title=('Living' if a.mode=='recovery' else 'Planned parallel')+' | hard-chronology | '+tag
            api.api(f'actions/workflows/{workflow}/dispatches','POST',{'ref':os.environ['GITHUB_REF_NAME'],'inputs':inputs})
            run=None
            for _ in range(18):
                found=[r for r in api.api(f'actions/workflows/{workflow}/runs?event=workflow_dispatch&per_page=50')['workflow_runs'] if r.get('display_title')==title]
                if len(found)>1:raise ValueError('Duplicate trial dispatch; inspect before continuing')
                if found:run=found[0];break
                time.sleep(10)
            if run is None:raise ValueError('Uncertain trial dispatch; refusing a duplicate')
            active=run['id'];(out/'active.json').write_text(json.dumps({'run_id':active}))
            require_sha=os.environ['GITHUB_SHA']
            if run['head_sha']!=require_sha:raise ValueError('Trial child revision mismatch')
            print(run['html_url'],flush=True)
            q=Queue(api,{'poll_seconds':30,'cases':[]},out,os.environ['GITHUB_REF_NAME'],require_sha,tag)
            run=q.wait(run,45);active=None
            artifacts=[]
            for page in range(1,6):
                d=api.api(f'actions/runs/{run["id"]}/artifacts?per_page=100&page={page}');artifacts+=d['artifacts']
                if len(artifacts)>=d['total_count']:break
            for artifact in artifacts:
                if artifact['name'] in {'episode-audit','story-recovery','readable-story','parallel-readable-story'}:api.artifact(artifact,out/f'attempt-{attempt+1}'/artifact['name'])
            proofs=list((out/f'attempt-{attempt+1}').rglob('episode-audit.json' if a.mode=='recovery' else 'report.json'))
            proof=json.loads(proofs[0].read_text()) if proofs else {}
            passed=run['conclusion']=='success' and proof.get('pass') is True
            parse=lambda t:datetime.datetime.fromisoformat(t.replace('Z','+00:00'))
            rows.append({'run_id':run['id'],'url':run['html_url'],'source_run':source if a.mode=='recovery' else None,'pass':passed,'status':run['conclusion'],'seconds':(parse(run['updated_at'])-parse(run['created_at'])).total_seconds(),'audit':proof})
            (out/'report.json').write_text(json.dumps({'mode':a.mode,'complete':passed or attempt==1 or a.mode=='parallel','pass':passed,'attempts':rows},indent=2))
            if passed:break
            source=run['id']
            if a.mode=='recovery' and attempt==0:
                print('Incomplete: preserving output, waiting 90 seconds, then starting a NEW workflow run at its checkpoint.',flush=True)
                time.sleep(90)
        if os.getenv('GITHUB_STEP_SUMMARY'):
            Path(os.environ['GITHUB_STEP_SUMMARY']).write_text('## '+a.mode+' trial\n\n'+json.dumps(rows,indent=2)+'\n\nTrial completion is separate from manuscript approval.\n')
    finally:
        if active:
            try:api.api(f'actions/runs/{active}/cancel','POST')
            except Exception:pass


if __name__=='__main__':main()
