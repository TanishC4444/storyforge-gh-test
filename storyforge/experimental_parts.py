"""Opt-in paragraph work: explicit indices, immutable bases, and bounded parallel calls."""
import copy,hashlib,json,re
from difflib import SequenceMatcher
from .contracts import require
from .evidence import passages,payload
from .editorial import editorial_review,STORY_CHECKS,RHETORIC_CHECKS
from .output_schema import editorial_schema
from .patching import apply,digest
from .worker_policy import parallel
from .inference import ROOT


def changes(before,after):
    old=passages(before);new=passages(after);matcher=SequenceMatcher(None,[p['text'] for p in old],[p['text'] for p in new],autojunk=False)
    unchanged={};edited=[];removed=[]
    for tag,a,b,c,d in matcher.get_opcodes():
        if tag=='equal':unchanged.update({old[i]['id']:new[c+i-a]['id'] for i in range(a,b)})
        else:
            edited.extend({'index':j,'id':new[j]['id'],'text':new[j]['text']} for j in range(c,d))
            removed.extend({'index':i,'id':old[i]['id'],'text':old[i]['text']} for i in range(a,b))
    return {'before_sha256':digest(before),'after_sha256':digest(after),'changed':edited,'removed':removed,'unchanged':unchanged}


def needs_repair(review,req):
    threshold=req.get('execution_policy',{}).get('gate_repair_threshold','blocking')
    require(threshold in {'blocking','advisory'},'Invalid repair threshold')
    return not review.get('pass',False) or review.get('unverified',False) or any(i['severity']=='blocking' or threshold=='advisory' for i in review['issues'])


def bind_finding_targets(raw,catalog):
    """Passage IDs are authoritative; never ask models to count paragraphs twice."""
    lookup={p['id']:i for i,p in enumerate(catalog)}
    raw=copy.deepcopy(raw)
    for issue in raw.get('issues',[]):
        ids=issue.get('evidence_ids')
        require(isinstance(ids,list) and bool(ids) and all(pid in lookup for pid in ids),'Finding cites unknown evidence')
        scope=issue.get('scope')
        if scope is None:
            # Legacy cached outputs may contain off-by-one or one-based indices.
            # Preserve scene-level findings and cross-passage scope, not bad metadata.
            scope='paragraph' if issue.get('paragraph') is not None and len(ids)==1 else 'scene'
        require(scope in {'paragraph','scene'},'Invalid finding scope')
        require(scope!='paragraph' or len(ids)==1,'Paragraph finding must cite exactly one passage')
        issue['paragraph']=lookup[ids[0]] if scope=='paragraph' else None
    return raw


