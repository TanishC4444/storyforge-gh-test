"""Local production planning app. Run: python -m storyforge.production_web."""
from __future__ import annotations
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import urlencode, urlsplit, parse_qs
from .production import create_plan, normalize_config, validate_breakdown, schedule, budget
from .production_exports import export, GoogleCalendar
from .production_research import ProviderError
from .soundtracks import context, discover_stories
from .storage import load, save
from . import image_studio


class ProductionServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self, address, folder):
        self.folder=Path(folder).resolve();context(self.folder)
        self.csrf=secrets.token_urlsafe(32);self.jobs={};self.plans={};self.oauth={}
        self.google=GoogleCalendar();self.pool=ThreadPoolExecutor(max_workers=1)
        self.guard=threading.Lock();self.busy=False
        super().__init__(address, Handler)

    def work(self, ident, data):
        try:
            def progress(message):self.jobs[ident]={'status':'running','message':message}
            plan=create_plan(self.folder,data.get('config',{}),data.get('images',[]),progress)
            self.plans[plan['id']]=plan
            self.jobs[ident]={'status':'complete','plan_id':plan['id']}
        except (ValueError,OSError,KeyError,TypeError) as exc:
            self.jobs[ident]={'status':'failed','message':str(exc)[:800]}
        except Exception:
            self.jobs[ident]={'status':'failed','message':'Planning failed unexpectedly; no external bookings or calendar writes were made.'}
        finally:
            with self.guard:self.busy=False

    def image_work(self, ident, data, prepare=False):
        try:
            def progress(message): self.jobs[ident]={'status':'running','message':message}
            if prepare:
                progress('Muse Glimmer is preparing your visual prompt')
                result=image_studio.prepare_prompt(self.folder,data,enhance=bool(data.get('enhance',True)))
                self.jobs[ident]={'status':'complete','prompt_result':result}
            else:
                result=image_studio.generate(self.folder,data,progress)
                self.jobs[ident]={'status':'complete','image_id':result['id']}
        except (ValueError,OSError,KeyError,TypeError) as exc:
            self.jobs[ident]={'status':'failed','message':str(exc)[:800]}
        except Exception:
            self.jobs[ident]={'status':'failed','message':'Image processing failed unexpectedly. Check the gallery before repeating a potentially billable request.'}
        finally:
            with self.guard:self.busy=False

    def plan(self, ident):
        if not re.fullmatch('[a-f0-9]{24}',ident):raise ValueError('Invalid plan ID')
        if ident not in self.plans:
            path=self.folder/'production'/'plans'/(ident+'.json')
            if not path.is_file():raise ValueError('Plan not found')
            self.plans[ident]=load(path)
        return self.plans[ident]


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    @property
    def origin(self):return f'http://127.0.0.1:{self.server.server_port}'
    def host_ok(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
    def send(self,raw,mime='application/json',code=200,filename=None):
        if not isinstance(raw,bytes):raw=json.dumps(raw,ensure_ascii=False).encode()
        self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if not self.host_ok():self.send({'error':'Host rejected'},code=403);return
        path=urlsplit(self.path).path
        try:
            if path=='/':
                page=Path(__file__).with_name('production_ui.html').read_text(encoding='utf-8-sig').replace('__CSRF__',self.server.csrf)
                self.send(page.encode(),'text/html; charset=utf-8')
            elif path=='/images':
                page=Path(__file__).with_name('image_ui.html').read_text(encoding='utf-8-sig').replace('__CSRF__',self.server.csrf)
                self.send(page.encode(),'text/html; charset=utf-8')
            elif path=='/api/images/models':
                self.send({'models':image_studio.CATALOG.list()})
            elif path=='/api/images':
                self.send({'images':image_studio.gallery(self.server.folder)})
            elif re.fullmatch(r'/api/images/[a-f0-9]{24}',path):
                self.send(image_studio.read_record(self.server.folder,path.split('/')[-1]))
            elif re.fullmatch(r'/media/images/[a-f0-9]{24}/[0-3]\.png',path):
                parts=path.split('/')
                image=image_studio.image_file(self.server.folder,parts[3],int(parts[4].split('.')[0]))
                self.send(image.read_bytes(),'image/png',filename=image.name if parse_qs(urlsplit(self.path).query).get('download') else None)
            elif path=='/api/config':
                plans=sorted((self.server.folder/'production'/'plans').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]
                self.send({'story':self.server.folder.name,'vultr':bool(os.getenv('VULTR_INFERENCE_API_KEY')),'search':bool(os.getenv('SERPAPI_API_KEY')),'google':bool(self.server.google.access or self.server.google.refresh),'google_oauth':bool(os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET')),'redirect_uri':self.origin+'/google/callback','plans':[p.stem for p in plans]})
            elif path.startswith('/api/job/'):
                self.send(self.server.jobs.get(path.split('/')[-1],{'status':'failed','message':'Job not found'}))
            elif path.startswith('/api/plan/'):
                self.send(self.server.plan(path.split('/')[-1]))
            elif path.startswith('/export/'):
                _,_,ident,kind=path.split('/')
                raw,mime=export(self.server.plan(ident),kind);self.send(raw,mime,filename='storyforge-'+kind)
            elif path=='/google/connect':
                client=os.getenv('GOOGLE_CLIENT_ID','')
                if not client or not os.getenv('GOOGLE_CLIENT_SECRET'):raise ValueError('Configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, and authorize the redirect URI shown in Settings.')
                state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
                self.server.oauth={state:(time.time(),verifier)}
                challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                url='https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':client,'redirect_uri':self.origin+'/google/callback','response_type':'code','scope':'https://www.googleapis.com/auth/calendar.events','state':state,'access_type':'offline','prompt':'consent','code_challenge':challenge,'code_challenge_method':'S256'})
                self.send_response(302);self.send_header('Location',url);self.send_header('Content-Length','0');self.end_headers()
            elif path=='/google/callback':
                query=parse_qs(urlsplit(self.path).query);state=query.get('state',[''])[0]
                record=self.server.oauth.pop(state,None)
                if not record or time.time()-record[0]>600:raise ValueError('Google connection expired or state mismatched; try connecting again')
                if 'code' not in query:raise ValueError('Google authorization was not granted')
                token=self.server.google.form_token({'grant_type':'authorization_code','code':query['code'][0],'redirect_uri':self.origin+'/google/callback','code_verifier':record[1]})
                self.server.google.accept(token)
                self.send(b'Google Calendar connected for this server session. Return to the production planner and refresh.','text/plain; charset=utf-8')
            else:self.send({'error':'Not found'},code=404)
        except (ValueError,OSError,KeyError) as exc:self.send({'error':str(exc)[:800]},code=400)
        except (BrokenPipeError,ConnectionResetError):pass

    def do_POST(self):
        if (not self.host_ok() or self.headers.get('Origin') not in (None,self.origin) or self.headers.get('X-Storyforge-Token')!=self.server.csrf or self.headers.get('Content-Type','').split(';')[0]!='application/json'):
            # Drain small rejected bodies before closing: otherwise Windows may
            # reset the connection before the browser receives the error response.
            length=self.headers.get('Content-Length','0')
            if length.isdigit() and int(length)<=65536:
                self.rfile.read(int(length))
            self.send({'error':'Request rejected; refresh the local planner'},code=403);return
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<=23*1024*1024:raise ValueError('Request too large (maximum three images, 5 MB each)')
            data=json.loads(self.rfile.read(length));path=urlsplit(self.path).path
            if not isinstance(data,dict):raise ValueError('Expected a request object')
            if path=='/api/generate':
                normalize_config(data.get('config',{}))
                with self.server.guard:
                    if self.server.busy:self.send({'error':'A plan is already running; wait for it to finish'},code=409);return
                    self.server.busy=True
                ident=secrets.token_hex(12);self.server.jobs[ident]={'status':'queued','message':'Preparing production plan'}
                if len(self.server.jobs)>50:self.server.jobs.pop(next(iter(self.server.jobs)))
                self.server.pool.submit(self.server.work,ident,data)
                self.send({'job_id':ident},code=202)
            elif path in ('/api/images/prepare','/api/images/generate'):
                prepare=path.endswith('/prepare')
                if prepare:image_studio.input_spec(data)
                else:image_studio.generation_settings(data,image_studio.CATALOG.get(data.get('model')))
                with self.server.guard:
                    if self.server.busy:self.send({'error':'A generation job is already running; wait for it to finish'},code=409);return
                    self.server.busy=True
                ident=secrets.token_hex(12);self.server.jobs[ident]={'status':'queued','message':'Preparing image request'}
                if len(self.server.jobs)>50:self.server.jobs.pop(next(iter(self.server.jobs)))
                self.server.pool.submit(self.server.image_work,ident,data,prepare)
                self.send({'job_id':ident},code=202)
            elif path=='/api/recalculate':
                original=self.server.plan(data['id']);plan=json.loads(json.dumps(original))
                cfg=normalize_config(data.get('config',plan['config']))
                breakdown=plan['breakdown'];breakdown['budget_items']=data.get('budget_items',breakdown['budget_items']);breakdown['scenes']=data.get('scenes',breakdown['scenes'])
                validate_breakdown(breakdown)
                plan['config']=cfg;plan['schedule']=schedule(breakdown['scenes'],cfg);plan['budget']=budget(breakdown['budget_items'],cfg)
                plan['id']=hashlib.sha256(json.dumps([original['id'],cfg,breakdown],sort_keys=True).encode()).hexdigest()[:24]
                plan['warnings'].append('Schedule/budget edited locally; research recommendations have not been regenerated.')
                save(self.server.folder/'production'/'plans'/(plan['id']+'.json'),plan);self.server.plans[plan['id']]=plan;self.send(plan)
            elif path=='/api/calendar-sync':
                self.send(self.server.google.sync(self.server.plan(data['id']),str(data.get('calendar','primary'))[:300]))
            else:self.send({'error':'Not found'},code=404)
        except (ValueError,OSError,KeyError,TypeError) as exc:self.send({'error':str(exc)[:800]},code=400)
        except (BrokenPipeError,ConnectionResetError):pass


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--story',type=Path);parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args();folder=args.story
    if folder is None:
        found=discover_stories(Path.cwd())
        if len(found)!=1:parser.error('Select a story with --story. Available: '+', '.join(map(str,found)))
        folder=found[0]
    try:
        server=ProductionServer(('127.0.0.1',args.port),folder)
        print(f'StoryForge production planner: http://127.0.0.1:{server.server_port}',flush=True)
        print('Story: '+str(server.folder),flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close();server.pool.shutdown(wait=False,cancel_futures=True)
    except (ValueError,OSError) as exc:parser.exit(1,str(exc)+'\n')

if __name__=='__main__':main()
