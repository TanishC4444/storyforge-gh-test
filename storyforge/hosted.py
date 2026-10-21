"""Quota-aware Google hosted inference. Secrets never enter packets or diagnostics."""
from __future__ import annotations
import fcntl,json,math,os,time,urllib.request,urllib.error
from pathlib import Path
from .storage import save

BASE='https://generativelanguage.googleapis.com/v1beta/models/'
MODELS={'gemma':'gemma-4-31b-it','flash':'gemini-3.8-flash'}
class HostedError(RuntimeError):pass

class GoogleHosted:
    def __init__(self,folder,key=None):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.key=key or os.getenv('GEMINI_API_KEY','');self.disabled=set()
    def request(self,path,body,timeout=300):
        if not self.key:raise HostedError('Google API key unavailable')
        req=urllib.request.Request(BASE+path,data=json.dumps(body).encode(),headers={'x-goog-api-key':self.key,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            # Do not persist provider error bodies: they may contain request data.
            raise HostedError('Google HTTP '+str(exc.code)) from None
        except (TimeoutError,OSError):raise HostedError('Google connection failed or timed out') from None
    def reserve(self,kind,tokens):
        limits={'gemma':(24,14000,120),'flash':(4,220000,6)}
        rpm,tpm,max_calls=limits[kind]
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
                    current['recent'].append([now,tokens]);current['calls']+=1;save(path,state);return
                wait=max(.2,61-(now-current['recent'][0][0]))
            time.sleep(min(wait,1))
    def can_rescue(self):
        path=self.folder/'quota.json'
        with (self.folder/'quota.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            value=json.loads(path.read_text()) if path.exists() else {}
            if value.get('_rescue_calls',0)>=2 or value.get('flash',{}).get('calls',0)>=5:return False
            value['_rescue_calls']=value.get('_rescue_calls',0)+1;save(path,value);return True

    def complete(self,kind,system,prompt,tokens,structured=False):
        if kind in self.disabled:raise HostedError(kind+' circuit open after prior provider failure')
        model=MODELS[kind]
        contents=[{'role':'user','parts':[{'text':prompt}]}]
        body={'systemInstruction':{'parts':[{'text':system}]},'contents':contents}
        try:
            count=self.request(model+':countTokens',{'contents':[{'parts':[{'text':system+'\n'+prompt}]}]},timeout=10).get('totalTokens')
        except HostedError:count=None
        estimate=count or math.ceil(len((system+prompt).encode())/3)
        print('Hosted '+model+': reserving '+str(estimate)+' input tokens',flush=True)
        self.reserve(kind,estimate)
        config={'maxOutputTokens':tokens,'thinkingConfig':{'thinkingLevel':'minimal' if kind=='gemma' else 'low'}}
        if structured:config['responseMimeType']='application/json'
        started=time.monotonic()
        for attempt in range(2):
            try:
                result=self.request(model+':generateContent',{**body,'generationConfig':config},timeout=150 if kind=='gemma' else 240);break
            except HostedError as exc:
                if attempt==0 and any(code in str(exc) for code in ['500','502','503','504']):
                    time.sleep(2);self.reserve(kind,estimate);continue
                if any(code in str(exc) for code in ['400','401','403','404','429']):self.disabled.add(kind)
                raise
        candidates=result.get('candidates',[])
        if not candidates or candidates[0].get('finishReason')!='STOP':raise HostedError('Hosted generation did not finish naturally')
        text=''.join(p.get('text','') for p in candidates[0]['content']['parts'] if not p.get('thought'))
        if not text.strip():raise HostedError('Hosted response was empty')
        return text,{'model':model,'provider':'google','seconds':round(time.monotonic()-started,3),'input_tokens':estimate,'usage':result.get('usageMetadata',{}),'finish_reason':'stop'}
