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
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=HostedError('Google HTTP 429')),patch('storyforge.local_worker.execute',return_value=('Fallback prose',{'finish_reason':'stop'})) as local:
            self.assertEqual(Executor(req,d,'worker').call('writer',{'scene':'test'},'write'),'Fallback prose')
            local.assert_called_once()
    def test_hosted_success_does_not_start_cpu_model(self):
        req=example();req['api_roles']={'writer':'gemma'}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',return_value=('Hosted prose',{'finish_reason':'stop','model':'gemma-4-31b-it'})),patch('storyforge.local_worker.execute',side_effect=AssertionError('CPU must stay idle')):
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

class MemoryScopeTests(unittest.TestCase):
    def test_explicit_witness_schema_does_not_offer_public(self):
        from storyforge.output_schema import memory_schema,continuity_schema
        from storyforge.evidence import payload
        schema=memory_schema(payload('The smith inspected the mark.'),['smith','king'],allow_public=False)
        self.assertEqual(schema['properties']['memories']['items']['properties']['known_by']['items']['enum'],['smith','king'])
        ledger=continuity_schema(2)
        self.assertEqual(ledger['properties']['approved_memory_indices']['maxItems'],2)
        self.assertEqual(ledger['properties']['approved_memory_indices']['items']['enum'],[0,1])
    def test_known_identity_corruption_is_blocked(self):
        self.assertTrue(any('identity' in x for x in defects('Thestor, the blind hearth-priest, sat in the grotto.')))

class CPUFallbackSchemaTests(unittest.TestCase):
    def test_remote_cpu_keeps_structured_decoding(self):
        import os,sys,types
        from dataclasses import dataclass
        from unittest.mock import MagicMock
        from storyforge.cpu_fallback import execute
        @dataclass
        class Result:finish_reason:str='stop'
        module=types.ModuleType('gh_ai_runner');module.__path__=[]
        module.Agent=MagicMock();module.GitHubAIRunner=MagicMock()
        module.Agent.return_value.run.return_value='{"approved_memory_indices":[]}'
        module.Agent.return_value.last_result=Result()
        limits=types.ModuleType('gh_ai_runner.limits');limits.Limits=MagicMock()
        schema={'type':'object','properties':{'approved_memory_indices':{'type':'array','maxItems':0}}}
        with patch.dict(sys.modules,{'gh_ai_runner':module,'gh_ai_runner.limits':limits}),patch.dict(os.environ,{'GH_AI_TOKEN':'test-placeholder'}),patch('storyforge.cpu_fallback.importlib.util.find_spec',return_value=None):
            execute('qwen3b','system','prompt',700,16384,'memory_quality',schema)
        kwargs=module.Agent.call_args.kwargs
        self.assertEqual(kwargs['n_ctx'],16384)
        self.assertEqual(kwargs['generation_options']['response_format']['schema'],schema)

class ContinuityRecoveryTests(unittest.TestCase):
    def test_unknown_indices_never_grant_knowledge(self):
        from storyforge.continuity import validate
        value=validate({'approved_memory_indices':[0,'1',1,9,-1],'charges_remaining':'23','charges_used_this_scene':2},2)
        self.assertEqual(value['approved_memory_indices'],[0,1]);self.assertEqual(value['quarantined_approval_indices'],[9,-1]);self.assertEqual(value['charges_remaining'],23)
    def test_bad_usage_count_is_withheld_not_silently_rewritten(self):
        from storyforge.continuity import reconcile
        value=reconcile({'charges_remaining':23,'charges_used_this_scene':2},{'charges_remaining':24},2)
        self.assertIsNone(value['charges_used_this_scene']);self.assertEqual(value['net_charge_count_reduction'],1);self.assertEqual(value['quarantined_reported_usage'],2)

class PublicAudienceTests(unittest.TestCase):
    def test_greek_council_is_not_worldwide_public_knowledge(self):
        from storyforge.coordinator import visible
        facts=[{'text':'The council knows the inventory','known_by':['public'],'source':'council'},{'text':'The war is ongoing','known_by':['public'],'source':'user_input'}]
        scope={'council':['odysseus','achilles']}
        self.assertEqual([x['text'] for x in visible(facts,'hector',scope)],['The war is ongoing'])
        self.assertEqual(len(visible(facts,'achilles',scope)),2)

class WholeStorySeparatorTests(unittest.TestCase):
    def test_scene_dividers_are_not_duplicated_prose(self):
        text='\n\n* * *\n\n'.join(['Unique opening '+str(i)+'. '+('Different words '+str(i)+' ') * 80 for i in range(4)])
        self.assertFalse(any('Duplicate paragraph' in x for x in defects(text)))
    def test_actual_duplicate_paragraph_still_fails(self):
        self.assertTrue(any('Duplicate paragraph' in x for x in defects('Same paragraph.\n\n* * *\n\nSame paragraph.')))


class RefinementFailureRegressionTests(unittest.TestCase):
    def test_actual_failed_run_outputs_remain_rejected(self):
        from storyforge.contracts import refinement, ContractError
        req=example()
        for path in (Path(__file__).parent/'fixtures/retell-refiner-39618729263').glob('*.json'):
            value=json.loads(path.read_text())
            # Retell binds the immutable user prompt itself, as in the failed run.
            value['original_prompt']=req['premise']
            with self.subTest(path=path.name),self.assertRaises(ContractError):
                refinement(value,req)

    def test_provider_outage_then_missing_fields_gets_complete_retry(self):
        from storyforge.contracts import refinement
        from storyforge.output_schema import refinement_schema
        req=example();req['api_roles']={'refiner':'flash'};req['max_stage_retries']=1
        complete={key: [] if spec['type']=='array' else 'Developed detail'
                  for key,spec in refinement_schema()['properties'].items()}
        complete['original_prompt']=req['premise']
        bad={'original_prompt':req['premise'],'refined_prompt':'Draft',
             'central_conflict':'Conflict','reader_experience':'Tension'}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=HostedError('Google HTTP 503')),patch('storyforge.local_worker.execute',side_effect=[(json.dumps(bad),{'finish_reason':'stop'}),(json.dumps(complete),{'finish_reason':'stop'})]) as cpu:
            result=Executor(req,d,'worker').call('refiner',{'request':req},'Develop premise',validator=lambda x:refinement(x,req))
            self.assertEqual(result,complete)
            self.assertEqual(cpu.call_count,2)
            for call in cpu.call_args_list:
                self.assertEqual(call.kwargs['response_schema'],refinement_schema())
                self.assertIn('character_tensions',call.args[1])
            self.assertIn('original request',cpu.call_args.args[2])
            self.assertNotIn('Repair JSON structure only',cpu.call_args.args[1])

    def test_flash_receives_schema_and_gemma_uses_prompt_contract(self):
        from storyforge.output_schema import refinement_schema
        result={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{}'}]}}]}
        for kind in ['flash','gemma']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                h=GoogleHosted(d,'placeholder')
                with patch.object(h,'request',side_effect=[{'totalTokens':100},result]) as request:
                    h.complete(kind,'system','prompt',100,structured=True,response_schema=refinement_schema())
                config=request.call_args.args[1]['generationConfig']
                self.assertEqual(config['responseMimeType'],'application/json')
                self.assertEqual(config.get('responseJsonSchema'),refinement_schema() if kind=='flash' else None)
