"""Unified FastAPI project, creative, media, planning and workflow surface."""
from __future__ import annotations
import base64
from functools import lru_cache
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlencode
from fastapi import APIRouter,Body,Depends,Header,HTTPException,Request,Query
from fastapi.responses import HTMLResponse,FileResponse,Response,StreamingResponse,RedirectResponse
from .. import image_studio,creative_studio
from ..production import create_plan,normalize_config,validate_breakdown,schedule,budget
from ..production_exports import export
from ..soundtracks import Vultr,plan as soundtrack_plan,wav_stream
from ..storage import load,save
from .config import ROOT,get_settings
from .studio_runtime import StudioRuntime
from . import workflow_browser as workflows

router=APIRouter()


@lru_cache
def get_runtime():return StudioRuntime(os.getenv('STORYFORGE_WORKSPACE',str(ROOT)))


def local(request:Request):
    if request.url.hostname not in ('127.0.0.1','localhost','::1','testserver') or (request.client and request.client.host not in ('127.0.0.1','::1','testclient')):
        raise HTTPException(403,'Studio is a local workspace. Start on 127.0.0.1 and access it locally.')


def write(request:Request,runtime:StudioRuntime=Depends(get_runtime)):
    local(request)
    if request.headers.get('X-Storyforge-Token')!=runtime.token:raise HTTPException(403,'Refresh this page to obtain its local request token')
    origin=request.headers.get('Origin')
    if origin and origin!=str(request.base_url).rstrip('/'):raise HTTPException(403,'Origin rejected')


RUNTIME=Depends(get_runtime)


def folder(request,runtime):return runtime.folder(request.cookies.get('sf_project'))


def page(path,runtime,legacy=False):
    text=Path(path).read_text(encoding='utf-8-sig').replace('__CSRF__',runtime.token)
    if legacy:
        text=text.replace('href="/"','href="/production"').replace("'/?reference='","'/production?reference='")
    nav='''<style>.sf-bar{position:sticky;top:0;z-index:1000;display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:12px 4vw;background:#101722;color:#eef3fa;border-bottom:1px solid #354258;font:14px system-ui}.sf-bar a{color:#e8cd95;text-decoration:none}.sf-bar select{width:auto;max-width:230px;padding:5px;background:#192638;color:#fff;border:1px solid #4e5d72}.sf-bar strong{margin-right:8px}</style><nav class="sf-bar" aria-label="Unified workspace"><strong>StoryForge Studio</strong><a href="/">Home</a><a href="/writing">Writing runners</a><a href="/ideas">Ideas & revisions</a><a href="/images">Images</a><a href="/music">Music</a><a href="/production">Production</a><a href="/workflows">Workflows & history</a><a href="/outputs">Outputs</a><a href="/testing">Test console</a><a href="/connections">Connections</a><label>Project <select id="sf-project-nav" aria-label="Current project"></select></label></nav>'''
    script='''<script>(async()=>{try{const r=await fetch('/api/studio/projects');const v=await r.json();const s=document.getElementById('sf-project-nav');for(const p of v.projects){const o=document.createElement('option');o.value=p.id;o.textContent=p.title;o.selected=p.id===v.current;s.append(o)}s.onchange=async()=>{const r=await fetch('/api/studio/project/select',{method:'POST',headers:{'Content-Type':'application/json','X-Storyforge-Token':'__CSRF__'},body:JSON.stringify({id:s.value})});if(r.ok)location.reload()}}catch(e){}})();</script>'''.replace('__CSRF__',runtime.token)
    return text.replace('<body>','<body>'+nav).replace('</body>',script+'</body>')


@router.get('/api/studio/projects',tags=['studio projects'],dependencies=[Depends(local)])
def projects(request:Request,runtime=RUNTIME):
    return {'projects':runtime.project_list(),'current':runtime.project_id(folder(request,runtime))}


@router.post('/api/studio/projects',tags=['studio projects'],dependencies=[Depends(write)])
def new_project(request:Request,data:dict=Body(...),runtime=RUNTIME):
    ident=runtime.create_project(data.get('title',''),data.get('text',''),data.get('brief'))
    response=Response(json.dumps({'id':ident}),media_type='application/json');response.set_cookie('sf_project',ident,httponly=True,samesite='strict');return response


