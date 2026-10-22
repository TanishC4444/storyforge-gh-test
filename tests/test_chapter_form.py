import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.editorial import validate_review_brief,ReviewBriefError,editorial_review
from storyforge.inference import Executor
from test_story import example

class ChapterFormTests(unittest.TestCase):
    def test_actual_failed_audit_cannot_demand_forbidden_dialogue(self):
        raw=json.loads(Path('tests/fixtures/practice-chapter-39786876575/review.json').read_text())
        with self.assertRaises(ReviewBriefError):validate_review_brief(raw,{'pov':'No dialogue or quoted speech.'})
        self.assertIs(validate_review_brief(raw,{'pov':'Third-person dialogue permitted.'}),raw)

    def test_substantive_retry_preserves_source_and_may_still_reject_scene(self):
        req=example();req['pov']='No dialogue or quoted speech.';req['api_roles']={};req['max_stage_retries']=1
        prose='The smith refused the offer and lost his wage.'
        bad={'pass':False,'checks':{'dialogue_tactics':{'verdict':'fail','evidence_ids':['p001'],'reason':'The exchange lacks a concrete tactical consequence.'}},'issues':[{'severity':'blocking','category':'dialogue_tactics','evidence_ids':['p001'],'problem':'The bargain needs a specific competing demand.','fix':'Add direct speech to establish the bargain.','replacement':''}]}
        revised=copy.deepcopy(bad);revised['issues'][0]['fix']='Clarify the narrated counteroffer and its cost.'
        packet={'required_checks':['dialogue_tactics'],'evidence_passages':[{'id':'p001','text':prose}]}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.local_worker.execute',side_effect=[(json.dumps(bad),{'finish_reason':'stop'}),(json.dumps(revised),{'finish_reason':'stop'})]) as cpu:
            result=Executor(req,d,'worker').call('chapter_quality',packet,'Assess the chapter.',validator=lambda x:editorial_review(x,prose,['dialogue_tactics']))
            self.assertFalse(result['pass']);self.assertEqual(cpu.call_count,2)
            self.assertIn(prose,cpu.call_args.args[2]);self.assertNotIn('Repair JSON structure only',cpu.call_args.args[1])

    def test_chapter_audit_receives_author_form(self):
        text=Path('storyforge/dag.py').read_text()
        self.assertIn("'nonnegotiable_form':req.get('pov')",text)
        self.assertIn('absence of quoted speech is not itself a defect',text)
