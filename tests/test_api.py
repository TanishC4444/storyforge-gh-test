"""HTTP API: mode catalog vs workflow YAML, input building, demo flow, GitHub backend over a mock transport."""
import io
import json
import time
import unittest
import zipfile
from pathlib import Path

try:
    import httpx
    from fastapi.testclient import TestClient
    import yaml
except ImportError:  # the API is an optional extra: pip install -e '.[api,test]'
    httpx = None

ROOT = Path(__file__).resolve().parents[1]
P = '/api/v1'
DEMO = {'Authorization': 'Bearer demo'}


def workflow_inputs(name):
    data = yaml.safe_load((ROOT / '.github/workflows' / name).read_text())
    return (data.get('on') or data.get(True))['workflow_dispatch']['inputs']


@unittest.skipIf(httpx is None, 'API extra not installed')
class ModeCatalogTest(unittest.TestCase):
    def test_inputs_match_workflows(self):
        from storyforge.api.modes import MANAGED_INPUTS, MODES
        api_only = {'strategy'}
        for mode in MODES.values():
            declared = workflow_inputs(mode.workflow)
            for spec in mode.inputs:
                if spec.name in api_only:
                    continue
                self.assertIn(spec.name, declared, f'{mode.id}.{spec.name} is not a {mode.workflow} input')
                actual = declared[spec.name]
                self.assertEqual(spec.type, actual.get('type', 'string'), f'{mode.id}.{spec.name} type')
                if spec.type == 'choice':
                    self.assertEqual(spec.options, [str(o) for o in actual['options']], f'{mode.id}.{spec.name} options')
            for name in MANAGED_INPUTS[mode.workflow]:
                self.assertIn(name, declared, f'managed input {name} missing from {mode.workflow}')

    def test_openapi_snapshot_is_current(self):
        from storyforge.api.app import app
        # Compare routes and field names only, so FastAPI version formatting differences don't fail CI.
        def shape(spec):
            routes = sorted((path, method) for path, item in spec['paths'].items() for method in item)
            fields = {name: sorted(schema.get('properties', {})) for name, schema in spec['components']['schemas'].items()}
            return routes, fields
        committed = json.loads((ROOT / 'web/openapi.json').read_text())
        self.assertEqual(shape(committed), shape(app.openapi()), 'Run: python -m scripts.export_openapi')

    def test_titles_carry_request_and_tag(self):
        from storyforge.api.modes import parse_title
        for name in ['living-universe-pipeline.yml', 'planned-parallel.yml']:
            run_name = yaml.safe_load((ROOT / '.github/workflows' / name).read_text())['run-name']
            self.assertIn('${{ inputs.request_file }}', run_name)
            self.assertIn('inputs.queue_tag', run_name)
        self.assertEqual(parse_title('Living | hard-chronology | api-1a2b3c4d'), ('hard-chronology', 'api-1a2b3c4d'))
        self.assertEqual(parse_title('Planned parallel | x | 12'), ('x', '12'))
        self.assertEqual(parse_title('Tests'), (None, None))

    def test_start_inputs(self):
        from storyforge.api.modes import start_inputs
        from storyforge.api.schemas import StartRun
        workflow, inputs = start_inputs(StartRun(mode='sequential', request_file='harbor', inputs={'scene_limit': '4'}), 'api-x')
        self.assertEqual(workflow, 'living-universe-pipeline.yml')
        self.assertEqual(inputs, {'request_file': 'harbor', 'backend': 'fixture', 'scene_limit': '4', 'queue_tag': 'api-x'})
        with self.assertRaisesRegex(ValueError, 'one of'):
            start_inputs(StartRun(mode='sequential', request_file='harbor', inputs={'scene_limit': '9'}), 't')
        for managed in ['queue_tag', 'fresh_run', 'backend']:
            with self.assertRaisesRegex(ValueError, 'Unknown input'):
                start_inputs(StartRun(mode='sequential', request_file='harbor', inputs={managed: 'x'}), 't')
        with self.assertRaisesRegex(ValueError, 'Unknown input'):
            start_inputs(StartRun(mode='parallel', request_file='harbor', inputs={'profile': 'fast'}), 't')

    def test_recovery_inputs(self):
        from storyforge.api.modes import recovery_inputs
        from storyforge.api.schemas import RecoverRun
        workflow, inputs = recovery_inputs(RecoverRun(strategy='rerun', scene='2'), 55, None, None)
        self.assertEqual((workflow, inputs), ('resume-story.yml', {'source_run': '55', 'scene': '2', 'restart_stage': 'auto'}))
        workflow, inputs = recovery_inputs(RecoverRun(inputs={'profile': 'small'}), 55, 'harbor', 'api-y')
        self.assertEqual(workflow, 'living-universe-pipeline.yml')
        self.assertEqual(inputs['fresh_run'], '55')
        self.assertEqual(inputs['profile'], 'small')
        self.assertEqual(inputs['backend'], 'live')
        with self.assertRaisesRegex(ValueError, 'original brief'):
            recovery_inputs(RecoverRun(), 55, None, 'api-y')


