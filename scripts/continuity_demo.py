"""Focused live comparison, not the full Actions universe workflow or a quality guarantee."""
from __future__ import annotations
import argparse,copy,hashlib,json,os,random,time,shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from storyforge.hosted import GoogleHosted,HostedError,MODELS
from storyforge.storage import load,save
from storyforge.contracts import require,request as validate_request
from storyforge.canon import bridge
from storyforge.continuation import append_verified_branch
from storyforge.evidence import payload
from storyforge.editorial import editorial_review
from storyforge.fast_edit import validate as validate_edits
from storyforge.patching import apply,digest
from storyforge import memory_batches as memory
from storyforge.usage import summarize

ROOT=Path(__file__).resolve().parents[1]
CHECKS=['knowledge','resources_and_custody','irreversible_consequences','repetition','prose_craft']
WRITER='Write finished fiction only. Respect the supplied author brief, established events and chapter task. A character knows only what they have learned. No outline, commentary, review labels, or recap. Aim for 220–280 words, with concrete detail, varied sentences and consequential action.'


def request(case):
    req=copy.deepcopy(load(ROOT/'examples/chaos-novel-practice.json'))
    req.update(project_id='continuity-demo',title=case['title'],premise=case['premise'],chapters=3,words_per_scene=250,medium='novel',references=[],world_rules=case['rules'],initial_facts=case['facts'],scene_designs=[])
    req['adaptation']['strength']=0
    req['creative_freedom'].update(enabled=False,resurrection=False)
    req['execution_policy'].update(model_routing='quality',continue_with_warnings=False,hosted_required_roles=['memory','memory_quality'],hosted_routes={'memory':['lite'],'memory_quality':['lite']})
    req['api_roles']={'memory':'lite','memory_quality':'lite'}
    req['characters']=[{'id':name.lower(),'name':name,'goal':'Act within the author brief.','voice':'Distinct, concrete speech.'} for name in ['Iona','Val','Sen']]
    req['plot_design']={};req['world_design']={}
    return validate_request(req)


def state_for(case):
    req=request(case)
    return {'version':0,'request':req,'memories':[dict(f,id=f'm{i:05}',source='user_input',state_version=0) for i,f in enumerate(case['facts'])],
            'accepted':[],'retrieval':{'sources':[]},'draft_memories':[]}


def schema_review():
    check={'type':'object','properties':{'id':{'type':'string','enum':CHECKS},'verdict':{'type':'string','enum':['pass','fail']},'evidence_ids':{'type':'array','minItems':1,'maxItems':3,'items':{'type':'string'}},'reason':{'type':'string','minLength':20}},'required':['id','verdict','evidence_ids','reason'],'additionalProperties':False}
    issue={'type':'object','properties':{'severity':{'type':'string','enum':['blocking','advisory']},'category':{'type':'string','enum':CHECKS},'evidence_ids':{'type':'array','minItems':1,'maxItems':3,'items':{'type':'string'}},'problem':{'type':'string'},'fix':{'type':'string'}},'required':['severity','category','evidence_ids','problem','fix'],'additionalProperties':False}
    return {'type':'object','properties':{'pass':{'type':'boolean'},'checks':{'type':'array','items':check},'issues':{'type':'array','items':issue}},'required':['pass','checks','issues'],'additionalProperties':False}


class Provider:
    def __init__(self,out):
        self.out=Path(out);self.counter=0
        self.client=GoogleHosted(self.out/'provider-budget')
        self.client.request_budget={'remaining':2}
        for child in self.client.project_children:child.request_budget=self.client.request_budget
    def call(self,role,packet,instruction,tokens=2000,schema=None):
        self.counter+=1;folder=self.out/f'call-{self.counter:02}-{role}'
        save(folder/'input.json',{'instruction':instruction,'packet':packet})
        self.client.request_budget['remaining']=2
        started=time.monotonic()
        try:
            text,meta=self.client.complete('flash36',instruction,json.dumps(packet,ensure_ascii=False),tokens,structured=schema is not None,response_schema=schema,role=role,
                policy={'timeout':55,'route_budget':65,'thinking':'low','quality_routing':True,'literary_quality':True,'max_project_attempts':2,'request_attempt_limit':2,'estimate_small_calls':True,'estimate_max_bytes':48000})
            save(folder/'output.txt',text);save(folder/'metadata.json',meta)
            return json.loads(text) if schema else text
        except (HostedError,ValueError) as exc:
            save(folder/'failure.json',{'error':str(exc),'seconds':round(time.monotonic()-started,3)})
            raise


