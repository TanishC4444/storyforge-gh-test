import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge import batch_pipeline as b,memory_batches as m,living_stages as ls
from storyforge.adaptive import writing_count
from storyforge.contracts import ContractError
from storyforge.dag import stage
from storyforge.expansion import prepare
from storyforge.storage import save,load

class FinalMemoryRecoveryTests(unittest.TestCase):
    def scene(self,p):
        stage('prepare',p/'none',p/'base',request_file='classic-universe-practice',profile='fast',backend='fixture')
        s=prepare(p/'base/snapshot.json',p/'prepared');s['request']['performance']['strict_draft_handoff']=True
        return s,s['plan']['scenes'][0]
    def test_moderate_scene_is_one_coherent_generation(self):
        self.assertEqual(writing_count({'words_per_scene':1100,'performance':{'adaptive_batches':True}}),1)
        self.assertEqual(writing_count({'words_per_scene':3000,'performance':{'adaptive_batches':True}}),2)
    def test_compact_source_alias_cannot_create_a_spurious_ledger_change(self):
        from storyforge.contracts import delta
        from storyforge.experimental import bind_memory
        prose='Mara keeps one token.'
        raw={'memories':[{'kind':'resource','text':prose,'known_by':['c01'],'evidence_ids':['p001'],'evidence_source_ref':'h1'}]}
        facts=delta(raw,prose,['c01']);retained,_=bind_memory(facts,prose,prose)
        refreshed=delta({'memories':retained},prose,['c01'])
        self.assertEqual(facts,refreshed);self.assertNotIn('evidence_source_ref',facts['memories'][0]);self.assertEqual(facts['memories'][0]['evidence_prose_sha256'],b.digest(prose))
    def test_memory_checker_can_resolve_reference_outside_its_history_partition(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);actor=s['request']['characters'][0]['id']
            s['request']['performance'].update(adaptive_batches=True,memory_pair_batches=True,pipelined_living=True)
            s['memories']=[{'id':'m%05d'%i,'kind':'resource','fact_key':'pool:'+str(i),'text':'Pool '+str(i)+' holds two tokens.','known_by':[actor]} for i in range(41)]
            prose='Mara keeps one token.';facts={'memories':[{'kind':'resource','fact_key':'pool:40','text':prose,'known_by':[actor],'supersedes':['m00040'],'evidence_ids':['p001']}]}
            save(p/'edited/prose.txt',prose);save(p/'memory/memory.json',facts);m.plan(s,p,p/'plan','final');received=[]
            def check(executor,role,packet,instruction,**kw):
                received.append(packet);return kw['validator']({'pass':True,'issues':[]})
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=check):m.check(s,c,p,p/'checked','worker','0')
            packet=received[0]
            self.assertNotIn('m00040',{f['id'] for f in packet['prior_canon']})
            self.assertIn('m00040',{f['id'] for f in packet['canon_identity_index']})
            self.assertEqual(packet['linked_prior_facts'][0]['fact_key'],'pool:40')
            self.assertEqual(packet['application_reference_checks'],[{'fact_index':0,'prior_id':'m00040','exists':True,'same_key_and_kind':True}])
    def test_linked_structural_finding_allocates_one_editor_not_each_paragraph(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);prose='\n\n'.join('Action '+str(i)+'.' for i in range(25))
            save(p/'edited/prose.txt',prose)
            issue={'category':'scene_change','evidence_ids':['p%03d'%i for i in range(1,26)],'problem':'No enacted tactic.','fix':'Replace redundant negotiation with one concrete attempt.'}
            save(p/'story-review/review.json',{'pass':False,'issues':[issue]});save(p/'rhetoric-review/review.json',{'pass':True,'issues':[]})
            plan=b.plan_repairs(s,p,p/'plan');self.assertEqual(len(plan['batches']),1);self.assertEqual(len(plan['batches'][0]['owned']),25)
    def test_multi_paragraph_memory_correction_refreshes_all_evidence_and_retains_other_facts(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);prose='Mara waits.\n\nIvo listens.\n\nSera arrives.\n\nTomas leaves.'
            facts=[{'kind':'event','text':'Mara and Sera meet.','known_by':['c01'],'evidence_ids':['p001','p003']},{'kind':'event','text':'Ivo listens.','known_by':['c02'],'evidence_ids':['p002']},{'kind':'event','text':'Tomas leaves.','known_by':['c04'],'evidence_ids':['p004']}]
            for path in ['edited/prose.txt','original/prose.txt']:save(p/path,prose)
            save(p/'initial-memory/memory.json',{'memories':facts})
            save(p/'preflight-memory/review.json',{'source_sha256':b.digest(prose),'issues':[{'target':'memory','evidence_ids':['p001'],'quote':'Mara waits.','problem':'Wrong knowledge.','fix':'Use witnesses.'}]})
            plan=m.refresh_plan(s,p,p/'out');self.assertEqual({pid for batch in plan['batches'] for pid in batch['ids']},{'p001','p003'});self.assertEqual(len(plan['retained']),2)
            self.assertEqual(m.affected_passages([{'quote':'Mara waits.\n\nIvo listens.'}],prose),{'p001','p002'})
    def test_final_memory_repair_is_targeted_source_bound_and_rechecked_without_changing_prose(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);actor,observer=[x['id'] for x in s['request']['characters'][:2]];prose='Mara keeps one token privately.\n\nIvo waits at the gate.'
            bad={'kind':'resource','text':'Mara keeps one token privately.','known_by':['public'],'evidence_ids':['p001']}
            other={'kind':'event','text':'Ivo waits at the gate.','known_by':[observer],'evidence_ids':['p002']}
            facts={'memories':[bad,other]};issue={'target':'memory','severity':'blocking','category':'knowledge','quote':prose.split('\n\n')[0],'evidence_ids':['p001'],'problem':'Private knowledge is public.','fix':'Restrict known_by to c01.'}
            proof={'pass':False,'issues':[issue],'source_sha256':b.digest(prose),'state_sha256':b.bind_state(s),'memory_sha256':b.bind_state(facts)}
            src=p/'input'
            for path,value in [('state/snapshot.json',s),('edited/prose.txt',prose),('memory/memory.json',facts),('memory-review/review.json',proof)]:save(src/path,value)
            ls.execute('memory_recovery_plan',src,p/'plan',0,'fixture')
            plan=load(p/'plan/extract-plan.json');self.assertEqual(plan['retained'][0]['text'],other['text']);self.assertEqual([pid for batch in plan['batches'] for pid in batch['ids']],['p001'])
            import shutil
            shutil.copytree(p/'plan',src/'plan');fixed={**bad,'known_by':[actor]}
            with patch('storyforge.resilience.memory_extract',return_value={'memories':[fixed]}):
                for batch in plan['batches']:m.extract_batch(s,c,src,src/'batches'/batch['id'],'worker',batch['id'])
            ls.execute('memory_recovered_plan',src,p/'recovered',0,'fixture')
            memory=load(p/'recovered/memory.json');self.assertEqual(len(memory['memories']),2)
            self.assertEqual((src/'edited/prose.txt').read_text(),prose)
            save(src/'memory/memory.json',memory);save(src/'plan/memory-plan.json',load(p/'recovered/memory-plan.json'))
            def passing(executor,role,packet,instruction,**kw):
                self.assertEqual(packet['previous_findings_to_verify'][0]['problem'],issue['problem'])
                return kw['validator']({'pass':True,'issues':[]})
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=passing):
                for batch in load(src/'plan/memory-plan.json')['batches']:m.check(s,c,src,src/'batches'/('check-'+batch['id']),'worker',batch['id'])
            ls.execute('memory_recovery_join',src,p/'joined',0,'fixture');result=load(p/'joined/review.json')
            self.assertTrue(result['pass']);self.assertEqual(result['memory_sha256'],b.bind_state(memory));self.assertFalse(load(p/'joined/recovery.json')['further_recovery'])
            # A failed independent recheck must still block acceptance, even with
            # a structurally valid corrected ledger and unchanged prose.
            result['pass']=False;result['issues']=[issue]
            save(src/'recovered-memory/memory.json',memory);save(src/'recovered-memory/review.json',result)
            with self.assertRaisesRegex(ContractError,'Memory handoff blocked'):ls.execute('accept',src,p/'blocked',0,'fixture')

if __name__=='__main__':unittest.main()
