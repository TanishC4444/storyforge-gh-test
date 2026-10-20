import io,json,os,tempfile,time,unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
from storyforge.tracking import tracked_stage,event,heartbeat,report

class TrackingTests(unittest.TestCase):
    def test_success_records_events_summary_and_live_heartbeat(self):
        @tracked_stage
        def sample(task,source,out):
            event('model_start','Model begins',model='fixture')
            with heartbeat('Waiting on test model',interval=.01):time.sleep(.035)
            event('validated','Validated fixture')
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()) as output:
            root=Path(d)
            with patch.dict(os.environ,{'GITHUB_STEP_SUMMARY':str(root/'summary.md')}):sample('writer',root/'in',root/'out')
            state=json.loads((root/'out/status.json').read_text())
            self.assertEqual(state['status'],'success')
            self.assertEqual(state['model_calls_started'],1)
            self.assertEqual(state['model_calls_validated'],1)
            self.assertIn('Waiting on test model',output.getvalue())
            self.assertIn('| Elapsed | Phase | Detail |',(root/'summary.md').read_text())
    def test_failure_preserves_exact_error(self):
        @tracked_stage
        def sample(task,source,out):raise ValueError('Duplicate world_rules; character_depth missing')
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            root=Path(d)
            with self.assertRaisesRegex(ValueError,'Duplicate'):sample('review',root/'in',root/'out')
            state=json.loads((root/'out/status.json').read_text())
            self.assertEqual(state['status'],'failure')
            self.assertIn('character_depth missing',state['error'])
    def test_report_handles_failure_before_task_started(self):
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()) as output:
            with patch.dict(os.environ,{'TASK_RESULT':'failure'}):report(Path(d)/'out')
            self.assertIn('Task not reached',output.getvalue())
    def test_generated_workflows_publish_status_and_artifact_links(self):
        root=Path(__file__).resolve().parents[1]
        for name in ['story','troy']:
            text=(root/'.github/workflows'/f'{name}.yml').read_text()
            self.assertIn('Job status and artifact link',text)
            self.assertIn('steps.artifact.outputs.artifact-url',text)
            self.assertIn('PYTHONUNBUFFERED: 1',text)
