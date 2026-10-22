import copy,json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge import batch_pipeline as b
from storyforge.dag import stage
from storyforge.expansion import prepare
from storyforge.storage import save,load
from storyforge.contracts import ContractError
from storyforge.patching import digest

class BatchPipelineTests(unittest.TestCase):
    def setup_scene(self,p):
        stage('prepare',p/'none',p/'base',request_file='classic-universe-practice',profile='fast',backend='fixture')
        s=prepare(p/'base/snapshot.json',p/'prepared');return s,s['plan']['scenes'][0]
    def test_full_fixture_batches_compile_and_share_one_final_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.setup_scene(p);save(p/'source/direction/direction.txt','FIXTURE direction')
            plan=b.plan_draft(s,c,p/'source',p/'plan','fixture')
            self.assertEqual(len(plan['beats']),3);self.assertEqual(sum(x['target_words'] for x in plan['beats']),900)
            save(p/'write/plan/draft-plan.json',plan)
            for beat in plan['beats']:b.write_batch(s,c,p/'write',p/'merge/batches'/beat['id'],'fixture',beat['id'])
            save(p/'merge/plan/draft-plan.json',plan);prose=b.merge_draft(s,p/'merge',p/'draft')
            self.assertIn('FIXTURE',prose);self.assertEqual(len(prose.split('\n\n')),3)
            save(p/'review/edited/prose.txt',prose)
            for kind in ['story','rhetoric']:
                for group in range(3):b.review_batch(s,c,p/'review',p/kind/'batches'/str(group),'fixture',kind,group)
                save(p/kind/'edited/prose.txt',prose);v=b.join_reviews(s,p/kind,p/'findings'/('story-review' if kind=='story' else 'rhetoric-review'),kind);self.assertTrue(v['pass'])
            save(p/'findings/edited/prose.txt',prose);rp=b.plan_repairs(s,p/'findings',p/'repair-plan')
            self.assertEqual(rp['batches'][0]['id'],'noop')
            save(p/'rb/plan/repair-plan.json',rp);b.repair_batch(s,c,p/'rb',p/'repairmerge/batches/noop','fixture','noop')
            save(p/'repairmerge/plan/repair-plan.json',rp);save(p/'repairmerge/edited/prose.txt',prose)
            self.assertEqual(b.merge_repairs(s,p/'repairmerge',p/'repaired'),prose)
            for kind in ['story-review','rhetoric-review']:shutil.copytree(p/'findings'/kind,p/'final-input'/kind)
            shutil.copytree(p/'repaired',p/'final-input/edited')
            final=b.finalize(s,c,p/'final-input',p/'final','fixture');self.assertTrue(final['verdict']['pass'])
            self.assertEqual(final['judgment_calls'],1)
            # Exercise the remaining new memory plumbing and existing acceptance gate.
            b.extract_initial(s,c,p/'review',p/'initial','fixture')
            shutil.copytree(p/'final',p/'memory-input/edited')
            shutil.copytree(p/'review/edited',p/'memory-input/original')
            shutil.copytree(p/'initial',p/'memory-input/initial-memory')
            b.refresh_memory(s,c,p/'memory-input',p/'memory','fixture')
            shutil.copytree(p/'final',p/'mv/edited');shutil.copytree(p/'memory',p/'mv/memory')
            from storyforge import memory_batches
            mp=memory_batches.plan(s,p/'mv',p/'mv/plan','final')
            for batch in mp['batches']:
                memory_batches.check(s,c,p/'mv',p/'mv/batches'/batch['id'],'fixture',batch['id'])
            self.assertTrue(memory_batches.join(s,p/'mv',p/'memory-review')['pass'])
            save(p/'accept/state/snapshot.json',s)
            shutil.copytree(p/'final',p/'accept/edited');shutil.copytree(p/'memory',p/'accept/memory')
            shutil.copytree(p/'memory-review',p/'accept/memory-review')
            save(p/'accept/story-review/review.json',final['story'])
            save(p/'accept/rhetoric-review/review.json',final['rhetoric'])
            stage('accept',p/'accept',p/'accepted',index=0,backend='fixture')
            accepted=load(p/'accepted/snapshot.json')
            self.assertEqual(len(accepted['accepted']),1)
            self.assertTrue(accepted['accepted'][0]['canon_committed'])

    def test_only_flagged_paragraph_can_change_and_foreign_patches_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.setup_scene(p);prose='The smith worked.\n\nThe wrong person lost passage.\n\nThe tide rose.'
            save(p/'findings/edited/prose.txt',prose)
            issue={'category':'pov_knowledge','problem':'Wrong household identity.','fix':'Restore the smith as the affected person.','evidence_ids':['p002']}
            save(p/'findings/story-review/review.json',{'pass':False,'issues':[issue]});save(p/'findings/rhetoric-review/review.json',{'pass':True,'issues':[]})
            plan=b.plan_repairs(s,p/'findings',p/'plan');self.assertEqual(plan['batches'][0]['owned'],['p002'])
            save(p/'batch/plan/repair-plan.json',plan)
            def editor(executor,role,packet,instruction,**kw):
                self.assertEqual(executor.req['max_stage_retries'],0);self.assertEqual(packet['batch']['owned'],['p002'])
                return kw['validator']({'replacements':{'p002':'The smith lost passage.'}})
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=editor):b.repair_batch(s,c,p/'batch',p/'merge/batches/0','worker','0')
            save(p/'merge/plan/repair-plan.json',plan);save(p/'merge/edited/prose.txt',prose)
            fixed=b.merge_repairs(s,p/'merge',p/'fixed');self.assertEqual(fixed,prose.replace('The wrong person lost passage.','The smith lost passage.'))
            value=load(p/'merge/batches/0/repair-batch.json');value['source_sha256']='stale';save(p/'merge/batches/0/repair-batch.json',value)
            with self.assertRaises(ContractError):b.merge_repairs(s,p/'merge',p/'bad')
    def test_rejected_writing_retries_only_that_small_batch(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.setup_scene(p);save(p/'source/direction/direction.txt','Direction');plan=b.plan_draft(s,c,p/'source',p/'plan','fixture');save(p/'write/plan/draft-plan.json',plan)
            seen=[]
            def writer(executor,role,packet,instruction,**kw):
                seen.append(role);self.assertEqual(packet['your_beat']['target_words'],300)
                self.assertEqual(packet['author_contract']['style'],s['request']['style'])
                if len(seen)==1:
                    save(executor.folder/'calls/mock.json',{'role':'writer_beat','output':'"Invalid dialogue."'});raise ContractError('Quoted speech')
                self.assertEqual(packet['rejected_batch'],'"Invalid dialogue."')
                return kw['validator'](' '.join(['An earned physical action carries a specific material cost.']*30))
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=writer):value=b.write_batch(s,c,p/'write',p/'written','worker','0')
            self.assertEqual(seen,['writer_beat','repair']);self.assertTrue(value['verified_form'])
    def test_missing_reviews_are_unverified_not_approved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.setup_scene(p);save(p/'edited/prose.txt','A scene.')
            self.assertTrue(b.join_reviews(s,p,p/'joined','story')['unverified'])
    def test_unchanged_memory_is_reused_without_model_call(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.setup_scene(p)
            save(p/'edited/prose.txt','Unchanged.');save(p/'original/prose.txt','Unchanged.');save(p/'initial-memory/memory.json',{'memories':[]})
            with patch('storyforge.batch_pipeline.memory_extract',side_effect=AssertionError('No re-extraction')):
                self.assertEqual(b.refresh_memory(s,c,p,p/'out','fixture'),{'memories':[]})

    def test_failed_repair_batch_keeps_original_text_and_records_uncertainty(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.setup_scene(p);text='Original paragraph.'
            save(p/'findings/edited/prose.txt',text)
            save(p/'findings/story-review/review.json',{'pass':False,'issues':[{'category':'scene_change','problem':'Test issue','fix':'Specific fix','evidence_ids':['p001']}]})
            save(p/'findings/rhetoric-review/review.json',{'pass':True,'issues':[]})
            plan=b.plan_repairs(s,p/'findings',p/'plan');save(p/'batch/plan/repair-plan.json',plan)
            with patch('storyforge.inference.Executor.call',side_effect=TimeoutError('Batch deadline')):
                b.repair_batch(s,c,p/'batch',p/'merge/batches/0','worker','0')
            save(p/'merge/plan/repair-plan.json',plan);save(p/'merge/edited/prose.txt',text)
            self.assertEqual(b.merge_repairs(s,p/'merge',p/'out'),text)
            self.assertEqual(load(p/'out/repair.json')['unverified_batches'],['0'])
