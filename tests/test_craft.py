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
    def test_legacy_cpu_policy_is_available(self):
        self.req['execution_policy']['literary_quality']=False
        self.req['execution_policy'].pop('model_routing',None)
        self.req['execution_policy'].pop('hosted_prose',None)
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


class ProseRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.req=request(json.loads((ROOT/'examples/troy-parallel-experiment.json').read_text()))
        self.req['api_roles']={}
        self.good=' '.join(['bronze']*900)

    def test_each_edit_pass_retries_form_and_length_before_publication(self):
        self.req['execution_policy'].pop('model_routing',None)
        self.req['execution_policy'].pop('hosted_prose',None)
        from storyforge.tracking import Tracker,_CURRENT
        card={**self.req['scene_designs'][0],'chapter':1}
        state={'request':self.req,'plan':{'scenes':[card]},'accepted':[]}
        responses=[('“A quoted short scene.”',{'finish_reason':'stop'}),
                   (self.good,{'finish_reason':'stop'}),
                   ('A collapsed summary.',{'finish_reason':'stop'}),
                   (self.good+' ash',{'finish_reason':'stop'})]
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            root=Path(d);save(root/'inputs/draft/draft.txt',self.good)
            tracker=Tracker(root/'out','edit');token=_CURRENT.set(tracker)
            try:
                with patch('storyforge.dag.context',return_value={}),patch('storyforge.local_worker.execute',side_effect=responses) as worker:
                    dispatch('edit',root/'inputs',root/'out',state,0,'fast','worker','unused')
            finally:_CURRENT.reset(token)
            self.assertEqual(worker.call_count,4)
            retry=json.loads(worker.call_args_list[1].args[2])
            self.assertEqual(retry['rejected_prose'],responses[0][0])
            self.assertIn('word',retry['validation_error'])
            self.assertIn('900',json.loads(worker.call_args_list[3].args[2])['validation_error'])
            self.assertEqual((root/'out/prose.txt').read_text(),self.good+' ash')
            self.assertEqual(len(list((root/'out/calls').glob('*.json'))),4)
            self.assertEqual(tracker.state['model_calls_validated'],2)

    def test_repeated_invalid_edit_preserves_evidence_and_stops(self):
        from storyforge.inference import Executor
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            with patch('storyforge.local_worker.execute',return_value=('“Forbidden speech.”',{'finish_reason':'stop'})) as worker:
                with self.assertRaisesRegex(ContractError,'bounded retries'):
                    Executor(self.req,d,'worker').call('humanizer',{'prose':self.good},'Edit.',
                        validator=lambda p:validate_prose(p,self.req),output_format='text')
            self.assertEqual(worker.call_count,2)
            self.assertEqual(len(list((Path(d)/'calls').glob('*.json'))),2)
            self.assertFalse((Path(d)/'prose.txt').exists())

    def test_parallel_outline_artifacts_merge_and_reject_missing_or_stale_inputs(self):
        from storyforge.experimental import plan_chapter,combine_chapters
        from storyforge.retrieval import retrieve
        req=copy.deepcopy(self.req);req['retrieval_mode']='lexical'
        state={'version':0,'backend':'fixture','accepted':[],'memories':[],
               'request':req,'refinement':compile_brief(req),'retrieval':retrieve(req)}
        original=copy.deepcopy(state)
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            root=Path(d)
            chunks=[plan_chapter(state,i,root/str(i),'fast','fixture','unused') for i in [3,1,2]]
            self.assertEqual(state,original)
            for bad in [chunks[:2],[chunks[0],chunks[0],chunks[2]],
                        [{**chunks[0],'base_sha256':'stale'},*chunks[1:]]]:
                with self.assertRaises(ContractError):combine_chapters(copy.deepcopy(state),bad,root/'bad')
            result=combine_chapters(state,chunks,root/'combined')
            self.assertEqual([c['id'] for c in result['plan']['scenes']],
                             [f'ch{c:02}-sc{s:02}' for c in range(1,4) for s in range(1,5)])
            self.assertEqual(len(result['chapter_development_reviews']),3)

    def test_generated_outline_jobs_share_only_the_immutable_brief(self):
        from scripts.build_workflow import build_experimental
        text=build_experimental()
        self.assertEqual(text,(ROOT/'.github/workflows/troy-parallel-experiment.yml').read_text())
        for chapter in range(1,4):
            block=text.split(f'  plan_ch{chapter:02}:',1)[1].split('\n  plan_',1)[0]
            self.assertIn('needs: [refine_bundle]',block)
        self.assertIn('needs: [refine_bundle, plan_ch01, plan_ch02, plan_ch03]',text)
