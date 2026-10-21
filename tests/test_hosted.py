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
            for _ in range(6):
                h.reserve('flash',100)
                path=Path(d,'quota.json');value=json.loads(path.read_text());value['flash']['recent']=[];path.write_text(json.dumps(value))
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

class HostedTransportTests(unittest.TestCase):
    def test_transient_server_failure_gets_one_budgeted_retry(self):
        from storyforge.hosted import MODELS
        result={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'Accepted prose'}]}}]}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.time.sleep'):
            h=GoogleHosted(d,'private-key')
            with patch.object(h,'request',side_effect=[{'totalTokens':100},HostedError('Google HTTP 500'),result]):
                text,diag=h.complete('gemma','system','prompt',100)
            self.assertEqual(text,'Accepted prose');self.assertEqual(diag['model'],MODELS['gemma'])
            self.assertEqual(json.loads(Path(d,'quota.json').read_text())['gemma']['calls'],2)
    def test_truncated_hosted_output_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            h=GoogleHosted(d,'private-key')
            with patch.object(h,'request',side_effect=[{'totalTokens':100},{'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'Partial prose'}]}}]}]):
                with self.assertRaisesRegex(HostedError,'finish naturally'):h.complete('gemma','s','p',100)
    def test_auth_failure_opens_circuit(self):
        with tempfile.TemporaryDirectory() as d:
            h=GoogleHosted(d,'private-key')
            with patch.object(h,'request',side_effect=[{'totalTokens':100},HostedError('Google HTTP 403')]) as request:
                with self.assertRaises(HostedError):h.complete('gemma','s','p',100)
                with self.assertRaisesRegex(HostedError,'circuit open'):h.complete('gemma','s','p',100)
                self.assertEqual(request.call_count,2)
    def test_rhetoric_signals_are_contextual_not_blocking(self):
        from storyforge.narrative_gate import rhetorical_signals
        signals=rhetorical_signals('The gesture was a plea. His voice measured each name.')
        self.assertTrue(signals)
        self.assertIn('Assess in context',signals[0]['guidance'])

class ContextBudgetTests(unittest.TestCase):
    def test_large_editor_retains_configured_cpu_context(self):
        req=example();req['n_ctx']=16384;req['profile']='fast';req['api_roles']={'humanizer':'gemma'}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=HostedError('Google HTTP 403')),patch('storyforge.local_worker.execute',return_value=('Revised prose',{'finish_reason':'stop'})) as cpu:
            Executor(req,d,'worker').call('humanizer',{'prose':'Source'},'edit')
            self.assertEqual(cpu.call_args.args[4],16384)

class AuditEvidenceTests(unittest.TestCase):
    def test_case_only_quote_is_bound_to_actual_source(self):
        from storyforge.retell import review
        result=review({'pass':False,'issues':[{'quote':'the smith waited.','problem':'Specific issue','fix':'Specific repair'}]},'The smith waited.')
        self.assertEqual(result['issues'][0]['quote'],'The smith waited.')
    def test_paraphrased_quote_is_still_rejected(self):
        from storyforge.retell import review
        from storyforge.contracts import ContractError
        with self.assertRaises(ContractError):review({'pass':False,'issues':[{'quote':'The craftsman lingered.','problem':'p','fix':'f'}]},'The smith waited.')

class RescueBudgetTests(unittest.TestCase):
    def test_at_most_two_rescue_attempts(self):
        with tempfile.TemporaryDirectory() as d:
            h=GoogleHosted(d)
            self.assertTrue(h.can_rescue());self.assertTrue(h.can_rescue());self.assertFalse(h.can_rescue())
    def test_last_flash_slot_is_reserved_for_final_audit(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'quota.json').write_text(json.dumps({'flash':{'calls':5,'recent':[]}}))
            self.assertFalse(GoogleHosted(d).can_rescue())

class CharacterKnowledgeTests(unittest.TestCase):
    def test_future_scene_events_and_world_spoilers_are_withheld(self):
        from storyforge.character_proposals import actor_input
        state={'memories':[{'text':'Own fact','known_by':['smith']},{'text':'Other secret','known_by':['king']}]}
        card={'location':'shore','time':'dawn','intended_change':'Secret future weapons acquired'}
        value=actor_input({'id':'smith','goal':'Go home'},state,card,'Work beside ships')
        text=json.dumps(value)
        self.assertIn('Own fact',text);self.assertNotIn('Other secret',text);self.assertNotIn('future weapons',text)
