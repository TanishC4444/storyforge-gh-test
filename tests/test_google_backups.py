import io,json,os,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from storyforge.hosted import GoogleHosted,HostedError,MODELS
from storyforge.worker_policy import policy

class BackupTests(unittest.TestCase):
    def hosted(self,folder):
        with patch.dict(os.environ,{'GEMINI_API_KEYS':'["backup-one","backup-two","primary"]'}):
            return GoogleHosted(folder,'primary')

    def test_deduplicated_pool_rotates_authentication_and_remembers_success(self):
        with tempfile.TemporaryDirectory() as d:
            h=self.hosted(d)
            self.assertEqual(len(h.keys),3)
            with patch.object(h,'_request',side_effect=[HostedError('Google HTTP 401'),HostedError('Google HTTP 403'),{'ok':True},{'ok':True}]) as call:
                self.assertTrue(h.request('model:generateContent',{})['ok'])
                h.request('model:generateContent',{})
                self.assertEqual([c.args[3] for c in call.call_args_list],['primary','backup-one','backup-two','backup-two'])

    def test_quota_failure_does_not_rotate_credentials_or_retry_generation(self):
        with tempfile.TemporaryDirectory() as d:
            h=self.hosted(d)
            with patch.object(h,'_request',side_effect=HostedError('Google HTTP 429')) as call:
                with self.assertRaises(HostedError):h.request('model:generateContent',{})
                self.assertEqual(call.call_count,1);self.assertEqual(h.key_index,0)
            with patch.object(h,'request',side_effect=[{'totalTokens':20},HostedError('Google HTTP 429')]) as call:
                with self.assertRaises(HostedError):h.complete('lite','s','p',100,policy={'timeout':10,'quality_routing':True})
                self.assertEqual(call.call_count,2)
            self.assertTrue(h.circuit('lite'));self.assertNotIn('lite',h.disabled)

    def test_count_tokens_quota_failure_does_not_send_generation(self):
        with tempfile.TemporaryDirectory() as d:
            h=self.hosted(d)
            with patch.object(h,'request',side_effect=HostedError('Google HTTP 429')) as call:
                with self.assertRaises(HostedError):h.complete('lite','s','p',100)
                self.assertEqual(call.call_count,1)
            self.assertTrue(h.circuit('lite'))

    def test_http_errors_redact_body_and_detect_daily_quota(self):
        with tempfile.TemporaryDirectory() as d:
            h=self.hosted(d)
            body={'error':{'status':'RESOURCE_EXHAUSTED','message':'primary secret prompt','details':[{'violations':[{'quotaId':'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]}]}}
            error=urllib.error.HTTPError('https://example.invalid',429,'bad',{},io.BytesIO(json.dumps(body).encode()))
            with patch('urllib.request.urlopen',side_effect=error):
                with self.assertRaises(HostedError) as result:h.request('model:generateContent',{})
            self.assertTrue(result.exception.daily)
            self.assertNotIn('secret',str(result.exception))
            self.assertNotIn('primary',(Path(d)/'requests.jsonl').read_text())
            h.circuit('lite',result.exception)
            health=json.loads((Path(d)/'health.json').read_text())
            self.assertGreater(health['lite']['until'],0)

    def test_pool_format_is_checked_without_echoing_input(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'GEMINI_API_KEYS':'secret-invalid-json'}):
            with self.assertRaisesRegex(HostedError,'JSON array') as result:GoogleHosted(d)
            self.assertNotIn('secret',str(result.exception))

    def test_quality_profile_routes_by_work_and_preserves_legacy(self):
        req={'execution_policy':{'model_routing':'quality'}}
        for role,tier in [('writer','flash'),('global_repair','flash'),('structural_editor','flash36'),('refiner_part','lite'),('memory','lite'),('story_quality','lite'),('memory_quality','gemma')]:
            self.assertEqual(policy(req,role,1200)['tier'],tier)
        self.assertIsNone(policy({'execution_policy':{}},'writer',1200)['tier'])
        self.assertEqual(MODELS['lite'],'gemini-3.5-flash-lite')

    def test_all_workflow_primary_secrets_have_backup_pool(self):
        for path in Path('.github/workflows').glob('*.yml'):
            text=path.read_text()
            self.assertEqual(text.count('GEMINI_API_KEY:'),text.count('GEMINI_API_KEYS:'),str(path))
