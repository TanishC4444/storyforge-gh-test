import unittest
from storyforge.fast_edit import batches,merge,validate
from storyforge.contracts import ContractError

class ParallelEditTests(unittest.TestCase):
    def setUp(self):
        self.prose='One waits.\n\nTwo speaks.\n\nThree listens.\n\nFour leaves.\n\nFive returns.'
        self.plan=batches(self.prose)
        self.results=[{'id':b['id'],'source_sha256':b['source_sha256'],'replacements':{}} for b in self.plan]
    def test_unique_ownership_and_lossless_merge(self):
        ids=[p for b in self.plan for p in b['owned']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(merge(self.prose,self.plan,self.results),self.prose)
        self.results[0]['replacements']={self.plan[0]['owned'][0]:'One speaks.'}
        self.assertEqual(merge(self.prose,self.plan,self.results),self.prose.replace('One waits.','One speaks.'))
    def test_stale_missing_duplicate_and_neighbor_results_rejected(self):
        with self.assertRaises(ContractError):merge(self.prose+' Changed.',self.plan,self.results)
        with self.assertRaises(ContractError):merge(self.prose,self.plan,self.results[:-1])
        with self.assertRaises(ContractError):merge(self.prose,self.plan,[self.results[0]]*4)
        with self.assertRaises(ContractError):validate({'replacements':{'p005':'Wrong owner.'}},self.plan[0])
    def test_editor_may_not_delete_whole_paragraph(self):
        with self.assertRaises(ContractError):validate({'replacements':{self.plan[0]['owned'][0]:''}},self.plan[0])
    def test_continuation_graph_has_one_final_review_and_separate_characters(self):
        from pathlib import Path
        text=(Path(__file__).resolve().parents[1]/'.github/workflows/troy-continue.yml').read_text()
        self.assertIn('s03_characters:',text)
        self.assertIn('s03_edit_batches:',text)
        self.assertNotIn('s03_verify:',text)
        self.assertNotIn('s01_draft:',text)
        self.assertIn('name: s02_accept',text)
