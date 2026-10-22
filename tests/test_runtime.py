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
        self.assertIn('signal.setitimer(signal.ITIMER_REAL,inference_timeout_seconds(role))',text)
        self.assertIn('job_timeout_minutes=JOB_TIMEOUT_MINUTES',text)
    def test_normalized_refinement_paths_are_real(self):
        document={'request':{},'candidate':{'expanded_story_elements':[{'name':'medium_length','value':'Four scenes'}],'refined_prompt':'A premise'}}
        paths=source_paths(document)
        self.assertIn('candidate.expanded_story_elements.0',paths)
        self.assertNotIn('candidate.expanded_story_elements.medium_length',paths)
        for path in paths:_path(document,path)

class FullApiWorkflowTests(unittest.TestCase):
    def test_full_api_graph_keeps_every_stage_and_secret(self):
        import importlib.util
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('full_api_builder',root/'scripts/build_workflow.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        workflow=builder.build(total=4,per_chapter=4,troy=True,full_api=True)
        self.assertEqual(workflow,(root/'.github/workflows/troy-full-api.yml').read_text())
        self.assertIn('python -m storyforge.full_flow',workflow)
        self.assertEqual(workflow.count('uses: ./.github/actions/setup-worker'),1)
        self.assertEqual(workflow.count('GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}'),1)
        self.assertIn('timeout-minutes: 360',workflow)
        self.assertNotIn('Restore first two committed scenes',workflow)
        self.assertNotIn('actions/download-artifact',workflow)

    def test_benchmark_brief_is_unchanged_and_has_no_shortcuts(self):
        import json
        from storyforge.contracts import request
        root=Path(__file__).resolve().parents[1]
        req=request(json.loads((root/'examples/troy-full-api.json').read_text()))
        original=json.loads((root/'examples/troy-narrative-api.json').read_text())
        for key in ['premise','characters','scene_designs','world_rules','pov','style','words_per_scene']:
            self.assertEqual(req[key],original[key])
        self.assertFalse(req['performance'].get('single_editorial_pass'))
        self.assertFalse(req['performance'].get('combine_direction'))
        self.assertFalse(req['performance'].get('targeted_edits'))
        self.assertNotIn('resume_seed',req['execution_policy'])
        for role in ['development_editor','scene_designer','director','refiner','architect','writer','humanizer','character','story_quality','rhetoric_quality','memory','memory_quality','chapter_quality']:
            self.assertIn(req['api_roles'][role],['gemma','flash'])
