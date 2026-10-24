"""Transient capacity waits are bounded, and never become output or approval."""
import io,json,os,tempfile,time,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from storyforge.contracts import request,ContractError
from storyforge.hosted import HostedError
from storyforge.inference import Executor
from storyforge.provider_recovery import configuration,transient,wait_to_retry
from storyforge.storage import load

class ProviderRecoveryTests(unittest.TestCase):
    def req(self):
        r=request(load('examples/iron-man-alternate-origin.json'));r['max_stage_retries']=0;r['profile']='fast';return r
    def exercise(self,failures,stage_retries=0):
        req=self.req();req['max_stage_retries']=stage_retries;clock=[0.];base=time.time();calls=[];waits=[];states=[]
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            def serve(http_request,timeout):
                calls.append(clock[0])
                if len(calls)<=failures:raise urllib.error.HTTPError('https://example.invalid',503,'Unavailable',{'Retry-After':'20'},io.BytesIO(b'{"error":{"status":"UNAVAILABLE"}}'))
                return io.BytesIO(json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'A candidate awaiting ordinary quality and memory checks.'}]}}]}).encode())
            def sleep(seconds):
                waits.append(seconds);states.append(load(folder/'provider-recovery.json')['state']);clock[0]+=seconds
            with patch.dict(os.environ,{'GEMINI_API_KEY':'placeholder','GEMINI_API_KEYS':'["backup-placeholder"]','GEMINI_DISTINCT_PROJECTS':'true','STORY_QUOTA_DIR':str(folder/'provider-budget')}),patch('urllib.request.urlopen',side_effect=serve),patch('storyforge.provider_recovery.random.uniform',return_value=0),patch('storyforge.provider_recovery.time.monotonic',side_effect=lambda:clock[0]),patch('storyforge.provider_recovery.time.time',side_effect=lambda:base+clock[0]),patch('storyforge.provider_recovery.time.sleep',side_effect=sleep),patch('storyforge.local_worker.execute',side_effect=AssertionError('No downgrade or invented output')):
                executor=Executor(req,folder,'worker')
                try:text=executor.call('writer_beat',{},'Write the scene.',output_format='text',tokens=200)
                except ContractError:text=None
            record=load(folder/'provider-recovery.json') if (folder/'provider-recovery.json').exists() else None
            if record is not None:record['test_warnings']=load(folder/'warnings.json') if (folder/'warnings.json').exists() else []
            return text,calls,waits,states,record,list((folder/'packets').glob('*.json'))!=[]
    def test_healthy_provider_never_delays_or_consumes_buffer(self):
        text,calls,waits,states,record,checkpoint=self.exercise(0)
        self.assertTrue(text);self.assertEqual(len(calls),1);self.assertEqual(waits,[]);self.assertIsNone(record)
    def test_three_unavailable_routes_wait_then_recover_without_redrafting(self):
        text,calls,waits,states,record,checkpoint=self.exercise(3)
        self.assertTrue(text,str((calls,record)));self.assertEqual(len(calls),4)
        self.assertEqual(calls[:3],[0,0,0]);self.assertGreaterEqual(calls[3],45)
        self.assertTrue(waits);self.assertLessEqual(max(waits),5)
        self.assertEqual(set(states),{'waiting_for_provider'});self.assertEqual(record['state'],'provider_recovered');self.assertTrue(checkpoint)
    def test_persistent_outage_keeps_checkpoint_and_never_fakes_a_pass(self):
        text,calls,waits,states,record,checkpoint=self.exercise(99)
        self.assertIsNone(text);self.assertEqual(len(calls),9,str((calls,record)))
        self.assertEqual(record['state'],'awaiting_provider_resume');self.assertFalse(record['approval_granted']);self.assertTrue(checkpoint)
        self.assertGreaterEqual(sum(waits),135)
    def test_auth_daily_quota_and_generation_errors_are_not_capacity_retries(self):
        for error in [HostedError('Google HTTP 400'),HostedError('Google HTTP 401'),HostedError('Google HTTP 403'),HostedError('Google HTTP 429',daily=True),ContractError('Invalid source evidence')]:
            self.assertFalse(transient(error))
        self.assertTrue(transient(HostedError('Google HTTP 503 UNAVAILABLE')))
        self.assertTrue(transient(HostedError('Google connection failed or timed out')))
        self.assertTrue(transient(HostedError('Hosted generation did not finish naturally: MAX_TOKENS')))
    def test_expired_shared_deadline_saves_resume_status_without_waiting(self):
        with tempfile.TemporaryDirectory() as d,patch('storyforge.runtime.worker_timeout_seconds',return_value=20),patch('storyforge.provider_recovery.time.sleep',side_effect=AssertionError('No time for a retry')):
            self.assertFalse(wait_to_retry([HostedError('Google HTTP 503')],d,'writer_beat',1,configuration(self.req())))
            self.assertEqual(load(Path(d)/'provider-recovery.json')['state'],'awaiting_provider_resume')
    def test_unbounded_or_implicit_retry_settings_are_rejected(self):
        for change in [{'max_rounds':100},{'buffer_seconds':100000},{'extra_requests':19},{'delay_seconds':True}]:
            req=self.req();req['execution_policy']['provider_outage_recovery'].update(change)
            with self.assertRaises(ContractError):configuration(req)

    def test_recovery_request_cap_is_shared_across_validation_attempts(self):
        text,calls,waits,states,record,checkpoint=self.exercise(99,stage_retries=1)
        self.assertIsNone(text);self.assertEqual(len(calls),9)
        self.assertEqual(record['state'],'awaiting_provider_resume')
    def test_retry_after_longer_than_deadline_is_not_shortened(self):
        with tempfile.TemporaryDirectory() as d,patch('storyforge.runtime.worker_timeout_seconds',return_value=540),patch('storyforge.provider_recovery.time.sleep',side_effect=AssertionError('Do not retry before provider cooldown')):
            self.assertFalse(wait_to_retry([HostedError('Google HTTP 429',retry_after=3600)],d,'writer_beat',1,configuration(self.req())))
            self.assertGreaterEqual(load(Path(d)/'provider-recovery.json')['delay_seconds'],3600)
