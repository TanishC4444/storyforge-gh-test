import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.development import evidence_cards,resolve_review,review_schema,assess
from storyforge.editorial import DESIGN_CHECKS
from storyforge.contracts import ContractError,request
from storyforge.inference import Executor,ROOT
from storyforge.output_schema import editorial_schema
from storyforge.fixture import respond

class SpeedTests(unittest.TestCase):
    def test_named_list_evidence_resolves_actual_source(self):
        doc={'candidate':{'expanded_story_elements':[{'name':'character_behavior_arcs','value':'A costly choice.'}]},'request':{}}
        cards=evidence_cards(doc)
        self.assertEqual(cards[0]['path'],'candidate.expanded_story_elements.0')
        review={'pass':True,'checks':[{'id':key,'verdict':'pass','evidence_id':cards[0]['id'],'reason':'A specific fixture reason with adequate length.'} for key in DESIGN_CHECKS],'issues':[]}
        result=resolve_review(review,doc,cards)
        self.assertEqual(result['checks'][0]['path'],'candidate.expanded_story_elements.0')
        review['checks'][0]['evidence_id']='invented'
        with self.assertRaises(ContractError):resolve_review(review,doc,cards)
    def test_schemas_constrain_evidence_identifiers(self):
        cards=[{'id':'e001'}]
        schema=review_schema(cards,['character_depth'])
        self.assertEqual(schema['properties']['checks']['properties']['character_depth']['properties']['evidence_id']['enum'],['e001'])
        schema=editorial_schema({'required_checks':['scene_change'],'evidence_passages':[{'id':'p001'}]})
        self.assertEqual(schema['properties']['checks']['properties']['scene_change']['properties']['evidence_ids']['items']['enum'],['p001'])
    def test_development_packets_are_scoped_and_smaller_than_original(self):
        req=request(json.loads((ROOT/'examples/troy-first-thunder.json').read_text()))
        candidate={'refined_prompt':req['premise'],'expanded_story_elements':[{'name':k,'value':req.get(v)} for k,v in [('medium_length','chapters'),('themes_tensions','keywords'),('scenes','scene_designs'),('world_constraints','world_rules'),('character_behavior_arcs','characters'),('plots_subplots','plot_design'),('genre_tone_mood','tone_mood'),('reference_influence','references'),('figurative_style','style')]]}
        class Fake:
            def __init__(self):self.packets=[]
            def call(self,role,packet,instruction,**kwargs):
                self.packets.append(packet)
                return kwargs['validator'](json.loads(respond(role,packet,req)))
        fake=Fake();review=assess(fake,{'request':req,'refinement':candidate},'refine')
        self.assertTrue(review['pass']);self.assertEqual(len(fake.packets),4)
        largest=max(len(json.dumps(p)) for p in fake.packets)
        self.assertLess(largest,24000)
        self.assertTrue(all('request' not in p for p in fake.packets))

    def test_actual_duplicate_world_review_is_rejected(self):
        from storyforge.editorial import design_review
        review=json.loads((ROOT/'tests/fixtures/duplicate-world-review.json').read_text())
        self.assertEqual([c['id'] for c in review['checks']],['world_rules','world_rules'])
        with self.assertRaisesRegex(ContractError,'every required check exactly once'):
            design_review(review,{},required=['world_rules','character_depth'])

    def test_keyed_contract_requires_each_distinct_check(self):
        schema=review_schema([{'id':'e001'}],['world_rules','character_depth'])
        checks=schema['properties']['checks']
        self.assertEqual(checks['type'],'object')
        self.assertEqual(set(checks['required']),{'world_rules','character_depth'})
        self.assertFalse(checks['additionalProperties'])
        self.assertNotIn('id',checks['properties']['world_rules']['properties'])

    def test_keyed_assessments_resolve_without_model_generated_labels(self):
        doc={'request':{},'candidate':{'world_constraints':['Finite charges.'],'character_tensions':['A costly choice.']}}
        cards=evidence_cards(doc);lookup={c['label']:c['id'] for c in cards}
        review={'pass':True,'checks':{'world_rules':{'verdict':'pass','evidence_id':lookup['world_constraints'],'reason':'The candidate fixes a finite charge supply.'},'character_depth':{'verdict':'pass','evidence_id':lookup['character_tensions'],'reason':'The candidate describes an explicit costly choice.'}},'issues':[]}
        result=resolve_review(review,doc,cards,required=['world_rules','character_depth'])
        self.assertEqual({c['id'] for c in result['checks']},{'world_rules','character_depth'})
