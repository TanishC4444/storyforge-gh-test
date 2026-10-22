"""Measured worker timings; no claims about literary quality or queue/setup time."""
import argparse,json,math,re
from pathlib import Path
from .storage import save
from .usage import collect


def percentile(values,fraction):
    return sorted(values)[max(0,math.ceil(len(values)*fraction)-1)] if values else None


def summarize(source,out,workflow=None):
    source=Path(source);rows=collect(source);groups={}
    for row in rows:
        if isinstance(row.get('seconds'),(int,float)):groups.setdefault(row.get('role') or 'unknown',[]).append(row['seconds'])
    review_files={};durations={};tasks={};repair=[];verify=[]
    for path in source.rglob('status.json'):
        if '_steps' in path.parts or '_chapters' in path.parts:continue
        value=json.loads(path.read_text());relative=path.relative_to(source);job=relative.parts[0]
        if len(relative.parts)!=2:continue
        durations[job]=value.get('elapsed_seconds',0);tasks[job]=value.get('task')
    for path in source.rglob('review.json'):
        relative=path.relative_to(source)
        if len(relative.parts)!=2:continue
        value=json.loads(path.read_text());review_files[relative.parts[0]]=value
        if 'needs_repair' in value:repair.append(value['needs_repair'])
        if tasks.get(relative.parts[0]) in {'verify','verify_rhetoric','memory_review'}:verify.append(value.get('pass',False))
    needs={}
    if workflow:
        text=Path(workflow).read_text();current=None
        for line in text.splitlines():
            match=re.fullmatch(r'  ([\w-]+):',line)
            if match:current=match[1];needs[current]=[]
            match=re.fullmatch(r'    needs: \[(.*)\]',line)
            if match and current:needs[current]=[x.strip() for x in match[1].split(',') if x.strip()]
    # Matrix duration is its longest branch, never the sum of concurrent branches.
    for job in needs:
        values=[v for k,v in durations.items() if k.startswith(job+'-')]
        if values:durations[job]=max(values)
    memo={}
    def critical(job,visiting=()):
        if job in memo:return memo[job]
        if job in visiting:raise ValueError('Workflow dependency cycle')
        memo[job]=durations.get(job,0)+max([critical(n,visiting+(job,)) for n in needs.get(job,[])],default=0)
        return memo[job]
    issues=[i for review in review_files.values() for i in review.get('issues',[])]
    result={'by_stage':{k:{'calls':len(v),'p50_seconds':percentile(v,.5),'p95_seconds':percentile(v,.95)} for k,v in groups.items()},
            'api_429_attempts':sum('429' in str(r.get('status')) for r in rows),
            'repair_gate_checks':len(repair),'repair_gate_skip_rate':sum(not x for x in repair)/len(repair) if repair else None,
            'verify_checks':len(verify),'verify_pass_rate':sum(verify)/len(verify) if verify else None,
            'findings_by_severity':{level:sum(i.get('severity')==level for i in issues) for level in ['blocking','advisory']},
            'observed_tokens':sum(r.get('total_tokens') or 0 for r in rows),
            'worker_critical_path_seconds':max([critical(k) for k in needs],default=None),
            'note':'Critical path covers observed stage execution only, excluding runner queue, setup and artifact transfer. Missing timings are not measured. Findings include separate review and verification passes; they are not a quality score.'}
    save(Path(out)/'performance.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);p.add_argument('--workflow')
    a=p.parse_args();summarize(a.source,a.out,a.workflow)
