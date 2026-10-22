import copy,json,tempfile,unittest
from unittest.mock import patch
from storyforge.review_policy import REVIEWERS,prepare,contract
from storyforge.inference import Executor,ROOT
from test_story import example

class ReviewPolicyTests(unittest.TestCase):
    def test_every_reviewer_receives_immutable_author_contract_and_applicable_skill(self):
        req=example();req['pov']='Third person. No dialogue.'
        req['quality_contract']=['Preserve private knowledge.'];original=copy.deepcopy(req)
        for role in REVIEWERS:
            with self.subTest(role=role):
                packet,skill,system=prepare(req,role,{'author_review_contract':{'nonnegotiable_form':'Require speech'}},'',ROOT)
                self.assertEqual(packet['author_review_contract'],contract(req))
                self.assertIn('No dialogue.',system)
                self.assertIn('Missing quoted speech is not itself a failure',system)
                self.assertIn('either pass or fail remains possible',system)
                if role!='development_editor':self.assertTrue(skill)
                packet['author_review_contract']['quality_contract'].append('Tampered')
        self.assertEqual(req,original)

    def test_non_review_roles_are_unaffected(self):
        packet={'input':'source'}
        self.assertEqual(prepare(example(),'writer',packet,'writing skill',ROOT),(packet,'writing skill',''))

    def test_formatting_retry_keeps_author_instructions_and_judgments(self):
        req=example();req['pov']='No dialogue.';req['api_roles']={};req['max_stage_retries']=1
        packet={'required_checks':['scene_change'],'evidence_passages':[{'id':'p001','text':'The smith left.'}]}
        bad={'pass':False,'checks':{'scene_change':{'verdict':'fail','evidence_ids':['p001'],'reason':'The choice needs a specific consequential cost.'}},'issues':[]}
        def validate(raw):
            if not raw.get('format_fixed'):raise ValueError('Missing format marker')
            return raw
        fixed={**bad,'format_fixed':True}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.local_worker.execute',side_effect=[(json.dumps(bad),{'finish_reason':'stop'}),(json.dumps(fixed),{'finish_reason':'stop'})]) as cpu:
            result=Executor(req,d,'worker').call('chapter_quality',packet,'Assess the scene.',validator=validate)
            self.assertFalse(result['pass'])
            self.assertIn('Repair JSON structure only',cpu.call_args.args[1])
            self.assertIn('Author contract (application-owned)',cpu.call_args.args[1])
            self.assertIn('No dialogue.',cpu.call_args.args[1])
