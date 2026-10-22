"""Bounded, evidence-checked memory recovery; prose findings use the prose DAG."""
from .evidence import passages
from .patching import digest
from .storage import save
from .contracts import require


def prose_findings(verdict,prose):
    result=[];catalog=passages(prose)
    for issue in verdict.get('issues',[]):
        if issue.get('target')!='prose':continue
        selected=[(i,p) for i,p in enumerate(catalog) if issue['quote'] in p['text']]
        index,p=selected[0] if len(selected)==1 else (None,None)
        result.append({**issue,'category':'continuity_clock','paragraph':index,
                       'evidence_ids':[p['id']] if p else [c['id'] for c in catalog if c['text'] in issue['quote']],
                       'replacement':''})
    return {'issues':result,'reviewed_sha256':digest(prose)}


def recover(executor,req,out,prose,packet,instruction,extract,verify,result=None):
    """One regeneration and fresh independent review; never edits source prose."""
    result=result if result is not None else extract(executor,req,out,prose,packet,instruction)
    verdict=verify(executor,req,prose,result['memories'])
    save(out/'memory-initial-review.json',verdict)
    if not verdict['pass'] and not prose_findings(verdict,prose)['issues']:
        save(out/'memory-rejected.json',result)
        had_facts=bool(result['memories'])
        result=extract(executor,req,out,prose,{**packet,'rejected_memory':result,'verification_findings':verdict['issues']},
                       instruction+' Correct the rejected extraction using these findings. Preserve exact source specificity and uncertainty. Do not modify prose or assume facts from the proposed memory; extract from evidence_passages again.')
        require(not had_facts or bool(result['memories']),'Memory recovery cannot discard all rejected facts to bypass verification')
        verdict=verify(executor,req,prose,result['memories'])
        save(out/'memory-recovery.json',{'attempts':1,'verified':verdict['pass'],'prose_sha256':digest(prose)})
    return result,verdict
