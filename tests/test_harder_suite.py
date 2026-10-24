import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import yaml
from scripts.stress_queue import validate_suite,Queue
from storyforge.storage import save

ROOT=Path(__file__).resolve().parents[1]


class HarderSuiteTests(unittest.TestCase):
    def suite(self):return json.loads((ROOT/'examples/harder-suite.json').read_text())
    def test_harder_cases_have_real_different_contracts_and_bounded_recovery(self):
        suite=validate_suite(self.suite());self.assertEqual(len(suite['cases']),5)
        reqs={c['id']:json.loads((ROOT/'examples'/f'{c["request_file"]}.json').read_text()) for c in suite['cases']}
        self.assertEqual(len(reqs['ensemble']['characters']),16)
        self.assertIn('Yesterday',reqs['chronology']['scene_designs'][1]['time'])
        self.assertIn('Today',reqs['chronology']['scene_designs'][2]['time'])
        a,b=[reqs[k]['premise'].split('AUTHOR SOURCE (authoritative):\n')[1] for k in ['adapt-screenplay','adapt-comic']]
        self.assertEqual(a,b)
        self.assertEqual(reqs['adapt-screenplay']['initial_facts'],reqs['adapt-comic']['initial_facts'])
        self.assertTrue(suite['cases'][-1]['recovery_probe'])
        self.assertLess(sum(suite['per_run_timeout_minutes']+c.get('retry_timeout_minutes',suite['retry_timeout_minutes']) for c in suite['cases']),350)
    def test_probe_is_explicit_and_only_interrupts_second_scene_first_attempt(self):
        graph=yaml.safe_load((ROOT/'.github/workflows/living-universe-pipeline.yml').read_text())
        probes=[(name,step) for name,j in graph['jobs'].items() for step in j.get('steps',[]) if step.get('name','').startswith('Controlled recovery probe')]
        self.assertEqual(len(probes),1);name,step=probes[0]
        self.assertEqual(name,'s02_design');self.assertIn('github.run_attempt == 1',step['if']);self.assertIn('inputs.recovery_probe',step['if'])
        self.assertFalse(graph['on']['workflow_dispatch']['inputs']['recovery_probe']['default'])
    def test_bounded_retry_preserves_prefix_and_rejects_changed_approved_scene(self):
        case=self.suite()['cases'][-1]
        before={'accepted':[{'id':'first','prose':'Approved text.'}],'memories':[{'id':'m1','text':'Complete fact.'}]}
        for corrupt in [False,'text','memory']:
            with self.subTest(corrupt=corrupt),tempfile.TemporaryDirectory() as d:
                run={'id':12,'run_attempt':2,'status':'completed','conclusion':'success'}
                class API:
                    def api(self,*args):return run
                q=Queue(API(),self.suite(),d,'main','sha','tag',sleep=lambda _:None)
                def backup(api,run_id,scene,stage,out):
                    self.assertEqual(stage,'scene');save(out/'saved-story/checkpoint/snapshot.json',before)
                    return {'run_attempt':1,'job_id':42,'completed_scenes_preserved':1}
                def collect(case,run):
                    after=copy.deepcopy(before);after['accepted'].append({'id':'second','prose':'New scene.'})
                    if corrupt=='text':after['accepted'][0]['prose']='Changed without permission.'
                    if corrupt=='memory':after['memories'][0]['text']='A silently altered fact.'
                    save(q.out/case['id']/'story-recovery/checkpoint/snapshot.json',after)
                    return {**case,'pass':True,'assessment':'approved','run_id':12}
                row={**case,'pass':False,'failed_jobs':[{'name':'Scene 2 / Reconcile','steps':[{'name':'Controlled recovery probe: interrupt before scene 2 once'}]}]}
                with patch('scripts.resume_story.plan',side_effect=backup),patch('scripts.resume_story.apply') as apply,patch.object(q,'collect',side_effect=collect):
                    result=q.recover(case,{'id':12},row)
                self.assertEqual(apply.call_count,1)
                self.assertEqual(result['pass'],not corrupt)
                self.assertEqual(result['recovery']['approved_prefix_unchanged'],not corrupt)
    def test_unapproved_case_stays_unapproved_and_independent_case_still_runs(self):
        suite=self.suite();suite['cases']=suite['cases'][:2];calls=[]
        with tempfile.TemporaryDirectory() as d:
            q=Queue(None,suite,d,'main','sha','tag')
            def dispatch(case,resume):calls.append(case['id']);return {'id':len(calls),'html_url':'https://example.invalid','conclusion':'failure'}
            with patch.object(q,'dispatch',side_effect=dispatch),patch.object(q,'wait',side_effect=lambda run,_:run),patch.object(q,'collect',side_effect=lambda case,run:{**case,'pass':False,'assessment':'needs_revision'}),patch.object(q,'recover',side_effect=lambda case,run,row:row) as recover:
                self.assertFalse(q.run());self.assertEqual(recover.call_count,2)
            report=json.loads((Path(d)/'report.json').read_text())
            self.assertTrue(report['complete']);self.assertFalse(report['all_passed']);self.assertEqual(report['quality_status'],'needs_revision')
        self.assertEqual(calls,['chronology','ensemble'])