@router.post('/api/studio/project/select',tags=['studio projects'],dependencies=[Depends(write)])
def select_project(data:dict=Body(...),runtime=RUNTIME):
    runtime.folder(data.get('id'));response=Response(json.dumps({'id':data['id']}),media_type='application/json');response.set_cookie('sf_project',data['id'],httponly=True,samesite='strict');return response


@router.get('/api/studio/jobs',tags=['studio jobs'],dependencies=[Depends(local)])
def job_list(request:Request,runtime=RUNTIME):
    ident=runtime.project_id(folder(request,runtime))
    return {'jobs':sorted([j for j in runtime.jobs.values() if j['project_id']==ident],key=lambda j:j['created_at'],reverse=True)[:50]}


@router.get('/api/job/{ident}',tags=['studio jobs'],dependencies=[Depends(local)])
def legacy_job(ident:str,runtime=RUNTIME):
    job=runtime.job(ident);result=job.get('result',{})
    return {**job,**({'prompt_result':result} if job['kind']=='image-prompt' else {'image_id':result['id']} if job['kind']=='image' and result else {'plan_id':result['id']} if job['kind']=='production' and result else {})}


@router.get('/api/config',tags=['studio configuration'],dependencies=[Depends(local)])
def config(request:Request,runtime=RUNTIME):
    current=folder(request,runtime);paths=sorted((current/'production'/'plans').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]
    return {'story':current.name,'vultr':bool(os.getenv('VULTR_INFERENCE_API_KEY')),'search':bool(os.getenv('SERPAPI_API_KEY')),'google':bool(runtime.google.access or runtime.google.refresh),'google_oauth':bool(os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET')),'redirect_uri':str(request.base_url).rstrip('/')+'/google/callback','plans':[p.stem for p in paths]}


@router.get('/api/studio/features',tags=['studio configuration'],dependencies=[Depends(local)])
def features(runtime=RUNTIME):
    return {'framework':'FastAPI','repositories':workflows.repositories(get_settings()),'workflow_count':len(workflows.local_catalog(runtime.root)),
            'features':['writing runners','all workflow dispatch inputs','workflow source and job graphs','run history and logs','artifact file previews/downloads','project uploads and switching','ideas','drafting','critique','revision loop','image generation','image prompt preparation','image to location scouting','Vultr film scores and songs','local ambience','progressive music playback','production schedules','budget arithmetic','SerpAPI scouting and key failover','legal/logistical follow-ups','Google Calendar OAuth/sync','ICS/CSV/call-sheet exports','persistent local jobs','local output library','interactive OpenAPI console'],
            'configured':{'vultr':bool(os.getenv('VULTR_INFERENCE_API_KEY')),'muse_image':bool(getattr(image_studio,'muse_key',lambda:'')()),'serpapi':bool(os.getenv('SERPAPI_API_KEY')),'google_oauth':bool(os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET')),'github_server_token':bool(os.getenv('STORYFORGE_GITHUB_TOKEN'))}}


@router.post('/api/studio/creative',tags=['creative writing'],dependencies=[Depends(write)],status_code=202)
def creative(request:Request,data:dict=Body(...),runtime=RUNTIME):
    cfg=creative_studio.validate(data);current=folder(request,runtime)
    return {'job_id':runtime.submit('creative',current,lambda progress:creative_studio.run(current,cfg,progress))}


@router.post('/api/studio/creative/{ident}/use-as-project',tags=['creative writing'],dependencies=[Depends(write)])
def adopt_creative(ident:str,request:Request,runtime=RUNTIME):
    if not re.fullmatch('[a-f0-9]{24}',ident):raise ValueError('Invalid creative output ID')
    value=load(folder(request,runtime)/'creative'/(ident+'.json'));text=value.get('result',{}).get('text')
    if not isinstance(text,str):raise ValueError('This result has no prose or idea text to use')
    project=runtime.create_project(value['result'].get('title','Creative draft'),text)
    response=Response(json.dumps({'id':project}),media_type='application/json');response.set_cookie('sf_project',project,httponly=True,samesite='strict');return response


@router.get('/api/studio/creative',tags=['creative writing'],dependencies=[Depends(local)])
def creative_results(request:Request,runtime=RUNTIME):
    paths=sorted((folder(request,runtime)/'creative').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:50]
    return {'results':[load(p) for p in paths]}


@router.get('/api/images/models',tags=['Vultr images'],dependencies=[Depends(local)])
def image_models():return {'models':image_studio.CATALOG.list()}


@router.get('/api/images',tags=['Vultr images'],dependencies=[Depends(local)])
def images(request:Request,runtime=RUNTIME):return {'images':image_studio.gallery(folder(request,runtime))}


@router.get('/api/images/{ident}',tags=['Vultr images'],dependencies=[Depends(local)])
def image_record(ident:str,request:Request,runtime=RUNTIME):return image_studio.read_record(folder(request,runtime),ident)


@router.get('/media/images/{ident}/{index}.png',tags=['Vultr images'],dependencies=[Depends(local)])
def image_media(ident:str,index:int,request:Request,download:bool=False,runtime=RUNTIME):
    path=image_studio.image_file(folder(request,runtime),ident,index)
    return FileResponse(path,media_type='image/png',filename=path.name if download else None,content_disposition_type='attachment' if download else 'inline')


@router.post('/api/images/prepare',tags=['Vultr images'],dependencies=[Depends(write)],status_code=202)
def image_prepare(request:Request,data:dict=Body(...),runtime=RUNTIME):
    image_studio.input_spec(data);current=folder(request,runtime)
    return {'job_id':runtime.submit('image-prompt',current,lambda progress:image_studio.prepare_prompt(current,data,bool(data.get('enhance',True))))}


@router.post('/api/images/generate',tags=['Vultr images'],dependencies=[Depends(write)],status_code=202)
def image_generate(request:Request,data:dict=Body(...),runtime=RUNTIME):
    image_studio.generation_settings(data,image_studio.CATALOG.get(data.get('model')));current=folder(request,runtime)
    return {'job_id':runtime.submit('image',current,lambda progress:image_studio.generate(current,data,progress))}


@router.post('/api/generate',tags=['production planning'],dependencies=[Depends(write)],status_code=202)
def production(request:Request,data:dict=Body(...),runtime=RUNTIME):
    normalize_config(data.get('config',{}));current=folder(request,runtime)
    return {'job_id':runtime.submit('production',current,lambda progress:create_plan(current,data.get('config',{}),data.get('images',[]),progress))}


def read_plan(current,ident):
    if not re.fullmatch('[a-f0-9]{24}',ident):raise ValueError('Invalid plan ID')
    return load(current/'production'/'plans'/(ident+'.json'))


@router.get('/api/plan/{ident}',tags=['production planning'],dependencies=[Depends(local)])
def production_plan(ident:str,request:Request,runtime=RUNTIME):return read_plan(folder(request,runtime),ident)


@router.post('/api/recalculate',tags=['production planning'],dependencies=[Depends(write)])
def recalculate(request:Request,data:dict=Body(...),runtime=RUNTIME):
    current=folder(request,runtime);value=read_plan(current,data['id']);cfg=normalize_config(data.get('config',value['config']))
    breakdown=value['breakdown'];breakdown['scenes']=data.get('scenes',breakdown['scenes']);breakdown['budget_items']=data.get('budget_items',breakdown['budget_items']);validate_breakdown(breakdown)
    value['config']=cfg;value['schedule']=schedule(breakdown['scenes'],cfg);value['budget']=budget(breakdown['budget_items'],cfg)
    value['id']=hashlib.sha256(json.dumps([data['id'],cfg,breakdown],sort_keys=True).encode()).hexdigest()[:24]
    value['warnings'].append('Schedule/budget edited locally; research recommendations were not regenerated.')
    save(current/'production'/'plans'/(value['id']+'.json'),value);return value


@router.get('/export/{ident}/{kind}',tags=['production planning'],dependencies=[Depends(local)])
def production_export(ident:str,kind:str,request:Request,runtime=RUNTIME):
    raw,mime=export(read_plan(folder(request,runtime),ident),kind)
    return Response(raw,media_type=mime,headers={'Content-Disposition':f'attachment; filename="storyforge-{kind}"'})


@router.post('/api/calendar-sync',tags=['Google Calendar'],dependencies=[Depends(write)])
def calendar_sync(request:Request,data:dict=Body(...),runtime=RUNTIME):return runtime.google.sync(read_plan(folder(request,runtime),data['id']),str(data.get('calendar','primary'))[:300])


@router.get('/google/connect',tags=['Google Calendar'],dependencies=[Depends(local)])
def google_connect(request:Request,runtime=RUNTIME):
    client=os.getenv('GOOGLE_CLIENT_ID','')
    if not client or not os.getenv('GOOGLE_CLIENT_SECRET'):raise ValueError('Configure Google OAuth credentials and register '+str(request.base_url).rstrip('/')+'/google/callback')
    state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48);runtime.oauth[state]=(time.time(),verifier)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    return RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':client,'redirect_uri':str(request.base_url).rstrip('/')+'/google/callback','response_type':'code','scope':'https://www.googleapis.com/auth/calendar.events','state':state,'access_type':'offline','prompt':'consent','code_challenge':challenge,'code_challenge_method':'S256'}))


@router.get('/google/callback',tags=['Google Calendar'],dependencies=[Depends(local)])
def google_callback(request:Request,state:str='',code:str='',runtime=RUNTIME):
    item=runtime.oauth.pop(state,None)
    if not item or time.time()-item[0]>600 or not code:raise ValueError('Google authorization expired or was not granted')
    runtime.google.accept(runtime.google.form_token({'grant_type':'authorization_code','code':code,'redirect_uri':str(request.base_url).rstrip('/')+'/google/callback','code_verifier':item[1]}))
    return RedirectResponse('/production')


@router.get('/api/studio/outputs',tags=['output library'],dependencies=[Depends(local)])
def output_list(request:Request,runtime=RUNTIME):return {'files':runtime.output_files(folder(request,runtime))}


@router.get('/api/studio/output',tags=['output library'],dependencies=[Depends(local)])
def output_file(request:Request,path:str,download:bool=False,runtime=RUNTIME):
    file=runtime.output_path(folder(request,runtime),path);mime=mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
    # HTML is never served from generated artifacts; text/JSON use nosniff.
    return FileResponse(file,media_type=mime,filename=file.name if download else None,content_disposition_type='attachment' if download else 'inline',headers={'X-Content-Type-Options':'nosniff'})


def music_record(current,ident):
    if not re.fullmatch(r'(music_[a-f0-9]{24}|local_[a-f0-9]{24})',ident):raise ValueError('Invalid music ID')
    direct=current/'soundtracks'/(ident+'.json')
    if direct.is_file():return load(direct)
    for path in (current/'soundtracks').glob('*.json'):
        value=load(path)
        if value.get('job',{}).get('id')==ident:return value
    raise ValueError('Music job does not belong to this project')


@router.get('/api/studio/music/models',tags=['Vultr music'],dependencies=[Depends(local)])
def music_models():return Vultr().json('/music/models')


@router.post('/api/studio/music',tags=['Vultr music'],dependencies=[Depends(write)],status_code=202)
def create_music(request:Request,data:dict=Body(...),runtime=RUNTIME):
    current=folder(request,runtime);mode=data.get('mode','score');seconds=data.get('seconds',60)
    if type(seconds) is not int or not 5<=seconds<=360:raise ValueError('Duration must be 5–360 whole seconds')
    cue=soundtrack_plan(current,mode,str(data.get('direction',''))[:1000])
    def operation(progress):
        if mode=='ambience':
            ident='local_'+secrets.token_hex(12);target=current/'soundtracks'/(ident+'.wav');target.parent.mkdir(parents=True,exist_ok=True)
            progress('Rendering the explicitly selected local ambience')
            with target.open('wb') as out:
                for block in wav_stream(cue,seconds):out.write(block)
            value={'cue':cue,'provider':'local procedural','job':{'id':ident,'status':'completed'},'file':target.name}
        else:
            progress('Submitting the soundtrack to Vultr')
            job=Vultr().create(cue,data.get('model','minimax-music3'),seconds,str(data.get('lyrics',''))[:12000]);ident=job['id'];value={'cue':cue,'provider':'Vultr Serverless Inference','job':job}
        save(current/'soundtracks'/(ident+'.json'),value);return value
    return {'job_id':runtime.submit('music',current,operation)}


@router.get('/api/studio/music',tags=['Vultr music'],dependencies=[Depends(local)])
def music_list(request:Request,runtime=RUNTIME):
    rows=[];seen=set()
    for path in sorted((folder(request,runtime)/'soundtracks').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]:
        value=load(path)
        ident=value.get('job',{}).get('id')
        if ident and ident not in seen:rows.append(value);seen.add(ident)
    return {'tracks':rows}


@router.get('/api/studio/music/{ident}',tags=['Vultr music'],dependencies=[Depends(local)])
def music_status(ident:str,request:Request,runtime=RUNTIME):
    current=folder(request,runtime);value=music_record(current,ident)
    if ident.startswith('music_') and value['job'].get('status') not in ('completed','failed','cancelled','expired') and time.time()-value.get('last_check',0)>5:
        value['job']=Vultr().json('/music/'+ident);value['last_check']=time.time();save(current/'soundtracks'/(ident+'.json'),value)
    return value


@router.get('/media/music/{ident}/{action}',tags=['Vultr music'],dependencies=[Depends(local)])
def music_media(ident:str,action:str,request:Request,runtime=RUNTIME):
    current=folder(request,runtime);value=music_record(current,ident)
    if action not in ('stream','content'):raise ValueError('Invalid music action')
    if ident.startswith('local_'):return FileResponse(current/'soundtracks'/value['file'],media_type='audio/wav')
    if value['job'].get('status')=='completed':action='content'
    response=Vultr().open('/music/'+ident+'/'+action)
    def chunks():
        try:
            while block:=response.read(8192):yield block
        finally:response.close()
    return StreamingResponse(chunks(),media_type=response.headers.get('Content-Type','audio/mpeg'))


@router.post('/api/studio/music/{ident}/save',tags=['Vultr music'],dependencies=[Depends(write)])
def save_music(ident:str,request:Request,runtime=RUNTIME):
    current=folder(request,runtime);value=music_record(current,ident)
    if value['job'].get('status')!='completed':raise ValueError('Wait for generation to complete before saving')
    if ident.startswith('local_'):return {'file':'soundtracks/'+value['file']}
    target=current/'soundtracks'/(ident+'.mp3')
    if not target.exists():
        temporary=target.with_suffix('.mp3.tmp')
        try:
            with Vultr().open('/music/'+ident+'/content') as response,temporary.open('wb') as out:
                size=0
                while block:=response.read(65536):
                    size+=len(block)
                    if size>100*1024*1024:raise ValueError('Track exceeds the 100 MB save limit')
                    out.write(block)
            os.replace(temporary,target)
        finally:temporary.unlink(missing_ok=True)
    value['file']=target.name;save(current/'soundtracks'/(ident+'.json'),value);return {'file':'soundtracks/'+target.name}


@router.post('/api/studio/music/{ident}/cancel',tags=['Vultr music'],dependencies=[Depends(write)])
def cancel_music(ident:str,request:Request,runtime=RUNTIME):
    current=folder(request,runtime);value=music_record(current,ident)
    if ident.startswith('local_'):raise ValueError('Local ambience is already complete')
    from urllib.request import Request as URLRequest,urlopen
    from urllib.error import HTTPError,URLError
    provider=Vultr()
    try:
        with urlopen(URLRequest('https://api.vultrinference.com/v1/music/'+ident,method='DELETE',headers={'Authorization':'Bearer '+provider.key}),timeout=30) as response:response.read()
    except (HTTPError,URLError,OSError):raise ValueError('Vultr could not cancel this music job') from None
    value['job']['status']='cancelled';save(current/'soundtracks'/(ident+'.json'),value);return {'cancelled':True}


@router.get('/api/studio/workflows',tags=['all workflow history'],dependencies=[Depends(local)])
def workflow_catalog(repository:str='',remote:bool=False,authorization:str|None=Header(default=None),runtime=RUNTIME):
    settings=get_settings();local_rows=workflows.local_catalog(runtime.root) if not repository or repository==settings.repo else []
    if local_rows and not remote:return {'workflows':local_rows,'repositories':workflows.repositories(settings),'source':'local checkout'}
    api=workflows.client(settings,repository,authorization)
    try:
        data=workflows.cached_get(api,api.repo_path('actions/workflows'),per_page=100)
        rows={w['file']:w for w in local_rows}
        for w in data['workflows']:
            name=w['path'].rsplit('/',1)[-1]
            rows[name]={**rows.get(name,{}),'file':name,'name':w['name'],'state':w['state'],'source':'GitHub','job_count':rows.get(name,{}).get('job_count')}
        return {'workflows':list(rows.values()),'repositories':workflows.repositories(settings),'source':'GitHub plus local checkout'}
    finally:api.close()


@router.get('/api/studio/workflows/{filename}',tags=['all workflow history'],dependencies=[Depends(local)])
def workflow_definition(filename:str,repository:str='',ref:str='main',remote:bool=False,authorization:str|None=Header(default=None),runtime=RUNTIME):
    settings=get_settings()
    if (not repository or repository==settings.repo) and ref==settings.ref and not remote:
        path=runtime.root/'.github'/'workflows'/filename
        if not re.fullmatch(r'[A-Za-z0-9_.-]+\.ya?ml',filename) or not path.is_file():raise ValueError('Workflow not found')
        return workflows.parse_workflow(filename,path.read_text(encoding='utf-8-sig'))
    api=workflows.client(settings,repository,authorization)
    try:return workflows.workflow(api,filename,ref)
    finally:api.close()


@router.get('/api/studio/history',tags=['all workflow history'],dependencies=[Depends(local)])
def history(repository:str='',workflow:str='',page:int=Query(1,ge=1,le=1000),limit:int=Query(20,ge=1,le=100),status:str='',authorization:str|None=Header(default=None)):
    api=workflows.client(get_settings(),repository,authorization)
    try:
        params={'page':page,'per_page':limit}
        if status:params['status']=status
        suffix='actions/workflows/'+workflow+'/runs' if workflow else 'actions/runs'
        if workflow and not re.fullmatch(r'[A-Za-z0-9_.-]+\.ya?ml',workflow):raise ValueError('Invalid workflow')
        return workflows.cached_get(api,api.repo_path(suffix),**params)
    finally:api.close()


@router.get('/api/studio/history/{run_id}',tags=['all workflow history'],dependencies=[Depends(local)])
def history_run(run_id:int,repository:str='',authorization:str|None=Header(default=None)):
    api=workflows.client(get_settings(),repository,authorization)
    try:return {'run':workflows.cached_get(api,api.repo_path(f'actions/runs/{run_id}')),'jobs':api.jobs(run_id),'artifacts':workflows.all_artifacts(api,run_id)}
    finally:api.close()


@router.post('/api/studio/workflows/{filename}/dispatch',tags=['all workflow history'],dependencies=[Depends(write)])
def workflow_dispatch(filename:str,data:dict=Body(...),authorization:str|None=Header(default=None)):
    api=workflows.client(get_settings(),data.get('repository',''),authorization)
    try:return workflows.dispatch(api,filename,str(data.get('ref',get_settings().ref)),data.get('inputs',{}))
    finally:api.close()


@router.post('/api/studio/history/{run_id}/actions/{action}',tags=['all workflow history'],dependencies=[Depends(write)])
def history_action(run_id:int,action:str,data:dict=Body(default={}),authorization:str|None=Header(default=None)):
    if action not in ('cancel','rerun','rerun-failed-jobs'):raise ValueError('Invalid workflow action')
    api=workflows.client(get_settings(),data.get('repository',''),authorization)
    try:api._request('POST',api.repo_path(f'actions/runs/{run_id}/{action}'));return {'requested':action,'run_id':run_id}
    finally:api.close()


@router.get('/api/studio/history/{run_id}/artifacts/{artifact_id}',tags=['all workflow history'],dependencies=[Depends(local)])
def artifact_files(run_id:int,artifact_id:int,repository:str='',path:str|None=None,download:bool=False,authorization:str|None=Header(default=None),runtime=RUNTIME):
    api=workflows.client(get_settings(),repository,authorization)
    try:data=workflows.artifact(api,run_id,artifact_id,runtime.root/'runs'/'artifact-cache')
    finally:api.close()
    if download:return Response(data,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="artifact-{artifact_id}.zip"'})
    if path is None:return {'files':workflows.zip_files(data)}
    raw=workflows.zip_files(data,path);suffix=Path(path).suffix.lower()
    mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.mp3':'audio/mpeg','.wav':'audio/wav','.json':'application/json'}.get(suffix,'text/plain; charset=utf-8')
    return Response(raw,media_type=mime,headers={'X-Content-Type-Options':'nosniff'})


@router.post('/api/studio/history/{run_id}/import',tags=['all workflow history'],dependencies=[Depends(write)])
def import_output(run_id:int,data:dict=Body(...),authorization:str|None=Header(default=None),runtime=RUNTIME):
    api=workflows.client(get_settings(),data.get('repository',''),authorization)
    try:blob=workflows.artifact(api,run_id,int(data['artifact_id']),runtime.root/'runs'/'artifact-cache')
    finally:api.close()
    path=str(data['path'])
    if Path(path).suffix.lower() not in ('.txt','.md'):raise ValueError('Select a readable .txt or .md story from this artifact')
    text=workflows.zip_files(blob,path).decode('utf-8-sig')
    ident=runtime.create_project(str(data.get('title','Imported run '+str(run_id))),text)
    save(runtime.folder(ident)/'workflow-source.json',{'run_id':run_id,'artifact_id':data['artifact_id'],'path':path,'repository':data.get('repository') or get_settings().repo})
    return {'project_id':ident}


@router.get('/api/studio/history/{run_id}/jobs/{job_id}/logs',tags=['all workflow history'],dependencies=[Depends(local)])
def job_logs(run_id:int,job_id:int,repository:str='',authorization:str|None=Header(default=None)):
    api=workflows.client(get_settings(),repository,authorization)
    try:
        if not any(j['id']==job_id for j in api.jobs(run_id)):raise ValueError('Job does not belong to this run')
        return Response(workflows.blob(api,api.repo_path(f'actions/jobs/{job_id}/logs'),limit=4*1024*1024),media_type='text/plain',headers={'X-Content-Type-Options':'nosniff'})
    finally:api.close()


@router.get('/',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
@router.get('/ideas',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
@router.get('/music',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
@router.get('/workflows',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
@router.get('/outputs',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
@router.get('/connections',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
@router.get('/testing',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
def studio_page(runtime=RUNTIME):return page(ROOT/'storyforge'/'studio_ui.html',runtime)


@router.get('/production',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
def production_page(runtime=RUNTIME):return page(ROOT/'storyforge'/'production_ui.html',runtime,True)


@router.get('/images',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
def images_page(runtime=RUNTIME):return page(ROOT/'storyforge'/'image_ui.html',runtime,True).replace('href="/production" aria-current="page"','href="/" aria-current="page"')


@router.get('/writing',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
def writing_page(runtime=RUNTIME):
    return page(ROOT/'web'/'index.html',runtime).replace('href="styles.css"','href="/legacy/styles.css"').replace('href="console.html"','href="/console"').replace('src="js/app.js"','src="/legacy/js/app.js"').replace('<button type="button" id="use-demo"', '<button type="button" id="use-server" class="secondary">Use server GitHub connection</button><button type="button" id="use-demo"')


@router.get('/console',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
def console_page(runtime=RUNTIME):
    return page(ROOT/'web'/'console.html',runtime).replace('href="styles.css"','href="/legacy/styles.css"').replace('href="console.css"','href="/legacy/console.css"').replace('href="index.html"','href="/writing"').replace('src="js/console.js"','src="/legacy/js/console.js"')


@router.get('/legacy/{path:path}',include_in_schema=False,dependencies=[Depends(local)])
def legacy_asset(path:str):
    file=(ROOT/'web'/path).resolve()
    if not file.is_relative_to((ROOT/'web').resolve()) or file.suffix not in ('.css','.js') or not file.is_file():raise HTTPException(404,'Asset not found')
    if file.suffix=='.js':return Response(file.read_text(encoding='utf-8-sig'),media_type='application/javascript')
    return FileResponse(file,media_type='text/css')


@router.post('/api/studio/connections',tags=['studio configuration'],dependencies=[Depends(write)])
def configure_connections(data:dict=Body(...),runtime=RUNTIME):
    allowed={'muse_image_key':'MUSE_IMAGE_API_KEY','vultr_key':'VULTR_INFERENCE_API_KEY','serp_key':'SERPAPI_API_KEY','serp_backup_keys':'SERPAPI_BACKUP_KEYS','github_token':'STORYFORGE_GITHUB_TOKEN','google_client_id':'GOOGLE_CLIENT_ID','google_client_secret':'GOOGLE_CLIENT_SECRET','runner_repos':'STORYFORGE_RUNNER_REPOS'}
    if set(data)-set(allowed):raise ValueError('Unknown connection setting')
    for name,value in data.items():
        if not isinstance(value,str):raise ValueError('Credential and repository settings must be text')
        if name=='runner_repos' and value and any(not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo.strip()) for repo in value.split(',')):raise ValueError('Runner repositories must be owner/name pairs')
        if not isinstance(value,str) or len(value)>4000:raise ValueError('Invalid credential value')
        if value.strip():os.environ[allowed[name]]=value.strip()
    image_studio.CATALOG.cached=None
    return {'saved':'server memory only; values are never returned or written to project files','configured':features(runtime)['configured']}


@router.post('/api/studio/briefs/publish',tags=['creative writing'],dependencies=[Depends(write)])
def publish_brief(data:dict=Body(...),authorization:str|None=Header(default=None)):
    from ..contracts import request as validate_request
    if not isinstance(data.get('brief'),dict):raise ValueError('Supply a complete brief JSON object')
    brief=validate_request(data['brief']);name=str(data.get('name',''))
    if not re.fullmatch('[A-Za-z0-9_-]{1,100}',name):raise ValueError('Brief name must contain letters, numbers, hyphens or underscores')
    ref=str(data.get('ref','main'));api=workflows.client(get_settings(),'',authorization)
    try:
        path=api.repo_path('contents/examples/'+name+'.json');old=None
        from .github import GitHubError
        try:old=api.get(path,ref=ref)
        except GitHubError as exc:
            if exc.status!=404:raise
        if old and not data.get('replace'):raise ValueError('This brief already exists; set replace explicitly to overwrite it')
        body={'message':'Add author brief '+name,'branch':ref,'content':base64.b64encode((json.dumps(brief,ensure_ascii=False,indent=2)+'\n').encode()).decode()}
        if old:body['sha']=old['sha']
        response=api._request('PUT',path,json=body).json()
        return {'name':name,'ref':ref,'url':response.get('content',{}).get('html_url'),'message':'Brief published. Dispatch a workflow whose request_file input accepts this name.'}
    finally:api.close()


@router.get('/docs',response_class=HTMLResponse,include_in_schema=False,dependencies=[Depends(local)])
def studio_swagger(runtime=RUNTIME):
    from fastapi.openapi.docs import get_swagger_ui_html
    response=get_swagger_ui_html(openapi_url='/openapi.json',title='StoryForge Studio · Interactive API')
    text=response.body.decode().replace('SwaggerUIBundle({',"SwaggerUIBundle({requestInterceptor: (req) => { req.headers['X-Storyforge-Token']='"+runtime.token+"'; return req; },",1)
    return HTMLResponse(text)
