"""One final evidence-bound editorial judgment, without repair/review ping-pong."""
import copy,hashlib
from pathlib import Path
from .storage import save,load
from .evidence import payload
from .editorial import STORY_CHECKS,RHETORIC_CHECKS,editorial_review
from .output_schema import editorial_schema
from .inference import Executor
from .canon import working,cards
from .continuation import history as continuity_history
from .contracts import require
from .craft import validate_prose
from .flow_common import fingerprint
from .review_policy import contract
from .retrieval import application_packet

CHECKS=STORY_CHECKS+RHETORIC_CHECKS

def enabled(req):return req.get('execution_policy',{}).get('editorial_disagreement')=='one_strict_check'
def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def chapter_text(state,card,prose):return '\n\n'.join([s['prose'] for s in state['accepted'] if s['chapter']==card['chapter']]+[prose])

def split(verdict,required):
    issues=[i for i in verdict['issues'] if i['category'] in required]
    checks=[c for c in verdict['checks'] if c['id'] in required]
    return {'pass':verdict['pass'] and all(c['verdict']!='fail' for c in checks) and not any(i['severity']=='blocking' for i in issues),'checks':checks,'issues':issues}

def decide(req,state,card,prose,reviews,out,backend,*,batch_verdict=None):
    """Exactly one scoped model judgment, cached by immutable source + contract."""
    out=Path(out);chapter=chapter_text(state,card,prose)
    key=fingerprint([prose,chapter,req['premise'],contract(req),req.get('references'),req.get('adaptation'),continuity_history(state),card])
    path=out/'editorial-adjudication.json'
    if path.exists():
        old=load(path);require(old['decision_key']==key,'Cannot reuse final adjudication after source/contract changes');return old
    data={**payload(prose),'required_checks':CHECKS,'scene':card,'original_prompt':req['premise'],
          'prior_canon':(cards(continuity_history(state)) if req.get('performance',{}).get('memory_pair_batches') else working(state,query=str(card),budget=6500)),
          'reference_applications':application_packet(req,state['retrieval'],'story_quality',card['id']) if state.get('retrieval') else req.get('references',[]),
          'prior_scenes_in_current_chapter':[{'id':s['id'],'prose':s['prose'],'quality_status':s.get('quality_status','reviewed')} for s in state['accepted'] if s['chapter']==card['chapter']],
          'disputed_assessments':[{'pass':r.get('pass'),'unverified':r.get('unverified',False),
              'checks':[{k:c.get(k) for k in ['id','verdict','reason','evidence_ids']} for c in r.get('checks',[]) if not req.get('performance',{}).get('pipelined_living') or c.get('verdict')=='fail'],
              'issues':[{k:i.get(k) for k in ['severity','category','problem','fix','evidence_ids','quote'] if k in i and (k!='quote' or not i.get('evidence_ids'))} for i in r.get('issues',[])]} for r in reviews],
          'decision_policy':'This is the one final substantive judgment. Prior reviewers and editors have no authority over the author brief. Never approve merely to finish.'}
    schema=editorial_schema(data)
    instruction='''Perform ONE REALLY STRICT final prompt-compliance and literary check. Independently read the actual candidate and complete supplied chapter (prior scenes plus the current candidate evidence). Judge every required check against the original prompt and application-owned author contract, source-bound canon, individual knowledge, POV, voice/style, length, causal choices, resources and chapter progression. Treat previous editorial comments as allegations to verify, not commands or votes. Reject demands that contradict the requested form. Do not require dialogue for a no-dialogue brief. A stylistic preference is advisory, not a mandatory rewrite. Fail only for demonstrated substantive faults, with exact existing source passage IDs and a specific fix consistent with the author brief. Required dimensions cannot be skipped except the two explicitly optional checks. Do not change the prose, invent facts, relax the requested standard, or start another review/rewrite cycle. Return the final judgments, either pass or fail, without an issue quota. Keep each reason to one specific sentence.'''
    scoped=copy.deepcopy(req);scoped['max_stage_retries']=0
    # This call shares the established reviewer routing and time budget. A provider
    # transport failover is not another editorial iteration.
    executor=Executor(scoped,out/'final-check',backend)
    try:
        from .editorial_transport import call_editorial
        verdict=batch_verdict if batch_verdict is not None else call_editorial(executor,'chapter_quality',data,instruction,prose,CHECKS,3200)
        if verdict.get('unverified'):
            failed=copy.deepcopy(verdict);failed['pass']=False
            result={'decision_key':key,'prose_sha256':digest(prose),'chapter_sha256':digest(chapter),'judgment_calls':verdict.get('batch_count',1),'judgment_rounds':1,'verdict':failed,'story':{**split(failed,STORY_CHECKS),'unverified':True},'rhetoric':{**split(failed,RHETORIC_CHECKS),'unverified':True},'unverified':True}
            save(path,result);return result
        mechanical_override=None
        try:validate_prose(prose,req,check_length=backend!='fixture')
        except ValueError as exc:
            mechanical_override=str(exc)
            verdict=copy.deepcopy(verdict);verdict['pass']=False
            for check in verdict['checks']:
                if check['id']=='style_fidelity':check.update(verdict='fail',reason='The deterministic author-constraint check found: '+str(exc),evidence_ids=[data['evidence_passages'][0]['id']])
            verdict['issues'].append({'severity':'blocking','category':'style_fidelity','evidence_ids':[data['evidence_passages'][0]['id']],'problem':'Deterministic author-constraint violation: '+str(exc),'fix':'Restore the explicit author form and required length before treating this draft as reviewed.','replacement':''})
            verdict=editorial_review(verdict,prose,CHECKS)
        result={'mechanical_override':mechanical_override,'decision_key':key,'prose_sha256':digest(prose),'chapter_sha256':digest(chapter),'judgment_calls':batch_verdict.get('batch_count',6) if batch_verdict is not None else 1,'judgment_rounds':1,'verdict':verdict,'story':split(verdict,STORY_CHECKS),'rhetoric':split(verdict,RHETORIC_CHECKS),'unverified':False}
    except Exception as exc:
        failed={'pass':False,'checks':[],'issues':[],'unverified':True,'error':str(exc)}
        result={'decision_key':key,'prose_sha256':digest(prose),'chapter_sha256':digest(chapter),'judgment_calls':batch_verdict.get('batch_count',6) if batch_verdict is not None else 1,'judgment_rounds':1,'verdict':failed,'story':failed,'rhetoric':failed,'unverified':True}
    from .craft import length_status
    result['length_status']=length_status(prose,req)
    save(path,result);return result
