import copy
import importlib.util
import json
from pathlib import Path
import unittest
from storyforge.contracts import request, ContractError
from storyforge.retrieval import application_packet

ROOT=Path(__file__).resolve().parents[1]
class TroyTests(unittest.TestCase):
    def brief(self):return json.loads((ROOT/'examples/troy-first-thunder.json').read_text())
    def test_complete_four_scene_input(self):
        req=request(self.brief())
        self.assertEqual(req['chapters']*req['scenes_per_chapter'],4)
        self.assertEqual(req['words_per_scene'],1400)
        self.assertEqual(req['references'][0]['record_id'],'work_136')
        self.assertIn('No usable firearm',req['scene_designs'][0]['restrictions'])
        self.assertEqual(req['style']['figurative_language']['density'],'lyrical')
    def test_weights_are_validated(self):
        for weights in [{'semantic_similarity':1,'keyword_match':1,'narrative_mechanism_match':1},{'semantic_similarity':float('nan'),'keyword_match':0,'narrative_mechanism_match':0}]:
            req=self.brief();req['retrieval_weights']=weights
            with self.assertRaises(ContractError):request(req)
    def test_troy_workflow_has_four_native_scene_chains(self):
        spec=importlib.util.spec_from_file_location('build_troy',ROOT/'scripts/build_workflow.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        actual=(ROOT/'.github/workflows/troy.yml').read_text()
        self.assertEqual(actual,mod.build(total=4,per_chapter=4,troy=True))
        self.assertIn('s04_accept:',actual)
        self.assertNotIn('s05_design:',actual)
        self.assertIn('backend: ${{ inputs.backend }}',actual)
    def test_reference_exclusions_reach_writer(self):
        req=request(self.brief())
        source={'id':'work_136','title':'Iliad','requested_scopes':req['references']}
        packet=application_packet(req,{'sources':[source]},'writer','ch01-sc01')
        self.assertIn('Modern translation wording',packet['references'][0]['do_not_borrow'])
