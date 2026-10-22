"""Exercise four-chapter handoff through the actual batched memory and canon gates."""
import json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.storage import load,save
from storyforge.dag import stage
from storyforge.living_prepare import prepare
from storyforge import batch_pipeline as b,memory_batches as m

class BoundedLivingTests(unittest.TestCase):
    def test_four_chapter_fixture_carries_canon_and_random_state_through_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);stage('prepare',p/'none',p/'base',request_file='iliad-2526-living-practice',profile='fast',backend='fixture')
            with patch('storyforge.inference.Executor.call',side_effect=AssertionError('No initial refinement inference')):
                state=prepare(p/'base/snapshot.json',p/'quick',backend='fixture')
            self.assertEqual(len(state['plan']['scenes']),4);self.assertEqual(state['universe_attempts'],0)
            self.assertEqual(state['plan']['scenes'][3]['chapter'],4)
            rng=state['universe_rng_state']
            for i in range(4):
                root=p/str(i);save(root/'design/state/snapshot.json',state)
                stage('scene_design',root/'design',root/'designed',index=i,backend='fixture')
                state=load(root/'designed/snapshot.json');card=state['plan']['scenes'][i]
                self.assertEqual(state['universe_attempts'],i+1);self.assertNotEqual(state['universe_rng_state'],rng)
                self.assertEqual(len(state['accepted']),i);rng=state['universe_rng_state']
                save(root/'source/direction/direction.txt','FIXTURE direction')
                plan=b.plan_draft(state,card,root/'source',root/'plan','fixture')
                save(root/'write/plan/draft-plan.json',plan)
                for beat in plan['beats']:b.write_batch(state,card,root/'write',root/'merge/batches'/beat['id'],'fixture',beat['id'])
                save(root/'merge/plan/draft-plan.json',plan);prose=b.merge_draft(state,root/'merge',root/'draft')
                save(root/'review/edited/prose.txt',prose)
                for kind in ['story','rhetoric']:
                    for group in range(3):b.review_batch(state,card,root/'review',root/kind/'batches'/str(group),'fixture',kind,group)
                    save(root/kind/'edited/prose.txt',prose);b.join_reviews(state,root/kind,root/'findings'/(kind+'-review'),kind)
                save(root/'findings/edited/prose.txt',prose)
                b.extract_initial(state,card,root/'review',root/'initial','fixture')
                def memory_round(folder,memory,phase,out):
                    save(folder/'edited/prose.txt',prose);shutil.copytree(memory,folder/'memory')
                    mp=m.plan(state,folder,folder/'plan',phase)
                    for batch in mp['batches']:m.check(state,card,folder,folder/'batches'/batch['id'],'fixture',batch['id'])
                    return m.join(state,folder,out)
                self.assertTrue(memory_round(root/'pre',root/'initial','preflight',root/'findings/memory-review')['pass'])
                rp=b.plan_repairs(state,root/'findings',root/'repair-plan')
                save(root/'rb/plan/repair-plan.json',rp)
                for batch in rp['batches']:b.repair_batch(state,card,root/'rb',root/'rm/batches'/batch['id'],'fixture',batch['id'])
                save(root/'rm/plan/repair-plan.json',rp);save(root/'rm/edited/prose.txt',prose);b.merge_repairs(state,root/'rm',root/'repaired')
                for kind in ['story-review','rhetoric-review','memory-review']:shutil.copytree(root/'findings'/kind,root/'final-input'/kind)
                shutil.copytree(root/'repaired',root/'final-input/edited');final=b.finalize(state,card,root/'final-input',root/'final','fixture')
                self.assertTrue(final['verdict']['pass']);self.assertEqual(final['judgment_calls'],1)
                save(root/'refresh/edited/prose.txt',prose);save(root/'refresh/original/prose.txt',prose);shutil.copytree(root/'initial',root/'refresh/initial-memory')
                b.refresh_memory(state,card,root/'refresh',root/'memory','fixture')
                self.assertTrue(memory_round(root/'fm',root/'memory','final',root/'accept/memory-review')['pass'])
                save(root/'accept/state/snapshot.json',state);shutil.copytree(root/'final',root/'accept/edited');shutil.copytree(root/'memory',root/'accept/memory')
                save(root/'accept/story-review/review.json',final['story']);save(root/'accept/rhetoric-review/review.json',final['rhetoric'])
                stage('accept',root/'accept',root/'accepted',index=i,backend='fixture')
                state=load(root/'accepted/snapshot.json')
                self.assertTrue(state['accepted'][i]['canon_committed']);self.assertEqual(len(state['accepted']),i+1)
            self.assertTrue(state['complete']);self.assertEqual(state['completion_status'],'complete')
            self.assertTrue((root/'accepted/story.txt').exists())
    def test_living_workflow_supports_four_chapters_with_sequential_canon_handoff(self):
        text=Path('.github/workflows/living-universe.yml').read_text()
        self.assertIn('  s04_accept:',text);self.assertIn('  s04_memory_preflight_batches:',text)
        self.assertIn("- '4'",text)
