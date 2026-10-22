import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge import parallel_story as ps
from storyforge import universe as u
from storyforge.contracts import ContractError
from storyforge.storage import load,save

class ParallelModeTests(unittest.TestCase):
    def make(self,d):
        p=Path(d);b=ps.prepare('troy-practice',p/'prepare','fixture',1,1,350)
        for sid in ps.scene_ids(b['request']):ps.design(b,sid,p/'contracts'/sid,'fixture')
        return p,ps.join_contracts(b,p/'contracts',p/'join','fixture')
    def test_fixture_pipeline_commits_only_at_end(self):
        with tempfile.TemporaryDirectory() as d:
            p,b=self.make(d);sid=ps.scene_ids(b['request'])[0]
            value=ps.draft(b,sid,p/'drafts'/sid,'fixture');self.assertEqual(value['quality_status'],'fixture')
            state=ps.reconcile(b,p/'drafts',p/'final','fixture')
            self.assertEqual(state['version'],1);self.assertEqual(state['completion_status'],'fixture_complete')
            self.assertFalse((p/'final/FINAL_STORY.txt').exists())
    def test_missing_duplicate_or_stale_artifacts_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p,b=self.make(d);ids=ps.scene_ids(b['request'])
            with self.assertRaises(ContractError):ps.load_set(p/'empty','scene.json',ids,b)
            value=ps.draft(b,ids[0],p/'drafts/a','fixture');save(p/'drafts/b/scene.json',value)
            with self.assertRaises(ContractError):ps.load_set(p/'drafts','scene.json',ids,b)
            value['brief_hash']='stale';save(p/'stale/scene.json',value)
            with self.assertRaises(ContractError):ps.load_set(p/'stale','scene.json',ids,b)
    def test_unverified_local_review_blocks_acceptance(self):
        with self.assertRaises(ContractError):ps.local_findings({'s':{'reviews':{'story':{'pass':False,'unverified':True,'issues':[]}},'prose':'Actual event.'}})
    def test_reconciler_cannot_invent_evidence(self):
        v={'pass':False,'issues':[{'scene_id':'s','problem':'Conflict','fix':'Correct','evidence_ids':['missing']}]}
        with self.assertRaises(ContractError):ps.validate_audit(v,['s'],{'s':{'prose':'Actual event.'}})
    def test_windows_cover_all_items_with_overlap_and_reject_oversize(self):
        items=[{'i':i,'body':'x'*100} for i in range(8)];windows=ps.bounded_windows(items,400)
        self.assertEqual(set(x['i'] for w in windows for x in w),set(range(8)))
        for a,b in zip(windows,windows[1:]):self.assertEqual(a[-1],b[0])
        with self.assertRaises(ContractError):ps.bounded_windows([{'body':'x'*500}],400)

class UniverseModeTests(unittest.TestCase):
    def test_local_only_role_configuration(self):
        spec,req=u.foundation('troy-universe');self.assertFalse(req['api_roles']);self.assertFalse(req['execution_policy']['experimental'])
        self.assertNotIn('model_routing',req['execution_policy']);self.assertEqual(req['execution_policy']['cpu_models']['story_quality'],'qwen7b')
    def test_resume_preserves_canon_and_advances_random_stream(self):
        with tempfile.TemporaryDirectory() as d:
            first=u.run('troy-universe',d,'fixture',1,5);old=copy.deepcopy(first['memories'])
            second=u.run('troy-universe',d,'fixture',1,5)
            self.assertEqual(second['version'],2);self.assertEqual(second['memories'][:len(old)],old)
            self.assertNotEqual(second['rng_state'],first['rng_state']);self.assertFalse(Path(d,'UNIVERSE.txt').exists())
    def test_rejected_event_records_draw_without_canon_commit(self):
        with tempfile.TemporaryDirectory() as d,patch('storyforge.universe.scene_card',side_effect=RuntimeError('Injected failure')):
            with self.assertRaises(RuntimeError):u.run('troy-universe',d,'fixture',1,5)
            state=load(Path(d,'checkpoint.json'));self.assertEqual(state['version'],0);self.assertEqual(state['accepted'],[]);self.assertEqual(state['attempts'],1)
    def test_foundation_and_fixture_mode_cannot_change_on_resume(self):
        with tempfile.TemporaryDirectory() as d:
            u.run('troy-universe',d,'fixture',1,5)
            with self.assertRaisesRegex(ContractError,'Fixture'):u.run('troy-universe',d,'worker',1,5)
            x=load(Path(d,'checkpoint.json'));x['foundation_hash']='changed';save(Path(d,'checkpoint.json'),x)
            with self.assertRaisesRegex(ContractError,'foundation'):u.run('troy-universe',d,'fixture',1,5)
    def test_random_draw_replays_from_same_checkpoint(self):
        spec,req=u.foundation('troy-universe');a={'rng_state':u.random.Random(spec['seed']).getstate(),'attempts':0};b=copy.deepcopy(a)
        self.assertEqual(u.propose(a,spec,req),u.propose(b,spec,req));self.assertEqual(a,b)
    def test_actor_view_withholds_private_rival_fact(self):
        state={'memories':[{'id':'a','kind':'event','text':'Own fact','known_by':['a']},{'id':'b','kind':'event','text':'Secret rival fact','known_by':['b']}],'accepted':[]}
        self.assertNotIn('Secret rival fact',json.dumps(u.working(state,character='a')))
    def test_workflows_are_separate_and_universe_has_no_api_secrets_or_schedule(self):
        text=Path('.github/workflows/living-universe.yml').read_text();self.assertNotIn('GEMINI_API_KEY',text);self.assertNotIn('schedule:',text)
        text=Path('.github/workflows/parallel-scenes.yml').read_text();self.assertIn('matrix:',text);self.assertIn('reconcile:',text)
