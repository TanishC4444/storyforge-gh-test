import copy,io,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout
from storyforge.inference import ROOT
from storyforge.contracts import request,ContractError
from storyforge.refinement import refine,validate_part,scene_layout,GROUPS
from storyforge.storage import save,load
from storyforge.dag import stage

class RefinementTests(unittest.TestCase):
    def setUp(self):
        self.req=request(json.loads((ROOT/'examples/troy-practice.json').read_text()))
    def test_parts_overlap_with_isolated_packets_and_preserve_author_choices(self):
        original=copy.deepcopy(self.req);barrier=threading.Barrier(2);seen=[];lock=threading.Lock()
        class Fake:
            hosted=None
            def __init__(self,req,folder,backend):self.folder=folder
            def call(self,role,packet,instruction,**kwargs):
                with lock:seen.append((packet,self.folder));order=len(seen)
                if order<=2:barrier.wait(timeout=5)
                return kwargs['validator']({'guidance':['Specific costly action for '+packet['category']], 'assumptions':[],'open_decisions':[]})
        with tempfile.TemporaryDirectory() as d,patch('storyforge.refinement.Executor',Fake):
            result=refine(self.req,{'sources':[]},d,'fixture')
            self.assertEqual(len(load(Path(d)/'refinement-parts.json')),5)
        self.assertEqual(self.req,original);self.assertEqual(result['original_prompt'],original['premise'])
        self.assertEqual(result['world_constraints'],original['world_rules'])
        self.assertEqual(len({str(folder) for _,folder in seen}),5)
        for packet,_ in seen:
            self.assertEqual(set(packet['author_requirements']),set(GROUPS[packet['category']]))
        self.assertTrue(all(line.startswith('Proposed ') for line in result['expanded_story_elements']))
    def test_bad_or_empty_part_cannot_become_valid_development(self):
        for value in [{}, {'guidance':[],'assumptions':[],'open_decisions':[]},
                      {'guidance':['x'*601],'assumptions':[],'open_decisions':[]}]:
            with self.assertRaises(ContractError):validate_part(value)
    def test_one_scene_fixture_exercises_new_refinement_and_all_acceptance_gates(self):
        import shutil
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            root=Path(d)
            def run(name,task,state=None,extras=(),character=None,index=0):
                inputs=root/name/'inputs'
                if state:shutil.copytree(state,inputs/'state')
                for path,target in extras:shutil.copytree(path,inputs/target)
                out=root/name/'out'
                from storyforge.retrieval import retrieve
                offline=copy.deepcopy(self.req);offline['retrieval_mode']='lexical'
                with patch('storyforge.dag.retrieve',return_value=retrieve(offline)):
                    stage(task,inputs,out,index,character,'troy-practice','small','fixture')
                return out
            state=run('prepare','prepare')
            parts=[(run('part-'+name,'refine_part',state,index=i),'refinement/'+name) for i,name in enumerate(GROUPS)]
            state=run('refine','combine_refinement',state,parts)
            self.assertEqual(load(state/'snapshot.json')['refinement_method'],'parallel_scoped_proposals_immutable_author_brief')
            chapter=run('chapter','chapter_plan',state)
            state=run('join','combine_plans',state,[(chapter,'chapters/one')]);state=run('design','scene_design',state)
            chars=load(state/'snapshot.json')['plan']['scenes'][0]['participants']
            actors=[(run('actor-'+cid,'character',state,character=cid),'characters/'+cid) for cid in chars]
            direction=run('direction','director',state,actors)
            draft=run('draft','writer',state,[(direction,'direction')]);edit=run('edit','edit',state,[(draft,'draft')])
            story=run('story','story_review',state,[(edit,'edited')]);rhetoric=run('rhetoric','rhetoric_review',state,[(edit,'edited')]);memory=run('memory','memory',state,[(edit,'edited')])
            final=run('accept','accept',state,[(edit,'edited'),(story,'initial-story'),(rhetoric,'initial-rhetoric'),(memory,'memory')])
            snapshot=load(final/'snapshot.json')
            self.assertTrue(snapshot['complete']);self.assertEqual(snapshot['version'],1)
            self.assertTrue(load(final/'chapter-review.json')['pass'])
            # Acceptance cannot reuse a review from a different candidate.
            review=load(story/'review.json');review['reviewed_sha256']='stale';save(story/'review.json',review)
            with self.assertRaisesRegex(ContractError,'stale prose'):
                run('stale-accept','accept',state,[(edit,'edited'),(story,'initial-story'),(rhetoric,'initial-rhetoric'),(memory,'memory')])
    def test_small_api_calls_avoid_extra_count_request_only_when_enabled(self):
        from storyforge.hosted import GoogleHosted
        answer={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'OK'}]}}]}
        for flag,expected in [(True,1),(False,2)]:
            with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
                hosted=GoogleHosted(d,'placeholder');calls=[]
                def respond(path,*args,**kwargs):
                    calls.append(path);return {'totalTokens':2} if path.endswith('countTokens') else answer
                with patch.object(hosted,'request',side_effect=respond),patch.object(hosted,'reserve'):
                    hosted.complete('gemma','s','p',20,policy={'timeout':10,'estimate_small_calls':flag})
                self.assertEqual(len(calls),expected)

    def test_later_chapter_edit_packets_fit_budget_with_provenance(self):
        from storyforge.craft import author_packet,compile_brief
        from storyforge.coordinator import packet
        from storyforge.fixture import respond
        from storyforge.retrieval import retrieve
        from storyforge.working_context import concise_packet
        req=request(json.loads((ROOT/'examples/troy-parallel-experiment.json').read_text()))
        req['retrieval_mode']='keyword'
        state={'request':req,'retrieval':retrieve(req),'refinement':compile_brief(req),'memories':[],
               'accepted':[],'plan':json.loads(respond('architect',{},req))}
        state['refinement']['expanded_story_elements']=['Proposed plot: '+('specific choices and consequences '*12) for _ in range(25)]
        prose=' '.join(['material']*1560)
        for card in state['plan']['scenes']:
            data=concise_packet({**packet(req,state,card),**author_packet(req,state,card),'prose':prose},req)
            self.assertLess(len(json.dumps(data,ensure_ascii=False,separators=(',',':')))+2500,req['context_chars'])
            for item in data['completed_events']:
                self.assertEqual(item['omitted_prefix_characters'],len(prose)-1000)
                self.assertEqual(item['prose'],prose[-1000:])
            state['accepted'].append({**card,'prose':prose})
            state['memories'].extend({'kind':'resource','text':'Material custody and household obligations '+('specific '*30),'known_by':['public'],'source':card['id'],'fact_key':card['id']+str(j)} for j in range(6))

    def test_native_refinement_join_rejects_missing_duplicate_and_stale_parts(self):
        from storyforge.refinement import join_parts,base_hash
        from storyforge.worker_policy import policy
        state={'request':self.req,'retrieval':{'sources':[]}}
        good={'guidance':['A specific concrete consequence.'],'assumptions':[],'open_decisions':[]}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in GROUPS:save(root/name/'refinement-part.json',{'category':name,'base_sha256':base_hash(self.req,state['retrieval']),'result':good})
            save(root/'extra/refinement-part.json',{'category':'plot','base_sha256':'stale','result':good})
            with self.assertRaisesRegex(ContractError,'duplicate'):join_parts(copy.deepcopy(state),root,root/'out')
            (root/'extra/refinement-part.json').unlink()
            save(root/'plot/refinement-part.json',{'category':'plot','base_sha256':'stale','result':good})
            with self.assertRaisesRegex(ContractError,'stale'):join_parts(copy.deepcopy(state),root,root/'out')
            (root/'plot/refinement-part.json').unlink()
            with self.assertRaisesRegex(ContractError,'Missing'):join_parts(copy.deepcopy(state),root,root/'out')
        self.assertEqual(policy(self.req,'refiner_part',850)['tier'],'lite')
        req=copy.deepcopy(self.req);req['execution_policy'].pop('model_routing',None);req['execution_policy']['refinement_provider']='gemma'
        self.assertEqual(policy(req,'refiner_part',850)['tier'],'gemma')

    def test_basic_scene_plan_preserves_authored_layout_without_model_development(self):
        from storyforge.craft import compile_scene_plan
        result=compile_scene_plan(self.req)
        self.assertEqual(result['scenes'][0]['pov'],self.req['scene_designs'][0]['pov'])
        self.assertEqual(result['scenes'][0]['intended_change'],self.req['scene_designs'][0]['choice_and_consequence'])
        self.assertNotIn('first deployment',self.req['ending_tendency'].lower())

    def test_actual_failed_writer_reports_all_errors_in_first_retry(self):
        from storyforge.craft import validate_prose
        text=(ROOT/'tests/fixtures/practice-writer-39714540410/attempt-2.txt').read_text()
        # Select the original short artifact independently of filename ordering.
        texts=[p.read_text() for p in (ROOT/'tests/fixtures/practice-writer-39714540410').glob('*.txt')]
        short=min(texts,key=lambda s:len(s.split()))
        with self.assertRaises(ContractError) as caught:validate_prose(short,self.req,check_length=True)
        self.assertIn('269 words',str(caught.exception));self.assertIn('no-dialogue',str(caught.exception))
    def test_no_dialogue_packets_remove_voice_examples_at_every_nesting_level(self):
        from storyforge.working_context import concise_packet
        speaker=self.req['characters'][0]
        packet={'characters':[speaker],'pov_profile':speaker,'author_requirements':{'characters':[speaker]}}
        result=concise_packet(packet,self.req)
        self.assertIn('examples',speaker['voice_design'])
        self.assertNotIn('examples',result['pov_profile']['voice_design'])
        self.assertNotIn('examples',result['author_requirements']['characters'][0]['voice_design'])

    def test_practice_and_full_story_use_quality_routing(self):
        from storyforge.worker_policy import policy
        full=request(json.loads((ROOT/'examples/troy-parallel-experiment.json').read_text()))
        for role,tier in [('writer','flash'),('humanizer','flash36'),('structural_editor','flash36')]:
            self.assertEqual(policy(self.req,role,1800)['tier'],tier)
            self.assertEqual(policy(full,role,1800)['tier'],tier)

    def test_optional_editor_outage_retains_valid_input_without_cpu_fallback(self):
        from storyforge.experimental import dispatch
        from storyforge.inference import Executor
        from storyforge.hosted import HostedError
        req=copy.deepcopy(self.req);req['min_words_ratio']=.1;req['max_words_ratio']=3
        prose=' '.join(['bronze']*350)
        card={**req['scene_designs'][0],'chapter':1}
        state={'request':req,'plan':{'scenes':[card]},'accepted':[]}
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            root=Path(d);save(root/'inputs/draft/draft.txt',prose)
            with patch('storyforge.dag.context',return_value={}),patch('storyforge.hosted.GoogleHosted.complete',side_effect=HostedError('Google HTTP 429 RESOURCE_EXHAUSTED')),patch('storyforge.local_worker.execute') as cpu:
                dispatch('edit',root/'inputs',root/'out',state,0,'small','worker','unused')
            cpu.assert_not_called()
            self.assertEqual((root/'out/prose.txt').read_text(),prose)
            report=load(root/'out/edit-report.json')
            self.assertTrue(report['quality_review_required']);self.assertTrue(report['retained_valid_candidate'])
            self.assertEqual(report['passes'],[])

    def test_invalid_line_edit_keeps_successful_structural_candidate(self):
        from storyforge.experimental import dispatch
        prose=' '.join(['bronze']*350)
        structural=(ROOT/'tests/fixtures/practice-editor-39717076545/structural.txt').read_text()
        rejected=(ROOT/'tests/fixtures/practice-editor-39717076545/rejected-line-edit.txt').read_text()
        card={**self.req['scene_designs'][0],'chapter':1}
        state={'request':self.req,'plan':{'scenes':[card]},'accepted':[]}
        class Fake:
            def __init__(self,*args):pass
            def call(self,role,packet,instruction,**kwargs):
                return kwargs['validator'](rejected if role=='humanizer' else structural)
        with tempfile.TemporaryDirectory() as d,patch('storyforge.experimental.Executor',Fake),patch('storyforge.dag.context',return_value={}):
            root=Path(d);save(root/'inputs/draft/draft.txt',prose)
            dispatch('edit',root/'inputs',root/'out',state,0,'small','worker','unused')
            self.assertEqual((root/'out/prose.txt').read_text(),structural)
            self.assertTrue(load(root/'out/edit-report.json')['quality_review_required'])
