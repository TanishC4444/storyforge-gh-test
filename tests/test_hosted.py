import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.hosted import GoogleHosted,HostedError
from storyforge.narrative_gate import defects,change_metrics
from storyforge.inference import Executor
from test_story import example

class HostedTests(unittest.TestCase):
    def test_flash_hard_call_budget(self):
        with tempfile.TemporaryDirectory() as d:
            h=GoogleHosted(d,'not-a-real-key')
            for _ in range(4):h.reserve('flash',100)
            with self.assertRaisesRegex(HostedError,'budget exhausted'):h.reserve('flash',100)
            self.assertNotIn('not-a-real-key',Path(d,'quota.json').read_text())
    def test_overlarge_prompt_falls_back_without_waiting(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(HostedError,'per-minute'):GoogleHosted(d).reserve('gemma',15000)
    def test_provider_failure_uses_existing_worker(self):
        req=example();req['api_roles']={'writer':'gemma'}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=HostedError('Google HTTP 429')),patch('storyforge.cpu_fallback.execute',return_value=('Fallback prose',{'finish_reason':'stop'})) as local:
            self.assertEqual(Executor(req,d,'worker').call('writer',{'scene':'test'},'write'),'Fallback prose')
            local.assert_called_once()
    def test_hosted_success_does_not_start_cpu_model(self):
        req=example();req['api_roles']={'writer':'gemma'}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',return_value=('Hosted prose',{'finish_reason':'stop','model':'gemma-4-31b-it'})),patch('storyforge.cpu_fallback.execute',side_effect=AssertionError('CPU must stay idle')):
            self.assertEqual(Executor(req,d,'worker').call('writer',{},'write'),'Hosted prose')
            call=json.loads(next(Path(d,'calls').glob('*.json')).read_text());self.assertEqual(call['model'],'gemma-4-31b-it')
    def test_structural_defects_are_blocking(self):
        prose='He took the iron.\n\nHe took the iron.\n\n"We must go," he said.\n\n{\"prose\":'
        issues=' '.join(defects(prose))
        self.assertIn('Duplicate paragraph',issues);self.assertIn('no-dialogue',issues);self.assertIn('Serialization',issues)
    def test_change_fraction_is_diagnostic_not_quality(self):
        self.assertEqual(change_metrics('same','same')['changed_fraction'],0)
    def test_audit_requires_real_source_quote(self):
        from storyforge.retell import review
        from storyforge.contracts import ContractError
        with self.assertRaises(ContractError):review({'pass':False,'issues':[{'quote':'invented','problem':'p','fix':'f'}]},'Actual prose')
