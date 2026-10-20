import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from storyforge.contracts import request, ContractError
from storyforge.editorial import STORY_CHECKS,RHETORIC_CHECKS,editorial_review,rhetoric_signals,apply_signals,design_review,DESIGN_CHECKS
from storyforge.evidence import payload
from storyforge.fixture import respond
from storyforge.retrieval import ROOT,retrieve,application_packet
from storyforge.coordinator import packet

PROSE='Mara set the wrench beside the sealed log.\n\nOren moved the log beyond her reach.'


def verdict(required=STORY_CHECKS,prose=PROSE):
    return json.loads(respond('story_quality',{**payload(prose),'required_checks':required},{}))


class EditorialTests(unittest.TestCase):
    def test_actual_old_empty_approval_is_rejected(self):
        with self.assertRaises(ContractError):
            editorial_review({'pass':True,'issues':[]},PROSE,STORY_CHECKS)

    def test_cannot_skip_required_character_or_causality_checks(self):
        value=verdict();value['checks'][0]['verdict']='not_applicable'
        with self.assertRaises(ContractError):editorial_review(value,PROSE,STORY_CHECKS)

    def test_failed_check_cannot_be_approved(self):
        value=verdict();value['checks'][0]['verdict']='fail'
        with self.assertRaises(ContractError):editorial_review(value,PROSE,STORY_CHECKS)

    def test_check_evidence_must_exist(self):
        value=verdict();value['checks'][0]['evidence_ids']=['p999']
        with self.assertRaises(ContractError):editorial_review(value,PROSE,STORY_CHECKS)

    def test_real_instruction_leak_cannot_receive_clean_gate(self):
        prose='"I’m just doing my job," she said, her voice hardening into a concrete observation.'
        value=editorial_review(verdict(RHETORIC_CHECKS,prose),prose,RHETORIC_CHECKS)
        value=apply_signals(value,rhetoric_signals(prose))
        self.assertFalse(value['pass'])
        self.assertTrue(any(x['category']=='instruction_leakage' for x in value['issues']))

    def test_design_approval_needs_all_categories_and_real_paths(self):
        doc={'request':{},'candidate':{'refined_prompt':'A proposal'}}
        value=json.loads(respond('development_editor',{'review_document':doc,'required_checks':DESIGN_CHECKS},{}))
        design_review(value,doc)
        value['checks'][0]['path']='candidate.invented'
        with self.assertRaises(ContractError):design_review(value,doc)

    def test_deep_input_validates_actual_character_depth_and_figure_controls(self):
        value=json.loads((ROOT/'examples/silent-bell-deep.json').read_text())
        request(copy.deepcopy(value))
        del value['characters'][0]['arc']['costly_choice']
        with self.assertRaises(ContractError):request(value)

    def test_all_creative_controls_reach_writer_and_scoped_rag_packet(self):
        req=request(json.loads((ROOT/'examples/silent-bell-deep.json').read_text()))
        # Unit test retrieval with real lexical ranking; semantic benchmark is separate.
        req['retrieval_mode']='keyword';rag=retrieve(req)
        card={'id':'ch01-sc02','pov':'mara','participants':['mara','oren']}
        state={'retrieval':rag,'accepted':[],'memories':[],'plan':{'threads':[]},'refinement':{'refined_prompt':'Author-only debt detail'}}
        context=packet(req,state,card)
        self.assertEqual(context['creative_controls']['style']['figurative_language']['density'],'sparse')
        self.assertTrue(context['creative_controls']['world_design']['physical_systems'])
        self.assertEqual(context['pov_profile']['arc']['costly_choice'],req['characters'][0]['arc']['costly_choice'])
        self.assertNotIn('refined_premise',context)
        self.assertTrue(context['literary_application']['references'])
        self.assertFalse(any(r['id']=='work_136' for r in context['literary_application']['references'])) # chapter-two reference
        rhetoric=application_packet(req,rag,'rhetoric_quality','ch01-sc02')
        self.assertIn(20,[c['chapter'] for c in rhetoric['craft']])

    def test_explicit_disabled_reference_is_not_silently_replaced(self):
        req=request(json.loads((ROOT/'examples/harbor.json').read_text()))
        req['references']=[{'record_id':'does-not-exist','scope':'story','purpose':'Test request'}]
        with self.assertRaisesRegex(ValueError,'unavailable or disabled'):retrieve(req)

if __name__=='__main__':unittest.main()
