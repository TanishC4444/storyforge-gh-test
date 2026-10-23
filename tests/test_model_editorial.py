import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge import batch_pipeline as b,memory_batches as m,section_reviews as sr
from storyforge.editorial_transport import editorial,patches,factual
from storyforge.editorial import STORY_CHECKS
from storyforge.contracts import ContractError
from storyforge.dag import stage
from storyforge.expansion import prepare
from storyforge.storage import save,load

class ModelEditorialTests(unittest.TestCase):
    def scene(self,p):
        stage('prepare',p/'none',p/'base',request_file='classic-universe-practice',profile='fast',backend='fixture')
        s=prepare(p/'base/snapshot.json',p/'prepared');s['request']['performance']['adaptive_batches']=False;return s,s['plan']['scenes'][0]
    def test_readable_reviews_preserve_blocking_findings_despite_bad_pass_header(self):
        text='The smith refuses.'
        v=editorial('CHECK scene_change | fail | p001 | The character makes no consequential choice.\nISSUE blocking | scene_change | p001 | No changed state | Show the cost of refusal.',text,['scene_change'])
        self.assertFalse(v['pass']);self.assertEqual(v['issues'][0]['quote'],text)
        v['pass']=True;self.assertFalse(editorial(v,text,['scene_change'])['pass'])
        with self.assertRaises(ContractError):editorial('CHECK scene_change | pass | p999 | The character changes an actual material state.',text,['scene_change'])
    def test_plain_edit_blocks_allow_merging_and_deletion_with_ownership(self):
        batch={'owned':['p001','p002'],'allow_deletions':True}
        v=patches('REPLACE p001\nThe complete action happens once.\nEND_REPLACE\nDELETE p002',batch)
        self.assertEqual(v['replacements'],{'p001':'The complete action happens once.','p002':''})
        with self.assertRaises(ContractError):patches('DELETE p003',batch)
        self.assertEqual(patches('NO_CHANGES',batch),{'replacements':{}})
    def test_fact_text_contract_never_erases_blocking_issue(self):
        value=factual('PASS\nISSUE blocking | memory | knowledge | The smith refuses. | The claim adds a witness. | Remove unsupported witness.','The smith refuses.')
        self.assertFalse(value['pass'])
    def test_memory_pairs_cover_every_current_canon_fact_and_new_fact(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p)
            s['memories']=[{'id':'m'+str(i),'kind':'event','text':'Canon fact '+str(i),'known_by':['public']} for i in range(19)]
            facts=[{'kind':'event','text':'New supported fact '+str(i),'known_by':[],'evidence_ids':['p001']} for i in range(5)]
            save(p/'edited/prose.txt','The smith refuses.');save(p/'memory/memory.json',{'memories':facts})
            plan=m.plan(s,p,p/'plan','final');pairs={(new,old) for batch in plan['batches'] for new in batch['fact_indices'] for old in batch['prior_indices']}
            self.assertEqual(pairs,{(n,o) for n in range(5) for o in range(19)})
            self.assertTrue(all(len(x['fact_indices'])<=2 and len(x['prior_indices'])<=8 for x in plan['batches']))
            received=[]
            def checker(executor,role,packet,instruction,**kw):
                received.append(packet);self.assertNotIn('literary_application',packet)
                return kw['validator']({'pass':True,'issues':[]})
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=checker):
                m.check(s,c,p,p/'batch','worker','0')
            self.assertEqual(len(received[0]['prior_canon']),8);self.assertEqual(len(s['memories']),19)
    def test_failed_review_group_keeps_valid_findings_for_editors(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);text='The smith refuses.';save(p/'edited/prose.txt',text)
            v={'kind':'story','group':0,'state_sha256':b.bind_state(s),'source_sha256':b.digest(text),'review':{'pass':False,'checks':[],'issues':[{'category':'scene_change','evidence_ids':['p001'],'problem':'No consequence','fix':'Show a consequence'}]}}
            save(p/'batches/0/review-batch.json',v)
            v=b.join_reviews(s,p,p/'joined','story');self.assertTrue(v['unverified']);self.assertEqual(len(v['issues']),1)
    def test_related_duplicate_passages_share_editor_and_bad_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);text='An action happens.\n\nUnrelated detail.\n\nAn action happens.'
            save(p/'findings/edited/prose.txt',text)
            save(p/'findings/story-review/review.json',{'pass':True,'issues':[]})
            save(p/'findings/rhetoric-review/review.json',{'pass':False,'issues':[{'category':'rhythm_repetition','evidence_ids':['p001','p003'],'problem':'Action repeated','fix':'Keep it once and remove the duplicate.'}]})
            plan=b.plan_repairs(s,p/'findings',p/'plan');self.assertEqual(plan['batches'][0]['owned'],['p001','p003']);self.assertTrue(plan['batches'][0]['allow_deletions'])
            save(p/'input/plan/repair-plan.json',plan)
            def model(executor,role,packet,instruction,**kw):
                if 'candidate_patch' in packet:return kw['validator']('FAIL | Repetition is still present and expanded.')
                return kw['validator']('REPLACE p001\nAn action happens. An action happens.\nEND_REPLACE')
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=model):b.repair_batch(s,c,p/'input',p/'merge/batches/0','worker','0')
            save(p/'merge/plan/repair-plan.json',plan);save(p/'merge/edited/prose.txt',text)
            self.assertEqual(b.merge_repairs(s,p/'merge',p/'out'),text)
            self.assertEqual(load(p/'out/repair.json')['unverified_batches'],['0'])
    def test_summary_sources_are_bound_and_prose_review_reads_original(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);text='First action.\n\nSecond action.\n\nA consequence.'
            save(p/'edited/prose.txt',text);plan=sr.plan(s,p,p/'plan')
            for sec in plan['sections']:sr.summarize(s,c,p,p/'batches'/sec['id'],'fixture',sec['id'])
            summaries=sr.join_summaries(s,p,p/'summaries');self.assertEqual(len(summaries['sections']),2)
            received=[]
            def reviewer(executor,role,packet,instruction,**kw):
                received.append(packet)
                return kw['validator']({'pass':True,'checks':[{'id':k,'verdict':'pass','reason':'This actual source passage fulfills the requested dimension.','evidence_ids':['p001']} for k in packet['required_checks']],'issues':[]})
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=reviewer):sr.review_section(s,c,p,p/'review','worker','0-0')
            self.assertEqual(received[0]['evidence_passages'][0]['text'],'First action.')
            save(p/'edited/prose.txt',text+' Changed.')
            with self.assertRaises(ContractError):sr.join_summaries(s,p,p/'stale')
    def test_source_extraction_recovery_corrects_only_failed_batch(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);text='The smith refuses.\n\nThe tide rises.';save(p/'edited/prose.txt',text)
            plan=m.extract_plan(s,p,p/'plan');calls=[]
            def extract(executor,req,out,prose,packet,instruction):
                calls.append(packet)
                if len(calls)==1:
                    save(Path(out)/'calls/memory-invalid.json',{'output':'Rejected update'})
                    raise ContractError('Memory update changed fact identity')
                self.assertEqual(packet['specific_validation_error'],'Memory update changed fact identity')
                return {'memories':[]}
            with patch('storyforge.resilience.memory_extract',side_effect=extract):m.extract_batch(s,c,p,p/'batches/0','worker','0')
            self.assertEqual(len(calls),2);self.assertFalse(m.extract_join(s,p,p/'joined').get('unverified',False))

    def test_refresh_retains_unchanged_facts_and_repairs_only_flagged_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);text='The smith refuses.\n\nThe tide rises.'
            facts=[{'kind':'event','text':'The smith refuses.','known_by':[],'evidence_ids':['p001']},{'kind':'event','text':'The tide rises.','known_by':[],'evidence_ids':['p002']}]
            save(p/'original/prose.txt',text);save(p/'edited/prose.txt',text);save(p/'initial-memory/memory.json',{'memories':facts})
            save(p/'preflight-memory/review.json',{'source_sha256':b.digest(text),'issues':[{'target':'memory','quote':'The tide rises.','problem':'Incomplete extracted consequence','fix':'Extract this event accurately.'}]})
            plan=m.refresh_plan(s,p,p/'plan');self.assertEqual(plan['batches'][0]['ids'],['p002']);self.assertEqual(len(plan['retained']),1)
            m.extract_batch(s,c,p,p/'batches/0','fixture','0');result=m.extract_join(s,p,p/'out')
            self.assertEqual(len(result['memories']),2);self.assertFalse(result.get('unverified',False))
    def test_failed_initial_extraction_schedules_complete_recovery_and_cannot_auto_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);text='First event.\n\nSecond event.\n\nThird event.'
            save(p/'original/prose.txt',text);save(p/'edited/prose.txt',text);save(p/'initial-memory/memory.json',{'memories':[],'unverified':True})
            plan=m.refresh_plan(s,p,p/'plan');self.assertTrue(plan['full_reextraction'])
            self.assertEqual([pid for x in plan['batches'] for pid in x['ids']],['p001','p002','p003'])
            self.assertTrue(m.extract_join(s,p,p/'missing')['unverified'])
    def test_role_budget_is_shared_and_restores_existing_deadline(self):
        import os
        from storyforge.runtime import scoped_call_budget,worker_timeout_seconds
        class Call:
            backend='worker';req={'execution_policy':{'total_call_seconds':{'memory':300}}}
            @scoped_call_budget
            def run(self,role):return float(os.environ['STORY_JOB_DEADLINE'])
        with patch.dict(os.environ,{'STORY_JOB_DEADLINE':'1000'}),patch('storyforge.runtime.time.time',return_value=100):
            self.assertEqual(Call().run('memory'),400);self.assertEqual(os.environ['STORY_JOB_DEADLINE'],'1000')
    def test_readable_review_uses_qwen7b_without_json_grammar(self):
        from storyforge.inference import Executor
        from storyforge.editorial_transport import call_editorial
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);req=copy.deepcopy(s['request']);req['api_roles']={};req['execution_policy']['hosted_required_roles']=[]
            seen=[]
            def local(model,system,prompt,tokens,n_ctx,role,response_schema=None):
                seen.append((model,system,response_schema))
                return 'CHECK scene_change | pass | p001 | The refusal creates a concrete change in the household situation.',{'finish_reason':'stop','usage':{}}
            with patch('storyforge.local_worker.execute',side_effect=local):
                v=call_editorial(Executor(req,p/'review','worker'),'story_quality',{'evidence_passages':[{'id':'p001','text':'The smith refuses.'}],'required_checks':['scene_change']},'Judge actual source.','The smith refuses.',['scene_change'],500)
            self.assertTrue(v['pass']);self.assertEqual(seen[0][0],'qwen7b');self.assertIsNone(seen[0][2]);self.assertNotIn('Required output JSON Schema:',seen[0][1])