def writer_packet(case,history,chapter):
    return {'author_brief':case['premise'],'world_rules':case['rules'],'initial_facts':case['facts'],
            'all_previous_chapters':list(history),'chapter_number':chapter+1,'chapter_task':case['chapters'][chapter],
            'target_words':250}


def review_scene(provider,case,history,prose,state):
    data={'author_brief':case['premise'],'world_rules':case['rules'],'chapter_history':history,'source_verified_memory':bridge(state),**payload(prose),'required_checks':CHECKS}
    raw=provider.call('editorial',data,'Assess the current scene against its actual prior text, facts and author brief. Do not demand a future task early. Judge knowledge, resource custody, irreversible events, non-purposeful repetition and concrete prose craft. Do not invent faults. Assess every required check once with pass or fail; absence of a relevant change can pass with an evidence-supported explanation. Any fail needs a matching source-supported ISSUE; use one to three distinct supplied passage IDs per check and issue, including passing checks. Never return empty evidence. Advisory style preferences must not become blocking facts.',2500,schema_review())
    return editorial_review(raw,prose,CHECKS)


def repair_scene(provider,case,history,prose,review):
    from storyforge.evidence import passages
    batch={'id':'scene','owned':[p['id'] for p in passages(prose)],'context':passages(prose)}
    raw=provider.call('repair',{'author_brief':case['premise'],'world_rules':case['rules'],'history':history,'findings':review,**payload(prose)},
        'Correct the demonstrated blocking issues only. Return JSON {"replacements":{"p001":"complete replacement paragraph"}}. Own only supplied paragraph IDs; do not add IDs or delete paragraphs. Preserve unaffected prose, character voice, plot and author choices.',2400,
        {'type':'object','properties':{'replacements':{'type':'object','additionalProperties':{'type':'string'}}},'required':['replacements'],'additionalProperties':False})
    # Production source ownership and patch checks guard every applied paragraph.
    result=validate_edits(raw,batch)
    return apply(prose,result['replacements'],digest(prose))


def retain_memory(state,card,prose,folder,prior=None):
    folder=Path(folder);save(folder/'edited/prose.txt',prose)
    if prior and (prior/'verified/review.json').exists() and (prior/'memory/memory.json').exists():
        from storyforge.batch_pipeline import bind_state
        proof=load(prior/'verified/review.json');facts=load(prior/'memory/memory.json')
        if proof.get('pass') and not proof.get('unverified') and proof.get('source_sha256')==digest(prose) and proof.get('state_sha256')==bind_state(state) and proof.get('memory_sha256')==bind_state(facts):
            append_verified_branch(state,facts,card['id'],prose,proof)
            shutil.copytree(prior,folder,dirs_exist_ok=True)
            save(folder/'reuse.json',{'unchanged_source_state_and_memory':True,'source_sha256':digest(prose)})
            return
    p=memory.extract_plan(state,folder,folder/'plan')
    for b in p['batches']:
        memory.extract_batch(state,card,folder,folder/'batches'/b['id'],'worker',b['id'])
    extracted=memory.extract_join(state,folder,folder/'memory')
    require(not extracted.get('unverified'),'Memory extraction unavailable: '+str(extracted.get('error')))
    p=memory.plan(state,folder,folder/'plan','preflight')
    # Modest source-batch concurrency; state remains immutable until all checks join.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(memory.check,state,card,folder,folder/'batches'/('check-'+b['id']),'worker',b['id']) for b in p['batches']]
        for future in futures:future.result()
    verdict=memory.join(state,folder,folder/'verified')
    require(verdict.get('pass') and not verdict.get('unverified'),'Memory handoff blocked; see verification artifacts')
    append_verified_branch(state,extracted,card['id'],prose,verdict)
    save(folder/'state-after.json',state)