@unittest.skipIf(httpx is None, 'API extra not installed')
class DemoApiTest(unittest.TestCase):
    def setUp(self):
        from storyforge.api import demo
        from storyforge.api.app import app
        demo.reset()
        self.demo = demo
        self.client = TestClient(app)

    def test_public_routes(self):
        self.assertEqual(self.client.get(P + '/health').json()['demo_available'], True)
        self.assertEqual([m['id'] for m in self.client.get(P + '/modes').json()], ['sequential', 'parallel', 'recovery'])
        requests = {r['id']: r for r in self.client.get(P + '/requests').json()}
        self.assertEqual(requests['harbor']['chapters'], 3)
        self.assertEqual(self.client.get(P + '/requests/nope').status_code, 404)
        brief = self.client.get(P + '/requests/harbor').json()
        self.assertTrue(self.client.post(P + '/requests/validate', json=brief).json()['valid'])
        self.assertFalse(self.client.post(P + '/requests/validate', json={'project_id': 'x'}).json()['valid'])

    def test_token_required(self):
        self.assertEqual(self.client.get(P + '/runs').status_code, 401)
        self.assertEqual(self.client.get(P + '/runs', headers={'Authorization': 'token abc'}).status_code, 401)

    def test_sample_runs(self):
        runs = {r['id']: r for r in self.client.get(P + '/runs', headers=DEMO).json()['runs']}
        self.assertEqual({k: v['status'] for k, v in runs.items()}, {9001: 'succeeded', 9002: 'failed', 9003: 'failed'})
        story = self.client.get(P + '/runs/9001/story', headers=DEMO).json()
        self.assertEqual([s['id'] for s in story['scenes']], ['ch01-sc01', 'ch02-sc01'])
        self.assertTrue(story['text'])
        scene = self.client.get(P + '/runs/9001/scenes/ch01-sc01', headers=DEMO).json()
        self.assertIn('story', scene['reviews'])
        self.assertEqual(self.client.get(P + '/runs/9001/scenes/zz', headers=DEMO).status_code, 404)
        self.assertTrue(self.client.get(P + '/runs/9001/canon', headers=DEMO).json()['memories'])
        self.assertEqual(self.client.get(P + '/runs/9002/canon', headers=DEMO).status_code, 409)
        parallel = self.client.get(P + '/runs/9002/story', headers=DEMO).json()
        self.assertEqual(len(parallel['scenes']), 4)
        self.assertFalse(parallel['complete'])
        self.assertTrue(self.client.get(P + '/runs/9003', headers=DEMO).json()['recoverable'])
        self.assertFalse(self.client.get(P + '/runs/9002', headers=DEMO).json()['recoverable'])
        archive = self.client.get(P + '/runs/9001/artifacts/readable-story', headers=DEMO)
        self.assertIn('READABLE_DRAFT.txt', zipfile.ZipFile(io.BytesIO(archive.content)).namelist())

    def _finish(self, run_id):
        run = self.demo.store().runs[run_id]
        run.started -= run.duration + 1

    def test_start_progress_and_events(self):
        started = self.client.post(P + '/runs', headers=DEMO, json={'mode': 'parallel', 'request_file': 'hard-chronology'})
        self.assertEqual(started.status_code, 202)
        run_id = started.json()['run_id']
        tag = started.json()['tracking_tag']
        self.assertEqual([r['id'] for r in self.client.get(P + '/runs', headers=DEMO, params={'tag': tag}).json()['runs']], [run_id])
        self.assertIn(self.client.get(P + f'/runs/{run_id}', headers=DEMO).json()['status'], {'queued', 'running'})
        self.assertEqual(self.client.get(P + f'/runs/{run_id}/story', headers=DEMO).status_code, 404)
        self._finish(run_id)
        with self.client.stream('GET', P + f'/runs/{run_id}/events', headers=DEMO) as stream:
            body = stream.read().decode()
        self.assertIn('event: run', body)
        self.assertTrue(body.rstrip().endswith('data: {}'))
        self.assertEqual(json.loads(body.split('data: ', 1)[1].split('\n', 1)[0])['status'], 'succeeded')
        self.assertEqual(self.client.post(P + '/runs', headers=DEMO, json={'mode': 'sequential', 'request_file': 'missing'}).status_code, 404)

    def test_cancel(self):
        run_id = self.client.post(P + '/runs', headers=DEMO, json={'mode': 'sequential', 'request_file': 'harbor'}).json()['run_id']
        self.assertEqual(self.client.post(P + f'/runs/{run_id}/cancel', headers=DEMO).status_code, 202)
        self.assertEqual(self.client.get(P + f'/runs/{run_id}', headers=DEMO).json()['status'], 'cancelled')
        self.assertEqual(self.client.post(P + '/runs/9001/cancel', headers=DEMO).status_code, 409)

    def test_recovery(self):
        self.assertEqual(self.client.post(P + '/runs/9001/recover', headers=DEMO).status_code, 409)
        self.assertEqual(self.client.post(P + '/runs/9002/recover', headers=DEMO).status_code, 409)
        fresh = self.client.post(P + '/runs/9003/recover', headers=DEMO, json={'strategy': 'fresh'}).json()
        self.assertEqual(fresh['mode'], 'sequential')
        rerun = self.client.post(P + '/runs/9003/recover', headers=DEMO, json={'strategy': 'rerun'}).json()
        self.assertEqual((rerun['mode'], rerun['tracks_run_id']), ('recovery', 9003))
        original = self.client.get(P + '/runs/9003', headers=DEMO).json()
        self.assertEqual(original['attempt'], 2)
        self.assertEqual(self.client.get(P + f'/runs/{rerun["run_id"]}/story', headers=DEMO).status_code, 409)


