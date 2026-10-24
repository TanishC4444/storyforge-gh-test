"""Boundary, brief/mode and HTTP failure regressions found by the API stress pass."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
try:
    import httpx
    from fastapi.testclient import TestClient
    from storyforge.api.app import app,settings
    from storyforge.api.config import Settings
    from storyforge.api.service import GitHubBackend,supported_modes,checked_start
    from storyforge.api.github import GitHubClient,GitHubError
    from storyforge.api.schemas import StartRun
except ImportError:
    httpx=None

P='/api/v1';AUTH={'Authorization':'Bearer demo'};ROOT=Path(__file__).resolve().parents[1]

@unittest.skipIf(httpx is None,'API extra not installed')
class APIStressTests(unittest.TestCase):
    def setUp(self):self.client=TestClient(app,raise_server_exceptions=False)
    def test_each_brief_field_rejects_bad_shapes_without_server_errors(self):
        base=json.loads((ROOT/'examples/hard-chronology.json').read_text())
        for key in base:
            for value in [None,False,0,'bad',[],{},[{}]]:
                with self.subTest(field=key,value=value):
                    brief=copy.deepcopy(base);brief[key]=value
                    response=self.client.post(P+'/requests/validate',json=brief)
                    self.assertLess(response.status_code,500)
        for field in ['performance','execution_policy','api_roles']:
            brief=copy.deepcopy(base);brief[field]=None
            result=self.client.post(P+'/requests/validate',json=brief)
            self.assertFalse(result.json()['valid']);self.assertIn('object',result.json()['error'])
    def test_paths_auth_filters_and_unknown_fields_are_rejected(self):
        for suffix in ['', '/story','/canon','/artifacts','/events','/scenes/x']:
            for invalid in ['0','-1','abc','1.2']:
                with self.subTest(suffix=suffix,id=invalid):
                    self.assertEqual(self.client.get(P+'/runs/'+invalid+suffix,headers=AUTH).status_code,422)
        for limit in [-1,0,51,'NaN']:
            self.assertEqual(self.client.get(P+'/runs',params={'limit':limit},headers=AUTH).status_code,422)
        self.assertEqual(self.client.get(P+'/runs?status=bogus',headers=AUTH).status_code,422)
        for body in [{},{'mode':'recovery','request_file':'hard-chronology'}, {'mode':'sequential','request_file':'hard-chronology','typo':True}]:
            self.assertEqual(self.client.post(P+'/runs',headers=AUTH,json=body).status_code,422)
        for token in ['', 'Basic demo','Bearer ','Token demo']:
            self.assertEqual(self.client.get(P+'/auth/check',headers={'Authorization':token}).status_code,401)
    def test_catalog_supports_only_actual_workflow_compatible_inputs(self):
        listed=self.client.get(P+'/requests').json()
        for brief in listed:
            raw=self.client.get(P+'/requests/'+brief['id']).json()
            self.assertEqual(brief['supported_modes'],supported_modes(raw))
        self.assertNotIn('sequential',next(r for r in listed if r['id']=='harbor')['supported_modes'])
        with patch.object(GitHubBackend,'_dispatch') as dispatch:
            api=GitHubBackend(Settings(),'placeholder')
            try:
                with self.assertRaises(ValueError):api.start_run(StartRun(mode='sequential',request_file='harbor'))
                with self.assertRaises(ValueError):api.start_run(StartRun(mode='parallel',request_file='living-scale-practice'))
                dispatch.assert_not_called()
            finally:api.close()
        for mode,brief in [('sequential','living-scale-practice'),('parallel','hard-chronology')]:
            for invalid in [{'scene_limit':'9'},{'unknown':'x'},{'backend':'live'},{'fresh_run':'123'}]:
                response=self.client.post(P+'/runs',headers=AUTH,json={'mode':mode,'request_file':brief,'inputs':invalid})
                self.assertEqual(response.status_code,422,response.text)
        body=checked_start(Settings(),StartRun(mode='sequential',request_file='stress-fairytale'))
        total=json.loads((ROOT/'examples/stress-fairytale.json').read_text())['chapters']
        self.assertLessEqual(int(body.inputs['scene_limit']),total)
        for values in [{'scene_limit':'4'},{'resume_run':'nonsense'}]:
            response=self.client.post(P+'/runs',headers=AUTH,json={'mode':'sequential','request_file':'living-scale-practice','inputs':values})
            self.assertEqual(response.status_code,422)
    def test_browser_cors_and_demo_disabled(self):
        response=self.client.options(P+'/runs',headers={'Origin':'http://127.0.0.1:8080','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.headers['access-control-allow-origin'],'http://127.0.0.1:8080')
        response=self.client.options(P+'/runs',headers={'Origin':'https://untrusted.invalid','Access-Control-Request-Method':'POST'})
        self.assertNotIn('access-control-allow-origin',response.headers)
        app.dependency_overrides[settings]=lambda:Settings(allow_demo=False)
        try:self.assertEqual(self.client.get(P+'/runs',headers=AUTH).status_code,401)
        finally:app.dependency_overrides.clear()
    def test_provider_failures_are_bounded_and_do_not_expose_token(self):
        for status in [401,403,404,429,500,502,503]:
            transport=httpx.MockTransport(lambda r:httpx.Response(status,json={'message':'upstream unavailable'}))
            api=GitHubClient('placeholder','example/repo',transport=transport)
            with self.assertRaises(GitHubError) as caught:api.user()
            self.assertEqual(caught.exception.status,status);api.close()
        def timeout(req):raise httpx.ReadTimeout('timeout',request=req)
        api=GitHubClient('placeholder','example/repo',transport=httpx.MockTransport(timeout))
        with self.assertRaises(GitHubError) as caught:api.user()
        self.assertEqual(caught.exception.status,502);api.close()
        api=GitHubClient('placeholder','example/repo',transport=httpx.MockTransport(lambda r:httpx.Response(200,text='<html>proxy error</html>')))
        with self.assertRaises(GitHubError) as caught:api.user()
        self.assertEqual(caught.exception.status,502);api.close()
    def test_pagination_fetches_more_than_hundred_jobs_and_artifacts(self):
        def handler(req):
            page=int(req.url.params['page']);key='jobs' if req.url.path.endswith('jobs') else 'artifacts'
            rows=[{'id':i} for i in range((page-1)*100,min(page*100,237))]
            return httpx.Response(200,json={'total_count':237,key:rows})
        api=GitHubClient('placeholder','example/repo',transport=httpx.MockTransport(handler))
        self.assertEqual(len(api.jobs(1)),237);self.assertEqual(len(api.artifacts(1)),237);api.close()

    def test_legacy_recovery_export_restores_missing_approved_prefix(self):
        from storyforge.api.artifacts import sequential_story,sequential_scene
        snapshot={'accepted':[{'id':f'ch{i:02}-sc01','quality_status':'reviewed','prose':f'Unique approved passage {i}.'} for i in range(1,4)],'plan':{'scenes':[{'id':f'ch{i:02}-sc01'} for i in range(1,5)]}}
        text='CLASSIC UNIVERSE EXPANSION\n\ns03 | reviewed\n\nUnique approved passage 3.\n\n* * *\n\ns04 | unreviewed\n\nRetained unfinished fourth scene.'
        files={'canon/snapshot.json':json.dumps(snapshot).encode(),'READABLE_DRAFT.txt':text.encode()}
        class Reader:
            def files(self,name):return files if name=='readable-story' else None
        result=sequential_story(1,Reader())
        self.assertEqual(len(result.scenes),4)
        for i in range(1,4):self.assertEqual(result.text.count(f'Unique approved passage {i}.'),1)
        self.assertLess(result.text.index('passage 1'),result.text.index('passage 2'))
        self.assertIn('Retained unfinished fourth scene.',result.text)
        draft=sequential_scene(Reader(),'ch04-sc01');self.assertEqual(draft.status,'unreviewed')
        self.assertEqual(draft.reviews,{})
    def test_collector_recovers_approved_scenes_without_preview_artifacts(self):
        from storyforge.expansion import collect
        from storyforge.storage import save
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);accepted=[{'id':f'ch{i:02}-sc01','quality_status':'reviewed','prose':f'Approved scene {i}.'} for i in range(1,5)]
            save(p/'source/s04_accept/snapshot.json',{'accepted':accepted})
            sections=collect(p/'source',p/'out')
            self.assertEqual(len(sections),4)
            self.assertTrue(all(status=='reviewed' for _,_,status in sections))

    def test_corrupt_artifact_is_a_gateway_error_and_cache_can_recover(self):
        import io,zipfile
        from storyforge.api.artifacts import InvalidArtifact,_json
        from storyforge.api.service import GitHubReader
        from storyforge.api.demo import DemoBackend
        with patch.object(DemoBackend,'story',side_effect=InvalidArtifact('Saved artifact is invalid')):
            response=self.client.get(P+'/runs/9001/story',headers=AUTH)
            self.assertEqual(response.status_code,502)
        with self.assertRaises(InvalidArtifact):_json({'snapshot.json':b'[]'},'snapshot.json')
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:archive.writestr('prose.txt','Recovered text')
        class Client:
            downloads=0
            def artifacts(self,run):return [{'id':1,'name':'story','expired':False}]
            def artifact_zip(self,id):
                self.downloads+=1
                return b'corrupt' if self.downloads==1 else data.getvalue()
        with tempfile.TemporaryDirectory() as folder:
            reader=GitHubReader(Client(),1,Path(folder))
            with self.assertRaises(InvalidArtifact):reader.files('story')
            self.assertFalse((Path(folder)/'1.zip').exists())
            self.assertEqual(reader.files('story')['prose.txt'],b'Recovered text')

    def test_fresh_recovery_inherits_length_and_backend_and_cannot_skip_failure(self):
        from storyforge.api.service import checked_recovery,Conflict
        from storyforge.api.schemas import RecoverRun
        class Reader:
            def files(self,name):
                if name=='story-recovery':return {'recovery.json':b'{"total_scenes":4,"resume_scene":4}'}
                if name=='quickstart':return {'snapshot.json':b'{"backend":"fixture"}'}
        body=checked_recovery(Settings(),RecoverRun(),'hard-chronology',Reader())
        self.assertEqual(body.inputs['scene_limit'],'4');self.assertEqual(body.backend,'fixture')
        with self.assertRaises(Conflict):checked_recovery(Settings(),RecoverRun(backend='live'),'hard-chronology',Reader())
        with self.assertRaises(ValueError):checked_recovery(Settings(),RecoverRun(inputs={'scene_limit':'2'}),'hard-chronology',Reader())

    def test_simultaneous_cold_start_uses_one_demo_store_and_unique_run_ids(self):
        import time
        from concurrent.futures import ThreadPoolExecutor
        from storyforge.api import demo
        original=demo.DemoStore;calls=[]
        def slow_init():
            calls.append(True);time.sleep(.02);return original()
        demo.reset()
        with patch.object(demo,'DemoStore',side_effect=slow_init):
            with ThreadPoolExecutor(max_workers=16) as pool:stores=list(pool.map(lambda _:demo.store(),range(32)))
        self.assertEqual(len(calls),1);self.assertEqual(len({id(s) for s in stores}),1)
        with ThreadPoolExecutor(max_workers=16) as pool:
            runs=list(pool.map(lambda _:demo.store().create(mode='sequential',request_file='hard-chronology',outcome='succeeded',data='sequential'),range(32)))
        self.assertEqual(len({r.id for r in runs}),32)
