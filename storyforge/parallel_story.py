"""Independent scene contracts and drafts, followed by evidence-bound reconciliation."""
import argparse,copy,json,os
from pathlib import Path
from .contracts import request,plan,require,delta
from .storage import save,load
from .flow_common import fingerprint,example_path,object_schema,strings,generated
from .inference import Executor
from .output_schema import plan_schema
from .retrieval import retrieve,application_packet
from .evidence import payload
from .craft import validate_prose
from .canon import index,append
from .resilience import memory_extract
from .coordinator import MEMORY_INSTRUCTION,visible
from .experimental import review_memory
from .experimental_parts import review
from .editorial import STORY_CHECKS,RHETORIC_CHECKS


def identity(bundle):return bundle['brief_hash']
def scene_ids(req):return [f'ch{c:02}-sc{s:02}' for c in range(1,req['chapters']+1) for s in range(1,req['scenes_per_chapter']+1)]
def refs(bundle,card):
    return application_packet(bundle['request'],bundle['retrieval'],'writer',card['id'])
def initial_state(req):
    memories=[dict(m,id=f'm{i:05}',kind=m.get('kind','event'),source='user_input') for i,m in enumerate(req['initial_facts'])]
    return {'version':0,'request':req,'memories':memories,'canon':index(memories),'accepted':[]}


def prepare(name,out,backend,chapters=None,scenes=None,words=None):
    req=load(example_path(name))
    for key,value in [('chapters',chapters),('scenes_per_chapter',scenes),('words_per_scene',words)]:
        if value is not None:req[key]=value
    req=request(req);require(req['chapters']*req['scenes_per_chapter']<=24,'Parallel pilot supports at most 24 scenes')
    req['profile']='balanced';req.setdefault('execution_policy',{}).update(experimental=True,model_routing='quality',literary_quality=True,continue_with_warnings=False)
    if backend=='fixture':req['retrieval_mode']='lexical';req.pop('retrieval_weights',None)
    retrieval=retrieve(req);chunks=[]
    for chapter in range(1,req['chapters']+1):
        scoped=copy.deepcopy(req);scoped['chapters']=1
        scoped['performance']['application_plan_binding']=False
        scoped['premise']+=f' Develop ONLY chapter {chapter}, preserving the supplied overall arc and user constraints.'
        # One chapter per planning context keeps large requested lengths bounded.
        candidate=generated(scoped,Path(out)/'planning'/str(chapter),backend,'architect',{'request':scoped,'references':retrieval['sources']},
            'Plan every scene of this chapter in reading order. Establish time, place, POV, an attempted action, resistance and a consequential change. Adjacent scenes must have compatible handoffs. Plans are proposals, not accepted history.',
            plan_schema(scoped),lambda v:plan(v,scoped),lambda:_fixture_plan(scoped),tokens=3000)
        for c in candidate['scenes']:c.update(id=f'ch{chapter:02}-'+c['id'].split('-',1)[1],chapter=chapter)
        chunks.extend(candidate['scenes'])
    bundle={'request':req,'brief_hash':fingerprint(req),'retrieval':retrieval,'reference_hash':fingerprint(retrieval['sources']),'plan':{'scenes':chunks},'mode':'fixture' if backend=='fixture' else 'live'}
    save(Path(out)/'prepared.json',bundle)
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('matrix='+json.dumps({'scene_id':scene_ids(req)})+'\n')
    return bundle


def _fixture_plan(req):
    from .fixture import respond
    return json.loads(respond('architect',{},req))


def contract_schema(bundle,card):
    allowed=[r['id'] for r in refs(bundle,card)['references']]
    use=object_schema({'record_id':{'type':'string','enum':allowed} if allowed else {'type':'string'},'application':{'type':'string'}})
    return object_schema({'entry_state':strings(8),'exit_state':strings(8),'beats':strings(8),'knowledge_boundaries':strings(8),'custody_and_resources':strings(8),'time_and_location':{'type':'string'},'reference_uses':{'type':'array','items':use,'maxItems':len(allowed)}})


