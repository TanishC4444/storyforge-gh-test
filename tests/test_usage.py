import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.usage import record,collect,summarize
from storyforge.hosted import GoogleHosted,HostedError
from storyforge.inference import Executor,ROOT
from storyforge.contracts import plan
from test_story import example


class UsageTests(unittest.TestCase):
    def test_truncated_provider_output_still_records_actual_usage(self):
        with tempfile.TemporaryDirectory() as d:
            h=GoogleHosted(d,'not-a-real-key')
            result={'candidates':[{'finishReason':'MAX_TOKENS'}],'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':20,'thoughtsTokenCount':30,'totalTokenCount':150}}
            with patch.object(h,'request',side_effect=[{'totalTokens':100},result]):
                with self.assertRaises(HostedError):h.complete('gemma','private instruction','private prompt',100,role='refiner')
            value=collect(d)[0]
            self.assertEqual(value['total_tokens'],150);self.assertEqual(value['thinking_tokens'],30)
            self.assertEqual(value['finish_reason'],'MAX_TOKENS')
            self.assertNotIn('private',(Path(d)/'usage.jsonl').read_text())
            self.assertNotIn('not-a-real-key',(Path(d)/'usage.jsonl').read_text())
    def test_retries_count_separately_and_unknown_is_not_zero(self):
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.time.sleep'):
            h=GoogleHosted(d,'placeholder')
            with patch.object(h,'request',side_effect=[{'totalTokens':100},HostedError('Google HTTP 503'),{'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'OK'}]}}],'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':1,'totalTokenCount':101}}]):
                h.complete('gemma','s','p',100,role='writer')
            report=summarize(d,Path(d)/'report')
            self.assertEqual(report['requests'],2)
            self.assertEqual(report['unknown_usage_requests'],1)
            self.assertEqual(report['observed_total_tokens'],101)
    def test_copying_usage_files_and_raw_calls_does_not_double_count(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);record(root/'a','cpu','qwen3b','writer',{'prompt_tokens':3,'completion_tokens':2,'total_tokens':5})
            (root/'b').mkdir();(root/'b/usage.jsonl').write_text((root/'a/usage.jsonl').read_text())
            (root/'a/calls').mkdir();(root/'a/calls/legacy.json').write_text(json.dumps({'role':'writer','diagnostic':{'usage':{'total_tokens':5}}}))
            self.assertEqual(len(collect(root)),1)
    def test_usage_artifact_survives_failed_workflow_and_is_retained(self):
        text=(ROOT/'.github/workflows/troy-multi-api.yml').read_text()
        self.assertIn('retention-days: 90',text)
        self.assertIn('name: usage-${{ github.run_id }}',text)
        self.assertLess(text.index('python -m storyforge.usage'),text.index('name: story-run-${{ github.run_id }}'))
        self.assertIn('if: always()\n        run: python -m storyforge.usage',text)


class LatestFailureTests(unittest.TestCase):
    def test_actual_responses_bind_metadata_without_reordering_story_choices(self):
        req=example();req.update(chapters=1,scenes_per_chapter=4)
        req['characters']=[{'id':cid} for cid in ['agamemnon','odysseus','achilles','hector','thestor']]
        req['performance']={'application_plan_binding':True}
        for filename in ['plan-82ba6cd38e29f639d683.json','plan-95bdc9b1feabc5b35df1.json']:
            raw=(ROOT/'tests/fixtures'/filename).read_text();original=json.loads(raw)
            with tempfile.TemporaryDirectory() as d,patch('storyforge.fixture.respond',return_value=raw):
                result=Executor(req,d,'fixture').call('architect',{},'Plan in requested reading order',validator=lambda x:plan(x,req))
                self.assertEqual([c['chapter'] for c in result['scenes']],[1,1,1,1])
                self.assertEqual([c['id'] for c in result['scenes']],[f'ch01-sc{i:02}' for i in range(1,5)])
                self.assertEqual([c['goal'] for c in result['scenes']],[c['goal'] for c in original['scenes']])
                # This is a format fix, never an automatic semantic approval.
                self.assertNotIn('pass',result)
    def test_batched_development_fallback_keeps_configured_context(self):
        req=example();req['profile']='fast';req['n_ctx']=16384
        req['performance']={'compact_packets':True};req['api_roles']={'development_editor':'gemma'}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=HostedError('Google HTTP 503')),patch('storyforge.local_worker.execute',return_value=('{"pass":true}',{'finish_reason':'stop'})) as cpu:
            Executor(req,d,'worker').call('development_editor',{},'Review',validator=lambda x:x)
            self.assertEqual(cpu.call_args.args[4],16384)
