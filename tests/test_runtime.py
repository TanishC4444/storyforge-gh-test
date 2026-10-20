import os
from pathlib import Path
import unittest
from unittest.mock import patch
from storyforge.runtime import JOB_TIMEOUT_MINUTES, WORKER_TIMEOUT_SECONDS, worker_timeout_seconds
from storyforge.development import source_paths
from storyforge.editorial import _path

class RuntimeTests(unittest.TestCase):
    def test_every_workflow_job_has_six_hour_budget(self):
        import importlib.util
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('runtime_builder',root/'scripts/build_workflow.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        for workflow in [builder.build(),builder.build(total=4,per_chapter=4,troy=True)]:
            jobs=[line for line in workflow.splitlines() if line.startswith('  ') and not line.startswith('   ') and line.endswith(':')]
            # Exclude workflow_dispatch's enclosing "on" child.
            jobs=[line for line in workflow.split('jobs:\n',1)[1].splitlines() if line.startswith('  ') and not line.startswith('   ') and line.endswith(':')]
            self.assertEqual(workflow.count('    timeout-minutes: 360'),len(jobs))
            self.assertIn('STORY_JOB_DEADLINE=',workflow)
        self.assertEqual(JOB_TIMEOUT_MINUTES,360)
        self.assertEqual(WORKER_TIMEOUT_SECONDS,21300)
    def test_retries_share_remaining_deadline(self):
        with patch.dict(os.environ,{'STORY_JOB_DEADLINE':'12000'}),patch('storyforge.runtime.time.time',return_value=10000):
            self.assertEqual(worker_timeout_seconds(),2000)
        with patch.dict(os.environ,{'STORY_JOB_DEADLINE':'9999'}),patch('storyforge.runtime.time.time',return_value=10000):
            with self.assertRaises(TimeoutError):worker_timeout_seconds()
    def test_no_worker_35_minute_cap(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'storyforge/local_worker.py').read_text()
        self.assertNotIn('timeout=2100',text)
        self.assertIn('signal.setitimer(signal.ITIMER_REAL,worker_timeout_seconds())',text)
        self.assertIn('job_timeout_minutes=JOB_TIMEOUT_MINUTES',text)
    def test_normalized_refinement_paths_are_real(self):
        document={'request':{},'candidate':{'expanded_story_elements':[{'name':'medium_length','value':'Four scenes'}],'refined_prompt':'A premise'}}
        paths=source_paths(document)
        self.assertIn('candidate.expanded_story_elements.0',paths)
        self.assertNotIn('candidate.expanded_story_elements.medium_length',paths)
        for path in paths:_path(document,path)