def validate_contract(value,bundle,card):
    require(isinstance(value,dict),'Scene contract must be an object')
    for key in ['entry_state','exit_state','beats','knowledge_boundaries','custody_and_resources']:
        require(isinstance(value.get(key),list) and all(isinstance(x,str) and x.strip() for x in value[key]),'Invalid contract '+key)
    require(3<=len(value['beats'])<=8,'A deep scene contract needs 3–8 actionable beats')
    require(bool(value.get('entry_state')) and bool(value.get('exit_state')),'Contract needs entry and exit states')
    require(isinstance(value.get('time_and_location'),str) and bool(value['time_and_location'].strip()),'Contract needs a time/location handoff')
    allowed={r['id'] for r in refs(bundle,card)['references']}
    require(isinstance(value.get('reference_uses'),list),'Contract needs reference applications')
    for use in value['reference_uses']:
        require(use.get('record_id') in allowed and bool(use.get('application')),'Reference is outside this scene scope or lacks an application')
    return value


def design(bundle,sid,out,backend,previous=None,findings=None):
    cards=bundle['plan']['scenes'];position=next(i for i,c in enumerate(cards) if c['id']==sid);card=cards[position]
    req=bundle['request'];state=initial_state(req)
    packet={'author_brief':req,'scene':card,'previous_planned_scene':cards[position-1] if position else None,'following_planned_scene':cards[position+1] if position+1<len(cards) else None,
            'initial_visible_facts':visible(state['memories'],card['pov']),'references':refs(bundle,card),'prior_contract':previous,'findings':findings or [],
            'status':'All future entry/exit conditions are proposed branch assumptions, not accepted canon or automatically shared character knowledge.'}
    fixture={'entry_state':['Continue from the preceding planned exit; preserve initial canon.'],'exit_state':[card['intended_change']],
             'beats':['Attempt the concrete task.','Meet resistance while preserving the stated alternatives.','Choose and pay the specific cost.'],
             'knowledge_boundaries':['Only participants witness this attempted action.'],'custody_and_resources':['Account for every transfer and cost.'],
             'time_and_location':card['time']+' at '+card['location'],'reference_uses':[]}
    value=generated(req,Path(out)/'calls',backend,'scene_designer',packet,
        'Develop a deep scene contract before writing. Specify compatible entry/exit conditions, 3–8 physical action beats, character-specific knowledge limits, custody/resources, elapsed time and scoped reference applications. Earlier planned outcomes are conditional assumptions; never grant later revelations early. Repair supplied findings without changing immutable author constraints.',
        contract_schema(bundle,card),lambda v:validate_contract(v,bundle,card),fixture)
    result={'scene_id':sid,'brief_hash':identity(bundle),'reference_hash':bundle['reference_hash'],'contract':value}
    save(Path(out)/'contract.json',result);return result


def audit_schema(ids,evidence=False):
    props={'scene_id':{'type':'string','enum':ids},'problem':{'type':'string'},'fix':{'type':'string'}}
    if evidence:props['evidence_ids']=strings(3)
    return object_schema({'pass':{'type':'boolean'},'issues':{'type':'array','items':object_schema(props),'maxItems':12}})


def validate_audit(value,ids,scenes=None):
    require(isinstance(value,dict) and type(value.get('pass')) is bool and isinstance(value.get('issues'),list),'Audit requires pass and issues')
    for issue in value['issues']:
        require(issue.get('scene_id') in ids and bool(issue.get('problem')) and bool(issue.get('fix')),'Invalid reconciler finding')
        if scenes is not None:
            allowed={p['id'] for p in payload(scenes[issue['scene_id']]['prose'])['evidence_passages']}
            require(isinstance(issue.get('evidence_ids'),list) and bool(issue['evidence_ids']) and set(issue['evidence_ids'])<=allowed,'Reconciliation finding lacks source evidence')
    require(not value['pass'] or not value['issues'],'Passing audit cannot retain unresolved findings')
    return value


def load_set(root,filename,ids,bundle):
    result={}
    for p in Path(root).rglob(filename):
        value=load(p);sid=value.get('scene_id')
        require(sid in ids and sid not in result,'Missing, duplicate or unexpected scene artifact')
        require(value.get('brief_hash')==identity(bundle) and value.get('reference_hash')==bundle['reference_hash'],'Scene artifact belongs to a different brief/reference snapshot')
        result[sid]=value
    require(set(result)==set(ids),'A scene artifact is missing')
    return result


