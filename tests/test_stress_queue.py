import copy,io,json,tempfile,unittest,urllib.error,zipfile
from pathlib import Path
from unittest.mock import patch
from scripts.stress_queue import Queue,GitHub,validate_suite,verdict,select_cases

ROOT=Path(__file__).resolve().parents[1]

class StressQueueTests(unittest.TestCase):
    def test_targeted_retry_retains_dependency_order_and_reuses_only_the_novel_draft(self):
        suite=select_cases(self.suite(),'ensemble-continuation,ensemble','123')
        validate_suite(suite)
        self.assertEqual([c['id'] for c in suite['cases']],['ensemble','ensemble-continuation'])
        self.assertEqual(suite['cases'][0]['saved_draft_run'],'123');self.assertNotIn('saved_draft_run',suite['cases'][1])
        for cases,run in [('ensemble-continuation',''),('unknown',''),('ensemble,ensemble',''),('comic','123'),('ensemble','invalid')]:
            with self.subTest(cases=cases,run=run),self.assertRaises(ValueError):select_cases(self.suite(),cases,run)
    def suite(self):return json.loads((ROOT/'examples/stress-suite.json').read_text())
    def run_record(self,case='fairytale',status='completed',conclusion='success'):
        return {'id':12,'head_sha':'tested','status':status,'conclusion':conclusion,'html_url':'https://example.invalid/12','display_title':'Living | stress-'+case+' | tag-'+case}
    def test_all_requests_validate_and_cover_all_formats_lengths_and_cast(self):
        suite=validate_suite(self.suite());cases=suite['cases']
        self.assertEqual(len({c['medium'] for c in cases}),6)
        self.assertEqual(sum(c['scenes'] for c in cases),20)
        self.assertEqual(max(c['cast'] for c in cases),16)
        self.assertGreaterEqual(len({c['words_per_scene'] for c in cases}),4)
        req=json.loads((ROOT/'examples/stress-ensemble.json').read_text())
        participants={cid for s in req['scene_designs'] for cid in s['participants']}
        self.assertEqual(participants,{c['id'] for c in req['characters']})
    def test_bad_resume_order_and_missing_wait_policy_are_rejected(self):
        suite=self.suite();suite['cases'].insert(0,suite['cases'].pop())
        with self.assertRaisesRegex(ValueError,'Resume dependency'):validate_suite(suite)
        suite=self.suite();suite['cases'][0]['scenes']=3
        with self.assertRaisesRegex(ValueError,'scene count'):validate_suite(suite)
        real=json.loads
        def bad_policy(text):
            value=real(text)
            if 'execution_policy' in value:value['execution_policy']['provider_outage_recovery']={}
            return value
        with patch('scripts.stress_queue.json.loads',side_effect=bad_policy):
            with self.assertRaisesRegex(ValueError,'wait buffer'):validate_suite(self.suite())
    def test_green_job_without_exact_complete_audit_is_not_a_pass(self):
        audit={'pass':True,'expected_scenes':2,'scenes':[{'approved':True,'factual_proof_bound':True} for _ in range(2)]}
        self.assertTrue(verdict({'conclusion':'success'},audit,2))
        self.assertFalse(verdict({'conclusion':'failure'},audit,2))
        self.assertFalse(verdict({'conclusion':'success'},{},2))
        self.assertFalse(verdict({'conclusion':'success'},audit,4))
        audit['scenes'][1]['factual_proof_bound']=False
        self.assertFalse(verdict({'conclusion':'success'},audit,2))
    def test_uncertain_dispatch_is_discovered_without_duplicate_post(self):
        case=self.suite()['cases'][0];posts=[];run=self.run_record()
        class API:
            def api(self,path,method='GET',body=None):
                if method=='POST':posts.append(body);raise urllib.error.URLError('Connection lost after dispatch')
                return {'workflow_runs':[run]}
        with tempfile.TemporaryDirectory() as d:
            q=Queue(API(),self.suite(),d,'main','tested','tag',sleep=lambda _:None)
            self.assertEqual(q.dispatch(case,None)['id'],12)
        self.assertEqual(len(posts),1)
    def test_mismatched_revision_stops_queue_with_active_child_available_for_cancel(self):
        run=self.run_record();run['head_sha']='untested'
        class API:
            def api(self,path,method='GET',body=None):return {'workflow_runs':[run]} if method=='GET' else None
        with tempfile.TemporaryDirectory() as d:
            q=Queue(API(),self.suite(),d,'main','tested','tag',sleep=lambda _:None)
            with self.assertRaisesRegex(RuntimeError,'revision'):q.dispatch(self.suite()['cases'][0],None)
            self.assertEqual(q.active,12)
    def test_cases_are_serial_and_independent_failures_do_not_stop_queue(self):
        suite=self.suite();suite['cases']=suite['cases'][:3]+[suite['cases'][-1]]
        events=[]
        with tempfile.TemporaryDirectory() as d:
            q=Queue(None,suite,d,'main','tested','tag')
            def dispatch(case,resume):events.append('dispatch:'+case['id']);return {'id':case['id'],'html_url':'https://example.invalid'}
            def wait(run,minutes):events.append('complete:'+run['id']);return run
            def collect(case,run):return {**case,'run_id':run['id'],'pass':case['id']!='ensemble','status':'failure' if case['id']=='ensemble' else 'success'}
            with patch.object(q,'dispatch',side_effect=dispatch),patch.object(q,'wait',side_effect=wait),patch.object(q,'collect',side_effect=collect):self.assertFalse(q.run())
            report=json.loads((Path(d)/'report.json').read_text())
        self.assertEqual(events,['dispatch:fairytale','complete:fairytale','dispatch:ensemble','complete:ensemble','dispatch:screenplay','complete:screenplay'])
        self.assertEqual(report['cases'][-1]['status'],'blocked_by_failed_checkpoint')
        self.assertTrue(report['complete']);self.assertFalse(report['all_passed'])
    def test_successful_checkpoint_is_given_only_to_its_continuation(self):
        suite=self.suite();suite['cases']=[suite['cases'][1],suite['cases'][-1]];resumes=[]
        with tempfile.TemporaryDirectory() as d:
            q=Queue(None,suite,d,'main','tested','tag')
            def dispatch(case,resume):resumes.append(resume);return {'id':42,'html_url':'https://example.invalid'}
            with patch.object(q,'dispatch',side_effect=dispatch),patch.object(q,'wait',side_effect=lambda run,minutes:run),patch.object(q,'collect',side_effect=lambda case,run:{**case,'run_id':42,'pass':True}):self.assertTrue(q.run())
        self.assertEqual(resumes,[None,42])
    def test_timeout_requires_confirmed_terminal_child_before_continuing(self):
        events=[];clock=[0];run=self.run_record(status='in_progress',conclusion=None)
        class API:
            def api(self,path,method='GET',body=None):
                events.append((path,method));return {**run,'status':'completed','conclusion':'cancelled'} if method=='GET' else None
        def sleep(seconds):clock[0]+=seconds
        with tempfile.TemporaryDirectory() as d:
            q=Queue(API(),self.suite(),d,'main','tested','tag',sleep=sleep,now=lambda:clock[0]);q.active=12
            result=q.wait(run,0)
        self.assertEqual(events[0],('actions/runs/12/cancel','POST'));self.assertEqual(result['conclusion'],'cancelled');self.assertIsNone(q.active)
    def test_artifact_storage_redirect_never_receives_github_credentials(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:z.writestr('episode-audit.json','{}')
        redirect=urllib.error.HTTPError('https://api.github.com/',302,'Found',{'Location':'https://storage.example.invalid/a.zip'},None)
        client=GitHub('owner/repo','DO-NOT-FORWARD')
        with tempfile.TemporaryDirectory() as d,patch('urllib.request.OpenerDirector.open',side_effect=redirect),patch('urllib.request.urlopen',return_value=io.BytesIO(buffer.getvalue())) as fetch:
            client.artifact({'id':1},d)
            self.assertEqual(fetch.call_args.args,('https://storage.example.invalid/a.zip',))
            self.assertEqual((Path(d)/'episode-audit.json').read_text(),'{}')

if __name__=='__main__':unittest.main()
