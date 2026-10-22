import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.experimental_parts import bind_finding_targets
from storyforge.contracts import ContractError
from storyforge.inference import Executor,judgment_signature
from storyforge.worker_policy import policy
from storyforge.writing_policy import instructions
from storyforge.editorial import RHETORIC_CHECKS
from storyforge.hosted import GoogleHosted,HostedError
from test_story import example

class LiteraryPolicyTests(unittest.TestCase):
    def test_actual_failed_indices_are_derived_without_changing_criticism(self):
        root=Path('tests/fixtures/practice-references-39796492449')
        raw=json.loads((root/'review.json').read_text());catalog=json.loads((root/'passages.json').read_text())
        bound=bind_finding_targets(raw,catalog)
        self.assertEqual(bound['issues'][0]['paragraph'],4)
        self.assertEqual(bound['issues'][1]['paragraph'],2)
        self.assertIsNone(bound['issues'][2]['paragraph'])
        self.assertEqual(judgment_signature(json.dumps(raw)),judgment_signature(json.dumps(bound)))
        self.assertFalse(bound['pass'])

    def test_unknown_citation_and_ambiguous_local_scope_remain_invalid(self):
        catalog=[{'id':'p001'},{'id':'p002'}]
        for issue in [{'scope':'paragraph','evidence_ids':['missing']},{'scope':'paragraph','evidence_ids':['p001','p002']}]:
            with self.assertRaises(ContractError):bind_finding_targets({'issues':[issue]},catalog)

    def test_strong_writing_fallback_and_provider_routes(self):
        req=example();req['profile']='small';req['execution_policy']={'experimental':True,'model_routing':'quality','literary_quality':True}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=HostedError('Google HTTP 503')) as api,patch('storyforge.local_worker.execute',return_value=('Concrete original prose.',{'finish_reason':'stop'})) as cpu:
            Executor(req,d,'worker').call('writer',{},'Write a scene.',output_format='text')
            self.assertEqual(cpu.call_args.args[0],'glitter-12b')
            self.assertEqual([call.args[0] for call in api.call_args_list],['flash','flash36','gemma'])
            self.assertIn('Application-owned literary brief',cpu.call_args.args[1])
        for role in ['humanizer','rhetoric_quality','chapter_quality']:
            self.assertEqual(policy(req,role,4200)['tier'],'flash36')
        self.assertEqual(policy(req,'story_quality',1600)['tier'],'gemma')

    def test_critic_failover_never_downgrades_to_flash_lite(self):
        req=example();req['profile']='small';req['execution_policy']={'experimental':True,'model_routing':'quality','literary_quality':True}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=HostedError('Google HTTP 503')) as api,patch('storyforge.local_worker.execute',return_value=('Review unavailable',{'finish_reason':'stop'})) as cpu:
            Executor(req,d,'worker').call('story_quality',{},'Review source.',output_format='text')
            self.assertEqual([call.args[0] for call in api.call_args_list],['gemma','flash36','flash'])
            self.assertEqual(cpu.call_args.args[0],'gemma-4-12b')

    def test_literary_brief_follows_input_and_style_check_is_required(self):
        req=example();req['style']={'register':'Spare contemporary realism.'};req['adaptation']={'mode':'none'}
        prompt=instructions(req,'writer')
        self.assertIn('Spare contemporary realism',prompt)
        self.assertIn('Do not impose epic language on unrelated inputs',prompt)
        self.assertIn('style_fidelity',RHETORIC_CHECKS)

    def test_literary_routes_do_not_repeat_failed_provider_before_handoff(self):
        with tempfile.TemporaryDirectory() as d:
            h=GoogleHosted(d,'placeholder')
            with patch.object(h,'request',side_effect=[{'totalTokens':20},HostedError('Google HTTP 503')]) as request:
                with self.assertRaises(HostedError):h.complete('flash','s','p',100,policy={'timeout':20,'literary_quality':True},role='writer')
                self.assertEqual(request.call_count,2)
