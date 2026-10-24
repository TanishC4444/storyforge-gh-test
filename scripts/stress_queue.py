"""Dispatch exactly one existing full-graph run at a time; collect honest audits."""
from __future__ import annotations
import argparse,datetime,io,json,os,re,time,urllib.request,urllib.error,zipfile
from pathlib import Path

PIPELINE='living-universe-pipeline.yml'

def validate_suite(suite):
    from storyforge.contracts import request
    from storyforge.provider_recovery import configuration
    from storyforge.craft import compile_scene_plan
    root=Path(__file__).resolve().parents[1];seen=set()
    if not 1<=len(suite['cases'])<=8:raise ValueError('Expected 1–8 bounded cases')
    if not 1<=suite['per_run_timeout_minutes']<=45:raise ValueError('Invalid child timeout')
    if not 15<=suite['poll_seconds']<=60:raise ValueError('Invalid polling interval')
    for case in suite['cases']:
        if not re.fullmatch(r'[a-z0-9-]+',case['id']) or case['id'] in seen:raise ValueError('Invalid case ID')
        if case.get('resume_case') and case['resume_case'] not in seen:raise ValueError('Resume dependency must precede case')
        if not re.fullmatch(r'[a-z0-9-]+',case['request_file']):raise ValueError('Invalid request path')
        req=request(json.loads((root/'examples'/f'{case["request_file"]}.json').read_text()))
        recovery=configuration(req)
        if not recovery or recovery['max_rounds']<2 or recovery['delay_seconds']<45:raise ValueError('Gemini wait buffer required')
        if not set(req['api_roles'])<=set(req['execution_policy']['hosted_required_roles']):raise ValueError('No automatic local downgrade during benchmark')
        if req['medium']!=case['medium'] or req['words_per_scene']!=case['words_per_scene'] or len(req['characters'])!=case['cast']:raise ValueError('Manifest/request mismatch')
        if case['scenes'] not in {1,2,4} or len(compile_scene_plan(req)['scenes'])!=case['scenes']:raise ValueError('Manifest scene count mismatch')
        seen.add(case['id'])
    return suite

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class GitHub:
    def __init__(self,repo,token):
        self.base='https://api.github.com/repos/'+repo+'/'
        self.headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
    def api(self,path,method='GET',body=None):
        req=urllib.request.Request(self.base+path,headers=self.headers,method=method,data=json.dumps(body).encode() if body is not None else None)
        # Retry reads only. Retrying an uncertain dispatch could create a duplicate run.
        for attempt in range(3 if method=='GET' else 1):
            try:
                with urllib.request.urlopen(req,timeout=40) as response:
                    data=response.read();return json.loads(data) if data else None
            except (urllib.error.URLError,TimeoutError):
                if attempt==(2 if method=='GET' else 0):raise
                time.sleep(5*(attempt+1))
    def artifact(self,artifact,dest):
        req=urllib.request.Request(self.base+f'actions/artifacts/{artifact["id"]}/zip',headers=self.headers)
        try:
            response=urllib.request.build_opener(NoRedirect).open(req,timeout=40)
            with response:data=response.read()
        except urllib.error.HTTPError as exc:
            if exc.code!=302:raise
            url=exc.headers['Location']
            if not url.startswith('https://'):raise ValueError('Artifact redirect must use HTTPS')
            # Deliberately omit GitHub credentials on the storage redirect.
            with urllib.request.urlopen(url,timeout=60) as response:data=response.read()
        dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for item in archive.infolist():
                target=(dest/item.filename).resolve()
                if not target.is_relative_to(dest.resolve()):raise ValueError('Unsafe artifact path')
                if item.is_dir():continue
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(item))

def verdict(run,audit,expected):
    return bool(run.get('conclusion')=='success' and audit.get('pass') is True and audit.get('expected_scenes')==expected and len(audit.get('scenes',[]))==expected and all(s.get('approved') and s.get('factual_proof_bound') for s in audit['scenes']))