def join_contracts(bundle,source,out,backend,rounds=2):
    ids=scene_ids(bundle['request']);contracts=load_set(source,'contract.json',ids,bundle)
    for attempt in range(rounds+1):
        audits=[]
        bible={k:bundle['request'].get(k) for k in ['premise','world_rules','pov','style','quality_contract']}
        for window,group in enumerate(bounded_windows([contracts[s] for s in ids])):
            allowed=[c['scene_id'] for c in group]
            packet={'bible':bible,'contracts':group,'phase':'Proposals only; no history has been committed.'}
            audits.append(generated(bundle['request'],Path(out)/'audit'/str(attempt)/str(window),backend,'development_editor',packet,
                'Audit proposed scene/chapter handoffs before parallel writing: time, custody, resources, entry/exit dependencies, private knowledge, reference scope and style. Find contradictory assumptions or skipped causal steps. Name the contract to revise; pass only if supplied contracts are compatible.',
                audit_schema(allowed),lambda v,allowed=allowed:validate_audit(v,allowed),{'pass':True,'issues':[]},tokens=1800))
        verdict={'pass':all(a['pass'] for a in audits),'issues':[i for a in audits for i in a['issues']]}
        save(Path(out)/f'contract-audit-{attempt}.json',verdict)
        if verdict['pass']:break
        if attempt==rounds:raise ValueError('Scene contract reconciliation remains unresolved')
        for sid in dict.fromkeys(i['scene_id'] for i in verdict['issues']):
            contracts[sid]=design(bundle,sid,Path(out)/'revised'/sid,backend,contracts[sid]['contract'],[i for i in verdict['issues'] if i['scene_id']==sid])
    result={**bundle,'contracts':contracts};save(Path(out)/'ready.json',result);return result


def extract_facts(bundle,card,prose,out,backend):
    req=bundle['request'];executor=Executor(req,out,backend)
    return memory_extract(executor,req,out,prose,{**payload(prose),'characters':[c['id'] for c in req['characters']],
                         'prior_canon':initial_state(req)['memories']},MEMORY_INSTRUCTION)


def assess_scene(bundle,card,prose,facts,out,backend):
    req=bundle['request'];executor=Executor(req,out,backend)
    packet={'scene':card,'scene_contract':bundle['contracts'][card['id']]['contract'],
            'references':refs(bundle,card),'accepted_facts':initial_state(req)['memories'],
            'status':'Later scene entry conditions are proposed parallel-branch assumptions. Do not treat them as accepted history.'}
    story=review(executor,req,prose,packet,STORY_CHECKS,'story_quality','story')
    rhetoric=review(executor,req,prose,packet,RHETORIC_CHECKS,'rhetoric_quality','rhetoric')
    memory=review_memory(executor,req,prose,facts['memories'])
    return {'story':story,'rhetoric':rhetoric,'memory':memory}


def draft(bundle,sid,out,backend,prior=None,findings=None):
    req=bundle['request'];card=next(c for c in bundle['plan']['scenes'] if c['id']==sid)
    position=scene_ids(req).index(sid);ids=scene_ids(req)
    packet={'scene':card,'contract':bundle['contracts'][sid]['contract'],
            'preceding_contract':bundle['contracts'][ids[position-1]]['contract'] if position else None,
            'following_contract':bundle['contracts'][ids[position+1]]['contract'] if position+1<len(ids) else None,
            'bible':{'premise':req['premise'],'world_rules':req['world_rules'],'characters':[c for c in req['characters'] if c['id'] in card['participants']]},
            'pov_visible_initial_facts':visible(initial_state(req)['memories'],card['pov']),
            'references':refs(bundle,card),'target_words':req['words_per_scene'],'previous_draft':prior,'reconciliation_findings':findings or [],
            'branch_policy':'Preceding planned conditions are conditional branch assumptions. Do not narrate future scenes or grant a character private facts without a supported acquisition.'}
    def fixture():
        from .fixture import respond
        return respond('writer',{'scene':card},req)
    prose=generated(req,Path(out)/'writer',backend,'global_repair' if prior else 'writer',packet,
        'Write this complete scene to its deep contract and author style. Develop its decisive action rather than recapping the outline. Preserve planned entry/exit custody, knowledge and timing. Ground reference influence in choices and perception. If findings are supplied, correct all of them while preserving unaffected facts. Prose alone.',
        None,lambda text:validate_prose(text,req,check_length=backend!='fixture'),fixture,tokens=4200,text=True)
    facts=extract_facts(bundle,card,prose,Path(out)/'memory',backend)
    assessments=assess_scene(bundle,card,prose,facts,Path(out)/'quality',backend)
    result={'scene_id':sid,'brief_hash':identity(bundle),'reference_hash':bundle['reference_hash'],'prose':prose,'facts':facts,'reviews':assessments,
            'quality_status':'fixture' if backend=='fixture' else 'provisional_until_reconciled'}
    save(Path(out)/'scene.json',result);save(Path(out)/'prose.txt',prose);return result


