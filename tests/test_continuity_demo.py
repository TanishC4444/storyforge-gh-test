import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import continuity_demo as demo
from storyforge.storage import load
from storyforge.contracts import ContractError

class ComparisonTests(unittest.TestCase):
    def setUp(self):self.case=load(demo.ROOT/'demos/continuity-cases.json')['resource']
    def test_baseline_gets_full_history_and_same_author_contract(self):
        history=['First exact scene.','Second exact scene.']
        packet=demo.writer_packet(self.case,history,2)
        self.assertEqual(packet['all_previous_chapters'],history)
        self.assertEqual(packet['initial_facts'],self.case['facts'])
        self.assertEqual(packet['chapter_task'],self.case['chapters'][2])
        self.assertNotIn('source_verified_memory',packet)
    def test_failed_memory_handoff_keeps_draft_and_stops_next_scene(self):
        with tempfile.TemporaryDirectory() as d,patch.object(demo.Provider,'call',return_value='The ferry stopped. Iona held the empty cell.'),patch.object(demo,'review_scene',return_value={'pass':True,'checks':[],'issues':[]}),patch.object(demo,'retain_memory',side_effect=ContractError('No verified handoff')):
            result,history=demo.run_arm(self.case,'storyforge',d)
            self.assertFalse(result['complete']);self.assertEqual(len(history),1)
            self.assertIn('No verified handoff',result['errors'])
            self.assertIn(history[0],(Path(d)/'story.txt').read_text())
    def test_baseline_writes_three_scenes_without_hidden_memory_or_reviews(self):
        with tempfile.TemporaryDirectory() as d,patch.object(demo.Provider,'call',side_effect=['First.','Second.','Third.']) as calls,patch.object(demo,'review_scene',side_effect=AssertionError('Baseline must not get editorial help')):
            result,history=demo.run_arm(self.case,'baseline',d)
            self.assertTrue(result['complete']);self.assertEqual(history,['First.','Second.','Third.'])
            self.assertEqual(calls.call_args_list[2].args[1]['all_previous_chapters'],['First.','Second.'])
    def test_repairs_obey_production_passage_ownership_and_source_hash(self):
        class Provider:
            def __init__(self,value):self.value=value
            def call(self,*a,**kw):return self.value
        prose='Iona held one cell.\n\nVal took the wheel.'
        fixed=demo.repair_scene(Provider({'replacements':{'p001':'Iona held no cells.'}}),self.case,[],prose,{'issues':[]})
        self.assertEqual(fixed,'Iona held no cells.\n\nVal took the wheel.')
        for bad in [{'p999':'Extra text'},{'p001':''}]:
            with self.assertRaises(ContractError):demo.repair_scene(Provider({'replacements':bad}),self.case,[],prose,{'issues':[]})
    def test_blind_judge_cannot_cite_nonexistent_source(self):
        rows=[{'label':label,'prose_score':3,'prose_reason':'A specific reason.','checks':[{'criterion':i,'verdict':'pass','chapter':1,'evidence_ids':['p999'],'reason':'Reason.'} for i in range(1,6)]} for label in ['A','B']]
        arms={arm:({},['Some actual text.']*3) for arm in ['baseline','storyforge']}
        with tempfile.TemporaryDirectory() as d,patch.object(demo.Provider,'call',return_value={'assessments':rows}):
            with self.assertRaisesRegex(ContractError,'absent source'):demo.judge_pair(self.case,arms,d)
    def test_all_cases_have_three_chapters_and_five_preregistered_criteria(self):
        for case in load(demo.ROOT/'demos/continuity-cases.json').values():
            self.assertEqual(len(case['chapters']),3);self.assertEqual(len(case['criteria']),5)
            state=demo.state_for(case)
            self.assertEqual(len(demo.bridge(state)['facts']),len(case['facts']))