class Queue:
    def __init__(self,api,suite,out,ref,sha,tag,sleep=time.sleep,now=time.monotonic):
        self.api=api;self.suite=suite;self.out=Path(out);self.ref=ref;self.sha=sha;self.tag=tag;self.sleep=sleep;self.now=now;self.rows=[];self.active=None
    def save(self):
        self.out.mkdir(parents=True,exist_ok=True)
        (self.out/'active.json').write_text(json.dumps({'run_id':self.active})+'\n')
        report={'cases':self.rows,'complete':len(self.rows)==len(self.suite['cases']),'all_passed':len(self.rows)==len(self.suite['cases']) and all(x.get('pass') for x in self.rows),'literary_assessment':'Human reading pending; automated approvals do not establish originality or literary excellence.'}
        (self.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        lines=['# Sequential workflow stress test','',report['literary_assessment'],'','| Case | Result | Words | Run |','|---|---|---:|---|']
        for row in self.rows:
            result='PASS' if row.get('pass') else row.get('status','FAIL')
            lines.append(f'| {row["id"]} | {result} | {row.get("words",0)} | {row.get("url", "—")} |')
        (self.out/'report.md').write_text('\n'.join(lines)+'\n')
        if os.getenv('GITHUB_STEP_SUMMARY'):Path(os.environ['GITHUB_STEP_SUMMARY']).write_text('\n'.join(lines)+'\n')
    def dispatch(self,case,resume):
        tag=self.tag+'-'+case['id'];title='Living | '+case['request_file']+' | '+tag
        inputs={'backend':'live','profile':'fast','request_file':case['request_file'],'scene_limit':str(case['scenes']),'resume_run':str(resume) if resume else '','checkpoint_artifact':'universe-canon','queue_tag':tag}
        dispatch_error=None
        try:self.api.api(f'actions/workflows/{PIPELINE}/dispatches','POST',{'ref':self.ref,'inputs':inputs})
        except (urllib.error.URLError,TimeoutError) as exc:
            dispatch_error=type(exc).__name__
        # An ambiguous POST may have succeeded. Search its unique tag; never dispatch twice.
        for _ in range(12):
            runs=self.api.api(f'actions/workflows/{PIPELINE}/runs?event=workflow_dispatch&per_page=100')['workflow_runs']
            matches=[r for r in runs if r.get('display_title')==title]
            if len(matches)>1:raise RuntimeError('Duplicate correlated runs; stop queue for inspection')
            if matches:
                self.active=matches[0]['id']
                self.save()
                if matches[0]['head_sha']!=self.sha:raise RuntimeError('Child revision differs from tested queue revision')
                return matches[0]
            self.sleep(10)
        raise RuntimeError('Cannot identify dispatch; stopping queue to avoid overlapping runs'+(' ('+dispatch_error+')' if dispatch_error else ''))
    def wait(self,run,minutes):
        deadline=self.now()+minutes*60
        while run['status']!='completed' and self.now()<deadline:
            self.sleep(self.suite['poll_seconds']);run=self.api.api('actions/runs/'+str(run['id']))
        if run['status']!='completed':
            self.api.api(f'actions/runs/{run["id"]}/cancel','POST')
            for _ in range(10):
                self.sleep(15);run=self.api.api('actions/runs/'+str(run['id']))
                if run['status']=='completed':break
            if run['status']!='completed':raise RuntimeError('Child cancellation unresolved; refusing to start another run')
        self.active=None;self.save();return run
    def collect(self,case,run):
        path=self.out/case['id'];path.mkdir(parents=True,exist_ok=True);artifacts=[]
        for page in range(1,6):
            data=self.api.api(f'actions/runs/{run["id"]}/artifacts?per_page=100&page={page}');artifacts+=data['artifacts']
            if len(artifacts)>=data['total_count']:break
        errors=[]
        for artifact in artifacts:
            if artifact['name'] in {'episode-audit','readable-story'}:
                try:self.api.artifact(artifact,path/artifact['name'])
                except Exception as exc:errors.append(artifact['name']+': '+type(exc).__name__)
        audits=list((path/'episode-audit').rglob('episode-audit.json'));audit=json.loads(audits[0].read_text()) if audits else {}
        jobs=[]
        if run.get('conclusion')!='success':
            for page in range(1,6):
                data=self.api.api(f'actions/runs/{run["id"]}/jobs?per_page=100&page={page}');jobs+=data['jobs']
                if len(jobs)>=data['total_count']:break
        failed=[{'name':j['name'],'conclusion':j['conclusion'],'url':j['html_url'],'steps':[{'name':s['name'],'conclusion':s['conclusion']} for s in j.get('steps',[]) if s.get('conclusion') in {'failure','timed_out','cancelled'}]} for j in jobs if j.get('conclusion') in {'failure','timed_out','cancelled'}]
        row={**case,'run_id':run['id'],'url':run['html_url'],'status':run.get('conclusion'),'pass':verdict(run,audit,case['scenes']) and not errors,'words':sum(x['words'] for x in audit.get('scenes',[])),'audit':audit,'collection_errors':errors,'failed_jobs':failed}
        parse=lambda x:datetime.datetime.fromisoformat(x.replace('Z','+00:00'))
        row['elapsed_seconds']=(parse(run['updated_at'])-parse(run['created_at'])).total_seconds()
        (path/'result.json').write_text(json.dumps(row,indent=2)+'\n');return row
    def run(self):
        self.save()
        for case in self.suite['cases']:
            prior=next((r for r in self.rows if r['id']==case.get('resume_case')),None)
            if case.get('resume_case') and not (prior and prior.get('pass')):
                self.rows.append({**case,'status':'blocked_by_failed_checkpoint','pass':False});self.save();continue
            print('Starting '+case['id'],flush=True)
            child=self.dispatch(case,prior['run_id'] if prior else None)
            print(child['html_url'],flush=True)
            child=self.wait(child,self.suite['per_run_timeout_minutes'])
            # Collection failure is a failed assessment, not permission to overlap execution.
            try:row=self.collect(case,child)
            except Exception as exc:row={**case,'run_id':child['id'],'url':child['html_url'],'pass':False,'status':'collection_error','error':type(exc).__name__}
            self.rows.append(row);self.save()
        return all(r.get('pass') for r in self.rows)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--validate-only',action='store_true');parser.add_argument('--out',default='stress-results');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];suite=validate_suite(json.loads((root/'examples/stress-suite.json').read_text()))
    if args.validate_only:print('Validated',len(suite['cases']),'strict sequential cases');return
    api=GitHub(os.environ['GITHUB_REPOSITORY'],os.environ['GH_TOKEN'])
    q=Queue(api,suite,args.out,os.environ['GITHUB_REF_NAME'],os.environ['GITHUB_SHA'],'stress-'+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT'])
    try:passed=q.run()
    except BaseException:
        if q.active:
            try:api.api(f'actions/runs/{q.active}/cancel','POST')
            except Exception:pass
        q.save();raise
    if not passed:raise SystemExit('Stress suite found failures; inspect report and preserved child drafts')

if __name__=='__main__':main()
