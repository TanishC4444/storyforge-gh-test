"""Quota-aware Google hosted inference. Secrets never enter packets or diagnostics."""
from __future__ import annotations
import json,math,os,time,random,uuid,threading,urllib.request,urllib.error,hashlib
from . import file_lock as fcntl
from pathlib import Path
from .storage import save

BASE='https://generativelanguage.googleapis.com/v1beta/models/'
MODELS={'gemma':'gemma-4-31b-it','flash':'gemini-3.8-flash','flash36':'gemini-3.6-flash','lite':'gemini-3.5-flash-lite'}
class HostedError(RuntimeError):
    def __init__(self,message,*,daily=False,retry_after=60):
        super().__init__(message);self.daily=daily;self.retry_after=retry_after

class GoogleHosted:
    def __init__(self,folder,key=None,*,backup_keys=None,distinct_projects=None):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        primary=key or os.getenv('GEMINI_API_KEY','')
        try:backups=json.loads(os.getenv('GEMINI_API_KEYS','[]')) if backup_keys is None else backup_keys
        except ValueError:raise HostedError('GEMINI_API_KEYS must be a JSON array') from None
        if not isinstance(backups,list) or any(not isinstance(k,str) for k in backups):
            raise HostedError('GEMINI_API_KEYS must be a JSON array of strings')
        self.keys=list(dict.fromkeys(k.strip() for k in [primary,*backups] if k.strip()))
        self.key=self.keys[0] if self.keys else '';self.key_index=0
        self.key_lock=threading.RLock()
        self.disabled=set();self.reserve_flash_final=False;self.optimized=False
        use_pool=os.getenv('GEMINI_DISTINCT_PROJECTS','').lower()=='true' if distinct_projects is None else distinct_projects
        self.project_children=[GoogleHosted(self.folder/f'project-{i+1:02}',key=k,backup_keys=[],distinct_projects=False) for i,k in enumerate(self.keys)] if use_pool and len(self.keys)>1 else []
    def telemetry(self,path,seconds,outcome):
        value={'model':path.split(':')[0],'operation':path.split(':')[-1],'seconds':round(seconds,3),'outcome':outcome}
        with (self.folder/'telemetry.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            with (self.folder/'requests.jsonl').open('a') as stream:stream.write(json.dumps(value)+'\n')

    def request(self,path,body,timeout=300):
        # Credential failover is separate from model quotas. Never rotate on 429.
        for _ in range(len(self.keys) or 1):
            with self.key_lock:index=self.key_index;credential=self.key
            try:return self._request(path,body,timeout,credential)
            except HostedError as exc:
                if not any(code in str(exc) for code in ['HTTP 401','HTTP 403','API_KEY_INVALID']):raise
                with self.key_lock:
                    if self.key_index==index:
                        if index+1>=len(self.keys):raise
                        self.key_index+=1;self.key=self.keys[self.key_index]

    def _request(self,path,body,timeout=300,credential=None):
        if not self.key:raise HostedError('Google API key unavailable')
        budget=getattr(self,'request_budget',None)
        if budget is not None:
            if budget['remaining']<=0:raise HostedError('Provider request attempt budget exhausted; no further HTTP calls')
            budget['remaining']-=1
        req=urllib.request.Request(BASE+path,data=json.dumps(body).encode(),headers={'x-goog-api-key':credential or self.key,'Content-Type':'application/json'})
        from .runtime import worker_timeout_seconds
        timeout=min(timeout,worker_timeout_seconds())
        started=time.monotonic()
        try:
            with urllib.request.urlopen(req,timeout=timeout) as response:result=json.load(response)
            self.telemetry(path,time.monotonic()-started,'success')
            return result
        except urllib.error.HTTPError as exc:
            # Only an allowlisted status code is retained, never provider messages,
            # request text, URLs, keys, or arbitrary error details.
            try:
                payload=json.loads(exc.read()).get('error',{});status=payload.get('status','')
            except (ValueError,AttributeError):payload={};status=''
            allowed={'UNAVAILABLE','RESOURCE_EXHAUSTED','INVALID_ARGUMENT','PERMISSION_DENIED','UNAUTHENTICATED','NOT_FOUND','INTERNAL','DEADLINE_EXCEEDED'}
            invalid_key=any(isinstance(d,dict) and d.get('reason')=='API_KEY_INVALID' for d in payload.get('details',[]))
            error='Google HTTP '+str(exc.code)+(' '+status if status in allowed else '')+(' API_KEY_INVALID' if invalid_key else '')
            self.telemetry(path,time.monotonic()-started,error)
            details=payload.get('details',[])
            daily=exc.code==429 and any('perday' in str(v.get('quotaId','')).lower() for d in details if isinstance(d,dict) for v in d.get('violations',[]) if isinstance(v,dict))
            retry_after=60
            try:retry_after=max(1,min(3600,int(exc.headers.get('Retry-After','60'))))
            except (ValueError,TypeError,AttributeError):pass
            raise HostedError(error,daily=daily,retry_after=retry_after) from None
        except (TimeoutError,OSError):
            self.telemetry(path,time.monotonic()-started,'connection_failure')
            raise HostedError('Google connection failed or timed out') from None
    def reserve(self,kind,tokens):
        limits={'gemma':(24,14000,120),'flash':(4,220000,18 if self.optimized else 6),'flash36':(4,220000,18),'lite':(12,220000,450)}
        rpm,tpm,max_calls=limits[kind]
        if kind=='flash' and self.reserve_flash_final:max_calls-=1
        if tokens>tpm:raise HostedError('Input exceeds conservative hosted per-minute allowance')
        path=self.folder/'quota.json'
        while True:
            from .runtime import worker_timeout_seconds
            worker_timeout_seconds()
            with (self.folder/'quota.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                state=json.loads(path.read_text()) if path.exists() else {}
                current=state.setdefault(kind,{'calls':0,'recent':[]})
                if current['calls']>=max_calls:raise HostedError(kind+' run call budget exhausted')
                now=time.time();current['recent']=[r for r in current['recent'] if now-r[0]<61]
                if len(current['recent'])<rpm and sum(r[1] for r in current['recent'])+tokens<=tpm:
                    current['recent'].append([now,tokens]);current['calls']+=1
                    current.setdefault('reservations',[]).append({'id':uuid.uuid4().hex,'time':now,'tokens':tokens})
                    save(path,state);return
                wait=max(.2,61-(now-current['recent'][0][0]))
            time.sleep(min(wait,1))
    def inherit(self,paths):
        """Union upstream reservation IDs; shared ancestry is counted once.

        This carries ancestry across runners, but is not a distributed lock.
        Concurrent independent jobs can still contend for project-wide quotas.
        """
        paths=list(paths)
        if self.project_children:
            for i,child in enumerate(self.project_children):
                child.inherit([p for p in paths if p.parent.name==f'project-{i+1:02}'])
            return
        ledger={};health={}
        for path in paths:
            value=json.loads(path.read_text())
            for kind in MODELS:
                for item in value.get(kind,{}).get('reservations',[]):
                    ledger.setdefault(kind,{})[item['id']]=item
            prior_health=path.parent/'health.json'
            if prior_health.exists():
                for kind,item in json.loads(prior_health.read_text()).items():
                    if 'HTTP 400' not in item.get('error','') and item['until']>health.get(kind,{}).get('until',0):health[kind]=item
        if ledger:
            save(self.folder/'quota.json',{kind:{'calls':len(items),'reservations':list(items.values()),
                'recent':[[item['time'],item['tokens']] for item in items.values() if time.time()-item['time']<61]}
                for kind,items in ledger.items()})
        if health:save(self.folder/'health.json',health)

    def can_rescue(self):
        path=self.folder/'quota.json'
        with (self.folder/'quota.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            value=json.loads(path.read_text()) if path.exists() else {}
            if value.get('_rescue_calls',0)>=2 or value.get('flash',{}).get('calls',0)>=5:return False
            value['_rescue_calls']=value.get('_rescue_calls',0)+1;save(path,value);return True

    def circuit(self,kind,error=None):
        path=self.folder/'health.json'
        with (self.folder/'health.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            health=json.loads(path.read_text()) if path.exists() else {}
            if error is not None:
                delay=3600 if any(c in str(error) for c in ['400','401','403','404']) else 120
                if '429' in str(error):
                    delay=getattr(error,'retry_after',60)
                    if getattr(error,'daily',False):
                        from datetime import datetime,timedelta
                        from zoneinfo import ZoneInfo
                        now=datetime.now(ZoneInfo('America/Los_Angeles'))
                        delay=((now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)-now).total_seconds()
                health[kind]={'until':time.time()+delay,'error':str(error)}
                save(path,health)
            return health.get(kind,{}).get('until',0)>time.time()

    def project_complete(self,kind,system,prompt,tokens,structured,response_schema,role,policy):
        # The user explicitly confirmed that these credentials belong to distinct
        # projects. Keep quotas/circuits isolated; legacy key pools do not rotate
        # on quota errors unless this opt-in is enabled.
        policy=policy or {'timeout':120 if role=='chapter_quality' else 90,'thinking':'low','quality_routing':True,'literary_quality':True}
        seed=os.getenv('STORY_BATCH',os.getenv('STORY_CHARACTER',''))+os.getenv('GITHUB_JOB','')+str(role)+hashlib.sha256(prompt.encode()).hexdigest()
        batch=os.getenv('STORY_BATCH','')
        phase=os.getenv('GITHUB_JOB','')+str(role)
        start=((int(hashlib.sha256(phase.encode()).hexdigest()[:8],16)+int(batch)) if batch.isdigit() else int(hashlib.sha256(seed.encode()).hexdigest()[:8],16))%len(self.project_children)
        start=(start+policy.get('project_offset',0))%len(self.project_children)
        last=None;started=time.monotonic();budget=min(360 if role=='chapter_quality' else 240,policy.get('route_budget',360))
        order=[(start+offset)%len(self.project_children) for offset in range(len(self.project_children))]
        # Reading local health is not a provider attempt. Do not spend a bounded
        # selection on a project already known to be unavailable for this model.
        available=[slot for slot in order if kind not in self.project_children[slot].disabled and not self.project_children[slot].circuit(kind)]
        attempts=available[:policy.get('max_project_attempts',len(self.project_children))]
        for position,slot in enumerate(attempts):
            child=self.project_children[slot]
            from .runtime import worker_timeout_seconds
            remaining=min(budget-(time.monotonic()-started),worker_timeout_seconds())
            if remaining<1:break
            route_policy={**policy,'timeout':min(policy['timeout'],remaining/max(1,len(attempts)-position))}
            try:
                output,meta=child.complete(kind,system,prompt,tokens,structured,response_schema,role,route_policy)
                from .tracking import event
                event('project_route_selected','Independent project served request',project_slot=slot+1,provider=kind)
                return output,{**meta,'project_slot':slot+1}
            except HostedError as exc:
                last=exc
                from .tracking import event
                event('project_route_unavailable','Trying another independent project',project_slot=slot+1,provider=kind,error=str(exc))
                if any(c in str(exc) for c in ['HTTP 400','HTTP 404']):break
        raise last or HostedError('No project route available')

    def complete(self,kind,system,prompt,tokens,structured=False,response_schema=None,role=None,policy=None):
        if self.project_children:return self.project_complete(kind,system,prompt,tokens,structured,response_schema,role,policy)
        if not self.key:raise HostedError('Google API key unavailable')
        self.optimized=bool(policy and policy.get('quality_routing'))
        self.reserve_flash_final=(kind=='flash' and role!='chapter_quality')
        if kind in self.disabled or self.circuit(kind):raise HostedError(kind+' circuit open after prior provider failure')
        model=MODELS[kind]
        contents=[{'role':'user','parts':[{'text':prompt}]}]
        body={'systemInstruction':{'parts':[{'text':system}]},'contents':contents}
        size=len((system+prompt).encode())
        if policy and policy.get('estimate_small_calls') and size<=policy.get('estimate_max_bytes',4000):
            # One token per UTF-8 byte is conservative; larger calls still count.
            count=size
        else:
            try:
                count=self.request(model+':countTokens',{'contents':[{'parts':[{'text':system+'\n'+prompt}]}]},timeout=10).get('totalTokens')
            except HostedError as exc:
                if any(code in str(exc) for code in ['400','401','403','404','429']):
                    self.circuit(kind,exc);raise
                count=None
        estimate=count or math.ceil(size/3)
        print('Hosted '+model+': reserving '+str(estimate)+' input tokens',flush=True)
        self.reserve(kind,estimate+tokens)
        # Thinking shares the output ceiling; do not starve short script output.
        thinking_reserve=(2048+policy.get('output_retry_reserve',0)) if policy and policy.get('quality_routing') and kind!='gemma' else 0
        config={'maxOutputTokens':min(16384,tokens+thinking_reserve),'thinkingConfig':{'thinkingLevel':'minimal' if kind=='gemma' else 'low'}}
        if policy:config['thinkingConfig']['thinkingLevel']='minimal' if kind=='gemma' else policy.get('thinking','low')
        if policy and policy.get('literary_quality'):
            config['temperature']=.7 if role in {'writer','writer_beat','humanizer','structural_editor','global_repair'} else .2
        # Gemini supports native JSON schemas; Gemma uses the explicit prompt
        # contract. Do not assume JSON MIME/schema compatibility across families.
        if structured and kind!='gemma':
            config['responseMimeType']='application/json'
            if response_schema is not None:config['responseJsonSchema']=response_schema
        started=time.monotonic()
        attempts=1 if policy and (policy.get('literary_quality') or policy.get('request_attempt_limit')) else 2
        compatibility_retry=False
        for attempt in range(attempts):
            from .usage import record
            request_started=time.monotonic()
            from .tracking import event
            event('api_attempt','Starting provider request',stage=role,attempt=attempt+1,model=model)
            try:
                try:
                    result=self.request(model+':generateContent',{**body,'generationConfig':config},timeout=policy['timeout'] if policy else (150 if kind=='gemma' else 240))
                except HostedError as exc:
                    if 'HTTP 400' not in str(exc) or compatibility_retry or kind=='gemma':raise
                    # A provider schema/configuration rejection is not a model-wide
                    # outage. Keep the full prompt contract and application validator;
                    # retry once using JSON MIME without native grammar/thinking knobs.
                    compatibility_retry=True
                    safe={k:v for k,v in config.items() if k not in {'responseJsonSchema','thinkingConfig'}}
                    self.reserve(kind,estimate+tokens)
                    event('api_compatibility_retry','Retrying rejected generation configuration with application validation',stage=role,model=model)
                    compatible=body
                    if config.get('responseJsonSchema') is not None:
                        compatible={**body,'systemInstruction':{'parts':[*body['systemInstruction']['parts'],{'text':'Return JSON matching this schema; source/evidence validation remains mandatory: '+json.dumps(config['responseJsonSchema'],separators=(',',':'))}]}}
                    result=self.request(model+':generateContent',{**compatible,'generationConfig':safe},timeout=policy['timeout'] if policy else 240)
                candidate=result.get('candidates',[{}])
                record(self.folder,'google',model,role,result.get('usageMetadata'),attempt=attempt+1,seconds=round(time.monotonic()-request_started,3),status='returned',finish_reason=candidate[0].get('finishReason') if candidate else None,reserved_input_tokens=estimate)
                break
            except HostedError as exc:
                from .tracking import event
                import re
                status=re.search(r'HTTP (\d+)',str(exc))
                transient=any(code in str(exc) for code in ['500','502','503','504']) or bool(policy and any(code in str(exc) for code in ['timed out']))
                event('api_retry' if attempt+1<attempts and transient else 'api_failed','Provider request rejected',stage=role,status_code=int(status.group(1)) if status else None,attempt=attempt+1,error=str(exc))
                record(self.folder,'google',model,role,attempt=attempt+1,seconds=round(time.monotonic()-request_started,3),status=str(exc),reserved_input_tokens=estimate)
                if attempt+1<attempts and transient:
                    time.sleep(4+random.random());self.reserve(kind,estimate+tokens);continue
                if any(code in str(exc) for code in ['400','401','403','404']):self.disabled.add(kind)
                self.circuit(kind,exc)
                raise
        candidates=result.get('candidates',[])
        if not candidates or candidates[0].get('finishReason')!='STOP':
            if candidates:
                partial=''.join(p.get('text','') for p in candidates[0].get('content',{}).get('parts',[]) if not p.get('thought'))
                if partial.strip():save(self.folder/'incomplete-generation.json',{'role':role,'model':model,'text':partial,'finish_reason':candidates[0].get('finishReason'),'verified':False})
            raise HostedError('Hosted generation did not finish naturally: '+str(candidates[0].get('finishReason') if candidates else 'NO_CANDIDATE'))
        text=''.join(p.get('text','') for p in candidates[0]['content']['parts'] if not p.get('thought'))
        if not text.strip():raise HostedError('Hosted response was empty')
        return text,{'model':model,'provider':'google','seconds':round(time.monotonic()-started,3),'input_tokens':estimate,'usage':result.get('usageMetadata',{}),'finish_reason':'stop'}