def review(executor,req,prose,packet,required,role,kind,prior=None,diff=None):
    source=payload(prose);catalog=passages(prose)
    active=list(required);retained=[]
    if prior is not None:
        require(diff['after_sha256']==digest(prose),'Diff targets stale candidate')
        for check in prior.get('checks',[]):
            if all(pid in diff['unchanged'] for pid in check.get('evidence_ids',[])) and check.get('evidence_ids') and not any(i.get('paragraph') is None and i['category']==check['id'] for i in prior.get('issues',[])):
                retained.append({**check,'evidence_ids':[diff['unchanged'][pid] for pid in check['evidence_ids']]})
        active=list(required)
        retained=[]
        packet={**packet,'previous_assessments':[{k:c.get(k) for k in ['id','verdict','reason']} for c in prior.get('checks',[])]}
        selected={p['id'] for p in diff['changed']}
        # Deletions need a surviving boundary as evidence; no full-scene resend.
        if not selected and catalog:selected.add(catalog[min(len(catalog)-1,diff['removed'][0]['index'] if diff['removed'] else 0)]['id'])
        # All dimensions (especially causality, POV and continuity) need the whole
        # candidate after a patch. Changed paragraphs remain explicit edit targets.
        packet['verification_scope']='Reassess the complete candidate for cross-paragraph consistency; focus corrections on the supplied changes without assuming unchanged text is automatically correct.'
        packet={**packet,'changed_paragraphs':diff['changed'],'removed_paragraphs':diff['removed'],'findings':prior['issues']}
    consolidated=req.get('execution_policy',{}).get('literary_quality',False)
    groups=[active] if consolidated else [active[i:i+3] for i in range(0,len(active),3)]
    def assess(group):
        data={**source,**packet,'required_checks':group}
        schema=editorial_schema(data)
        schema['properties']['issues']['items']['properties']['scope']={'type':'string','enum':['paragraph','scene']}
        schema['properties']['issues']['items']['required'].append('scope')
        def validate(raw):
            if isinstance(raw.get('checks'),dict):raw={**raw,'checks':[dict(c,id=k) for k,c in raw['checks'].items()]}
            raw=bind_finding_targets(raw,catalog)
            return editorial_review(raw,prose,group)
        return executor.call(role,data,'Review only the supplied evidence and required dimensions. Every finding needs severity blocking/advisory, existing evidence_ids, and scope=paragraph for a one-paragraph fix or scope=scene for cross-paragraph/whole-scene faults. A paragraph finding cites exactly one passage ID. Do not generate paragraph numbers; the application derives them from passage IDs. Never return unrequested dimensions. Required checks must be pass or fail, except subplot_function and reference_application may be not_applicable. For dialogue_tactics, assess narrated offers, refusals, bargaining or leverage when the brief prohibits direct dialogue; absence of quoted speech does not skip the check. Prior canon is context, not prose to edit.',tokens=1800 if consolidated else 1200,validator=validate,response_schema=schema,skill=(ROOT/'skills'/('story_quality.md' if kind=='story' else 'rhetoric_quality.md')).read_text())
    results=[assess(active)] if consolidated else parallel(req,'reviews',groups,assess)
    if any(r.get('unverified') for r in results):return {'pass':False,'unverified':True,'checks':[],'issues':[],'needs_repair':True,'reviewed_sha256':digest(prose)}
    result={'pass':all(r['pass'] for r in results),'checks':retained+[c for r in results for c in r['checks']],'issues':[i for r in results for i in r['issues']]}
    # Retain outstanding findings whose source paragraphs were not changed.
    if prior:
        for issue in prior['issues']:
            if issue.get('paragraph') is not None and all(pid in diff['unchanged'] for pid in issue.get('evidence_ids',[])):
                ids=[diff['unchanged'][pid] for pid in issue['evidence_ids']]
                result['issues'].append({**issue,'evidence_ids':ids,'paragraph':next(i for i,p in enumerate(catalog) if p['id']==ids[0])})
    if result['issues']:result['pass']=False
    result=editorial_review(result,prose,required)
    result.update(needs_repair=needs_repair(result,req),reviewed_sha256=digest(prose))
    return result


def repair(executor,req,prose,reviews):
    catalog=passages(prose);groups={};global_issues=[]
    for review in reviews:
        require(review.get('reviewed_sha256') in (None,digest(prose)),'Review targets stale prose')
        for issue in review['issues']:
            if issue.get('paragraph') is None:global_issues.append(issue)
            else:groups.setdefault(issue['paragraph'],[]).append(issue)
    def patch(item):
        index,findings=item;require(0<=index<len(catalog),'Repair index outside scene')
        result=executor.call('repair',{'paragraph':catalog[index]['text'],'findings':findings,'world_rules':req['world_rules'],'style':req['style']},'Patch this one paragraph for all findings together. Preserve unaffected facts and the requested voice. Return replacement and facts_changed (true if facts or knowledge change, or uncertain).',tokens=1300,validator=lambda x:x,response_schema={'type':'object','properties':{'replacement':{'type':'string'},'facts_changed':{'type':'boolean'}},'required':['replacement','facts_changed'],'additionalProperties':False})
        require(isinstance(result.get('replacement'),str) and type(result.get('facts_changed')) is bool,'Invalid paragraph patch')
        return catalog[index]['id'],result['replacement']
    patches=dict(parallel(req,'repair',list(groups.items()),patch))
    revised=apply(prose,patches,digest(prose))
    if global_issues:
        from .craft import validate_prose
        revised=executor.call('global_repair',{'prose':revised,'findings':global_issues,'world_rules':req['world_rules'],'style':req['style']},'Resolve the whole-scene findings in one pass. Preserve every unaffected fact and return the complete prose alone.',tokens=3200,output_format='text',validator=lambda text:validate_prose(text,req,check_length=getattr(executor,'backend','fixture')!='fixture'))
    diff=changes(prose,revised)
    return revised,{'changed':revised!=prose,'facts_changed':revised!=prose,'reviewed_sha256':digest(prose),'candidate_sha256':digest(revised),'diff':diff,'global_pass':bool(global_issues)}