def local_findings(scenes):
    findings=[]
    for sid,scene in scenes.items():
        for kind,verdict in scene['reviews'].items():
            if verdict['pass']:continue
            for issue in verdict['issues']:
                ids=issue.get('evidence_ids') or [p['id'] for p in payload(scene['prose'])['evidence_passages'] if issue.get('quote','') in p['text']]
                require(bool(ids),'Rejected local review needs cited prose before repair')
                findings.append({'scene_id':sid,'problem':issue['problem'],'fix':issue['fix'],'evidence_ids':ids,'review':kind})
            require(bool(verdict['issues']),'Unverified scene review cannot silently pass reconciliation')
    return findings


def bounded_windows(items,budget=18000):
    """Full coverage with one-item overlaps; refuse an oversized atomic scene."""
    windows=[];current=[];used=0
    for item in items:
        size=len(json.dumps(item,ensure_ascii=False))
        require(size<=budget,'One scene exceeds reconciliation window budget; shorten scenes or use a larger tested context')
        if current and used+size>budget:
            windows.append(current)
            overlap=current[-1:]
            current=overlap if len(json.dumps(overlap,ensure_ascii=False))+size<=budget else []
            used=sum(len(json.dumps(x,ensure_ascii=False)) for x in current)
        current.append(item);used+=size
    if current:windows.append(current)
    return windows


def reconciliation_packets(bundle,scenes):
    req=bundle['request'];ids=scene_ids(req)
    bible={k:req.get(k) for k in ['premise','world_rules','pov','style','quality_contract','chapter_contract']}
    items=[{'scene_id':sid,'source':payload(scenes[sid]['prose']),'actual_facts':scenes[sid]['facts']['memories'],
            'contract':bundle['contracts'][sid]['contract']} for sid in ids]
    for group in bounded_windows(items):
        yield {'bible':bible,'ordered_actual_scenes':group,'audit_scope':'Read every supplied passage. Audit local causal handoffs, chronology, knowledge, reference application and chapter boundaries. Proposed contracts are not proof of actual events.'},[x['scene_id'] for x in group]
    # Explicit long-range trails connect distant scenes without placing the whole
    # manuscript into one prompt. Every fact retains its original source passages.
    trails={}
    for sid in ids:
        for fact in scenes[sid]['facts']['memories']:
            key=fact.get('fact_key') or fact['kind']
            trails.setdefault(key,[]).append({'scene_id':sid,'fact':fact,'source':payload(scenes[sid]['prose'])})
    for key,trail in trails.items():
        if len({t['scene_id'] for t in trail})<2:continue
        for group in bounded_windows(trail):
            yield {'bible':bible,'fact_trail':key,'ordered_occurrences':group,'audit_scope':'Check long-range changes, resources, obligations, identity and knowledge against the actual cited prose. Repetition of an event is not an earned development.'},list(dict.fromkeys(t['scene_id'] for t in group))


