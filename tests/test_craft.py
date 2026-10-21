import copy,json,tempfile,unittest,io
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout
from storyforge.craft import compile_brief,validate_prose,author_packet
from storyforge.inference import ROOT
from storyforge.contracts import ContractError,request
from storyforge.storage import save,load
from storyforge.experimental import run_bundle,dispatch
from storyforge.worker_policy import policy

class CraftTests(unittest.TestCase):
    def setUp(self):self.req=request(json.loads((ROOT/'examples/troy-parallel-experiment.json').read_text()))
    def test_compiled_brief_preserves_user_without_model_expansion(self):
        result=compile_brief(self.req)
        self.assertEqual(result['original_prompt'],self.req['premise'])
        self.assertEqual(result['world_constraints'],self.req['world_rules'])
        self.assertEqual(result['expanded_story_elements'],[])
    def test_form_and_duplicate_guards(self):
        for text in ['“We shall go,” he said.', 'Sing, Muse, of iron.', '# Scene 1']:
            with self.assertRaises(ContractError):validate_prose(text,self.req)
        paragraph='The smith carried the broken iron across the sand and set it beside the cold hearth.'
        with self.assertRaises(ContractError):validate_prose(paragraph+'\n\n'+paragraph,self.req)
        self.assertEqual(validate_prose(paragraph,self.req),paragraph)
    def test_large_scene_cannot_silently_collapse_to_summary(self):
        with self.assertRaises(ContractError):validate_prose('A short summary.',self.req,check_length=True)
    def test_creative_roles_do_not_use_api(self):
        for role in ['architect','writer','humanizer','structural_editor','story_quality','rhetoric_quality','chapter_quality','memory']:
            self.assertIsNone(policy(self.req,role,1000)['tier'])
        self.assertEqual(policy(self.req,'character',220)['tier'],'gemma')
    def test_chapter_context_is_bounded_and_keeps_canon_separate(self):
        card=self.req['scene_designs'][4];card={**card,'chapter':2}
        state={'accepted':[{'id':'old','chapter':1,'prose':'OLD'},{'id':'recent','chapter':2,'prose':'RECENT'}]}
        packet=author_packet(self.req,state,card)
        self.assertEqual(packet['completed_events'],[{'id':'recent','prose':'RECENT'}])
    def test_outline_chunks_remap_every_scene_and_keep_chapter_reviews(self):
        from storyforge.fixture import respond
        from storyforge.retrieval import retrieve
        self.req['retrieval_mode']='lexical'
        state={'version':0,'backend':'fixture','accepted':[],'memories':[], 'request':self.req,'refinement':compile_brief(self.req),'retrieval':retrieve(self.req)}
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            root=Path(d);save(root/'inputs/state/snapshot.json',state)
            result=run_bundle('plan_bundle',root/'inputs',root/'out',state,0,'fast','fixture','troy-parallel-experiment')
            self.assertEqual(len(result['plan']['scenes']),12)
            self.assertEqual(result['plan']['scenes'][-1]['id'],'ch03-sc04')
            self.assertEqual(len(result['chapter_development_reviews']),3)
    def test_structural_then_line_revision_precedes_export(self):
        from storyforge.fixture import respond
        req=copy.deepcopy(self.req);card={**req['scene_designs'][0],'chapter':1}
        state={'request':req,'plan':{'scenes':[card]},'accepted':[]}
        calls=[]
        class Fake:
            def __init__(self,*args):pass
            def call(self,role,packet,instruction,**kwargs):
                calls.append((role,packet['prose']));return packet['prose']+' '+role+'.'
        with tempfile.TemporaryDirectory() as d,patch('storyforge.experimental.Executor',Fake),patch('storyforge.dag.context',return_value={}):
            root=Path(d);save(root/'inputs/draft/draft.txt','The smith walked beside the shore.')
            dispatch('edit',root/'inputs',root/'out',state,0,'fast','fixture','unused')
            self.assertEqual([c[0] for c in calls],['structural_editor','humanizer'])
            self.assertIn('structural_editor.',calls[1][1])
            self.assertTrue((root/'out/prose.txt').exists())
