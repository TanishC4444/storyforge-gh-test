import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.hosted import GoogleHosted,HostedError

class IndependentProjectTests(unittest.TestCase):
    def env(self):return patch.dict(os.environ,{'GEMINI_API_KEY':'placeholder-primary','GEMINI_API_KEYS':json.dumps(['placeholder-b','placeholder-c','placeholder-d','placeholder-e','placeholder-f']),'GEMINI_DISTINCT_PROJECTS':'true','GITHUB_JOB':'batch-test'},clear=False)
    def test_expanded_pool_distributes_batches_without_expanding_retry_budget(self):
        backups=['placeholder-backup-'+str(i) for i in range(18)]
        with self.env(),tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'GEMINI_API_KEYS':json.dumps(backups)}):
            h=GoogleHosted(d);seen=[]
            self.assertEqual(len(h.project_children),19)
            for child in h.project_children:child.complete=lambda *a,**k:('text',{'model':'test'})
            for batch in range(19):
                with patch.dict(os.environ,{'STORY_BATCH':str(batch)}):
                    _,meta=h.complete('flash','system','prompt',100,role='writer_beat',policy={'timeout':10,'max_project_attempts':2})
                    seen.append(meta['project_slot'])
            self.assertEqual(set(seen),set(range(1,20)))
            calls=[]
            def unavailable(*a,**k):
                calls.append(1)
                raise HostedError('Google HTTP 429 RESOURCE_EXHAUSTED')
            for child in h.project_children:child.complete=unavailable
            with self.assertRaises(HostedError):
                h.complete('flash','system','prompt',100,role='writer_beat',policy={'timeout':10,'max_project_attempts':2})
            self.assertEqual(len(calls),2)
    def test_distinct_numeric_batches_start_on_distinct_projects(self):
        with self.env(),tempfile.TemporaryDirectory() as d:
            h=GoogleHosted(d);seen=[]
            for child in h.project_children:child.complete=lambda *a,**k:('text',{'model':'test'})
            for b in range(6):
                with patch.dict(os.environ,{'STORY_BATCH':str(b)}):
                    _,meta=h.complete('flash','system','prompt',100,role='writer_beat');seen.append(meta['project_slot'])
            self.assertEqual(set(seen),set(range(1,7)))
    def test_quota_failure_can_use_another_explicitly_independent_project(self):
        with self.env(),tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'STORY_BATCH':'0'}):
            h=GoogleHosted(d);calls=[]
            def responder(*a,**k):
                calls.append(1)
                if len(calls)==1:raise HostedError('Google HTTP 429 RESOURCE_EXHAUSTED')
                return 'text',{'model':'test'}
            for child in h.project_children:child.complete=responder
            text,meta=h.complete('flash','system','prompt',100,role='writer_beat')
            self.assertEqual(text,'text');self.assertEqual(len(calls),2);self.assertIn('project_slot',meta)
    def test_quota_ledgers_and_circuits_are_separate_and_inherited_by_slot(self):
        with self.env(),tempfile.TemporaryDirectory() as d:
            h=GoogleHosted(Path(d)/'a');h.project_children[0].reserve('flash',100)
            h.project_children[0].circuit('flash',HostedError('Google HTTP 429 RESOURCE_EXHAUSTED'))
            self.assertFalse(h.project_children[1].circuit('flash'))
            newer=GoogleHosted(Path(d)/'b');newer.inherit((Path(d)/'a').rglob('quota.json'))
            self.assertTrue(newer.project_children[0].circuit('flash'));self.assertFalse(newer.project_children[1].circuit('flash'))
            self.assertEqual(json.loads((Path(d)/'b/project-01/quota.json').read_text())['flash']['calls'],1)
            for p in Path(d).rglob('*.json'):self.assertNotIn('placeholder-',p.read_text())
    def test_legacy_pool_remains_credential_only_without_opt_in(self):
        with self.env(),tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'GEMINI_DISTINCT_PROJECTS':'false'}):
            h=GoogleHosted(d);self.assertEqual(h.project_children,[])
            with patch.object(h,'_request',side_effect=HostedError('Google HTTP 429')) as request:
                with self.assertRaises(HostedError):h.request('test',{})
                self.assertEqual(request.call_count,1)

    def test_project_model_configuration_error_does_not_burn_every_project(self):
        with self.env(),tempfile.TemporaryDirectory() as d:
            h=GoogleHosted(d);calls=[]
            def rejected(*a,**k):calls.append(1);raise HostedError('Google HTTP 400 INVALID_ARGUMENT')
            for child in h.project_children:child.complete=rejected
            with self.assertRaises(HostedError):h.complete('flash','s','p',100,role='repair')
            self.assertEqual(len(calls),1)
