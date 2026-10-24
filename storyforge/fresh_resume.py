"""Import an unfinished episode into a fresh run; never inherit draft approval."""
import argparse,copy,shutil
from pathlib import Path
from .storage import load,save
from .contracts import require
from .story_checkpoint import preserve
from .resilience import creative_request
from .patching import digest


def restore(state,source,out):
    source,out=Path(source),Path(out)
    base=load(source/'quickstart/snapshot.json')
    require(base.get('backend')==state.get('backend'),'Fresh resume backend mismatch')
    old,new=creative_request(base['request']),creative_request(state['request'])
    require(old==new,'Fresh resume must use the same author brief, cast and initial facts')
    recovery=preserve(source,out/'imported')
    saved=load(out/'imported/checkpoint/snapshot.json')
    approved=len(saved.get('accepted',[]))
    result=copy.deepcopy(saved if approved else state)
    # Operational fixes come from this revision. Generated cast identities and
    # the exact completed plan/memory remain from the approved checkpoint.
    operational=['execution_policy','performance','api_roles','max_stage_retries','max_repairs','profile']
    for key in operational:result['request'][key]=copy.deepcopy(state['request'][key])
    from .flow_common import fingerprint
    result['request_hash']=fingerprint(result['request'])
    drafts={}
    for item in recovery['drafts']:
        i=item['scene']-1
        if i<approved:continue
        text=(out/'imported/drafts'/f's{i+1:02}'/'prose.txt').read_text()
        require(digest(text)==item['sha256'],'Changed source draft during fresh import')
        drafts[str(i)]={'prose':text,'source_sha256':digest(text),'approved':False}
    result['fresh_drafts']=drafts
    result['fresh_resume']={'resume_index':approved,'imported_drafts':list(drafts),'policy':'Only approved prefix becomes canon; every unfinished draft receives new literary and factual checks.'}
    # Audit the untouched prefix against the exact original evidence, rather
    # than demanding newly generated proofs for chapters that were not rerun.
    for i in range(approved):
        prefix=f's{i+1:02}'
        for suffix in ['accept','design','final_memory','memory_review','memory_recovery_join']:
            folder=source/(prefix+'_'+suffix)
            if folder.exists():shutil.copytree(folder,out/'seed-results'/folder.name,dirs_exist_ok=True)
    # A fresh recovery can itself become the source of another fresh recovery.
    existing=source/'quickstart/seed-results'
    if existing.exists():shutil.copytree(existing,out/'seed-results',dirs_exist_ok=True)
    save(out/'snapshot.json',result);save(out/'fresh-resume.json',result['fresh_resume'])
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--state',default='out/snapshot.json');p.add_argument('--source',default='inputs/restart');p.add_argument('--out',default='out');a=p.parse_args()
    restore(load(a.state),a.source,a.out)


if __name__=='__main__':main()
