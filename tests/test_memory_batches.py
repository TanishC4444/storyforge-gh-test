import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge import batch_pipeline as b,memory_batches as m
from storyforge.dag import stage
from storyforge.expansion import prepare
from storyforge.storage import save,load
from storyforge.contracts import ContractError

class MemoryBatchTests(unittest.TestCase):
    def scene(self,p):
        stage('prepare',p/'none',p/'base',request_file='classic-universe-practice',profile='fast',backend='fixture')
        s=prepare(p/'base/snapshot.json',p/'prepared');s['request']['performance']['memory_pair_batches']=False;return s,s['plan']['scenes'][0]
    def make_inputs(self,p,s,phase='preflight'):
        prose='\n\n'.join(['Paragraph '+str(i)+' records an action.' for i in range(1,8)])
        save(p/'edited/prose.txt',prose);save(p/'memory/memory.json',{'memories':[]})
        plan=m.plan(s,p,p/'plan',phase);return prose,plan
    def test_parallel_checks_cover_paragraphs_and_facts_once_and_join(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);prose,plan=self.make_inputs(p,s)
            facts=[{'kind':'event','text':'An action.','known_by':[],'evidence_ids':['p001']} for _ in range(11)]
            save(p/'memory/memory.json',{'memories':facts});plan=m.plan(s,p,p/'plan','preflight')
            self.assertEqual([pid for x in plan['batches'] for pid in x['owned_passages']],['p%03d'%i for i in range(1,8)])
            self.assertEqual([i for x in plan['batches'] for i in x['fact_indices']],list(range(11)))
            for batch in plan['batches']:m.check(s,c,p,p/'batches'/batch['id'],'fixture',batch['id'])
            self.assertTrue(m.join(s,p,p/'joined')['pass'])
            value=load(p/'batches/0/memory-check-batch.json');value['plan_sha256']='stale';save(p/'batches/0/memory-check-batch.json',value)
            with self.assertRaises(ContractError):m.join(s,p,p/'stale')
    def test_preflight_continuity_issue_reaches_only_targeted_prose_repair(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);prose,plan=self.make_inputs(p,s)
            issue={'severity':'blocking','category':'continuity','quote':'Paragraph 2 records an action.','problem':'Character acts without entering.','fix':'Establish arrival in this paragraph.','target':'prose'}
            extraction={**issue,'quote':'Paragraph 1 records an action.','problem':'The extracted fact is unsupported.','fix':'Correct the memory rather than the prose.','target':'memory'}
            def checker(executor,role,packet,instruction,**kw):
                self.assertEqual(len(packet['proposed_memory']['memories']),0)
                return kw['validator']({'pass':False,'issues':[issue,extraction]})
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=checker):m.check(s,c,p,p/'batches/0','worker','0')
            for batch in plan['batches'][1:]:m.check(s,c,p,p/'batches'/batch['id'],'fixture',batch['id'])
            m.join(s,p,p/'memory-review')
            for kind in ['story-review','rhetoric-review']:save(p/kind/'review.json',{'pass':True,'issues':[]})
            rp=b.plan_repairs(s,p,p/'repair-plan')
            self.assertEqual(rp['batches'][0]['owned'],['p002'])
    def test_missing_or_failed_batch_never_becomes_approval(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);self.make_inputs(p,s)
            with patch('storyforge.inference.Executor.call',side_effect=TimeoutError('Deadline')):m.check(s,c,p,p/'batches/0','worker','0')
            result=m.join(s,p,p/'joined');self.assertFalse(result['pass']);self.assertTrue(result['unverified']);self.assertEqual(result['missing_batches'],['1','2'])
            save(p/'memory/memory.json',{'memories':[],'unverified':True})
            m.plan(s,p,p/'plan','preflight')
            with patch('storyforge.inference.Executor.call',side_effect=AssertionError('No unverifiable call')):
                self.assertTrue(m.check(s,c,p,p/'unavailable','worker','0')['review']['unverified'])
    def test_late_prose_finding_is_preserved_as_failure_and_source_is_bound(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);prose,plan=self.make_inputs(p,s,'final')
            issue={'severity':'blocking','category':'style','quote':'Paragraph 1 records an action.','problem':'Imagery repeats.','fix':'Rewrite simile.','target':'prose'}
            result=m.validate({'pass':False,'issues':[issue]},prose,plan['batches'][0],'final')
            self.assertFalse(result['pass']);self.assertTrue(result['issues'][0]['outside_requested_scope']);self.assertFalse(result.get('unverified',False))
            save(p/'edited/prose.txt',prose+' Changed.')
            with self.assertRaises(ContractError):m.check(s,c,p,p/'stale','fixture','0')
