import copy,json,tempfile,unittest,io
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
from storyforge import contracts
from storyforge.resilience import salvage_memory,memory_extract,load_seed
from storyforge.patching import apply,digest,repair
from storyforge.evidence import payload
from storyforge.output_schema import memory_schema
from storyforge.inference import ROOT,Executor

PROSE='Thestor lifted the iron.\n\nOdysseus closed the door.\n\nThe boy waited.\n\nRain fell.'
class ResilienceTests(unittest.TestCase):
    def req(self):
        return contracts.request(json.loads((ROOT/'examples/troy-first-thunder.json').read_text()))
    def test_memory_outer_array_losslessly_recovers(self):
        result=salvage_memory([{'kind':'event','text':'Thestor lifted the iron.','evidence_ids':['p001'],'known_by':['thestor']}],PROSE,['thestor'])
        self.assertEqual(len(result['memories']),1)
    def test_overbroad_evidence_quarantined_never_truncated(self):
        item={'kind':'event','text':'A supposed event','evidence_ids':['p001','p002','p003','p004'],'known_by':['thestor']}
        result=salvage_memory({'memories':[item]},PROSE,['thestor'])
        self.assertEqual(result['memories'],[])
        self.assertEqual(result['quarantined'][0]['raw']['evidence_ids'],item['evidence_ids'])
    def test_schema_prevents_original_missing_wrapper_and_evidence_overflow(self):
        schema=memory_schema(payload(PROSE),['thestor'])
        self.assertEqual(schema['required'],['memories'])
        ids=schema['properties']['memories']['items']['properties']['evidence_ids']
        self.assertEqual(ids['maxItems'],3)
        self.assertEqual(ids['items']['enum'],['p001','p002','p003','p004'])
    def test_memory_outage_preserves_prose_and_no_guessed_facts(self):
        class Broken:
            def call(self,*args,**kwargs):raise RuntimeError('Transport unavailable')
        with tempfile.TemporaryDirectory() as d:
            result=memory_extract(Broken(),self.req(),d,PROSE,payload(PROSE),'extract')
            self.assertEqual(result['memories'],[])
            self.assertEqual((Path(d)/'memory-source.txt').read_text(),PROSE)
    def test_patch_changes_only_selected_source_span(self):
        updated=apply(PROSE,{'p002':'Odysseus barred the door.'},digest(PROSE))
        self.assertEqual(updated,PROSE.replace('Odysseus closed the door.','Odysseus barred the door.'))
        with self.assertRaisesRegex(contracts.ContractError,'stale'):apply(PROSE,{'p002':'Wrong.'},'stale')
    def test_direct_editor_replacement_needs_no_extra_model_call(self):
        class NoCall:
            def call(self,*args,**kwargs):raise AssertionError('An editor already supplied the fix')
        review={'issues':[{'evidence_ids':['p002'],'replacement':'Odysseus barred the door.','problem':'Vague action','fix':'Specify action','category':'specificity'}]}
        updated,report=repair(NoCall(),self.req(),PROSE,[review])
        self.assertIn('barred',updated);self.assertEqual(report['direct_editor_fixes'],1)
    def test_patch_conflicts_use_one_targeted_call_not_whole_scene(self):
        class Fix:
            def call(self,role,packet,instruction,**kwargs):
                self.packet=packet
                return kwargs['validator']({'replacements':{'p002':'Odysseus barred the door.'}})
        editor=Fix();reviews=[{'issues':[{'evidence_ids':['p002'],'replacement':r,'problem':'Issue','fix':'Fix','category':'specificity'}]} for r in ['A.','B.']]
        updated,report=repair(editor,self.req(),PROSE,reviews)
        self.assertEqual(len(editor.packet['paragraphs']),1)
        self.assertNotIn('prose',editor.packet)
        self.assertEqual(report['targeted_editor_fixes'],1)
    def test_real_seed_reuses_plan_and_scene_without_creative_changes(self):
        seed=load_seed(self.req(),ROOT)
        self.assertEqual(seed['recovery']['scene_id'],'ch01-sc01')
        self.assertEqual(len(seed['plan']['scenes']),4)
        req=self.req();req['premise']='A different story'
        with self.assertRaisesRegex(contracts.ContractError,'different creative'):load_seed(req,ROOT)
    def test_review_model_outage_never_becomes_fake_pass(self):
        req=self.req();req['max_stage_retries']=0
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()),patch('storyforge.fixture.respond',return_value='not JSON'):
            result=Executor(req,d,'fixture').call('rhetoric_quality',{'required_checks':['specificity'],**payload(PROSE)},'review',validator=lambda x:x)
            self.assertTrue(result['unverified']);self.assertFalse(result['pass'])
