"""Regressions for the measured quota storm, lost handoff and blind micro-reviews."""
import copy,io,json,os,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from storyforge import batch_pipeline as b,memory_batches as m,section_reviews as sr
from storyforge.adaptive import writing_count,repetitions
from storyforge.continuation import append_verified_branch,history
from storyforge.canon import bridge
from storyforge.contracts import ContractError,delta,request
from storyforge.storage import save,load
from storyforge.dag import stage
from storyforge.living_prepare import prepare
from storyforge.editorial import STORY_CHECKS,RHETORIC_CHECKS
from storyforge.editorial_transport import factual_ids,editorial

class AdaptivePipelineTests(unittest.TestCase):
    def scene(self,p):
        stage('prepare',p/'none',p/'base',request_file='chaos-novel-practice',profile='fast',backend='fixture')
        state=prepare(p/'base/snapshot.json',p/'prepared',backend='fixture');return state,state['plan']['scenes'][0]
    def passing(self,keys):
        return {'pass':True,'checks':[{'id':key,'verdict':'pass','evidence_ids':['p001'],'reason':'The actual source supports this dimension under the author contract.'} for key in keys],'issues':[]}
    def test_short_scene_is_one_write_and_one_full_final_review(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.scene(p);self.assertEqual(writing_count(state['request']),1)
            text='\n\n'.join('Actual consequence '+str(i)+'.' for i in range(30));save(p/'edited/prose.txt',text)
            plan=sr.plan(state,p,p/'plan');self.assertEqual(len(plan['sections']),1);self.assertEqual(sr.final_ids(plan),['scene-0']);packets=[]
            def model(executor,role,packet,instruction,**kw):
                packets.append(packet);return kw['validator'](self.passing(packet['required_checks']))
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=model):v=sr.final_review(state,card,p,p/'final-batches/scene-0','worker','scene-0')
            self.assertTrue(v['review']['pass']);self.assertEqual(len(packets),1);self.assertEqual(len(packets[0]['evidence_passages']),30)
            self.assertEqual(set(packets[0]['required_checks']),set(STORY_CHECKS+RHETORIC_CHECKS))
    def test_fact_partitions_preserve_every_pair_with_larger_coherent_windows(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.scene(p)
            state['memories']=[{'id':'m'+str(i),'kind':'event','text':'Precise unchanged fact '+str(i),'known_by':['iona']} for i in range(80)]
            text='\n\n'.join('Exact source paragraph '+str(i)+'.' for i in range(16));save(p/'edited/prose.txt',text)
            facts=[{'kind':'event','text':'Supported change '+str(i),'known_by':['iona'],'evidence_ids':['p001']} for i in range(17)];save(p/'memory/memory.json',{'memories':facts})
            plan=m.plan(state,p,p/'plan','preflight')
            pairs={(i,j) for batch in plan['batches'] for i in batch['fact_indices'] for j in batch['prior_indices']}
            self.assertEqual(pairs,{(i,j) for i in range(17) for j in range(80)});self.assertLess(len(plan['batches']),20)
            covered={pid for batch in plan['batches'] for pid in batch['owned_passages']};self.assertEqual(len(covered),16)
            self.assertEqual(len(m.memory_canon(state)),80)
    def test_unchanged_passing_memory_proof_reuses_checks_without_model(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.scene(p);text='Iona pays the toll.';memory=delta({'memories':[{'kind':'event','text':text,'known_by':['iona'],'evidence_ids':['p001']}]},text,['iona'])
            save(p/'edited/prose.txt',text);save(p/'memory/memory.json',memory)
            proof={'pass':True,'issues':[],'state_sha256':b.bind_state(state),'source_sha256':b.digest(text),'memory_sha256':b.bind_state(memory)};save(p/'preflight-memory/review.json',proof)
            plan=m.plan(state,p,p/'plan','final');self.assertEqual([x['id'] for x in plan['batches']],['reuse'])
            with patch('storyforge.inference.Executor.call',side_effect=AssertionError('No repeated factual model call')):m.check(state,card,p,p/'batches/reuse','worker','reuse')
            self.assertTrue(m.join(state,p,p/'joined')['pass'])
            proof['memory_sha256']='stale';save(p/'preflight-memory/review.json',proof);self.assertIsNone(m.plan(state,p,p/'plan','final')['reused_preflight'])
    def test_branch_memory_keeps_source_facts_private_and_never_publishes_canon(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.scene(p);text='Iona recognizes her own signature.'
            memory=delta({'memories':[{'kind':'event','text':text,'known_by':['iona'],'evidence_ids':['p001'],'fact_key':'signature','supersedes':[]}]},text,['iona','val'])
            proof={'pass':True,'source_sha256':b.digest(text),'memory_sha256':b.bind_state(memory)};old=copy.deepcopy(state['memories'])
            state['version']=1;proof['state_sha256']=b.bind_state(state);append_verified_branch(state,memory,card['id'],text,proof)
            self.assertEqual(state['memories'],old);self.assertEqual(len(state['draft_memories']),1)
            self.assertTrue(any(x.get('fact_key')=='signature' for x in bridge(state,'iona')['facts']))
            self.assertFalse(any(x.get('fact_key')=='signature' for x in bridge(state,'val')['facts']))
            self.assertEqual(history(state)[-1]['continuity_scope'],'draft_branch')
            bad=copy.deepcopy(memory);bad['memories'][0]['text']='A different event.'
            with self.assertRaises(ContractError):append_verified_branch(state,bad,card['id'],text,proof)
            self.assertEqual(len(state['draft_memories']),1)
    def test_next_scene_stops_before_inference_when_memory_handoff_is_unverified(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.scene(p);state['accepted']=[{**card,'prose':'A provisional scene.','canon_committed':False}];save(p/'input/state/snapshot.json',state)
            with patch('storyforge.inference.Executor.call',side_effect=AssertionError('Do not spend tokens continuing without memory')):
                with self.assertRaisesRegex(ContractError,'no verified memory handoff'):stage('scene_design',p/'input',p/'out',index=1,backend='fixture')
    def test_memory_citations_use_owned_ids_instead_of_generated_quotes(self):
        text='Iona pays the toll.\n\nVal opens the gate.'
        v=factual_ids('FAIL\nISSUE blocking | prose | custody | p001,p002 | The custody claim contradicts the source. | Preserve the actual owner.',text,{'p001','p002'})
        self.assertEqual(v['issues'][0]['quote'],text);self.assertFalse(v['pass'])
        with self.assertRaises(ContractError):factual_ids('FAIL\nISSUE blocking | memory | custody | p999 | Wrong owner. | Correct it.',text,{'p001'})
    def test_global_repetition_candidates_link_distant_dialogue_without_auto_failing(self):
        repeated='You will find every crate from the lower wards accounted for.'
        text='"'+repeated+'"\n\nA long action intervenes.\n\n"'+repeated+'"'
        candidates=repetitions(text);self.assertEqual(candidates[0]['evidence_ids'],['p001','p003'])
        with self.assertRaises(ContractError):editorial({'checks':self.passing(['scene_change'])['checks'],'issues':[{'severity':'blocking','category':'ch01-sc01','evidence_ids':['p001'],'problem':'Wrong category.','fix':'Use an actual check.'}]},text,['scene_change'])
    def test_unchanged_passing_literary_reviews_are_reused_but_source_changes_are_not(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.scene(p);text='Iona pays the toll.';save(p/'edited/prose.txt',text);save(p/'original/prose.txt',text)
            save(p/'story-review/review.json',self.passing(STORY_CHECKS));save(p/'rhetoric-review/review.json',self.passing(RHETORIC_CHECKS));sr.plan(state,p,p/'plan')
            with patch('storyforge.inference.Executor.call',side_effect=AssertionError('Unchanged passing source needs no repeated model review')):v=sr.final_review(state,card,p,p/'out','worker','scene-0')
            self.assertTrue(v['reused_unchanged_passing_checks'])
            save(p/'edited/prose.txt',text+' Val closes the gate.');sr.plan(state,p,p/'plan')
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=lambda executor,role,data,instruction,**kw:kw['validator'](self.passing(data['required_checks']))) as calls:sr.final_review(state,card,p,p/'changed','worker','scene-0')
            self.assertEqual(calls.call_count,1)
    def test_provider_failure_does_not_trigger_a_second_empty_writer_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.scene(p);save(p/'direction/direction.txt','Write one consequential scene.');plan=b.plan_draft(state,card,p,p/'plan','fixture')
            with patch('storyforge.inference.Executor.call',side_effect=ContractError('Hosted writer unavailable')) as calls:b.write_batch(state,card,p,p/'batch','worker','0')
            self.assertEqual(calls.call_count,1);self.assertFalse(load(p/'batch/draft-batch.json')['verified_form'])
    def test_provider_budget_bounds_http_calls_and_never_loads_a_cpu_writer(self):
        from storyforge.inference import Executor
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'GEMINI_API_KEY':'test-primary','GEMINI_API_KEYS':'["test-b","test-c","test-d","test-e","test-f"]','GEMINI_DISTINCT_PROJECTS':'true'}):
            req=request(json.loads(Path('examples/chaos-novel-practice.json').read_text()))
            error=urllib.error.HTTPError('https://example.invalid',429,'quota',{},io.BytesIO(b'{}'))
            with patch('urllib.request.urlopen',side_effect=error) as http,patch('storyforge.local_worker.execute',side_effect=AssertionError('No silent CPU quality downgrade')) as cpu:
                with self.assertRaises(ContractError):Executor(req,Path(d),'worker').call('writer_beat',{'scene':'one'},'Write one scene.',tokens=100,output_format='text')
            self.assertEqual(http.call_count,2);cpu.assert_not_called()
    def test_final_unavailability_retains_the_actual_faults_and_batch_errors(self):
        from storyforge.adjudication import decide
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.scene(p);text='Iona pays the toll.'
            issue={'severity':'blocking','category':'continuity_clock','evidence_ids':['p001'],'problem':'Resource custody contradicts the current source.','fix':'Preserve the supported custodian.'}
            result=decide(state['request'],state,card,text,[],p/'out','fixture',batch_verdict={'pass':False,'unverified':True,'checks':[],'issues':[issue],'error':'Incomplete final batch','batch_count':1,'batch_errors':{'scene-0':'Missing required check'}})
            self.assertEqual(result['verdict']['issues'][0],issue);self.assertEqual(result['verdict']['batch_errors']['scene-0'],'Missing required check');self.assertFalse(result['story']['pass'])
    def test_native_review_clarification_preserves_existing_failure(self):
        from storyforge.inference import Executor
        from storyforge.editorial_transport import call_editorial
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.scene(p);text='Iona pays the toll.';executor=Executor(state['request'],p/'review','worker')
            calls=[]
            def model(executor,role,data,instruction,**kw):
                calls.append(role)
                if len(calls)==1:
                    save(executor.folder/'calls/story_quality-invalid.json',{'output':json.dumps({'checks':{'scene_change':{'verdict':'fail','evidence_ids':['p001'],'reason':'The source action has no demonstrated consequence.'}},'issues':[]})})
                    return {'pass':False,'checks':[],'issues':[],'unverified':True,'error':'A failed check needs an actionable matching issue'}
                changed=self.passing(['scene_change'])
                return kw['validator'](changed)
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=model):
                with self.assertRaisesRegex(ContractError,'changed an existing verdict'):call_editorial(executor,'story_quality',{'required_checks':['scene_change'],'evidence_passages':[{'id':'p001','text':text}]},'Assess the actual source.',text,['scene_change'])
            self.assertEqual(calls,['story_quality','director'])
    def test_native_review_clarifies_a_missing_issue_once_without_changing_verdict(self):
        from storyforge.inference import Executor
        from storyforge.editorial_transport import call_editorial
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.scene(p);text='Iona pays the toll.';calls=[]
            def model(executor,role,data,instruction,**kw):
                calls.append(role)
                check={'id':'scene_change','verdict':'fail','evidence_ids':['p001'],'reason':'The source action has no demonstrated consequence.'}
                if len(calls)==1:
                    save(executor.folder/'calls/story_quality-invalid.json',{'output':json.dumps({'checks':[check],'issues':[]})})
                    return {'pass':False,'unverified':True,'error':'A failed check needs an actionable matching issue'}
                return kw['validator']({'checks':[check],'issues':[{'severity':'blocking','category':'scene_change','evidence_ids':['p001'],'problem':'The payment has no demonstrated consequence.','fix':'Show the practical change caused by paying.'}]})
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=model):v=call_editorial(Executor(state['request'],p/'review','worker'),'story_quality',{'required_checks':['scene_change'],'evidence_passages':[{'id':'p001','text':text}]},'Assess the source.',text,['scene_change'])
            self.assertFalse(v['pass']);self.assertEqual(len(calls),2);self.assertEqual(v['checks'][0]['verdict'],'fail')
