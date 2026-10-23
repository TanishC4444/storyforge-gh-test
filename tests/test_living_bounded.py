"""Exercise four-chapter handoff through the actual batched memory and canon gates."""
import json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.storage import load,save
from storyforge.dag import stage
from storyforge.living_prepare import prepare
from storyforge import batch_pipeline as b,memory_batches as m,section_reviews as sr

class BoundedLivingTests(unittest.TestCase):
    def exercise(self,request_file,chapters,per_chapter=1,living=True,provisional_first=False):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);stage('prepare',p/'none',p/'base',request_file=request_file,profile='fast',backend='fixture')
            with patch('storyforge.inference.Executor.call',side_effect=AssertionError('No initial refinement inference')):
                if living:state=prepare(p/'base/snapshot.json',p/'quick',backend='fixture')
                else:
                    from storyforge.expansion import prepare as expansion_prepare
                    state=expansion_prepare(p/'base/snapshot.json',p/'quick')
            self.assertEqual(len(state['plan']['scenes']),chapters*per_chapter)
            rng=state.get('universe_rng_state')
            for i in range(chapters*per_chapter):
                root=p/str(i);save(root/'design/state/snapshot.json',state)
                stage('scene_design',root/'design',root/'designed',index=i,backend='fixture')
                state=load(root/'designed/snapshot.json');card=state['plan']['scenes'][i]
                if living:
                    self.assertEqual(state['universe_attempts'],i+1);self.assertNotEqual(state['universe_rng_state'],rng)
                self.assertEqual(len(state['accepted']),i);rng=state.get('universe_rng_state')
                save(root/'source/direction/direction.txt','FIXTURE direction')
                plan=b.plan_draft(state,card,root/'source',root/'plan','fixture')
                save(root/'write/plan/draft-plan.json',plan)
                for beat in plan['beats']:b.write_batch(state,card,root/'write',root/'merge/batches'/beat['id'],'fixture',beat['id'])
                save(root/'merge/plan/draft-plan.json',plan);prose=b.merge_draft(state,root/'merge',root/'draft')
                save(root/'review/edited/prose.txt',prose)
                sections=sr.plan(state,root/'review',root/'review/plan')
                for section in sections['sections']:sr.summarize(state,card,root/'review',root/'review/batches'/section['id'],'fixture',section['id'])
                sr.join_summaries(state,root/'review',root/'review/summaries')
                for group in range(1 if sections.get('adaptive') else 3):b.review_batch(state,card,root/'review',root/'story/batches'/str(group),'fixture','story',group)
                save(root/'story/edited/prose.txt',prose);b.join_reviews(state,root/'story',root/'findings/story-review','story')
                save(root/'rhetoric/edited/prose.txt',prose);shutil.copytree(root/'review/plan',root/'rhetoric/plan');shutil.copytree(root/'review/summaries',root/'rhetoric/summaries')
                for section in sections['sections']:
                    for group in range(1 if sections.get('adaptive') else 2):
                        bid=section['id']+'-'+str(group);sr.review_section(state,card,root/'rhetoric',root/'rhetoric/batches'/bid,'fixture',bid)
                sr.join_reviews(state,root/'rhetoric',root/'findings/rhetoric-review')
                save(root/'findings/edited/prose.txt',prose)
                ep=m.extract_plan(state,root/'review',root/'review/plan')
                for batch in ep['batches']:m.extract_batch(state,card,root/'review',root/'review/batches'/batch['id'],'fixture',batch['id'])
                m.extract_join(state,root/'review',root/'initial')
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
                shutil.copytree(root/'repaired',root/'final-input/edited')
                final_sections=sr.plan(state,root/'final-input',root/'final-input/plan')
                for sec in final_sections['sections']:sr.summarize(state,card,root/'final-input',root/'final-input/batches'/sec['id'],'fixture',sec['id'])
                sr.join_summaries(state,root/'final-input',root/'final-input/summaries')
                for bid in sr.final_ids(final_sections):sr.final_review(state,card,root/'final-input',root/'final-input/final-batches'/bid,'fixture',bid)
                final=b.finalize(state,card,root/'final-input',root/'final','fixture')
                self.assertTrue(final['verdict']['pass']);self.assertEqual(final['judgment_calls'],len(sr.final_ids(final_sections)));self.assertEqual(final['judgment_rounds'],1)
                save(root/'refresh/edited/prose.txt',prose);save(root/'refresh/original/prose.txt',prose);shutil.copytree(root/'initial',root/'refresh/initial-memory')
                shutil.copytree(root/'findings/memory-review',root/'refresh/preflight-memory')
                refreshed=m.refresh_plan(state,root/'refresh',root/'refresh/plan')
                for batch in refreshed['batches']:m.extract_batch(state,card,root/'refresh',root/'refresh/batches'/batch['id'],'fixture',batch['id'])
                m.extract_join(state,root/'refresh',root/'memory')
                self.assertTrue(memory_round(root/'fm',root/'memory','final',root/'accept/memory-review')['pass'])
                save(root/'accept/state/snapshot.json',state);shutil.copytree(root/'final',root/'accept/edited');shutil.copytree(root/'memory',root/'accept/memory')
                save(root/'accept/story-review/review.json',final['story']);save(root/'accept/rhetoric-review/review.json',final['rhetoric'])
                if provisional_first and i==0:
                    decision=load(root/'accept/edited/repair.json')
                    failed={'pass':False,'checks':[],'issues':[],'unverified':True,'error':'Simulated literary provider outage'}
                    decision['editorial_adjudication'].update(story=failed,rhetoric=failed,verdict=failed,unverified=True)
                    save(root/'accept/edited/repair.json',decision)
                    save(root/'accept/story-review/review.json',failed);save(root/'accept/rhetoric-review/review.json',failed)
                stage('accept',root/'accept',root/'accepted',index=i,backend='fixture')
                state=load(root/'accepted/snapshot.json')
                if provisional_first:
                    self.assertFalse(state['accepted'][i]['canon_committed']);self.assertTrue(state['draft_memories'])
                    self.assertEqual(state['draft_continuity_receipts'][-1]['scene'],card['id'])
                    self.assertTrue(all(m.get('source')=='user_input' for m in state['memories']))
                else:self.assertTrue(state['accepted'][i]['canon_committed'])
                self.assertEqual(len(state['accepted']),i+1)
            self.assertTrue(state['complete']);self.assertEqual(state['completion_status'],'complete_with_warnings' if provisional_first else 'complete')
            self.assertTrue((root/'accepted/story.txt').exists())
    def test_four_chapter_fixture_carries_canon_and_random_state_through_acceptance(self):
        self.exercise('iliad-2526-living-practice',4)
    def test_novel_two_chapter_hybrid_memory_handoff(self):
        self.exercise('chaos-novel-practice',2)
    def test_verified_draft_memory_survives_a_literary_outage_into_next_scene(self):
        self.exercise('chaos-novel-practice',2,provisional_first=True)
    def test_stage_play_two_scene_hybrid_memory_handoff(self):
        self.exercise('stage-play-practice',1,2,living=False)
    def test_living_workflow_supports_four_chapters_with_sequential_canon_handoff(self):
        text=Path('.github/workflows/living-universe.yml').read_text()
        self.assertIn('  s04_accept:',text);self.assertIn('  s04_memory_preflight_batches:',text)
        self.assertIn("- '4'",text)
