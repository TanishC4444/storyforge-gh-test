import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.runtime import inference_timeout_seconds
from storyforge.experimental_parts import review,needs_repair
from storyforge.editorial import STORY_CHECKS
from storyforge.inference import Executor
from storyforge.contracts import ContractError
from test_story import example

class ReviewBudgetTests(unittest.TestCase):
    def test_review_timeout_is_bounded_by_role_and_remaining_job_time(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(inference_timeout_seconds('story_quality'),600)
            self.assertEqual(inference_timeout_seconds('writer'),21300)
        with patch.dict(os.environ,{'STORY_JOB_DEADLINE':'1250'}),patch('storyforge.runtime.time.time',return_value=1000):
            self.assertEqual(inference_timeout_seconds('memory_quality'),250)

    def test_consolidated_review_assesses_every_dimension_once_on_main_thread(self):
        import threading
        req=example();req['execution_policy']={'literary_quality':True}
        prose='The smith refused the offer and lost his wage.'
        seen=[]
        class Fake:
            def call(self,role,packet,instruction,**kwargs):
                seen.append((threading.current_thread() is threading.main_thread(),packet['required_checks']))
                raw={'pass':True,'checks':{k:{'verdict':'pass','evidence_ids':['p001'],'reason':'A refusal has a specific material consequence in the cited action.'} for k in packet['required_checks']},'issues':[]}
                return kwargs['validator'](raw)
        result=review(Fake(),req,prose,{},STORY_CHECKS,'story_quality','story')
        self.assertEqual(seen,[(True,STORY_CHECKS)])
        self.assertEqual({c['id'] for c in result['checks']},set(STORY_CHECKS))

    def test_negative_advisory_review_can_trigger_repair(self):
        req={'execution_policy':{'gate_repair_threshold':'blocking'}}
        self.assertTrue(needs_repair({'pass':False,'issues':[{'severity':'advisory'}]},req))
        self.assertFalse(needs_repair({'pass':True,'issues':[]},req))

    def test_cpu_review_timeout_is_not_repeated_as_validation_retry(self):
        req=example();req['max_stage_retries']=2;req['api_roles']={}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.local_worker.execute',side_effect=TimeoutError('Inference call deadline exhausted')) as cpu:
            with self.assertRaises(ContractError):Executor(req,d,'worker').call('story_quality',{},'Review it.',output_format='text')
            self.assertEqual(cpu.call_count,1)

    def test_recovery_workflow_keeps_separate_verified_repair_dag(self):
        text=Path('.github/workflows/troy-review-recovery.yml').read_text()
        for key in ['s01_story','s01_rhetoric','s01_repair','s01_verify','s01_verify_rhetoric','s01_memory_review','s01_accept']:
            self.assertIn('  '+key+':',text)
        self.assertIn('run-id: ${{ inputs.source_run }}',text)
        self.assertIn("assert review['pass']",text)
        self.assertNotIn('s01_draft:',text)
