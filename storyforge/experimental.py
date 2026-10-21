"""Opt-in DAG stages. Existing workflows retain their original stage behavior."""
import copy,json,shutil
from pathlib import Path
from . import contracts
from .storage import load,save
from .inference import Executor,ROOT
from .coordinator import packet,MEMORY_INSTRUCTION
from .evidence import payload,passages
from .editorial import STORY_CHECKS,RHETORIC_CHECKS
from .resilience import memory_extract
from .canon import append,recording_context
from .experimental_parts import review,repair,writer,changes,needs_repair
from .patching import digest
from .craft import author_packet

UNHANDLED=object()

def memory_hash(state):return digest(json.dumps(state['memories'],sort_keys=True,separators=(',',':')))

def choose(source,preferred,fallback,filename):
    for folder in [preferred,fallback]:
        path=Path(source)/folder/filename
        if path.exists():return path
    raise contracts.ContractError('Missing both '+preferred+' and '+fallback+'/'+filename)


def bind_memory(memory,before,after):
    diff=changes(before,after);retained=[]
    for item in memory['memories']:
        ids=item.get('evidence_ids') or [s['id'] for s in item.get('evidence_spans',[]) if s.get('id')]
        if not ids:
            ids=[p['id'] for p in passages(before) if any(p['start']<=span['start'] and span['end']<=p['end'] for span in item.get('evidence_spans',[]))]
        if ids and all(pid in diff['unchanged'] for pid in ids):
            clean={k:v for k,v in item.items() if not k.startswith('evidence')}
            clean['evidence_ids']=[diff['unchanged'][pid] for pid in ids];retained.append(clean)
    return retained,diff


def review_memory(executor,req,prose,memories):
    if not memories:return {'pass':True,'issues':[]}
    return executor.call('memory_quality',{'current_prose':prose,'proposed_memory':{'memories':memories}},'Verify only these changed facts and their knowledge holders against the supplied evidence. Unsupported inference fails. Return pass and issues with exact quotes.',tokens=1000,validator=lambda x:contracts.review(x,prose))


def run_bundle(task,source,out,state,index,profile,backend,request_file):
    from .dag import stage,output
    kind=task.split('_')[0];previous=Path(source)/'state'
    if kind=='plan' and state['request'].get('execution_policy',{}).get('chapter_outline_chunks'):
        from .contracts import plan as validate_plan
        combined={'title':state['request']['title'],'threads':[],'technique_stack':[],'scenes':[]}
        chunk_reports=[]
        for chapter in range(1,state['request']['chapters']+1):
            local=copy.deepcopy(state);req=local['request'];req['chapters']=1
            req['execution_policy']['chapter_outline_chunks']=False
            req['scene_designs']=[copy.deepcopy(c) for c in state['request']['scene_designs'] if c['id'].startswith(f'ch{chapter:02}-')]
            for card in req['scene_designs']:card['id']='ch01-'+card['id'].split('-',1)[1]
            req['premise']=state['request']['premise']+f' Plan ONLY chapter {chapter}: '+state['request']['chapter_arcs'][chapter-1]
            # Preserve the immutable original refinement while limiting this planner's scene allocation.
            local['refinement']={**local['refinement'],'original_prompt':req['premise'],'refined_prompt':req['premise']}
            local['accepted']=[]
            chunk=Path(out)/'_chapters'/str(chapter);save(chunk/'inputs/state/snapshot.json',local)
            result=run_bundle('plan_bundle',chunk/'inputs',chunk/'out',local,0,profile,backend,request_file)
            for card in result['plan']['scenes']:
                card['chapter']=chapter;card['id']=f'ch{chapter:02}-'+card['id'].split('-',1)[1]
                combined['scenes'].append(card)
            for key in ['threads','technique_stack']:
                combined[key]=list(dict.fromkeys(combined[key]+result['plan'].get(key,[])))
            chunk_reports.append(result.get('development_gates',{}).get('plan'))
        state['plan']=validate_plan(combined,state['request']);state['plan_approved']=True
        state['chapter_development_reviews']=chunk_reports
        save(Path(out)/'plan.json',state['plan']);save(Path(out)/'snapshot.json',state)
        output('characters',state['plan']['scenes'][0]['participants']);return state
    if kind=='refine' and state['request'].get('execution_policy',{}).get('compile_supplied_brief'):
        from .craft import compile_brief
        state['refinement']=compile_brief(state['request'])
        state['refinement_method']='compiled_user_brief_no_model_expansion'
        save(Path(out)/'refinement.json',state['refinement']);save(Path(out)/'snapshot.json',state)
        return state
    for suffix in ['', '_review','_revision','_gate']:
        name=kind+suffix;work=Path(out)/'_steps'/name;inputs=work/'inputs'
        shutil.copytree(previous,inputs/'state',dirs_exist_ok=True)
        if suffix=='_revision':shutil.copytree(previous,inputs/'design-review',dirs_exist_ok=True)
        stage(name,inputs,work/'out',index,None,request_file,profile,backend)
        previous=work/'out'
    result=load(previous/'snapshot.json');save(Path(out)/'snapshot.json',result)
    if (previous/'provider-budget').exists():shutil.copytree(previous/'provider-budget',Path(out)/'provider-budget',dirs_exist_ok=True)
    if kind=='plan':output('characters',result['plan']['scenes'][0]['participants'])
    return result


