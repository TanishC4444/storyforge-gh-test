"""Fetch every artifact page, retaining the full graph's existing directory layout."""
import fnmatch,json,os,time,urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from scripts.stress_queue import GitHub


def fetch(api,run_id,destination,*,name=None,pattern=None):
    if name and pattern:raise ValueError('Choose an exact name or a pattern')
    patterns=(pattern[1:-1].split(',') if pattern and pattern.startswith('{') and pattern.endswith('}') else [pattern or '*'])
    selected=[];page=1
    while True:
        result=api.api(f'actions/runs/{int(run_id)}/artifacts?per_page=100&page={page}')
        rows=result['artifacts']
        selected.extend(a for a in rows if not a.get('expired') and (a['name']==name if name else any(fnmatch.fnmatchcase(a['name'],p) for p in patterns)))
        if not rows or page*100>=result['total_count']:break
        page+=1
    selected=list({a['id']:a for a in selected}.values())
    seen=set()
    for artifact in selected:
        label=artifact['name']
        if label in {'','.','..'} or '/' in label or '\\' in label:raise ValueError('Unsafe artifact name')
        if label in seen:raise ValueError('Ambiguous duplicate artifact: '+label)
        seen.add(label)
    if name and not selected:raise ValueError('Required artifact is missing: '+name)
    # Dependencies are complete before these reads; independent transfers do not
    # change job ordering or permit a scene to bypass its acceptance gate.
    def download(artifact):
        target=Path(destination) if name else Path(destination)/artifact['name']
        for attempt in range(3):
            try:
                api.artifact(artifact,target);return
            except (urllib.error.URLError,TimeoutError) as exc:
                if isinstance(exc,urllib.error.HTTPError) and exc.code not in {408,429,500,502,503,504}:raise
                if attempt==2:raise
                time.sleep(5*(attempt+1))
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(download,selected))
    return sorted(seen)


def main():
    spec=json.loads(os.environ['STORY_ARTIFACT_FETCH'])
    api=GitHub(os.environ['GITHUB_REPOSITORY'],os.environ['GH_TOKEN'])
    names=fetch(api,spec.get('run-id') or os.environ['GITHUB_RUN_ID'],spec.get('path','.'),name=spec.get('name'),pattern=spec.get('pattern'))
    print('Fetched '+str(len(names))+' artifacts across all listing pages.')

if __name__=='__main__':main()