def run_arm(case,arm,out,resume=None):
    out=Path(out);provider=Provider(out);state=state_for(case);history=[];started=time.monotonic();reviews=[]
    prior=Path(resume)/arm if resume else None
    prior_result=load(prior/'result.json') if prior and (prior/'result.json').exists() else {}
    if prior_result:
        shutil.copytree(prior,out/'previous-attempt')
        provider.client.inherit(prior.rglob('quota.json'))
    resumed=0
    result={'arm':arm,'model':MODELS['flash36'],'complete':False,'chapters_written':0,'errors':[],'editorial':reviews}
    try:
        for i,task in enumerate(case['chapters']):
            chapter=out/f'chapter-{i+1:02}';card={'id':f'ch{i+1:02}-sc01','chapter':i+1,'pov':'iona','participants':['iona','val','sen'],'goal':task,'obstacle':'The situation described in the author brief.','intended_change':task,'location':'As established in the story.','time':'Immediately after the previous chapter.'}
            packet=writer_packet(case,history,i)
            if arm=='storyforge':packet['source_verified_memory']=bridge(state)
            save(chapter/'writer-input.json',packet)
            previous=prior/f'chapter-{i+1:02}' if prior else None
            if previous and (previous/'original.txt').exists():
                require(load(previous/'writer-input.json')==packet,'Resumed writer inputs differ; refusing silent regeneration')
                metas=list(prior.glob('call-*-writer/metadata.json'))
                require(metas and all(load(p)['model']==MODELS['flash36'] for p in metas),'Resumed writing model differs')
                prose=(previous/'original.txt').read_text();resumed+=1
                save(chapter/'resume.json',{'source':str(previous),'source_sha256':digest(prose),'identical_writer_input':True})
            else:prose=provider.call('writer',packet,WRITER,1800)
            save(chapter/'original.txt',prose)
            # Save every returned draft even if later editorial or memory work fails.
            save(chapter/'prose.txt',prose)
            if arm=='storyforge':
                try:
                    if previous and (previous/'review.json').exists() and (previous/'prose.txt').read_text()==prose:
                        verdict=editorial_review(load(previous/'review.json'),prose,CHECKS)
                        save(chapter/'review-reused.json',{'source_sha256':digest(prose),'identical_writer_input':True})
                    else:verdict=review_scene(provider,case,history,prose,state)
                    save(chapter/'review.json',verdict)
                    if any(x['severity']=='blocking' for x in verdict['issues']):
                        proposed=repair_scene(provider,case,history,prose,verdict);save(chapter/'proposed-repair.txt',proposed)
                        final=review_scene(provider,case,history,proposed,state);save(chapter/'strict-final-review.json',final)
                        # Do not apply a repair merely because it was returned.
                        if final['pass']:prose=proposed;save(chapter/'prose.txt',prose)
                        verdict=final
                    reviews.append({'chapter':i+1,**verdict})
                except Exception as exc:
                    reviews.append({'chapter':i+1,'unverified':True,'error':str(exc)})
            history.append(prose);result['chapters_written']=len(history)
            save(out/'story.txt',case['title']+'\n\n'+'\n\n'.join(f'Chapter {j+1}\n\n{text}' for j,text in enumerate(history)))
            if arm=='storyforge' and i<len(case['chapters'])-1:
                retain_memory(state,card,prose,chapter/'memory',prior=previous/'memory' if previous else None)
                state['accepted'].append({'id':card['id'],'prose':prose,'participants':card['participants'],'canon_committed':False})
                state['version']+=1
        result['complete']=True
    except Exception as exc:result['errors'].append(str(exc))
    result.update(active_attempt_seconds=round(time.monotonic()-started,3),resumed_chapters=resumed,seconds=round(time.monotonic()-started+prior_result.get('seconds',0),3),words=sum(len(x.split()) for x in history),provisional=any(not x.get('pass') or x.get('unverified') for x in reviews))
    result['usage']=summarize(out,out/'usage')
    save(out/'result.json',result);save(out/'final-state.json',state)
    return result,history


