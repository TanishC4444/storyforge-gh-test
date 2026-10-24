import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch,MagicMock
import zipfile
from fastapi.testclient import TestClient
from storyforge.api.app import app
from storyforge.api.studio_runtime import StudioRuntime
from storyforge.api.studio_routes import get_runtime
from storyforge.api import workflow_browser as wf
from storyforge import creative_studio
from storyforge.storage import save


class UnifiedStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        story=self.root/'outputs'/'sample';story.mkdir(parents=True);(story/'story.txt').write_text('The Shore\nA smith works by the sea.')
        workflows=self.root/'.github'/'workflows';workflows.mkdir(parents=True)
        (workflows/'sample.yml').write_text("name: All features\non:\n  workflow_dispatch:\n    inputs:\n      backend:\n        type: choice\n        options: [fixture, live]\n        default: fixture\njobs:\n  idea:\n    runs-on: ubuntu-latest\n    steps: []\n  revise:\n    needs: idea\n    runs-on: ubuntu-latest\n    steps: []\n")
        self.runtime=StudioRuntime(self.root);self.addCleanup(self.runtime.pool.shutdown)
        app.dependency_overrides[get_runtime]=lambda:self.runtime
        self.addCleanup(app.dependency_overrides.clear)
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.headers={'X-Storyforge-Token':self.runtime.token}

    def post(self,path,body):return self.client.post(path,json=body,headers=self.headers)

    def result(self,ident):
        for _ in range(200):
            value=self.client.get('/api/job/'+ident).json()
            if value['status'] in ('complete','failed','interrupted'):return value
            time.sleep(.01)
        self.fail('Background job did not complete')

    def test_every_workspace_is_served_by_fastapi(self):
        for route in ('/','/writing','/ideas','/images','/music','/production','/workflows','/outputs','/testing','/connections','/console'):
            response=self.client.get(route);self.assertEqual(response.status_code,200,route);self.assertIn('Unified workspace',response.text)
        self.assertEqual(self.client.get('/legacy/js/app.js').status_code,200)
        docs=self.client.get('/docs')
        self.assertEqual(docs.status_code,200)
        self.assertIn('requestInterceptor',docs.text)
        self.assertIn(self.runtime.token,docs.text)
        self.assertEqual(self.client.get('/api/studio/features').json()['framework'],'FastAPI')
        self.assertEqual(self.client.get('/api/studio/features').json()['workflow_count'],1)
        self.assertNotIn('http://localhost:8766',self.client.get('/').text)

    def test_projects_switch_and_outputs_are_isolated(self):
        before=self.client.get('/api/studio/projects').json()['current']
        created=self.post('/api/studio/projects',{'title':'New project','text':'A new story'});self.assertEqual(created.status_code,200)
        self.assertNotEqual(created.json()['id'],before)
        files=self.client.get('/api/studio/outputs').json()['files'];self.assertIn('story.txt',[f['path'] for f in files])
        self.assertIn('A new story',self.client.get('/api/studio/output',params={'path':'story.txt'}).text)
        self.assertEqual(self.client.get('/api/studio/output',params={'path':'../../AGENTS.md'}).status_code,422)
        self.assertEqual(self.post('/api/studio/project/select',{'id':before}).status_code,200)
        self.assertIn('smith',self.client.get('/api/studio/output',params={'path':'story.txt'}).text)

    def test_csrf_origin_and_local_host_protection(self):
        self.assertEqual(self.client.post('/api/studio/projects',json={'title':'x','text':'x'}).status_code,403)
        self.assertEqual(self.client.post('/api/studio/projects',json={'title':'x','text':'x'},headers={**self.headers,'Origin':'https://other.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/studio/projects',headers={'Host':'evil.example'}).status_code,403)

    def test_creative_job_and_adoption_preserve_source(self):
        current=self.runtime.folder()
        def fake(folder,raw,progress):
            value={'id':'a'*24,'status':'complete','result':{'title':'Revised idea','text':'A different premise'}}
            save(folder/'creative'/('a'*24+'.json'),value);return value
        with patch('storyforge.api.studio_routes.creative_studio.run',side_effect=fake):
            response=self.post('/api/studio/creative',{'operation':'ideas','brief':'A sea story'})
            value=self.result(response.json()['job_id']);self.assertEqual(value['status'],'complete')
        response=self.post('/api/studio/creative/'+'a'*24+'/use-as-project',{})
        self.assertEqual(response.status_code,200)
        self.assertIn('smith', (current/'story.txt').read_text())
        self.assertIn('different premise',self.client.get('/api/studio/output',params={'path':'story.txt'}).text)

    def test_legacy_image_and_production_job_response_adapters(self):
        with patch('storyforge.api.studio_routes.image_studio.prepare_prompt',return_value={'prompt':'A shoreline','title':'Coast'}):
            response=self.post('/api/images/prepare',{'kind':'scene','enhance':False})
            result=self.result(response.json()['job_id']);self.assertEqual(result['prompt_result']['prompt'],'A shoreline')
        with patch('storyforge.api.studio_routes.create_plan',return_value={'id':'b'*24}):
            response=self.post('/api/generate',{'config':{'start_date':'2026-11-02'}})
            self.assertEqual(self.result(response.json()['job_id'])['plan_id'],'b'*24)

    def test_local_audio_generation_and_project_boundary(self):
        response=self.post('/api/studio/music',{'mode':'ambience','seconds':5})
        result=self.result(response.json()['job_id']);self.assertEqual(result['status'],'complete')
        ident=result['result']['job']['id']
        response=self.client.get('/media/music/'+ident+'/content');self.assertEqual(response.status_code,200);self.assertTrue(response.content.startswith(b'RIFF'))
        self.post('/api/studio/projects',{'title':'Different','text':'Other story'})
        self.assertEqual(self.client.get('/api/studio/music/'+ident).status_code,422)

    def test_vultr_submission_status_and_no_duplicate_media_calls(self):
        ident='music_'+'c'*24
        fake=MagicMock();fake.create.return_value={'id':ident,'status':'pending'};fake.json.return_value={'id':ident,'status':'completed','outputs':[]}
        with patch('storyforge.api.studio_routes.Vultr',return_value=fake):
            response=self.post('/api/studio/music',{'mode':'score','seconds':30});self.assertEqual(self.result(response.json()['job_id'])['status'],'complete')
            self.assertEqual(self.client.get('/api/studio/music/'+ident).json()['job']['status'],'completed')
            self.client.get('/api/studio/music/'+ident)
            self.assertEqual(fake.create.call_count,1);self.assertEqual(fake.json.call_count,1)
        self.assertEqual(len(self.client.get('/api/studio/music').json()['tracks']),1)

    def test_all_workflow_schema_and_dispatch_validation(self):
        catalog=self.client.get('/api/studio/workflows').json();self.assertEqual(catalog['workflows'][0]['job_count'],2)
        definition=self.client.get('/api/studio/workflows/sample.yml').json();self.assertEqual(definition['jobs'][1]['needs'],['idea'])
        api=MagicMock()
        with patch('storyforge.api.workflow_browser.workflow',return_value=definition):
            with self.assertRaises(ValueError):wf.dispatch(api,'sample.yml','main',{'backend':'made-up'})
            api.dispatch.assert_not_called()
            result=wf.dispatch(api,'sample.yml','main',{'backend':'fixture'});self.assertEqual(result['inputs']['backend'],'fixture')

    def test_artifact_preview_bounds_no_disk_extraction(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:archive.writestr('nested/STORY.txt','A story');archive.writestr('../odd-name.txt','Still inside the archive')
        data=stream.getvalue();self.assertEqual(len(wf.zip_files(data)),2)
        self.assertEqual(wf.zip_files(data,'nested/STORY.txt'),b'A story')
        api=MagicMock();api.repo='example/repo'
        with patch('storyforge.api.workflow_browser.all_artifacts',return_value=[{'id':1,'expired':True}]):
            with self.assertRaisesRegex(ValueError,'expired'):wf.artifact(api,4,1,self.root)
            api.http.stream.assert_not_called()

    def test_import_artifact_is_not_shadowed_by_run_actions(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:archive.writestr('STORY.txt','Imported story')
        with patch('storyforge.api.studio_routes.workflows.client',return_value=MagicMock()),patch('storyforge.api.studio_routes.workflows.artifact',return_value=stream.getvalue()):
            response=self.post('/api/studio/history/123/import',{'artifact_id':7,'path':'STORY.txt','title':'Prior run'})
        self.assertEqual(response.status_code,200,response.text);self.assertIn('project_id',response.json())

    def test_persisted_inflight_jobs_become_interrupted(self):
        path=self.runtime.job_dir/('f'*24+'.json');save(path,{'id':'f'*24,'status':'running','project_id':'x','created_at':'2026-10-24'})
        other=StudioRuntime(self.root)
        try:self.assertEqual(other.jobs['f'*24]['status'],'interrupted')
        finally:other.pool.shutdown()

    def test_connections_never_echo_or_persist_secrets(self):
        import os
        with patch.dict(os.environ,{},clear=False):
            response=self.post('/api/studio/connections',{'vultr_key':'do-not-leak','serp_key':'search-secret'})
            self.assertEqual(response.status_code,200);self.assertNotIn('do-not-leak',response.text)
            self.assertNotIn('search-secret',str(self.runtime.jobs))
        self.assertEqual(self.post('/api/studio/connections',{'arbitrary_environment':'bad'}).status_code,422)


class CreativeLoopTests(unittest.TestCase):
    def test_bounded_idea_review_revision_loop_preserves_evidence(self):
        import os
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'VULTR_INFERENCE_API_KEY':'test-key'}):
            root=Path(folder)
            values=[{'title':'Idea','text':'An initial premise'},{'pass':False,'summary':'Needs stakes','issues':[{'fix':'Add a consequence'}]},{'title':'Better idea','text':'An improved premise'}]
            responses=[{'choices':[{'message':{'content':json.dumps(v)}}],'usage':{}} for v in values]
            with patch('storyforge.creative_studio.request_json',side_effect=responses) as request:
                record=creative_studio.run(root,{'operation':'loop','loop_mode':'ideas','brief':'A meaningful choice','use_story':False,'rounds':1})
            self.assertEqual(request.call_count,3);self.assertEqual([s['stage'] for s in record['steps']],['Ideas','Review','Revise'])
            self.assertFalse(record['review_matches_result']);self.assertEqual(record['result']['text'],'An improved premise')
            self.assertTrue((root/'creative'/(record['id']+'.txt')).is_file())

    def test_passing_review_stops_without_extra_revision(self):
        import os
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'VULTR_INFERENCE_API_KEY':'test-key'}):
            response={'choices':[{'message':{'content':json.dumps({'pass':True,'issues':[]})}}]}
            with patch('storyforge.creative_studio.request_json',return_value=response) as request:
                record=creative_studio.run(Path(folder),{'operation':'loop','text':'Existing candidate','rounds':3,'use_story':False})
            self.assertEqual(request.call_count,1);self.assertTrue(record['review_matches_result'])

if __name__=='__main__':unittest.main()
