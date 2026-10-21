import copy,io,json,tempfile,unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
from storyforge.inference import Executor,ROOT
from storyforge.hosted import GoogleHosted,HostedError
from storyforge.contracts import ContractError
from storyforge.storage import load
from test_story import example


class CanonTests(unittest.TestCase):
    def state(self):
        return {'version':1,'accepted':[{'id':'scene1','participants':['mara']}],
                'memories':[{'id':'m00000','kind':'resource','fact_key':'lamp.oil','text':'Lamp has six measures of oil.', 'known_by':['mara','oren'],'source':'scene1'}]}
    def update(self):
        return {'kind':'resource','fact_key':'lamp.oil','text':'Lamp has four measures of oil.', 'known_by':['mara'],'supersedes':['m00000']}
    def test_state_transition_retains_history_and_actor_ignorance(self):
        from storyforge.canon import append,working
        state=self.state();append(state,[self.update()],'scene2')
        self.assertEqual(len(state['canon']['history']),2)
        self.assertEqual(state['canon']['current'][0]['text'],'Lamp has four measures of oil.')
        self.assertEqual(working(state,'oren')['facts'][0]['text'],'Lamp has six measures of oil.')
        self.assertEqual(working(state,'mara')['facts'][0]['text'],'Lamp has four measures of oil.')
    def test_unknown_or_mismatched_supersession_does_not_mutate_canon(self):
        from storyforge.canon import append
        for change in [{'supersedes':['nonexistent']},{'fact_key':'different'}]:
            state=self.state();before=copy.deepcopy(state)
            with self.assertRaises(ContractError):append(state,[{**self.update(),**change}],'scene2')
            self.assertEqual(state,before)
    def test_old_obligation_survives_many_recent_events(self):
        from storyforge.canon import working
        state=self.state();state['memories'][0].update(kind='thread',text='Return the lamp to its owner by dawn.')
        state['memories'] += [{'kind':'event','text':f'Routine event {i}', 'known_by':['mara'],'source':'scene1'} for i in range(60)]
        result=working(state,'mara',budget=1000)
        self.assertIn('Return the lamp',json.dumps(result['facts']))
        self.assertTrue(result['omitted_ids'])


class EfficiencyRoutingTests(unittest.TestCase):
    def test_flash_outage_uses_gemma_before_cpu(self):
        req=example();req['api_roles']={'writer':'flash'};req['performance']={'hosted_failover':True}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=[HostedError('Google HTTP 503'),('Actual prose',{'finish_reason':'stop'})]) as hosted,patch('storyforge.local_worker.execute',side_effect=AssertionError('CPU must stay idle')):
            self.assertEqual(Executor(req,d,'worker').call('writer',{},'write'),'Actual prose')
            self.assertEqual([c.args[0] for c in hosted.call_args_list],['flash','gemma'])
    def test_circuit_is_shared_between_role_executors(self):
        with tempfile.TemporaryDirectory() as d:
            first=GoogleHosted(d,'placeholder');first.circuit('flash',HostedError('Google HTTP 503'))
            second=GoogleHosted(d,'placeholder')
            with patch.object(second,'request',side_effect=AssertionError('Open circuit must not hit network')):
                with self.assertRaisesRegex(HostedError,'circuit open'):second.complete('flash','s','p',100)
    def test_output_allowance_counts_toward_shared_token_budget(self):
        with tempfile.TemporaryDirectory() as d:
            hosted=GoogleHosted(d,'placeholder')
            with patch.object(hosted,'request',side_effect=[{'totalTokens':13000}]),patch.object(hosted,'reserve',side_effect=HostedError('per-minute')) as reserve:
                with self.assertRaises(HostedError):hosted.complete('gemma','s','p',2000)
                reserve.assert_called_once_with('gemma',15000)
    def test_original_prompt_is_application_owned_not_regenerated(self):
        from storyforge.contracts import refinement
        from storyforge.fixture import respond
        req=example();req['performance']={'application_prompt_binding':True}
        value=json.loads(respond('refiner',{},req));value.pop('original_prompt')
        with tempfile.TemporaryDirectory() as d,patch('storyforge.fixture.respond',return_value=json.dumps(value)):
            result=Executor(req,d,'fixture').call('refiner',{'request':req},'refine',validator=lambda x:refinement(x,req))
            self.assertEqual(result['original_prompt'],req['premise'])
            call=next(Path(d,'packets').glob('*.json'))
            self.assertNotIn('original_prompt',load(call)['response_schema']['properties'])


class FullFlowTests(unittest.TestCase):
    def test_batched_full_process_keeps_all_stages_and_records_final_text_once(self):
        from storyforge.full_flow import run
        req=example();req['performance']={'compact_packets':True,'application_prompt_binding':True,'batch_development':True,'canon_index':True}
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            root=Path(d);(root/'examples').mkdir();(root/'skills').symlink_to(ROOT/'skills',target_is_directory=True)
            (root/'examples/fixture-full.json').write_text(json.dumps(req))
            with patch('storyforge.dag.ROOT',root):result=run(root/'run','fixture-full',backend='fixture')
            self.assertTrue(result['complete'])
            timeline=load(root/'run/phase-timings.json');names=[v['stage'] for v in timeline]
            count=req['chapters']*req['scenes_per_chapter']
            for phase in ['refine','refine_review','refine_revision','refine_gate','plan','plan_review','plan_revision','plan_gate']:
                self.assertIn(phase,names)
            self.assertEqual(sum(n.endswith('_memory') for n in names),count)
            self.assertEqual(sum(n.endswith('_memory_review') for n in names),count)
            self.assertEqual(sum(n.endswith('_review') and n.startswith('s') and not n.endswith('memory_review') for n in names),count)
            self.assertFalse(any('memory_final' in n for n in names))
            self.assertEqual(len(result['canon']['history']),len(result['memories']))
            for phase in ['s01_draft','s01_edit','s01_repair','s01_direction','s01_design','s01_accept']:
                self.assertIn(phase,names)
            dev_calls=list((root/'run/stages/refine_review/out/calls').glob('*.json'))
            self.assertEqual(len(dev_calls),1)
            # Neither the fixture marker nor synthetic approval is presented as a live benchmark.
            self.assertIn('FIXTURE',(root/'run/FINAL_STORY.txt').read_text())
