"""Execute every generated optimized stage and artifact edge across a larger episode."""
import copy,fnmatch,io,json,os,shlex,shutil,sys,tempfile,unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import yaml
from storyforge import batch_pipeline as b,living_stages as ls,memory_batches as memory
from storyforge.dag import stage
from storyforge.living_prepare import prepare
from storyforge.storage import load,save

class LivingPipelineTests(unittest.TestCase):
    def test_two_scene_generated_graph_with_full_cast_rules_and_memory(self):
        self.run_generated_graph()
    def test_generated_graph_executes_bounded_recovery_and_audits_the_recovered_ledger(self):
        self.run_generated_graph(force_recovery=True)
    def run_generated_graph(self,force_recovery=False):
        graph=yaml.safe_load(Path('.github/workflows/living-universe-pipeline.yml').read_text());jobs=graph['jobs']
        for name,job in jobs.items():
            self.assertTrue(set(job.get('needs',[]))<=set(jobs),name)
            if name.startswith('s'):
                self.assertIn('always()',job['if'],name)
                self.assertIn('!cancelled()',job['if'],name)
                self.assertEqual(sum(step.get('run')=='python -m storyforge.artifact_fetch' for step in job['steps']),2 if name=='s01_write_batches' else 1,name)
                manifest=next(step for step in job['steps'] if step.get('name')=='Bind downloaded artifacts to explicit source aliases')['env']['STORY_ARTIFACT_MANIFEST']
                self.assertNotIn('${{',manifest,name)
        self.assertEqual(jobs['s02_design']['needs'],['s01_accept','quickstart'])
        self.assertEqual(jobs['s01_memory_preflight_batches']['strategy']['max-parallel'],6)
        self.assertGreater(len(jobs),60)
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'STORY_LEAN_LIVING':'true','STORY_LIVING_PIPELINE':'true','STORY_HOSTED_ONLY':'true'}),redirect_stdout(io.StringIO()):
            root=Path(d);artifacts={};skipped=set()
            stage('prepare',root/'none',root/'prepare',request_file='living-scale-practice',profile='fast',backend='fixture');artifacts['prepare']=root/'prepare'
            state=prepare(root/'prepare/snapshot.json',root/'quickstart',backend='fixture');artifacts['quickstart']=root/'quickstart'
            self.assertEqual([m['kind'] for m in state['memories']],[m['kind'] for m in state['request']['initial_facts']]);self.assertEqual(len(state['memories']),96);self.assertEqual(len(state['request']['characters']),12);self.assertEqual(len(state['request']['world_rules']),24)
            pending={k for k in jobs if k.startswith(('s01_','s02_'))};done={'prepare','quickstart'}
            def required(prefix,field):
                if field=='repair_required':
                    proof=load(artifacts[prefix]/'review.json');return not proof.get('pass') or proof.get('unverified',False)
                file='extract-plan.json' if field=='refresh_required' else 'memory-plan.json'
                plan=load(artifacts[prefix]/file)
                return any(x['ids'] for x in plan['batches']) if field=='refresh_required' else not bool(plan.get('reused_preflight'))
            while pending:
                ready=sorted(k for k in pending if set(jobs[k].get('needs',[]))<=done)
                self.assertTrue(ready,'No ready job '+str(pending))
                for key in ready:
                    job=jobs[key];index=int(key[1:3])-1;p=key[:3]
                    skip=(key.endswith('_memory_refresh_batches') and not required(p+'_repair','refresh_required')) or (key.endswith('_memory_final_batches') and not required(p+'_final_memory','checks_required'))
                    if ('_memory_recovery_' in key or key.endswith('_memory_recovered')) and not required(p+'_memory_review','repair_required'):skip=True
                    if skip:skipped.add(key);done.add(key);pending.remove(key);continue
                    matrix=job.get('strategy',{}).get('matrix',{});axis=None
                    if 'character' in matrix:
                        axis='character';values=load(artifacts[p+'_design']/'snapshot.json')['plan']['scenes'][index]['participants']
                    elif 'batch' in matrix:
                        axis='batch';value=matrix['batch']
                        if isinstance(value,list):values=value
                        else:
                            upstream=value.split('needs.',1)[1].split('.outputs.',1)[0]
                            file='draft-plan.json' if upstream.endswith('_direction') else 'extract-plan.json' if upstream.endswith(('_draft','_repair','_memory_recovery_plan')) else 'repair-plan.json' if upstream.endswith('_repair_plan') else 'memory-plan.json'
                            plan=load(artifacts[upstream]/file);values=[x['id'] for x in plan.get('batches',plan.get('beats',[]))]
                    else:values=[None]
                    for value in values:
                        folder=root/key/(str(value) if value is not None else 'single');source=folder/'inputs';out=folder/'out'
                        arrangement=next(step for step in job['steps'] if step.get('name')=='Bind downloaded artifacts to explicit source aliases')
                        manifest=json.loads(arrangement['env']['STORY_ARTIFACT_MANIFEST'])
                        for name,artifact in artifacts.items():
                            if any(fnmatch.fnmatch(name,item['name']) for item in manifest):shutil.copytree(artifact,folder/'incoming'/name)
                        upstream={}
                        if p+'_repair' in artifacts:upstream[p+'_repair']={'outputs':{'refresh_required':'true' if required(p+'_repair','refresh_required') else 'false'}}
                        if p+'_final_memory' in artifacts:upstream[p+'_final_memory']={'outputs':{'checks_required':'true' if required(p+'_final_memory','checks_required') else 'false'}}
                        if p+'_memory_review' in artifacts:upstream[p+'_memory_review']={'outputs':{'repair_required':'true' if required(p+'_memory_review','repair_required') else 'false'}}
                        ls.arrange(folder/'incoming',source,manifest,upstream)
                        command=next(s['run'] for s in job['steps'] if s.get('id')=='task')
                        line=next(line for line in command.splitlines() if line.startswith('python -m'))
                        parts=shlex.split(line.replace('$backend','fixture').replace('$STORY_BATCH',str(value)).replace('$STORY_CHARACTER',str(value)))
                        if parts[2]=='storyforge.living_stages':ls.execute(parts[3],source,out,index,'fixture')
                        elif parts[2]=='storyforge.dag':stage(parts[3],source,out,index=index,character=value if axis=='character' else None,profile='fast',backend='fixture')
                        else:
                            with patch.object(sys,'argv',['batch_pipeline']+parts[3:]+['--source',str(source),'--out',str(out)]):b.main()
                        if force_recovery and index==0 and parts[3]=='memory_final_join':
                            facts=load(out/'memory.json');facts['memories'][0]['known_by']=['public'];save(out/'memory.json',facts)
                            proof=load(out/'review.json');proof['pass']=False;proof['memory_sha256']=b.bind_state(facts)
                            quote=b.passages((source/'edited/prose.txt').read_text())[0]['text']
                            proof['issues']=[{'severity':'blocking','target':'memory','category':'knowledge','quote':quote,'evidence_ids':['p001'],'problem':'Injected public knowledge error in extracted memory.','fix':'Re-extract actual witnesses from owned evidence.'}]
                            save(out/'review.json',proof)
                        artifacts[key+('-'+str(value) if axis else '')]=out
                    done.add(key);pending.remove(key)
            state=load(artifacts['s02_accept']/'snapshot.json')
            self.assertTrue(state['complete']);self.assertTrue(all(s['canon_committed'] for s in state['accepted']))
            self.assertGreater(len(state['memories']),96)
            self.assertEqual(sum(m.get('source')=='user_input' for m in state['memories']),96)
            second=load(artifacts['s02_design']/'snapshot.json')
            self.assertGreater(len(second['memories']),96);self.assertEqual(len(second['accepted']),1)
            from storyforge.episode_audit import audit
            for name,folder in artifacts.items():
                if name.endswith(('_accept','_design','_final_memory','_memory_review','_memory_recovery_join')):shutil.copytree(folder,root/'results'/name)
            assessment=audit(root/'results',root/'audit',2)
            self.assertTrue(assessment['pass']);self.assertEqual(assessment['retained_initial_facts'],96)
            corrupt=root/'results'/('s01_accept' if force_recovery else 's02_accept')/'consumed-proof.json'
            bad=load(corrupt);bad['source_sha256']='stale';save(corrupt,bad)
            self.assertFalse(audit(root/'results',root/'bad-audit',2)['pass'])
            for prefix in ['s01','s02']:
                plan=load(artifacts[prefix+'_memory']/'memory-plan.json');facts=load(artifacts[prefix+'_memory']/'memory.json')['memories']
                before=load(artifacts[prefix+'_design']/'snapshot.json')
                pairs={(i,j) for batch in plan['batches'] for i in batch['fact_indices'] for j in batch['prior_indices']}
                self.assertEqual(pairs,{(i,j) for i in range(len(facts)) for j in range(len(memory.memory_canon(before)))})
                if force_recovery and prefix=='s01':
                    self.assertIn(prefix+'_memory_recovery_join',artifacts)
                    self.assertTrue(load(artifacts[prefix+'_memory_recovery_join']/'review.json')['pass'])
                    self.assertFalse(load(artifacts[prefix+'_memory_recovery_join']/'recovery.json')['further_recovery'])
                else:self.assertTrue(load(artifacts[prefix+'_memory_review']/'review.json')['reused_preflight'])
    def test_complete_ledger_is_retained_when_pov_projection_uses_ids(self):
        from storyforge.working_context import concise_packet
        facts=[{'id':str(i),'text':'Fact '+str(i),'known_by':['a']} for i in range(96)]
        packet={'prior_canon':{'facts':facts},'pov_known_facts':{'facts':facts[:8]}}
        result=concise_packet(packet,{})
        self.assertEqual(result['prior_canon']['facts'],facts)
        self.assertEqual([r['fact_id'] for r in result['pov_known_facts']['facts']],[str(i) for i in range(8)])
        self.assertEqual(packet['pov_known_facts']['facts'],facts[:8])
    def test_changed_evidence_macro_requires_fresh_final_memory_checks(self):
        from storyforge.contracts import delta
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'STORY_LEAN_LIVING':'true','STORY_LIVING_PIPELINE':'true'}),redirect_stdout(io.StringIO()):
            root=Path(d);stage('prepare',root/'none',root/'base',request_file='living-scale-practice',backend='fixture');state=prepare(root/'base/snapshot.json',root/'quick',backend='fixture')
            before='Thestor put one bronze seal on the board.';after='Thestor put one spent bronze seal on the board.'
            facts=delta({'memories':[{'kind':'event','text':before,'known_by':['thestor'],'evidence_ids':['p001']}]},before,['thestor'])
            src=root/'merge';save(src/'state/snapshot.json',state);save(src/'edited/prose.txt',before);save(src/'initial-memory/memory.json',facts)
            proof={'pass':True,'issues':[],'source_sha256':b.digest(before),'state_sha256':b.bind_state(state),'memory_sha256':b.bind_state(facts)}
            save(src/'preflight-memory/review.json',proof)
            save(src/'plan/repair-plan.json',{'state_sha256':b.bind_state(state),'source_sha256':b.digest(before),'batches':[{'id':'0','source_sha256':b.digest(before),'owned':['p001'],'passages':[{'id':'p001','text':before}]}]})
            save(src/'batches/0/repair-batch.json',{'id':'0','source_sha256':b.digest(before),'replacements':{'p001':after},'unverified':False})
            ls.execute('repair_refresh_plan',src,root/'repaired',0,'fixture')
            plan=load(root/'repaired/extract-plan.json');self.assertTrue(any(x['ids'] for x in plan['batches']))
            dest=root/'final-input';save(dest/'state/snapshot.json',state);save(dest/'edited/prose.txt',after);save(dest/'plan/extract-plan.json',plan);save(dest/'preflight-memory/review.json',proof)
            for item in plan['batches']:memory.extract_batch(state,state['plan']['scenes'][0],dest,dest/'batches'/item['id'],'fixture',item['id'])
            ls.execute('final_memory_plan',dest,root/'final-memory',0,'fixture')
            final=load(root/'final-memory/memory-plan.json');self.assertFalse(final['reused_preflight'])
            self.assertFalse((root/'final-memory/review.json').exists())
    def test_native_schema_transport_keeps_full_ledger_without_echoing_grammar(self):
        from storyforge.inference import Executor
        from storyforge.editorial import STORY_CHECKS,RHETORIC_CHECKS
        from storyforge.canon import cards
        from storyforge.evidence import payload
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            root=Path(d);stage('prepare',root/'none',root/'base',request_file='living-scale-practice',backend='fixture');state=prepare(root/'base/snapshot.json',root/'quick',backend='fixture')
            data={**payload('Thestor waited at the closed gate.'),'prior_canon':cards(state['memories']),'required_checks':STORY_CHECKS+RHETORIC_CHECKS}
            Executor(state['request'],root/'check','fixture').call('chapter_quality',data,'Check every required source dimension.',tokens=3200,validator=lambda x:x)
            packet=load(next((root/'check/packets').glob('*.json')))
            self.assertNotIn('Required output JSON Schema:',packet['system'])
            self.assertIsNotNone(packet['response_schema'])
            self.assertEqual(len(packet['input']['prior_canon']),96)
            self.assertEqual(packet['input']['required_checks'],STORY_CHECKS+RHETORIC_CHECKS)
    def test_extended_context_requires_all_roles_to_be_hosted(self):
        from storyforge.contracts import request,ContractError
        req=load('examples/living-scale-practice.json');self.assertEqual(request(copy.deepcopy(req))['context_chars'],64000)
        req['execution_policy']['hosted_required_roles']=[]
        with self.assertRaisesRegex(ContractError,'hosted-only'):request(req)
    def test_empty_writer_is_a_failed_job_and_preserves_diagnostic_artifact(self):
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            root=Path(d);stage('prepare',root/'none',root/'base',request_file='living-scale-practice',backend='fixture');state=prepare(root/'base/snapshot.json',root/'quick',backend='fixture')
            save(root/'source/state/snapshot.json',state)
            def no_text(state,card,source,out,backend,bid):
                value={'prose':'','errors':['Provider unavailable']};save(Path(out)/'draft-batch.json',value);return value
            with patch.object(b,'write_batch',side_effect=no_text),patch.object(sys,'argv',['batch_pipeline','write_batch','--source',str(root/'source'),'--out',str(root/'out'),'--backend','worker','--batch','0']):
                with self.assertRaises(SystemExit):b.main()
            self.assertTrue((root/'out/draft-batch.json').exists());self.assertEqual(load(root/'out/status.json')['status'],'failure')

    def test_pipeline_character_context_preserves_knowledge_without_inference(self):
        from storyforge.dag import actor_packet
        from storyforge.canon import bridge
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'STORY_LEAN_LIVING':'true','STORY_LIVING_PIPELINE':'true'}),redirect_stdout(io.StringIO()):
            root=Path(d)
            stage('prepare',root/'none',root/'base',request_file='living-scale-practice',backend='fixture')
            state=prepare(root/'base/snapshot.json',root/'quick',backend='fixture')
            card=state['plan']['scenes'][0];cid=card['participants'][0]
            expected=actor_packet(state['request'],state,card,cid)
            save(root/'inputs/state/snapshot.json',state)
            with patch('storyforge.dag.Executor.call',side_effect=AssertionError('Optional actor inference was called')):
                stage('character',root/'inputs',root/'actor',character=cid,backend='fixture')
            proposal=load(root/'actor/proposal.json')
            self.assertEqual(proposal['state_version'],state['version'])
            self.assertEqual(proposal['character_profile'],expected['character'])
            self.assertEqual(proposal['method'],'source_bound_character_context_no_inference')
            author={m['id']:m for m in bridge(state)['facts']}
            resolved=[author[m['fact_id']] if 'fact_id' in m else m for m in proposal['known_facts']]
            self.assertEqual(resolved,expected['known_facts'])
            self.assertLess(len(resolved),len(state['memories']))
            save(root/'direction-input/state/snapshot.json',state)
            for actor in card['participants']:
                stale={**proposal,'character':actor,'state_version':state['version']-1}
                save(root/'direction-input/characters'/actor/'proposal.json',stale)
            with self.assertRaisesRegex(Exception,'Stale character proposal'):
                stage('director',root/'direction-input',root/'direction',backend='fixture')

    def test_capacity_fallback_uses_third_model_with_unchanged_http_cap(self):
        import urllib.error
        from storyforge.contracts import request
        from storyforge.inference import Executor
        from storyforge.worker_policy import validate
        req=request(load(Path('examples/living-scale-practice.json')))
        req['profile']='fast';req['max_stage_retries']=0
        validate(req)
        calls=[]
        result={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'A candidate scene awaiting the normal quality gates.'}]}}]}
        def serve(http_request,timeout):
            calls.append((http_request.full_url,timeout))
            if len(calls)==1:
                raise urllib.error.HTTPError('https://example.invalid',503,'Unavailable',{},io.BytesIO(b'{"error":{"status":"UNAVAILABLE"}}'))
            if len(calls)==2:raise TimeoutError('capacity timeout')
            return io.BytesIO(json.dumps(result).encode())
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'GEMINI_API_KEY':'placeholder','GEMINI_API_KEYS':'["placeholder-backup"]','GEMINI_DISTINCT_PROJECTS':'true'}),patch('urllib.request.urlopen',side_effect=serve),patch('storyforge.local_worker.execute',side_effect=AssertionError('No CPU quality downgrade')):
            text=Executor(req,d,'worker').call('writer_beat',{},'Write the candidate scene.',output_format='text',tokens=200)
            self.assertIn('candidate scene',text)
            self.assertEqual(len(calls),3)
            self.assertIn('gemini-3.6-flash:generateContent',calls[0][0])
            self.assertIn('gemini-3.8-flash:generateContent',calls[1][0])
            self.assertIn('gemini-3.5-flash-lite:generateContent',calls[2][0])
            self.assertGreater(calls[0][1],40)
            self.assertLessEqual(calls[0][1],90)
            self.assertLessEqual(max(t for _,t in calls),90)

    def test_capacity_fallback_never_accepts_truncated_or_unavailable_generation(self):
        from storyforge.contracts import request,ContractError
        from storyforge.inference import Executor
        req=request(load(Path('examples/living-scale-practice.json')))
        req['profile']='fast';req['max_stage_retries']=0
        calls=[]
        def serve(http_request,timeout):
            calls.append(1)
            return io.BytesIO(json.dumps({'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'Incomplete prose'}]}}]}).encode())
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'GEMINI_API_KEY':'placeholder','GEMINI_API_KEYS':'[]','GEMINI_DISTINCT_PROJECTS':'true'}),patch('urllib.request.urlopen',side_effect=serve),patch('storyforge.local_worker.execute',side_effect=AssertionError('No CPU fallback')):
            with self.assertRaises(ContractError):Executor(req,d,'worker').call('writer_beat',{},'Write.',output_format='text',tokens=200)
            self.assertEqual(len(calls),3)

    def test_strict_short_draft_expands_once_before_handoff(self):
        from storyforge.craft import validate_prose
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'STORY_LEAN_LIVING':'true','STORY_LIVING_PIPELINE':'true'}),redirect_stdout(io.StringIO()):
            root=Path(d);stage('prepare',root/'none',root/'base',request_file='living-scale-practice',backend='fixture')
            state=prepare(root/'base/snapshot.json',root/'quick',backend='fixture');card=state['plan']['scenes'][0]
            save(root/'source/direction/direction.txt','Use the authored scene and its exact knowledge restrictions.')
            b.plan_draft(state,card,root/'source',root/'source/plan','fixture')
            short=' '.join('action'+str(i) for i in range(551));expanded=' '.join('action'+str(i) for i in range(900))
            with patch('storyforge.hosted.GoogleHosted.complete',side_effect=[(short,{'finish_reason':'stop','model':'test'}),(expanded,{'finish_reason':'stop','model':'test'})]) as provider:
                result=b.write_batch(state,card,root/'source',root/'batch','worker','0')
            self.assertEqual(provider.call_count,2)
            self.assertEqual([c.kwargs['role'] for c in provider.call_args_list],['writer_beat','repair'])
            self.assertTrue(result['verified_form']);self.assertEqual(result['errors'],[])
            self.assertEqual(len(result['prose'].split()),900)
            validate_prose(result['prose'],state['request'],check_length=True)
            repair_packet=load(next((root/'batch/1/packets').glob('*.json')))
            self.assertIn('551 words',repair_packet['input']['specific_errors'][0])
            self.assertEqual(repair_packet['input']['rejected_batch'],short)

    def test_strict_merge_rejects_short_or_unverified_drafts(self):
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            root=Path(d);stage('prepare',root/'none',root/'base',request_file='living-scale-practice',backend='fixture')
            state=prepare(root/'base/snapshot.json',root/'quick',backend='fixture');state['backend']='worker';card=state['plan']['scenes'][0]
            save(root/'source/direction/direction.txt','Keep source canon.')
            plan=b.plan_draft(state,card,root/'source',root/'source/plan','fixture')
            value={'id':'0','state_sha256':plan['state_sha256'],'plan_sha256':plan['plan_sha256'],'prose':' '.join(['word']*551),'verified_form':True,'errors':[]}
            save(root/'source/batches/0/draft-batch.json',value)
            with self.assertRaisesRegex(ValueError,'551 words'):b.merge_draft(state,root/'source',root/'bad')
            value.update(prose=' '.join(['word']*900),verified_form=False,errors=['Rejected by form validator'])
            save(root/'source/batches/0/draft-batch.json',value)
            with self.assertRaisesRegex(ValueError,'Unverified writing batch'):b.merge_draft(state,root/'source',root/'bad')
            self.assertFalse((root/'bad/draft.txt').exists())

    def test_direction_sharing_preserves_full_memory_profiles_and_private_beliefs(self):
        from storyforge.working_context import concise_packet
        from storyforge.canon import bridge
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            root=Path(d);stage('prepare',root/'none',root/'base',request_file='living-scale-practice',backend='fixture')
            state=prepare(root/'base/snapshot.json',root/'quick',backend='fixture');req=state['request'];card=state['plan']['scenes'][0]
            data=b.scene_context(state,card)
            prior=bridge(state);facts=prior['facts'];belief={'id':'old-private','text':'An outdated private belief','known_by':['lyra']}
            profiles=req['characters'][:4]
            actors=[{'character':c['id'],'method':'source_bound_character_context_no_inference','character_profile':c,'knowledge_policy':'Only listed facts are known.','known_facts':[{'fact_id':m['id'],'source':'prior_canon.facts'} for m in facts[:12]]+[belief]} for c in profiles]
            data['direction']=json.dumps({'scene':card,'observable_proposals':actors})
            before=copy.deepcopy(data);compact=concise_packet(data,req)
            self.assertEqual(data,before);self.assertEqual(compact['prior_canon'],prior)
            self.assertEqual(len(compact['prior_canon']['facts']),96)
            self.assertEqual(compact['direction']['scene'],{'source':'scene'})
            self.assertNotIn('world_rules',compact)
            self.assertEqual(compact['author_contract']['world_rules'],req['world_rules'])
            for original,projected in zip(actors,compact['direction']['observable_proposals']):
                self.assertEqual(projected['character_profile'],original['character_profile'])
                self.assertEqual(projected['known_facts'],[m['id'] for m in facts[:12]]+[belief])
            self.assertLess(len(json.dumps(compact)),len(json.dumps(before)))