def judge_pair(case,arms,out):
    # Label/order concealment reduces presentation bias, but cannot make this a human evaluation.
    names=['baseline','storyforge'];random.Random(case['title']).shuffle(names)
    labels=dict(zip(['A','B'],names));provider=Provider(Path(out)/'judge')
    packet={'brief':case['premise'],'rules':case['rules'],'chapter_tasks':case['chapters'],'criteria':case['criteria'],
            'manuscripts':{label:{f'chapter-{i+1}':payload(text) for i,text in enumerate(arms[name][1])} for label,name in labels.items()}}
    row={'type':'object','properties':{'criterion':{'type':'integer'},'verdict':{'type':'string','enum':['pass','fail','uncertain']},'chapter':{'type':'integer'},'evidence_ids':{'type':'array','minItems':1,'maxItems':3,'items':{'type':'string'}},'reason':{'type':'string'}},'required':['criterion','verdict','chapter','evidence_ids','reason'],'additionalProperties':False}
    entry={'type':'object','properties':{'label':{'type':'string','enum':['A','B']},'checks':{'type':'array','items':row},'prose_score':{'type':'integer','minimum':1,'maximum':5},'prose_reason':{'type':'string'}},'required':['label','checks','prose_score','prose_reason'],'additionalProperties':False}
    schema={'type':'object','properties':{'assessments':{'type':'array','items':entry}},'required':['assessments'],'additionalProperties':False}
    result=provider.call('blind_judge',packet,'Assess both anonymous manuscripts independently. Do not assume either is superior. Evaluate criteria numbered 1 to 5, exactly once each. Cite chapter number and exact supplied passage IDs for every conclusion. Absence-based failures may cite the relevant attempted scene. If source is insufficient, return uncertain. Distinguish purposeful motifs from redundant discovery. Rate prose craft 1–5 with reasons; these are model judgments, not human validation.',3500,schema)
    require(len(result['assessments'])==2 and {x['label'] for x in result['assessments']}=={'A','B'},'Judge must assess both manuscripts')
    for entry in result['assessments']:
        name=labels[entry['label']];entry['arm']=name
        require(len(entry['checks'])==5 and {x['criterion'] for x in entry['checks']}==set(range(1,6)),'Judge omitted or duplicated a criterion')
        for check in entry['checks']:
            require(check['verdict'] in {'pass','fail','uncertain'},'Unknown verdict')
            require(1<=check['chapter']<=len(arms[name][1]),'Judge cites nonexistent chapter')
            valid={x['id'] for x in payload(arms[name][1][check['chapter']-1])['evidence_passages']}
            require(bool(check['evidence_ids']) and set(check['evidence_ids'])<=valid,'Judge cites absent source evidence')
    result['limitations']='One model judge, same model family as writers; labels concealed, not an independent human study. Three short cases do not establish long-context superiority.'
    save(Path(out)/'assessment.json',result);return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=['secret','resource','consequence'],required=True);parser.add_argument('--out',required=True);parser.add_argument('--resume-root');args=parser.parse_args()
    case=load(ROOT/'demos/continuity-cases.json')[args.case];out=Path(args.out);save(out/'case.json',case)
    resume=Path(args.resume_root)/args.case if args.resume_root else None
    if resume and resume.exists():require(load(resume/'case.json')==case,'Resumed demo brief differs')
    arms={};order=['baseline','storyforge'];random.Random(args.case).shuffle(order)
    for arm in order:arms[arm]=run_arm(case,arm,out/arm,resume=resume)
    report={'case':args.case,'title':case['title'],'arms':{name:value[0] for name,value in arms.items()},'comparison':'incomplete','scope':'Focused production memory/patch components; not the full universe Actions graph. Baseline receives full text and identical initial brief; managed arm gets additional verification/editing calls. No forced context truncation or planted faulty baseline.'}
    if all(value[0]['complete'] for value in arms.values()):
        try:report['assessment']=judge_pair(case,arms,out);report['comparison']='assessed'
        except Exception as exc:report['judge_error']=str(exc)
    report['usage']=summarize(out,out/'usage')
    save(out/'report.json',report)
    text=['# '+case['title'],'',report['scope'],'','| Arm | Chapters | Words | Seconds | Complete |','|---|---:|---:|---:|---|']
    for name,(r,_) in arms.items():text.append(f"| {name} | {r['chapters_written']} | {r['words']} | {r['seconds']} | {r['complete']} |")
    text+=['','Comparison status: '+report['comparison'], '','Resumed chapters are reused only with identical saved writer inputs and writing model. Timings and usage include previous attempts; active-attempt seconds are separate in result.json. Token counts are observed usage, not a dollar bill. No financial cost is estimated without a verified pricing source.','']
    if report.get('assessment'):
        text+=['| Arm | Criteria passed | Failed | Uncertain | Model prose score / 5 |','|---|---:|---:|---:|---:|']
        for entry in report['assessment']['assessments']:
            counts={verdict:sum(c['verdict']==verdict for c in entry['checks']) for verdict in ['pass','fail','uncertain']}
            text.append(f"| {entry['arm']} | {counts['pass']} | {counts['fail']} | {counts['uncertain']} | {entry['prose_score']} |")
        text+=['',report['assessment']['limitations'],'']
    save(out/'REPORT.md','\n'.join(text))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as stream:stream.write('\n'.join(text))
    if report['comparison']!='assessed':raise SystemExit('Demo incomplete; all returned drafts and diagnostics were saved')

if __name__=='__main__':main()
