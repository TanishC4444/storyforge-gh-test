"""Live job logs and durable, prompt-free execution evidence."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import json
import os
from pathlib import Path
import threading
import time
from .storage import save, load

_CURRENT=ContextVar('story_tracker',default=None)


class Tracker:
    def __init__(self,folder,task,**details):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.started=time.monotonic();self.lock=threading.RLock()
        self.state={'task':task,'status':'running','phase':'starting','details':details,'model_calls_started':0,'model_calls_validated':0}
    def event(self,phase,message,**details):
        with self.lock:
            if phase=='api_attempt' and details.get('attempt',1)>1:
                counters=self.state.setdefault('api_retry_counts',{})
                key=details.get('stage') or 'unknown';counters[key]=counters.get(key,0)+1
            if phase in {'api_retry','api_failed'}:
                counters=self.state.setdefault('api_failure_counts',{})
                key=str(details.get('status_code') or 'transport');counters[key]=counters.get(key,0)+1
            if phase=='warning':self.state['warnings_count']=self.state.get('warnings_count',0)+1
            if phase=='state_loaded':self.state['story_progress']={'accepted_scenes':details.get('accepted_scenes',0),'total_scenes':details.get('planned_scenes'),'state_version':details.get('version')}
            if phase=='model_start':self.state['model_calls_started']+=1
            if phase=='validated':self.state['model_calls_validated']+=1
            event={'time':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':round(time.monotonic()-self.started,1),'phase':phase,'message':message,**details}
            self.state.update(phase=phase,last_event=event,elapsed_seconds=event['elapsed_seconds'])
            with (self.folder/'events.jsonl').open('a') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')
            save(self.folder/'status.json',self.state)
            suffix=' | '+json.dumps(details,ensure_ascii=False) if details else ''
            print('[%s +%.1fs] %s: %s%s'%(event['time'],event['elapsed_seconds'],phase,message.replace('\n',' '),suffix),flush=True)
    def finish(self,status,error=None):
        self.state['status']=status
        if error:self.state['error']=str(error)
        snapshot=self.folder/'snapshot.json'
        if snapshot.exists():
            value=load(snapshot)
            if 'request' in value:
                self.state['story_progress']={'accepted_scenes':len(value.get('accepted',[])),'total_scenes':value['request']['chapters']*value['request']['scenes_per_chapter'],'state_version':value['version'],'complete':value.get('complete',False),'completion_status':value.get('completion_status','in_progress')}
        self.state['files']=[str(p.relative_to(self.folder)) for p in sorted(self.folder.rglob('*')) if p.is_file() and p.name not in {'status.json','events.jsonl'}]
        self.event(status,'Task completed' if status=='success' else 'Task failed; inspect error and saved artifacts',error=str(error) if error else None)
        self.summary()
    def summary(self):
        target=os.getenv('GITHUB_STEP_SUMMARY')
        if not target:return
        rows=['### '+self.state['task'], '', '**Status:** '+self.state['status'],'','Elapsed: '+str(self.state.get('elapsed_seconds',0))+' seconds', '', 'Model calls started / validated: %s / %s'%(self.state['model_calls_started'],self.state['model_calls_validated'])]
        rows+=['','API retries by stage: `'+json.dumps(self.state.get('api_retry_counts',{}))+'`','API failures by status: `'+json.dumps(self.state.get('api_failure_counts',{}))+'`']
        rows+=['','Warnings: **'+str(self.state.get('warnings_count',0))+'**']
        if self.state.get('story_progress'):rows+=['','Story progress: `'+json.dumps(self.state['story_progress'])+'`']
        if self.state.get('error'):rows+=['','**Failure:** '+self.state['error'].replace('\n',' ')]
        events=[json.loads(x) for x in (self.folder/'events.jsonl').read_text().splitlines()]
        rows+=['','| Elapsed | Phase | Detail |','|---:|---|---|']
        for event in events:
            if event['phase']=='waiting':continue
            message=event['message'].replace('|','/').replace('\n',' ')
            rows.append('| %ss | %s | %s |'%(event['elapsed_seconds'],event['phase'],message))
        rows+=['','Full timings, retries and outputs are in the job artifact: `status.json`, `events.jsonl`, `calls/`, `packets/`.']
        with open(target,'a') as f:f.write('\n'.join(rows)+'\n')


def event(phase,message,**details):
    tracker=_CURRENT.get()
    if tracker:tracker.event(phase,message,**details)


@contextmanager
def heartbeat(message,interval=20):
    tracker=_CURRENT.get();stop=threading.Event();started=time.monotonic()
    def run():
        while not stop.wait(interval):
            if tracker:tracker.event('waiting',message,operation_seconds=round(time.monotonic()-started,1))
    thread=threading.Thread(target=run,daemon=True);thread.start()
    try:yield
    finally:stop.set();thread.join(timeout=1)


def tracked_stage(func):
    @wraps(func)
    def wrapped(task,source,out,*args,**kwargs):
        tracker=Tracker(out,task,scene_index=kwargs.get('index',args[0] if args else None),character=kwargs.get('character',args[1] if len(args)>1 else None),request=kwargs.get('request_file',args[2] if len(args)>2 else None),job=os.getenv('GITHUB_JOB'))
        token=_CURRENT.set(tracker)
        tracker.event('inputs','Loading request and required upstream artifacts')
        try:
            result=func(task,source,out,*args,**kwargs)
            tracker.finish('success');return result
        except BaseException as exc:
            tracker.finish('failure',exc);raise
        finally:_CURRENT.reset(token)
    return wrapped


def report(folder):
    folder=Path(folder);path=folder/'status.json'
    status=load(path) if path.exists() else {'status':os.getenv('TASK_RESULT','unknown'),'phase':'Task not reached; inspect setup or input-download step'}
    print(json.dumps(status,ensure_ascii=False,indent=2))
    target=os.getenv('GITHUB_STEP_SUMMARY')
    if target:
        url=os.getenv('STORY_ARTIFACT_URL','')
        text='### Job output\n\nStatus: **'+status['status']+'**\n\n'
        if url:text+='[Download this job’s outputs, status and event timeline]('+url+')\n'
        if not path.exists():text+='The story task did not create status; inspect the setup and artifact download steps.\n'
        with open(target,'a') as f:f.write(text)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['report']);parser.add_argument('--out',default='out')
    args=parser.parse_args();report(args.out)
