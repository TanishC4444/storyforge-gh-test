import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.craft import validate_prose,length_status
from storyforge.contracts import ContractError,request
from storyforge.review_policy import prepare as review_policy
from storyforge.inference import ROOT
from storyforge.dag import stage
from storyforge.living_prepare import prepare
from storyforge.storage import save
from storyforge import batch_pipeline as b
from storyforge.adjudication import decide,CHECKS
from storyforge.editorial_transport import editorial

class QualityFirstLengthTests(unittest.TestCase):
    def req(self):return {'words_per_scene':100,'min_words_ratio':.8,'max_words_ratio':1.3,'length_policy':{'scene_words':'strict','overflow':'advisory'},'pov':'third person, no dialogue'}
    def text(self,n):return ' '.join('action'+str(i) for i in range(n))
    def test_excess_length_is_reported_without_truncation_or_rejection(self):
        text=self.text(160);req=self.req();self.assertEqual(validate_prose(text,req,check_length=True),text)
        status=length_status(text,req);self.assertTrue(status['advisory']);self.assertEqual(status['excess_words'],30)
        req['length_policy'].pop('overflow')
        with self.assertRaisesRegex(ContractError,'required range'):validate_prose(text,req,check_length=True)
    def test_short_incomplete_duplicate_and_forbidden_form_remain_blocked(self):
        for text in [self.text(20),self.text(80)+'\n\n'+self.text(80),'"'+self.text(160)+'"']:
            with self.subTest(text=text[:15]),self.assertRaises(ContractError):validate_prose(text,self.req(),check_length=True)
    def test_writer_keeps_long_first_response_without_a_length_only_repair_call(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);stage('prepare',p/'none',p/'base',request_file='living-scale-practice',backend='fixture')
            state=prepare(p/'base/snapshot.json',p/'quick',backend='fixture');state['request']['words_per_scene']=1100;state['request']['length_policy']['overflow']='advisory';card=state['plan']['scenes'][0]
            save(p/'source/direction/direction.txt','Preserve canon and develop the authored action.')
            b.plan_draft(state,card,p/'source',p/'source/plan','fixture');text=self.text(1596)
            with patch('storyforge.hosted.GoogleHosted.complete',return_value=(text,{'finish_reason':'stop','model':'test'})) as model:
                result=b.write_batch(state,card,p/'source',p/'out','worker','0')
            self.assertEqual(model.call_count,1);self.assertTrue(result['verified_form']);self.assertEqual(result['prose'],text);self.assertTrue(result['length_status']['advisory'])
    def test_real_editorial_failure_is_not_overridden_by_flexible_length(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);stage('prepare',p/'none',p/'base',request_file='living-scale-practice',backend='fixture')
            state=prepare(p/'base/snapshot.json',p/'quick',backend='fixture');req=state['request'];req['length_policy']['overflow']='advisory';card=state['plan']['scenes'][0];text=self.text(1596)
            checks=[{'id':c,'verdict':'fail' if c=='scene_change' else 'pass','evidence_ids':['p001'],'reason':'The actual source fails to enact the authored consequential choice.' if c=='scene_change' else 'The supplied source satisfies the required dimension.'} for c in CHECKS]
            result=editorial({'checks':checks,'issues':[{'severity':'blocking','category':'scene_change','evidence_ids':['p001'],'problem':'No enacted consequential choice.','fix':'Develop the authored choice without padding.'}]},text,CHECKS)
            with patch('storyforge.editorial_transport.call_editorial',return_value=result):final=decide(req,state,card,text,[],p/'final','worker')
            self.assertFalse(final['verdict']['pass']);self.assertTrue(final['length_status']['advisory']);self.assertIsNone(final['mechanical_override'])
            packet,_,policy=review_policy(req,'chapter_quality',{'scene':card},'',ROOT)
            self.assertIn('excess word count alone is advisory',policy);self.assertIn('repetition',policy)
    def test_unknown_overflow_policy_is_rejected(self):
        req=json.loads(Path('examples/stress-ensemble.json').read_text());req['length_policy']['overflow']='ignore_quality'
        with self.assertRaisesRegex(ContractError,'overflow'):request(req)
    def test_saved_length_rejected_draft_is_reused_without_calling_a_writer(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);stage('prepare',p/'none',p/'base',request_file='living-scale-practice',backend='fixture')
            state=prepare(p/'base/snapshot.json',p/'quick',backend='fixture');old_state=copy.deepcopy(state);state['request']['length_policy']['overflow']='advisory';card=state['plan']['scenes'][0];text=self.text(1596)
            try:validate_prose(text,old_state['request'],check_length=True)
            except ValueError as exc:error=str(exc)
            old={'id':'0','scene_id':card['id'],'state_sha256':b.bind_state(old_state),'prose':text,'verified_form':False,'errors':['repair failed after bounded retries: '+error]}
            save(p/'source/reused/s01_design/snapshot.json',old_state);save(p/'source/reused/s01_write_batches-0/draft-batch.json',old)
            save(p/'source/direction/direction.txt','Preserve the authored scene.')
            b.plan_draft(state,card,p/'source',p/'source/plan','fixture')
            with patch('storyforge.inference.Executor.call',side_effect=AssertionError('Do not rewrite saved prose for length')):result=b.write_batch(state,card,p/'source',p/'out','worker','0')
            self.assertEqual(result['prose'],text);self.assertTrue(result['verified_form']);self.assertIn('unreviewed',result['reused_draft']['policy'])
            for mutate in ['brief','canon','transport']:
                saved=copy.deepcopy(old_state);draft=copy.deepcopy(old)
                if mutate=='brief':saved['request']['premise']+=' A different story.';draft['state_sha256']=b.bind_state(saved)
                elif mutate=='canon':saved['memories']=[];draft['state_sha256']=b.bind_state(saved)
                else:draft['errors']=['Hosted generation did not finish naturally: MAX_TOKENS']
                save(p/'source/reused/s01_design/snapshot.json',saved);save(p/'source/reused/s01_write_batches-0/draft-batch.json',draft)
                with self.subTest(mutate=mutate),self.assertRaises(ContractError):b.write_batch(state,card,p/'source',p/'rejected','worker','0')

if __name__=='__main__':unittest.main()
