"""Quota-aware Google hosted inference. Secrets never enter packets or diagnostics."""
from __future__ import annotations
import fcntl,json,math,os,time,random,uuid,urllib.request,urllib.error
from pathlib import Path
from .storage import save

BASE='https://generativelanguage.googleapis.com/v1beta/models/'
MODELS={'gemma':'gemma-4-31b-it','flash':'gemini-3.8-flash'}
class HostedError(RuntimeError):pass

class GoogleHosted:
    def __init__(self,folder,key=None):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.key=key or os.getenv('GEMINI_API_KEY','');self.disabled=set();self.reserve_flash_final=False
    def telemetry(self,path,seconds,outcome):
        value={'model':path.split(':')[0],'operation':path.split(':')[-1],'seconds':round(seconds,3),'outcome':outcome}
        with (self.folder/'telemetry.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            with (self.folder/'requests.jsonl').open('a') as stream:stream.write(json.dumps(value)+'\n')

    def request(self,path,body,timeout=300):
        if not self.key:raise HostedError('Google API key unavailable')
        req=urllib.request.Request(BASE+path,data=json.dumps(body).encode(),headers={'x-goog-api-key':self.key,'Content-Type':'application/json'})
        started=time.monotonic()
        try:
            with urllib.request.urlopen(req,timeout=timeout) as response:result=json.load(response)
            self.telemetry(path,time.monotonic()-started,'success')
            return result
        except urllib.error.HTTPError as exc:
            # Only an allowlisted status code is retained, never provider messages,
            # request text, URLs, keys, or arbitrary error details.
            try:status=json.loads(exc.read()).get('error',{}).get('status','')
            except (ValueError,AttributeError):status=''
            allowed={'UNAVAILABLE','RESOURCE_EXHAUSTED','INVALID_ARGUMENT','PERMISSION_DENIED','UNAUTHENTICATED','NOT_FOUND','INTERNAL','DEADLINE_EXCEEDED'}
            error='Google HTTP '+str(exc.code)+(' '+status if status in allowed else '')
            self.telemetry(path,time.monotonic()-started,error)
            raise HostedError(error) from None
        except (TimeoutError,OSError):
            self.telemetry(path,time.monotonic()-started,'connection_failure')
            raise HostedError('Google connection failed or timed out') from None
    def reserve(self,kind,tokens):
        limits={'gemma':(24,14000,120),'flash':(4,220000,6)}
        rpm,tpm,max_calls=limits[kind]
        if kind=='flash' and self.reserve_flash_final:max_calls=5
        if tokens>tpm:raise HostedError('Input exceeds conservative hosted per-minute allowance')
        path=self.folder/'quota.json'
        while True:
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

        Distributed requests keep hosted work on a single dependency chain, so
        independent CPU branches cannot race to reserve provider capacity.
        """
        ledger={};health={}
        for path in paths:
            value=json.loads(path.read_text())
            for kind in MODELS:
                for item in value.get(kind,{}).get('reservations',[]):
                    ledger.setdefault(kind,{})[item['id']]=item
            prior_health=path.parent/'health.json'
            if prior_health.exists():
                for kind,item in json.loads(prior_health.read_text()).items():
                    if item['until']>health.get(kind,{}).get('until',0):health[kind]=item
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
                health[kind]={'until':time.time()+(3600 if any(c in str(error) for c in ['400','401','403','404','429']) else 120),'error':str(error)}
                save(path,health)
            return health.get(kind,{}).get('until',0)>time.time()

    def complete(self,kind,system,prompt,tokens,structured=False,response_schema=None,role=None):
        if not self.key:raise HostedError('Google API key unavailable')
        self.reserve_flash_final=(kind=='flash' and role!='chapter_quality')
        if kind in self.disabled or self.circuit(kind):raise HostedError(kind+' circuit open after prior provider failure')
        model=MODELS[kind]
        contents=[{'role':'user','parts':[{'text':prompt}]}]
        body={'systemInstruction':{'parts':[{'text':system}]},'contents':contents}
        try:
            count=self.request(model+':countTokens',{'contents':[{'parts':[{'text':system+'\n'+prompt}]}]},timeout=10).get('totalTokens')
        except HostedError:count=None
        estimate=count or math.ceil(len((system+prompt).encode())/3)
        print('Hosted '+model+': reserving '+str(estimate)+' input tokens',flush=True)
        self.reserve(kind,estimate+tokens)
        config={'maxOutputTokens':tokens,'thinkingConfig':{'thinkingLevel':'minimal' if kind=='gemma' else 'low'}}
        # Gemini supports native JSON schemas; Gemma uses the explicit prompt
        # contract. Do not assume JSON MIME/schema compatibility across families.
        if structured and kind=='flash':
            config['responseMimeType']='application/json'
            if response_schema is not None:config['responseJsonSchema']=response_schema
        started=time.monotonic()
        for attempt in range(2):
            from .usage import record
            request_started=time.monotonic()
            try:
                result=self.request(model+':generateContent',{**body,'generationConfig':config},timeout=150 if kind=='gemma' else 240)
                candidate=result.get('candidates',[{}])
                record(self.folder,'google',model,role,result.get('usageMetadata'),attempt=attempt+1,seconds=round(time.monotonic()-request_started,3),status='returned',finish_reason=candidate[0].get('finishReason') if candidate else None,reserved_input_tokens=estimate)
                break
            except HostedError as exc:
                record(self.folder,'google',model,role,attempt=attempt+1,seconds=round(time.monotonic()-request_started,3),status=str(exc),reserved_input_tokens=estimate)
                if attempt==0 and any(code in str(exc) for code in ['500','502','503','504']):
                    time.sleep(4+random.random());self.reserve(kind,estimate+tokens);continue
                if any(code in str(exc) for code in ['400','401','403','404','429']):self.disabled.add(kind)
                self.circuit(kind,exc)
                raise
        candidates=result.get('candidates',[])
        if not candidates or candidates[0].get('finishReason')!='STOP':raise HostedError('Hosted generation did not finish naturally: '+str(candidates[0].get('finishReason') if candidates else 'NO_CANDIDATE'))
        text=''.join(p.get('text','') for p in candidates[0]['content']['parts'] if not p.get('thought'))
        if not text.strip():raise HostedError('Hosted response was empty')
        return text,{'model':model,'provider':'google','seconds':round(time.monotonic()-started,3),'input_tokens':estimate,'usage':result.get('usageMetadata',{}),'finish_reason':'stop'}
