"""All-workflow catalog, runner history, logs and bounded artifact inspection."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
import zipfile
import yaml
from .github import GitHubClient,GitHubError

_CACHE={}


def repositories(settings):
    owner=settings.repo.split('/')[0]
    return list(dict.fromkeys([settings.repo,*filter(None,os.getenv('STORYFORGE_RUNNER_REPOS',owner+'/storyforge-inference-runner').split(','))]))


def client(settings,repository,authorization=None):
    repo=repository or settings.repo
    if repo not in repositories(settings):raise ValueError('Repository is not in the configured workflow/runner list')
    token=(authorization or '').removeprefix('Bearer ').strip()
    if token in ('demo','server'):token=''
    token=token or os.getenv('STORYFORGE_GITHUB_TOKEN','')
    return GitHubClient(token,repo,settings.github_api)


def cached_get(api,path,**params):
    scope=hashlib.sha256(api.http.headers.get('Authorization','').encode()).hexdigest()
    key=(api.repo,scope,path,json.dumps(params,sort_keys=True))
    if key in _CACHE and _CACHE[key][0]>time.time():return _CACHE[key][1]
    value=api.get(path,**params)
    if len(_CACHE)>100:_CACHE.clear()
    _CACHE[key]=(time.time()+30,value)
    return value


def parse_workflow(name,text):
    data=yaml.safe_load(text) or {};on=data.get('on') or data.get(True) or {}
    dispatch=on.get('workflow_dispatch') if isinstance(on,dict) else None
    enabled=isinstance(on,dict) and 'workflow_dispatch' in on
    inputs=(dispatch or {}).get('inputs',{})
    jobs=[]
    for ident,job in (data.get('jobs') or {}).items():
        needs=job.get('needs',[]);needs=[needs] if isinstance(needs,str) else needs
        jobs.append({'id':str(ident),'name':str(job.get('name',ident)),'needs':needs,'runner':job.get('runs-on'),'step_count':len(job.get('steps',[])),'reusable_workflow':job.get('uses')})
    return {'file':name,'name':str(data.get('name',name)),'dispatchable':enabled,'inputs':inputs,'jobs':jobs,'source':text}


def local_catalog(root):
    key=('local_catalog',str(root));latest=max((p.stat().st_mtime for p in (Path(root)/'.github'/'workflows').glob('*.yml')),default=0)
    if key in _CACHE and _CACHE[key][0]==latest:return _CACHE[key][1]
    rows=[]
    for path in sorted((Path(root)/'.github'/'workflows').glob('*.yml')):
        item=parse_workflow(path.name,path.read_text(encoding='utf-8-sig'))
        rows.append({k:v for k,v in item.items() if k not in ('source','jobs') }|{'job_count':len(item['jobs'])})
    _CACHE[key]=(latest,rows)
    return rows


def workflow(api,filename,ref='main'):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.ya?ml',filename):raise ValueError('Invalid workflow filename')
    value=cached_get(api,api.repo_path('contents/.github/workflows/'+filename),ref=ref)
    text=base64.b64decode(value.get('content','')).decode('utf-8-sig')
    return parse_workflow(filename,text)


def dispatch(api,filename,ref,inputs):
    definition=workflow(api,filename,ref)
    if not definition['dispatchable']:raise ValueError('This workflow has no manual dispatch trigger')
    specs=definition['inputs'];values={}
    if not isinstance(inputs,dict):raise ValueError('Workflow inputs must be an object')
    if set(inputs)-set(specs):raise ValueError('Unknown workflow inputs: '+', '.join(set(inputs)-set(specs)))
    for key,spec in specs.items():
        value=inputs.get(key,spec.get('default'))
        if value is None:
            if spec.get('required'):raise ValueError('Required input: '+key)
            continue
        kind=spec.get('type','string')
        if kind=='choice' and str(value) not in list(map(str,spec.get('options',[]))):raise ValueError('Invalid choice for '+key)
        if kind=='boolean' and not isinstance(value,bool):raise ValueError(key+' must be true or false')
        if kind=='number' and (isinstance(value,bool) or not isinstance(value,(float,int))):raise ValueError(key+' must be a number')
        if isinstance(value,(dict,list)) or len(str(value))>1000:raise ValueError('Invalid workflow input '+key)
        values[key]=str(value).lower() if isinstance(value,bool) else str(value)
    return {'run_id':api.dispatch(filename,ref,values),'workflow':filename,'ref':ref,'inputs':values,'message':'Workflow dispatched. Refresh history if the run ID is not yet available.'}


def blob(api,path,limit=64*1024*1024):
    with api.http.stream('GET',path) as response:
        if response.status_code>=400:raise GitHubError(response.status_code,'GitHub artifact/log access failed or has expired')
        parts=[];size=0
        for part in response.iter_bytes():
            size+=len(part)
            if size>limit:raise ValueError('Preview/download exceeds the 64 MB in-app limit; open this run on GitHub for the full download')
            parts.append(part)
    return b''.join(parts)


def all_artifacts(api,run_id):
    items=[]
    for page in range(1,51):
        data=cached_get(api,api.repo_path(f'actions/runs/{run_id}/artifacts'),per_page=100,page=page)
        items+=data.get('artifacts',[])
        if len(items)>=data.get('total_count',len(items)) or not data.get('artifacts'):return items
    raise ValueError('This run has over 5,000 artifacts; narrow inspection on GitHub')


def artifact(api,run_id,artifact_id,cache):
    items=all_artifacts(api,run_id)
    item=next((x for x in items if x['id']==artifact_id),None)
    if not item:raise ValueError('Artifact does not belong to the selected run')
    if item.get('expired'):raise ValueError('GitHub has expired this artifact. Any previously saved local outputs are still available in Projects & outputs.')
    if item.get('size_in_bytes',0)>64*1024*1024:raise ValueError('Artifact exceeds the 64 MB in-app limit; download from GitHub instead')
    target=Path(cache)/api.repo.replace('/','_')/(str(artifact_id)+'.zip')
    if target.is_file():return target.read_bytes()
    data=blob(api,api.repo_path(f'actions/artifacts/{artifact_id}/zip'))
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return data


def zip_files(data,path=None):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members=[x for x in archive.infolist() if not x.is_dir()]
        if len(members)>2000 or sum(x.file_size for x in members)>128*1024*1024:raise ValueError('Artifact is too large for safe in-app inspection')
        if path is None:return [{'path':x.filename,'bytes':x.file_size} for x in members]
        info=next((x for x in members if x.filename==path),None)
        if not info:raise ValueError('Artifact file not found')
        if info.file_size>4*1024*1024:raise ValueError('Individual preview limit is 4 MB; download the artifact to inspect the full file')
        return archive.read(info)