def stitch(parts):
    require(bool(parts) and all(isinstance(p,str) and p.strip() for p in parts),'Missing writer beat')
    return '\n\n'.join(p.strip() for p in parts)


def writer(executor,req,packet,direction,validator=None):
    count=req.get('execution_policy',{}).get('writer_beats',1)
    require(type(count) is int and 1<=count<=4,'writer_beats must be 1–4')
    if count==1:return executor.call('writer',{**packet,'direction':direction},'Write a developed complete scene at target_words. Obey nonnegotiable_form first. Use the scene and chapter contracts, completed events, private knowledge, and distinct-writing guidance. Dramatize the decisive choice and its material consequences; do not summarize, recap, add headings, dialogue, invocation, or a moral.',tokens=4200,skill=(ROOT/'skills/distinct_writing.md').read_text(),validator=validator,output_format='text')
    schema={'type':'object','properties':{'beats':{'type':'array','minItems':count,'maxItems':count,'items':{'type':'object','properties':{k:{'type':'string'} for k in ['action','entry_state','exit_state']},'required':['action','entry_state','exit_state'],'additionalProperties':False}}},'required':['beats'],'additionalProperties':False}
    def validate_plan(value):
        require(isinstance(value,dict) and isinstance(value.get('beats'),list) and len(value['beats'])==count,'Wrong beat count')
        require(all(isinstance(beat,dict) and all(isinstance(beat.get(key),str) and beat[key].strip() for key in ['action','entry_state','exit_state']) for beat in value['beats']),'Invalid beat handoff')
        return value
    plan=executor.call('director',{'direction':direction,'scene':packet['scene'],'count':count},'Split the direction into ordered causal beats. Establish consistent entry and exit states, including custody and elapsed time. These are planned handoffs, not accepted canon.',tokens=900,validator=validate_plan,response_schema=schema)
    require(len(plan['beats'])==count,'Wrong beat count')
    def draft(item):
        i,beat=item
        return executor.call('writer_beat',{'scene_context':packet,'beat':beat,'prior_exit_state':plan['beats'][i-1]['exit_state'] if i else beat['entry_state'],'target_words':max(100,req['words_per_scene']//count)},'Draft only this beat. The prior exit is a planned state, not prose and not guaranteed history. Honor its constraints; do not recap, add a scene opening or conclude the entire scene unless this is the final beat.',tokens=1100)
    parts=parallel(req,'writer',list(enumerate(plan['beats'])),draft)
    # Non-overlapping ownership: seam i can change only beat i+1's first paragraph.
    def seam(i):
        left=passages(parts[i]);right=passages(parts[i+1])
        def one_paragraph(text):
            require(isinstance(text,str) and len(passages(text))==1,'Seam editor must return exactly one paragraph')
            return text
        result=executor.call('seam',{'left_exit':left[-1]['text'],'right_entry':right[0]['text'],'planned_handoff':plan['beats'][i]['exit_state']},'Smooth only right_entry to connect the handoff. Preserve facts and all later paragraphs. Return exactly one replacement paragraph alone.',tokens=700,validator=one_paragraph,output_format='text')
        return i+1,result,right[0]['end']
    seams=parallel(req,'writer',list(range(count-1)),seam)
    for index,text,end in seams:parts[index]=text+parts[index][end:]
    result=stitch(parts)
    return validator(result) if validator else result
