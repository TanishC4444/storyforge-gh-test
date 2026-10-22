import json,unittest
from pathlib import Path
from storyforge.output_schema import editorial_schema,memory_schema
from storyforge.evidence import payload
from storyforge.editorial import editorial_review
from storyforge.contracts import ContractError

class GateContractTests(unittest.TestCase):
    def test_required_checks_cannot_request_skipped_verdicts(self):
        schema=editorial_schema({**payload('The smith refused the offered wage.'),'required_checks':['dialogue_tactics','continuity_clock','subplot_function','reference_application']})
        checks=schema['properties']['checks']['properties']
        for key in ['dialogue_tactics','continuity_clock']:self.assertEqual(checks[key]['properties']['verdict']['enum'],['pass','fail'])
        for key in ['subplot_function','reference_application']:self.assertIn('not_applicable',checks[key]['properties']['verdict']['enum'])

    def test_initial_canon_is_not_offered_as_supersession_target(self):
        prior=[{'id':'m00001','kind':'event','text':'The smith seeks passage.'}]
        schema=memory_schema(payload('The smith lost the wage.'),['smith'],prior_memories=prior)
        self.assertEqual(schema['properties']['memories']['items']['properties']['supersedes']['maxItems'],0)

    def test_only_keyed_canon_can_be_a_transition_target(self):
        prior=[{'id':'initial','kind':'event'},{'id':'wage','kind':'resource','fact_key':'smith.wage'}]
        spec=memory_schema(payload('The wage was lost.'),['smith'],prior_memories=prior)['properties']['memories']['items']['properties']['supersedes']
        self.assertEqual(spec['items']['enum'],['wage'])

    def test_failed_live_review_remains_invalid_under_validator(self):
        root=Path(__file__).parent/'fixtures/practice-gates-39722013919'
        packet=json.loads((root/'story-packet.json').read_text())
        raw=json.loads((root/'story-output.json').read_text())
        raw['checks']=[dict(v,id=k) for k,v in raw['checks'].items()]
        prose='\n\n'.join(p['text'] for p in packet['evidence_passages'])
        with self.assertRaisesRegex(ContractError,'cannot be skipped'):
            editorial_review(raw,prose,packet['required_checks'])

    def test_failed_live_memory_remains_blocked_without_mutating_canon(self):
        import tempfile,copy
        from storyforge.resilience import memory_extract
        root=Path(__file__).parent/'fixtures/practice-gates-39722013919'
        packet=json.loads((root/'memory-packet.json').read_text());raw=json.loads((root/'memory-output.json').read_text());original=copy.deepcopy(packet['prior_canon'])
        prose='\n\n'.join(p['text'] for p in packet['evidence_passages'])
        class Executor:
            def call(self,role,packet,instruction,**kwargs):return kwargs['validator'](raw)
        req={'characters':[{'id':x} for x in packet['characters']],'performance':{'canon_index':True}}
        with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(ContractError,'unkeyed prior facts cannot be superseded'):
            memory_extract(Executor(),req,d,prose,packet,'Extract memory')
        self.assertEqual(original,packet['prior_canon'])
