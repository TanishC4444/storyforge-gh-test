import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.adjudication import decide,CHECKS
from storyforge.dag import stage
from storyforge.expansion import prepare
from storyforge.editorial import STORY_CHECKS,RHETORIC_CHECKS,editorial_review
from storyforge.contracts import ContractError,delta
from storyforge.storage import save,load

PROSE='Thestor set down his hammer and forfeited his wage.'

def verdict(required,negative=False):
    checks=[{'id':k,'verdict':'fail' if negative and k==required[0] else 'pass','evidence_ids':['p001'],'reason':'The cited action directly establishes a specific consequential choice.'} for k in required]
    issues=[{'severity':'blocking','category':required[0],'evidence_ids':['p001'],'problem':'The choice contradicts the explicit author requirement.','fix':'Restore the required action while preserving the source facts.','replacement':''}] if negative else []
    return editorial_review({'pass':not negative,'checks':checks,'issues':issues},PROSE,required)

class AdjudicationTests(unittest.TestCase):
    def setup_scene(self,p):
        stage('prepare',p/'none',p/'base',request_file='classic-universe-practice',profile='fast',backend='fixture')
        state=prepare(p/'base/snapshot.json',p/'prepared');card=state['plan']['scenes'][0]
        save(p/'inputs/state/snapshot.json',state);save(p/'inputs/edited/prose.txt',PROSE)
        save(p/'inputs/diagnosis/review.json',verdict(STORY_CHECKS))
        save(p/'inputs/rhetoric/review.json',verdict(RHETORIC_CHECKS,True))
        return state,card

    def final_response(self,negative=False):
        def call(executor,role,packet,instruction,**kw):
            self.assertEqual(executor.req['max_stage_retries'],0)
            self.assertIn('ONE REALLY STRICT',instruction)
            return kw['validator'](verdict(CHECKS,negative))
        return call

    def run_to_accept(self,p,negative=False,unavailable=False,memory_pass=True):
        state,card=self.setup_scene(p)
        effect=RuntimeError('provider unavailable') if unavailable else self.final_response(negative)
        with patch('storyforge.inference.Executor.call',autospec=True,side_effect=effect) as calls:
            stage('repair',p/'inputs',p/'repair',backend='fixture')
            self.assertEqual(calls.call_count,1)
        save(p/'verify/state/snapshot.json',state);save(p/'verify/edited/prose.txt',PROSE);save(p/'verify/edited/repair.json',load(p/'repair/repair.json'))
        save(p/'verify/diagnosis/review.json',verdict(STORY_CHECKS));save(p/'verify/rhetoric/review.json',verdict(RHETORIC_CHECKS,True))
        with patch('storyforge.inference.Executor.call',side_effect=AssertionError('No repeated review or rewrite')):
            stage('verify',p/'verify',p/'story-final',backend='fixture')
            stage('verify_rhetoric',p/'verify',p/'rhetoric-final',backend='fixture')
            save(p/'accept/state/snapshot.json',state);save(p/'accept/edited/prose.txt',PROSE);save(p/'accept/edited/repair.json',load(p/'repair/repair.json'))
            save(p/'accept/story-review/review.json',load(p/'story-final/review.json'));save(p/'accept/rhetoric-review/review.json',load(p/'rhetoric-final/review.json'))
            memory=delta({'memories':[{'kind':'event','text':'Thestor forfeited his wage.','evidence_ids':['p001'],'known_by':['thestor']}]},PROSE,[c['id'] for c in state['request']['characters']])
            save(p/'accept/memory/memory.json',memory)
            mr={'pass':memory_pass,'issues':[] if memory_pass else [{'severity':'blocking','category':'knowledge','quote':PROSE,'problem':'Knowledge holder is unsupported.','fix':'Withhold the extracted fact.'}]}
            save(p/'accept/memory-review/review.json',mr)
            result=stage('accept',p/'accept',p/'final',backend='fixture')
        return state,result

    def test_positive_final_check_is_reused_without_extra_chapter_review(self):
        with tempfile.TemporaryDirectory() as d:
            old,new=self.run_to_accept(Path(d))
            self.assertEqual(new['accepted'][0]['quality_status'],'reviewed');self.assertTrue(new['accepted'][0]['canon_committed'])
            self.assertEqual(len(new['memories']),len(old['memories'])+1)

    def test_negative_final_check_moves_on_as_draft_without_new_canon(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);old,new=self.run_to_accept(p,negative=True)
            self.assertTrue(new['complete']);self.assertEqual(new['accepted'][0]['quality_status'],'needs_review');self.assertFalse(new['accepted'][0]['canon_committed'])
            self.assertEqual(new['memories'],old['memories']);self.assertTrue((p/'final/PROVISIONAL_STORY.txt').exists());self.assertFalse((p/'final/FINAL_STORY.txt').exists())

    def test_unavailable_final_check_never_becomes_an_approval(self):
        with tempfile.TemporaryDirectory() as d:
            old,new=self.run_to_accept(Path(d),unavailable=True)
            self.assertFalse(new['accepted'][0]['canon_committed']);self.assertEqual(new['memories'],old['memories'])

    def test_editorial_pass_cannot_override_failed_memory_verification(self):
        with tempfile.TemporaryDirectory() as d:
            old,new=self.run_to_accept(Path(d),memory_pass=False)
            self.assertEqual(new['memories'],old['memories']);self.assertFalse(new['accepted'][0]['canon_committed'])

    def test_cached_decision_is_one_call_and_rejects_stale_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.setup_scene(p)
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=self.final_response()) as calls:
                a=decide(state['request'],state,card,PROSE,[],p/'decision','fixture')
                b=decide(state['request'],state,card,PROSE,[],p/'decision','fixture')
                self.assertEqual(a,b);self.assertEqual(calls.call_count,1)
                with self.assertRaises(ContractError):decide(state['request'],state,card,PROSE+' Changed.',[],p/'decision','fixture')
                self.assertEqual(calls.call_count,1)
                changed=copy.deepcopy(state);changed['memories'].append({'text':'A changed canonical fact.','kind':'event','known_by':['public']})
                with self.assertRaises(ContractError):decide(state['request'],changed,card,PROSE,[],p/'decision','fixture')
                self.assertEqual(calls.call_count,1)

    def test_model_cannot_waive_mechanical_author_constraints(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);state,card=self.setup_scene(p)
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=self.final_response()):
                result=decide(state['request'],state,card,'"Hello," Thestor said.',[],p/'decision','worker')
            self.assertFalse(result['verdict']['pass'])
            self.assertIn('no-dialogue',result['mechanical_override'])