def _zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


@unittest.skipIf(httpx is None, 'API extra not installed')
class GitHubBackendTest(unittest.TestCase):
    TOKEN = 'ghp_secretvalue'

    def setUp(self):
        import tempfile
        from storyforge.api.config import Settings
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(cache_dir=Path(self.tmp.name))
        self.calls = []
        self.dispatch_status = 200
        snapshot = json.loads((ROOT / 'storyforge/api/demo_data/sequential/readable-story/canon/snapshot.json').read_text())
        snapshot['accepted'][1]['quality_status'] = 'needs_review'
        self.story_zip = _zip({'READABLE_DRAFT.txt': 'Prose.', 'reading-status.json': '{}', 'canon/snapshot.json': json.dumps(snapshot)})

    def tearDown(self):
        self.tmp.cleanup()

    def handler(self, request):
        self.calls.append((request.method, request.url.path, request.headers.get('authorization')))
        path = request.url.path
        base = '/repos/TanishC4444/storyforge-gh-test'
        run = {'id': 77, 'path': '.github/workflows/living-universe-pipeline.yml', 'display_title': 'Living | harbor | api-abcd1234',
               'status': 'completed', 'conclusion': 'success', 'run_attempt': 1, 'created_at': '2026-10-24T10:00:00Z',
               'updated_at': '2026-10-24T11:00:00Z', 'html_url': 'https://github.com/x'}
        if path == '/user':
            return httpx.Response(200, json={'login': 'octo'})
        if path == base:
            return httpx.Response(200, json={'permissions': {'push': True}})
        if path == f'{base}/actions/runs/77':
            return httpx.Response(200, json=run)
        if path == f'{base}/actions/runs/404':
            return httpx.Response(404, json={'message': 'Not Found'})
        if path == f'{base}/actions/runs/77/jobs':
            jobs = [{'id': 1, 'name': 'Scene 1 / Commit scene 1 only after literary and factual gates', 'status': 'completed', 'conclusion': 'success'},
                    {'id': 2, 'name': 'Scene 2 / Commit scene 2 only after literary and factual gates', 'status': 'completed', 'conclusion': 'skipped'}]
            return httpx.Response(200, json={'total_count': 2, 'jobs': jobs})
        if path == f'{base}/actions/runs/77/artifacts':
            items = [{'id': 5, 'name': 'readable-story', 'size_in_bytes': 10, 'expired': False},
                     {'id': 3, 'name': 'readable-story', 'size_in_bytes': 10, 'expired': False}]
            return httpx.Response(200, json={'total_count': 2, 'artifacts': items})
        if path == f'{base}/actions/artifacts/5/zip':
            return httpx.Response(302, headers={'Location': 'https://blob.example/artifact.zip'})
        if request.url.host == 'blob.example':
            return httpx.Response(200, content=self.story_zip)
        if path.endswith('/dispatches'):
            body = json.loads(request.content)
            self.calls.append(('dispatch', body))
            if self.dispatch_status == 422 and 'return_run_details' in body:
                return httpx.Response(422, json={'message': 'Invalid request: return_run_details is not permitted'})
            if self.dispatch_status == 422:
                return httpx.Response(204)
            return httpx.Response(200, json={'workflow_run_id': 88})
        if path.endswith('/actions/workflows/living-universe-pipeline.yml/runs'):
            return httpx.Response(200, json={'workflow_runs': [run]})
        return httpx.Response(500, json={'message': f'unexpected {path}'})

    def backend(self):
        from storyforge.api.github import GitHubClient
        from storyforge.api.service import GitHubBackend
        client = GitHubClient(self.TOKEN, self.settings.repo, transport=httpx.MockTransport(self.handler))
        return GitHubBackend(self.settings, self.TOKEN, client=client)

    def test_completed_run_with_warnings(self):
        api = self.backend()
        detail = api.get_run(77)
        self.assertEqual(detail.status, 'succeeded_with_warnings')
        self.assertEqual(detail.request_file, 'harbor')
        self.assertEqual(detail.tracking_tag, 'api-abcd1234')
        self.assertEqual((detail.progress.accepted_scenes, detail.progress.total_scenes), (2, 2))
        self.assertEqual(api.story(77).scenes[1].status, 'needs_review')
        # Newest artifact of a repeated name wins; the blob host never sees the token.
        blob = [c for c in self.calls if c[1] == '/artifact.zip']
        self.assertEqual(blob, [('GET', '/artifact.zip', None)])
        self.assertTrue((self.settings.cache_dir / '5.zip').exists())

    def test_auth_and_errors(self):
        from storyforge.api.service import NotFound
        api = self.backend()
        self.assertEqual(api.auth_check().login, 'octo')
        self.assertTrue(api.auth_check().can_dispatch)
        with self.assertRaises(NotFound) as caught:
            api.get_run(404)
        self.assertNotIn(self.TOKEN, str(caught.exception))

    def test_dispatch(self):
        from storyforge.api.schemas import StartRun
        started = self.backend().start_run(StartRun(mode='sequential', request_file='harbor'))
        self.assertEqual(started.run_id, 88)
        body = next(c[1] for c in self.calls if c[0] == 'dispatch')
        self.assertEqual(body['ref'], 'main')
        self.assertEqual(body['inputs']['queue_tag'], started.tracking_tag)

    def test_dispatch_fallback_finds_run_by_tag(self):
        from storyforge.api import modes
        from storyforge.api.schemas import StartRun
        self.dispatch_status = 422
        original = modes.new_tag
        import storyforge.api.service as service
        service.new_tag = lambda: 'api-abcd1234'
        try:
            started = self.backend().start_run(StartRun(mode='sequential', request_file='harbor'))
        finally:
            service.new_tag = original
        self.assertEqual(started.run_id, 77)
        bodies = [c[1] for c in self.calls if c[0] == 'dispatch']
        self.assertEqual(['return_run_details' in b for b in bodies], [True, False])

    def test_recover_rejects_successful_run(self):
        from storyforge.api.schemas import RecoverRun
        from storyforge.api.service import Conflict
        with self.assertRaises(Conflict):
            self.backend().recover_run(77, RecoverRun())


if __name__ == '__main__':
    unittest.main()