def reconcile(bundle,source,out,backend,rounds=2):
    req=bundle['request'];ids=scene_ids(req);scenes=load_set(source,'scene.json',ids,bundle)
    for attempt in range(rounds+1):
        audits=[]
        for window,(packet,window_ids) in enumerate(reconciliation_packets(bundle,scenes)):
            verdict=generated(req,Path(out)/'reconciliation'/str(attempt)/str(window),backend,'chapter_quality',packet,
                'Audit the actual ordered narrative and fact trail for cohesion. Every requested change must name its scene and cite existing passage IDs from that scene. Never change immutable world rules or invent history to hide a discrepancy. Pass only when the supplied narrative, references and author constraints cohere.',
                audit_schema(window_ids,True),lambda v,allowed=window_ids:validate_audit(v,allowed,scenes),{'pass':True,'issues':[]},tokens=2400)
            audits.append(verdict)
        verdict={'pass':all(a['pass'] for a in audits),'issues':[i for a in audits for i in a['issues']]}
        findings=verdict['issues']+local_findings(scenes)
        save(Path(out)/f'reconciliation-{attempt}.json',{'global':verdict,'findings':findings})
        if verdict['pass'] and not findings:break
        if attempt==rounds:
            save(Path(out)/'checkpoint.json',{'status':'unresolved','bundle':bundle,'scenes':scenes,'findings':findings})
            raise ValueError('Reconciliation did not converge; provisional manuscript saved without canon commit')
        for sid in dict.fromkeys(i['scene_id'] for i in findings):
            scenes[sid]=draft(bundle,sid,Path(out)/'repairs'/str(attempt)/sid,backend,scenes[sid]['prose'],[i for i in findings if i['scene_id']==sid])
    state=initial_state(req)
    for sid in ids:
        card=next(c for c in bundle['plan']['scenes'] if c['id']==sid)
        # Parallel branch IDs cannot supersede facts from another branch. Rebind
        # extracted transitions to the reconciled reading-order canon, then verify.
        executor=Executor(req,Path(out)/'commit-memory'/sid,backend)
        from .canon import recording_context
        facts=memory_extract(executor,req,Path(out)/'commit-memory'/sid,scenes[sid]['prose'],
            {**payload(scenes[sid]['prose']),'characters':[c['id'] for c in req['characters']],**recording_context(state,card)},MEMORY_INSTRUCTION)
        verdict=review_memory(executor,req,scenes[sid]['prose'],facts['memories'])
        if not verdict.get('pass') or verdict.get('unverified'):
            save(Path(out)/'checkpoint.json',{'status':'memory_commit_unresolved','bundle':bundle,'scenes':scenes,'scene_id':sid,'review':verdict})
            raise ValueError('Reconciled memory did not verify; no final canon exported')
        state['version']+=1;append(state,facts['memories'],sid)
        state['accepted'].append({**card,'prose':scenes[sid]['prose'],'quality_status':'fixture' if backend=='fixture' else 'reviewed'})
    state.update(complete=True,completion_status='fixture_complete' if backend=='fixture' else 'complete',brief_hash=identity(bundle),reference_hash=bundle['reference_hash'])
    save(Path(out)/'snapshot.json',state)
    save(Path(out)/('FIXTURE_STORY.txt' if backend=='fixture' else 'FINAL_STORY.txt'),'\n\n* * *\n\n'.join(scenes[s]['prose'] for s in ids)+'\n')
    return state


def main():
    parser=argparse.ArgumentParser();parser.add_argument('task',choices=['prepare','contract','join','draft','reconcile'])
    parser.add_argument('--source',default='inputs');parser.add_argument('--out',default='out');parser.add_argument('--request-file',default='troy-practice')
    parser.add_argument('--backend',choices=['fixture','worker'],default='fixture');parser.add_argument('--scene-id')
    parser.add_argument('--chapters',type=int);parser.add_argument('--scenes',type=int);parser.add_argument('--words',type=int);parser.add_argument('--rounds',type=int,default=2)
    args=parser.parse_args();require(0<=args.rounds<=3,'Reconciliation rounds must be 0–3')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    if args.task=='prepare':prepare(args.request_file,out,args.backend,args.chapters,args.scenes,args.words);return
    name='ready.json' if args.task in {'draft','reconcile'} else 'prepared.json';bundle=load(Path(args.source)/'state'/name)
    if args.task=='contract':
        require(args.scene_id in scene_ids(bundle['request']),'Unknown scene ID');design(bundle,args.scene_id,out,args.backend)
    elif args.task=='join':join_contracts(bundle,Path(args.source)/'contracts',out,args.backend,args.rounds)
    elif args.task=='draft':
        require(args.scene_id in scene_ids(bundle['request']),'Unknown scene ID');draft(bundle,args.scene_id,out,args.backend)
    else:reconcile(bundle,Path(args.source)/'drafts',out,args.backend,args.rounds)

if __name__=='__main__':main()
