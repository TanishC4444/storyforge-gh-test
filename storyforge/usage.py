"""Prompt-free usage accounting. Observed tokens and reservations are distinct."""
from __future__ import annotations
import argparse,csv,fcntl,hashlib,json,os,time,uuid
from pathlib import Path
from .storage import save


def record(folder,provider,model,role,usage=None,**details):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    usage=usage or {}
    def number(*names):
        for name in names:
            value=usage.get(name)
            if type(value) is int and value>=0:return value
        return None
    row={'id':uuid.uuid4().hex,'time':time.time(),'run_id':os.getenv('GITHUB_RUN_ID'),
         'job':os.getenv('GITHUB_JOB'),'provider':provider,'model':model,'role':role,
         'input_tokens':number('promptTokenCount','prompt_tokens'),
         'output_tokens':number('candidatesTokenCount','completion_tokens'),
         'thinking_tokens':number('thoughtsTokenCount'),
         'cached_input_tokens':number('cachedContentTokenCount'),
         'total_tokens':number('totalTokenCount','total_tokens'),**details}
    with (folder/'usage.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with (folder/'usage.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
    return row


def collect(source):
    source=Path(source);rows=[];seen=set()
    usage_paths=list(source.rglob('usage.jsonl'))
    for path in usage_paths:
        for line in path.read_text().splitlines():
            row=json.loads(line)
            if row['id'] not in seen:rows.append(row);seen.add(row['id'])
    for path in source.rglob('calls/*.json'):
        root=path.parent.parent
        if any(p.is_relative_to(root) for p in usage_paths):continue
        value=json.loads(path.read_text());diag=value.get('diagnostic',{})
        if diag.get('fixture'):continue
        rid='legacy-'+value.get('digest',hashlib.sha256(path.read_bytes()).hexdigest())
        if rid in seen:continue
        usage=diag.get('usage',{})
        fields={target:usage.get(a,usage.get(b)) for target,a,b in [
            ('input_tokens','promptTokenCount','prompt_tokens'),('output_tokens','candidatesTokenCount','completion_tokens'),
            ('total_tokens','totalTokenCount','total_tokens'),('thinking_tokens','thoughtsTokenCount','thoughts_tokens'),
            ('cached_input_tokens','cachedContentTokenCount','cached_tokens')]}
        rows.append({'id':rid,'provider':diag.get('provider','cpu'),'model':value.get('model'),
                     'role':value.get('role'),'seconds':(diag.get('timings') or {}).get('total_seconds',value.get('seconds')),
                     'finish_reason':diag.get('finish_reason'),'status':'returned','legacy':True,**fields})
        seen.add(rid)
    # Old instrumentation recorded failed HTTP requests without token metadata.
    for path in source.rglob('provider-budget/requests.jsonl'):
        root=path.parent.parent
        if any(p.is_relative_to(root) for p in usage_paths):continue
        known_successes=sum(json.loads(p.read_text()).get('diagnostic',{}).get('provider')=='google' for p in (root/'calls').glob('*.json'))
        for position,line in enumerate(path.read_text().splitlines()):
            value=json.loads(line)
            if value.get('operation')!='generateContent':continue
            if value.get('outcome')=='success' and known_successes:
                known_successes-=1;continue
            rid=hashlib.sha256((str(path.relative_to(source))+str(position)+line).encode()).hexdigest()
            rows.append({'id':rid,'provider':'google','model':value['model'],'role':root.name,
                         'status':value['outcome'],'seconds':value['seconds'],
                         **{k:None for k in ['input_tokens','output_tokens','total_tokens','thinking_tokens','cached_input_tokens']}})
    return rows


def summarize(source,out,run_id=None):
    rows=collect(source);groups={}
    for row in rows:
        key=(row.get('provider'),row.get('model'),row.get('role'))
        item=groups.setdefault(key,{'provider':key[0],'model':key[1],'role':key[2],'requests':0,'unknown_usage_requests':0,
            'observed_input_tokens':0,'observed_output_tokens':0,'observed_total_tokens':0,'observed_thinking_tokens':0,'seconds':0})
        item['requests']+=1
        if row.get('total_tokens') is None:item['unknown_usage_requests']+=1
        for field in ['input_tokens','output_tokens','total_tokens','thinking_tokens']:
            item['observed_'+field]+=row.get(field) or 0
        item['seconds']+=row.get('seconds') or 0
    summary={'run_id':run_id or os.getenv('GITHUB_RUN_ID'),'requests':len(rows),
        'unknown_usage_requests':sum(r.get('total_tokens') is None for r in rows),
        'observed_input_tokens':sum(r.get('input_tokens') or 0 for r in rows),
        'observed_output_tokens':sum(r.get('output_tokens') or 0 for r in rows),
        'observed_total_tokens':sum(r.get('total_tokens') or 0 for r in rows),
        'by_model_and_role':list(groups.values()),'requests_detail':rows,
        'note':'Observed usage is not a bill. Unknown usage is not zero. Reservations are estimates and are excluded. CPU tokens are reported separately from Google API tokens.'}
    out=Path(out);out.mkdir(parents=True,exist_ok=True);save(out/'usage-summary.json',summary)
    with (out/'usage-summary.csv').open('w',newline='') as stream:
        fields=['provider','model','role','requests','unknown_usage_requests','observed_input_tokens','observed_output_tokens','observed_total_tokens','observed_thinking_tokens','seconds']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(groups.values())
    text=['| Provider | Model | Role | Requests | Input tokens | Output tokens | Unknown usage |', '|---|---|---|---:|---:|---:|---:|']
    for g in groups.values():text.append('| %s | %s | %s | %s | %s | %s | %s |'%(g['provider'],g['model'],g['role'],g['requests'],g['observed_input_tokens'],g['observed_output_tokens'],g['unknown_usage_requests']))
    text+=['',summary['note']];save(out/'usage-summary.md','\n'.join(text)+'\n')
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as stream:stream.write('\n'.join(text)+'\n')
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--out',required=True);parser.add_argument('--run-id')
    args=parser.parse_args();value=summarize(args.source,args.out,args.run_id)
    print(json.dumps({k:value[k] for k in ['run_id','requests','unknown_usage_requests','observed_total_tokens']}))
