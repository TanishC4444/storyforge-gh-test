import copy,json,tempfile,unittest
from pathlib import Path
import yaml
from scripts.resume_story import plan,apply,select_job
from storyforge.story_checkpoint import preserve
from storyforge.storage import save,load

class StoryResumeTests(unittest.TestCase):
    def state(self):
        proof={'pass':True,'issues':[]}
        scene={'id':'ch01-sc01','prose':'The completed scene remains exactly as written.','quality_status':'reviewed','canon_committed':True,'review':proof,'rhetoric_review':proof,'memory_review':proof}
        return {'accepted':[scene],'memories':[{'id':'m00001','text':'Private fact retained in full.','known_by':['c01']}],'plan':{'scenes':[{'id':'ch01-sc01'},{'id':'ch02-sc01'}]}}
    def fake(self):
        state=self.state()
        class API:
            def __init__(self):self.posts=[];self.attempt=1
            def api(self,path,method='GET',body=None):
                if method=='POST':self.posts.append((path,body));return None
                if path.startswith('actions/runs/12/artifacts'):return {'total_count':3,'artifacts':[{'id':i,'name':n} for i,n in enumerate(['quickstart','s01_accept','s02_draft'])]}
                if path.startswith('actions/runs/12/jobs'):return {'total_count':2,'jobs':[{'id':41,'name':'Scene 2 / Reconcile scene 2 with verified prior memory','conclusion':'success'},{'id':42,'name':'Scene 2 / Compile literary findings and allocate targeted edits','conclusion':'success'}]}
                return {'id':12,'status':'completed','conclusion':'failure','run_attempt':self.attempt,'head_sha':'saved-revision','path':'.github/workflows/living-universe-pipeline.yml','html_url':'https://example.invalid/runs/12'}
            def artifact(self,artifact,dest):
                if artifact['name']=='quickstart':save(Path(dest)/'snapshot.json',{**state,'accepted':[]})
                elif artifact['name']=='s01_accept':save(Path(dest)/'snapshot.json',state)
                else:save(Path(dest)/'prose.txt','The failed scene draft is still available.')
        return API()
    def test_completed_scene_and_full_memory_survive_with_failed_draft_kept_separate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state=self.state();save(p/'input/s01_accept/snapshot.json',state)
            broken=copy.deepcopy(state);broken['accepted'].append({**state['accepted'][0],'id':'ch02-sc01','canon_committed':False,'quality_status':'needs_review'})
            save(p/'input/s02_accept/snapshot.json',broken);save(p/'input/s02_draft/prose.txt','Unapproved draft.');save(p/'input/s02_final_check/prose.txt','Latest failed reviewed candidate.')
            result=preserve(p/'input',p/'out')
            self.assertEqual(result['completed_scenes'],1);self.assertEqual(result['resume_scene'],2)
            self.assertEqual(load(p/'out/checkpoint/snapshot.json'),state)
            self.assertEqual((p/'out/drafts/s02/prose.txt').read_text(),'Latest failed reviewed candidate.')
            self.assertFalse(result['drafts'][0]['approved'])
            self.assertIsNone(preserve(p/'input',p/'limited',expected=1)['resume_scene'])
    def test_manual_resume_backs_up_first_then_reruns_only_the_editing_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);api=self.fake();result=plan(api,'12','auto','editing',p)
            self.assertEqual(result['job_id'],42);self.assertEqual(result['completed_scenes_preserved'],1);self.assertFalse(api.posts)
            self.assertEqual(load(p/'saved-story/checkpoint/snapshot.json')['memories'],self.state()['memories'])
            self.assertTrue((p/'backup/s02_draft/prose.txt').exists())
            apply(api,p);self.assertEqual(api.posts,[('actions/jobs/42/rerun',{})])
    def test_partial_writer_output_survives_without_a_compiled_scene(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);save(p/'input/s01_accept/snapshot.json',self.state())
            save(p/'input/s02_write_batches-0/draft-batch.json',{'prose':'A rejected but readable scene opening.','verified_form':False})
            save(p/'input/s02_write_batches-0/0/incomplete-generation.json',{'role':'writer_beat','text':'An earlier unfinished sentence, but'})
            result=preserve(p/'input',p/'out')
            self.assertEqual(result['resume_scene'],2);self.assertEqual(len(result['partial_batches']),2)
            self.assertEqual((p/'out/partial-batches/s02_write_batches-0/draft.txt').read_text(),'A rejected but readable scene opening.')
            self.assertTrue(all(not item['approved'] for item in result['partial_batches']))
    def test_resume_cannot_overwrite_completed_scenes_or_skip_missing_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            api=self.fake()
            with self.assertRaisesRegex(ValueError,'overwrite completed'):plan(api,'12','1','scene',d)
            self.assertFalse(api.posts)
    def test_source_attempt_change_blocks_the_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            api=self.fake();plan(api,'12','auto','editing',d);api.attempt=2
            with self.assertRaisesRegex(ValueError,'changed since backup'):apply(api,d)
            self.assertFalse(api.posts)
    def test_old_runs_can_resume_at_unique_scene_boundary(self):
        job={'id':9,'name':'Reconcile scene 2 with verified prior memory','conclusion':'success'}
        self.assertEqual(select_job([job],2,'editing')['id'],9)
    def test_resume_upload_precedes_dispatch_and_pipeline_artifacts_support_reruns(self):
        workflow=yaml.safe_load(Path('.github/workflows/resume-story.yml').read_text())
        steps=workflow['jobs']['resume']['steps'];upload=next(i for i,s in enumerate(steps) if s.get('uses')=='actions/upload-artifact@v4');dispatch=next(i for i,s in enumerate(steps) if s.get('run')=='python -m scripts.resume_story apply')
        self.assertLess(upload,dispatch);self.assertEqual(workflow['permissions']['actions'],'write')
        pipeline=yaml.safe_load(Path('.github/workflows/living-universe-pipeline.yml').read_text())
        for job in pipeline['jobs'].values():
            for step in job['steps']:
                if step.get('uses')=='actions/upload-artifact@v4':self.assertTrue(step['with']['overwrite'])
        self.assertTrue(any(s.get('with',{}).get('name')=='story-recovery' and s.get('if')=='always()' for s in pipeline['jobs']['results']['steps']))

if __name__=='__main__':unittest.main()