def reconcile(source,out,state,index,profile,backend,request_file):
    from .dag import stage,output
    anticipated=load(Path(source)/'anticipated/snapshot.json')
    expected=anticipated.get('design_memory_hash');actual=memory_hash(state)
    rerun=expected!=actual
    if rerun:
        inputs=Path(out)/'inline-design/inputs';save(inputs/'state/snapshot.json',state)
        result=stage('scene_design',inputs,Path(out)/'inline-design/out',index,None,request_file,profile,backend)
    else:
        result=copy.deepcopy(state);result['plan']['scenes'][index]=anticipated['plan']['scenes'][index]
    result['design_memory_hash']=actual
    save(Path(out)/'snapshot.json',result);save(Path(out)/'settle.json',{'expected':expected,'actual':actual,'design_rerun':rerun})
    output('characters',result['plan']['scenes'][index]['participants'])
    return result


def dispatch(task,source,out,state,index,profile,backend,request_file):
    from .dag import stage,output,context
    source=Path(source);out=Path(out);req=state['request']
    if task in {'refine_bundle','plan_bundle'}:return run_bundle(task,source,out,state,index,profile,backend,request_file)
    if task=='settle':return reconcile(source,out,state,index,profile,backend,request_file)
    if task=='anticipate_design':
        card=state['plan']['scenes'][index-1];prose=(source/'edited/prose.txt').read_text();memory=load(source/'memory/memory.json')
        speculative=copy.deepcopy(state);speculative['version']+=1
        speculative['accepted'].append({**card,'prose':prose,'quality_status':'speculative'})
        if load(source/'memory/memory-review.json')['pass']:append(speculative,memory['memories'],card['id'])
        temp=out/'speculative/inputs';save(temp/'state/snapshot.json',speculative)
        result=stage('scene_design',temp,out/'speculative/out',index,None,request_file,profile,backend)
        result['design_memory_hash']=memory_hash(speculative);save(out/'snapshot.json',result)
        output('characters',result['plan']['scenes'][index]['participants']);return result
    if task=='accept':
        # Conditional jobs produce no artifacts. Prefer repaired/refreshed outputs.
        for preferred,fallback,name,target in [('repair','edited','prose.txt','edited'),('final-memory','memory','memory.json','memory')]:
            path=choose(source,preferred,fallback,name)
            if path!=source/target/name:save(source/target/name,load(path) if name.endswith('.json') else path.read_text())
        for preferred,fallback,target in [('verified','initial-story','story-review'),('verified-rhetoric','initial-rhetoric','rhetoric-review')]:
            path=choose(source,preferred,fallback,'review.json');save(source/target/'review.json',load(path))
        path=source/'memory-review/review.json'
        if not path.exists():save(path,load(source/'memory/memory-review.json'))
        if req.get('execution_policy',{}).get('chapter_revision'):
            from .craft import validate_prose
            validate_prose((source/'edited/prose.txt').read_text(),req,check_length=backend!='fixture')
            validate_prose('\n\n'.join([s['prose'] for s in state['accepted']]+[(source/'edited/prose.txt').read_text()]),req)
        if index>0:contracts.require(state.get('design_memory_hash')==memory_hash(state),'Accepted scene used a stale memory design; settle must rerun design')
        return UNHANDLED
    if task=='edit' and req.get('execution_policy',{}).get('chapter_revision'):
        from .craft import REVISION,validate_prose
        executor=Executor(req,out,backend);card=state['plan']['scenes'][index]
        draft=(source/'draft/draft.txt').read_text()
        data={**context(req,state,card),**author_packet(req,state,card)}
        structural=executor.call('structural_editor',{**data,'prose':draft},REVISION+' First repair dramatic structure and chapter handoffs. Do not merely substitute adjectives.',tokens=4200)
        save(out/'structural-draft.txt',structural)
        revised=executor.call('humanizer',{**data,'prose':structural},REVISION+' Now perform the final line edit: specific perception, rhythm, coherent imagery, and no explanatory duplication.',tokens=4200)
        validate_prose(revised,req);save(out/'prose.txt',revised)
        save(out/'edit-report.json',{'passes':['chapter_structure','scene_line_edit'],'prior_scenes':len(state['accepted'])})
        return None
    if task not in {'writer','story_review','rhetoric_review','verify','verify_rhetoric','repair','memory','memory_final','memory_review'}:return UNHANDLED
    executor=Executor(req,out,backend)
    card=state['plan']['scenes'][index] if 'plan' in state else None
    if task=='writer':
        save(out/'draft.txt',writer(executor,req,{**context(req,state,card),**author_packet(req,state,card)},(source/'direction/direction.txt').read_text()));return None
    if task in {'story_review','rhetoric_review','verify','verify_rhetoric'}:
        prose=(source/'edited/prose.txt').read_text();kind='rhetoric' if task in {'rhetoric_review','verify_rhetoric'} else 'story'
        checks=RHETORIC_CHECKS if kind=='rhetoric' else STORY_CHECKS
        prior=load(source/('rhetoric' if kind=='rhetoric' else 'diagnosis')/'review.json') if task.startswith('verify') else None
        diff=load(source/'edited/repair.json')['diff'] if prior else None
        info={'scene':card,'world_rules':req['world_rules'],'pov':req.get('pov'),'accepted_facts':recording_context(state,card)}
        verdict=review(executor,req,prose,info,checks,'rhetoric_quality' if kind=='rhetoric' else 'story_quality',kind,prior,diff)
        if backend=='fixture' and task=='story_review' and req['execution_policy'].get('fixture_needs_repair'):
            p=passages(prose)[0];category=checks[0]
            verdict['checks'][0]['verdict']='fail';verdict['pass']=False
            verdict['issues']=[{'severity':'blocking','paragraph':0,'category':category,'evidence_ids':[p['id']],'quote':p['text'],'problem':'Fixture requests a paragraph repair.','fix':'Append a fixture repair marker.','replacement':p['text']}]
            verdict['needs_repair']=True
        save(out/'review.json',verdict);output('needs_repair',verdict['needs_repair']);return None
    if task=='repair':
        before=(source/'edited/prose.txt').read_text();after,info=repair(executor,req,before,[load(source/'diagnosis/review.json'),load(source/'rhetoric/review.json')])
        save(out/'prose.txt',after);save(out/'repair.json',info);save(out/'before.txt',before)
        for key in ['changed','facts_changed']:output(key,info[key])
        return None
    if task=='memory':
        prose=(source/'edited/prose.txt').read_text()
        result=memory_extract(executor,req,out,prose,{**payload(prose),'characters':[c['id'] for c in req['characters']],**recording_context(state,card)},MEMORY_INSTRUCTION)
        verdict=review_memory(executor,req,prose,result['memories'])
        save(out/'memory.json',result);save(out/'memory-review.json',verdict);save(out/'source.txt',prose);return None
    if task=='memory_final':
        after=(source/'edited/prose.txt').read_text();before=(source/'initial-memory/source.txt').read_text();base=load(source/'initial-memory/memory.json')
        verified=load(source/'initial-memory/memory-review.json')['pass']
        kept,diff=bind_memory(base,before,after) if verified else ([],changes(before,after))
        changed={p['id'] for p in diff['changed']} if verified else {p['id'] for p in passages(after)}
        evidence=[p for p in payload(after)['evidence_passages'] if p['id'] in changed]
        delta=memory_extract(executor,req,out,after,{'evidence_passages':evidence,'characters':[c['id'] for c in req['characters']],**recording_context(state,card)},MEMORY_INSTRUCTION+' Extract ONLY facts supported by these changed passages.') if evidence else {'memories':[]}
        allowed=[(p['start'],p['end']) for p in passages(after) if p['id'] in changed]
        # A provider cannot recycle an unchanged fact as a newly extracted update.
        valid=[]
        for item in delta['memories']:
            if item.get('evidence_spans') and all(any(start<=span['start'] and span['end']<=end for start,end in allowed) for span in item['evidence_spans']):valid.append(item)
            else:delta.setdefault('quarantined',[]).append({'error':'Delta cites evidence outside changed paragraphs','raw':item})
        delta['memories']=valid
        from .contracts import delta as validate_delta
        kept=validate_delta({'memories':kept},after,[c['id'] for c in req['characters']])['memories']
        result={'memories':kept+delta['memories'],'changed_memories':delta['memories'],'base_verified':verified,'quarantined':base.get('quarantined',[])+delta.get('quarantined',[]),'fallback':base.get('fallback') or delta.get('fallback')}
        save(out/'memory.json',result);output('facts_changed',bool(delta['memories']) or not verified)
        save(out/'memory-review.json',{'pass':verified and not delta['memories'],'issues':[]});return None
    if task=='memory_review':
        prose=(source/'edited/prose.txt').read_text();memory=load(source/'memory/memory.json')
        selected=memory.get('changed_memories',memory['memories']) if memory.get('base_verified') else memory['memories']
        verdict=review_memory(executor,req,prose,selected);save(out/'review.json',verdict);return None
    return UNHANDLED
