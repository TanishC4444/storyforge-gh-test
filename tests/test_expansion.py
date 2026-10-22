import copy,json,os,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.dag import stage
from storyforge.expansion import prepare,preview,collect,bible
from storyforge.storage import load,save
from storyforge.contracts import ContractError
from storyforge.runtime import inference_timeout_seconds,review_call_timeout_seconds

class ExpansionTests(unittest.TestCase):
    def initial(self,p):
        stage('prepare',p/'none',p/'prepare',request_file='classic-universe-practice',profile='fast',backend='fixture')
        with patch('storyforge.inference.Executor.call',side_effect=AssertionError('Preparation must not call a model')):
            return prepare(p/'prepare/snapshot.json',p/'quickstart')
    def test_preparation_preserves_author_brief_and_never_calls_model(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s=self.initial(p);req=s['request']
            self.assertEqual(s['refinement']['original_prompt'],req['premise']);self.assertEqual(s['plan']['scenes'][0]['id'],req['scene_designs'][0]['id'])
            self.assertEqual(s['universe_episode'],1);self.assertEqual(s['version'],0);self.assertEqual(s['accepted'],[])
            self.assertFalse(req['execution_policy']['continue_with_warnings'])
    def test_full_fixture_uses_parallel_passage_editing_and_strict_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.initial(p)
            def task(name,kind,state,extra=(),cid=None):
                dest=p/name;shutil.copytree(state,dest/'inputs/state')
                for a,b in extra:shutil.copytree(a,dest/'inputs'/b)
                stage(kind,dest/'inputs',dest/'out',character=cid,request_file='classic-universe-practice',profile='fast',backend='fixture')
                return dest/'out'
            s=task('design','scene_design',p/'quickstart');characters=[]
            for cid in load(s/'snapshot.json')['plan']['scenes'][0]['participants']:
                characters.append((task('char-'+cid,'character',s,cid=cid),'characters/'+cid))
            direction=task('direction','director',s,characters)
            draft=task('draft','writer',s,[(direction,'direction')]);preview(draft)
            edits=task('edit-plan','edit_plan',s,[(draft,'draft')]);batches=[]
            for b in load(edits/'batches.json'):
                batches.append((task('edit-'+b['id'],'edit_batch',s,[(edits,'edit-plan')],b['id']),'batches/'+b['id']))
            edited=task('edit','edit_merge',s,[(edits,'edit-plan')]+batches);preview(edited,'Passage-edited draft')
            story=task('story','story_review',s,[(draft,'draft'),(edited,'edited')]);rhet=task('rhet','rhetoric_review',s,[(edited,'edited')]);mem=task('memory','memory',s,[(edited,'edited')])
            fixed=task('repair','repair',s,[(edited,'edited'),(story,'diagnosis'),(rhet,'rhetoric')]);preview(fixed,'Review-repaired draft')
            verify=task('verify','verify',s,[(fixed,'edited'),(story,'diagnosis'),(draft,'draft')]);vr=task('verify-rhet','verify_rhetoric',s,[(fixed,'edited'),(rhet,'rhetoric')]);fm=task('final-memory','memory_final',s,[(fixed,'edited'),(mem,'initial-memory')]);mv=task('mem-review','memory_review',s,[(fixed,'edited'),(fm,'memory')])
            final=task('accept','accept',s,[(fixed,'edited'),(verify,'story-review'),(vr,'rhetoric-review'),(fm,'memory'),(mv,'memory-review')])
            state=load(final/'snapshot.json');self.assertTrue(state['complete']);self.assertEqual(state['accepted'][0]['quality_status'],'reviewed')
            self.assertTrue(any(m.get('source','').startswith('episode-000001/') for m in state['memories']))
    def test_reader_output_survives_failed_review_without_canon(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);save(p/'results/s01_draft/draft.txt','The smith refused the offer.');preview(p/'results/s01_draft')
            rows=collect(p/'results',p/'reading');self.assertEqual(len(rows),1)
            self.assertIn('unreviewed',(p/'reading/READABLE_DRAFT.txt').read_text());self.assertFalse((p/'reading/canon/snapshot.json').exists())
    def test_preview_of_rejected_response_is_labeled_and_does_not_expose_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);save(p/'calls/writer-test.json',{'output':'An incomplete scene.','secret_input':'never show'})
            v=preview(p);self.assertEqual(v['status'],'rejected_or_incomplete_model_response');self.assertNotIn('never show',(p/'readable-draft.txt').read_text())
    def test_review_time_budget_is_opt_in_and_bounded(self):
        with patch.dict(os.environ,{'STORY_REVIEW_TIMEOUT_SECONDS':'1800'},clear=True):self.assertEqual(inference_timeout_seconds('story_quality'),1800)
        with patch.dict(os.environ,{'STORY_REVIEW_TIMEOUT_SECONDS':'0'},clear=True):
            with self.assertRaises(ValueError):review_call_timeout_seconds()
    def test_resume_rejects_unreviewed_canon_and_repeated_episode(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s=self.initial(p)
            old=copy.deepcopy(s);old.update(complete=True,accepted=[{'quality_status':'needs_review'}]);save(p/'bad.json',old)
            with self.assertRaisesRegex(ContractError,'Unreviewed'):prepare(p/'prepare/snapshot.json',p/'next',p/'bad.json')
            old['accepted']=[{'quality_status':'reviewed',**{k:{'pass':True} for k in ['review','rhetoric_review','memory_review']}}];save(p/'bad.json',old)
            with self.assertRaisesRegex(ContractError,'new episode'):prepare(p/'prepare/snapshot.json',p/'next',p/'bad.json')
    def test_classic_graph_has_distinct_editors_and_readable_outputs(self):
        t=Path('.github/workflows/cinematic-expansion.yml').read_text()
        for x in ['s01_characters:','s01_draft_plan:','s01_write_batches:','s01_repair_plan:','s01_repair_batches:','s01_edit:','s01_memory_review:','s01_accept:','name: readable-story','name: universe-canon']:self.assertIn(x,t)
        self.assertNotIn('refine_review:',t);self.assertIn('STORY_REVIEW_TIMEOUT_SECONDS:',t)


class LivingRunnerGraphTests(unittest.TestCase):
    def test_local_event_preparation_preserves_draw_and_compiles_author_brief(self):
        from storyforge.living_prepare import prepare as living
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            stage('prepare',p/'none',p/'prepare',request_file='local-universe-massive',profile='expressive',backend='fixture')
            with patch('storyforge.inference.Executor.call',side_effect=AssertionError('Fixture preparation never runs an LLM')):
                state=living(p/'prepare/snapshot.json',p/'quickstart',backend='fixture')
            self.assertEqual(state['accepted'],[]);self.assertEqual(state['universe_attempts'],1)
            self.assertEqual(state['refinement_method'],'application_compiled_author_brief_no_model_calls')
            self.assertTrue((p/'quickstart/proposal.json').exists())
            self.assertEqual(state['request']['api_roles']['writer_beat'],'flash')
            # Retry a failed event with preserved prior canon and advanced random stream.
            second=living(p/'prepare/snapshot.json',p/'next',p/'quickstart/snapshot.json','fixture')
            self.assertEqual(second['universe_attempts'],2);self.assertEqual(second['universe_episode'],1)
            self.assertNotEqual(second['universe_rng_state'],state['universe_rng_state'])
    def test_local_workflow_exposes_full_runner_graph_without_nested_dispatch(self):
        t=Path('.github/workflows/living-universe.yml').read_text()
        for name in ['prepare','quickstart','s01_design','s01_characters','s01_draft','s01_draft_plan','s01_write_batches','s01_repair_plan','s01_repair_batches','s01_story','s01_rhetoric','s01_memory','s01_memory_review','s01_accept']:
            self.assertIn('  '+name+':',t)
        self.assertIn('GEMINI_API_KEY',t);self.assertIn('GEMINI_DISTINCT_PROJECTS',t);self.assertNotIn('workflow_dispatches',t)
        self.assertIn('python -m storyforge.living_prepare',t)
