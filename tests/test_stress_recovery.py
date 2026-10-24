import copy,io,json,os,tempfile,time,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from storyforge.contracts import request,delta,ContractError
from storyforge.evidence import payload
from storyforge.inference import Executor
from storyforge.resilience import memory_extract
from storyforge.hosted import GoogleHosted
from storyforge.working_context import concise_packet
from storyforge.provider_recovery import configuration

class StressRecoveryTests(unittest.TestCase):
    def req(self):return request(json.loads(Path('examples/stress-screenplay.json').read_text()))
    def test_location_metadata_can_be_removed_without_overwriting_life_or_location(self):
        req=self.req();prose='Mara stands at the quay with two tokens.'
        old={'id':'m1','kind':'event','fact_key':'location:c01','text':'Mara starts at the quay.','known_by':['c01']}
        record={'kind':'event','fact_key':'location:c01','text':'Mara stands at the quay with two tokens.','known_by':['c01'],'evidence_ids':['p001'],'supersedes':['m1'],'subject':'c01','life_state':'alive'}
        fixes={'repairs':{'r0':{'kind':'event','fact_key':'location:c01','supersedes':['m1'],'subject':None,'life_state':None}}}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=[(json.dumps({'memories':[record]}),{'finish_reason':'stop'}),(json.dumps(fixes),{'finish_reason':'stop'})]):
            result=memory_extract(Executor(req,d,'worker'),req,d,prose,{**payload(prose),'prior_canon':[old]},'Extract changes.')
        fact=result['memories'][0];self.assertEqual(fact['fact_key'],'location:c01');self.assertEqual(fact['supersedes'],['m1']);self.assertNotIn('life_state',fact);self.assertNotIn('subject',fact)
    def test_accidental_thread_fields_can_be_removed_from_claim(self):
        req=self.req();prose='Tomas says the dispensary is empty.'
        record={'kind':'claim','text':prose,'known_by':['c01','c04'],'claim_source':'c04','evidence_ids':['p001'],'fact_key':'claim:stores','supersedes':[],'thread_id':'stores','thread_state':'open'}
        fixes={'repairs':{'r0':{'kind':'claim','fact_key':'claim:stores','supersedes':[],'thread_id':None,'thread_state':None}}}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=[(json.dumps({'memories':[record]}),{'finish_reason':'stop'}),(json.dumps(fixes),{'finish_reason':'stop'})]):
            result=memory_extract(Executor(req,d,'worker'),req,d,prose,{**payload(prose),'prior_canon':[]},'Extract changes.')
        self.assertEqual(result['memories'][0]['kind'],'claim');self.assertNotIn('thread_id',result['memories'][0])
    def test_required_life_and_thread_state_cannot_be_deleted_to_pass(self):
        base={'kind':'event','text':'Mara died at the quay.','known_by':['c01'],'evidence_ids':['p001'],'fact_key':'life:c01'}
        with self.assertRaisesRegex(ContractError,'lifecycle'):delta({'memories':[base]},base['text'],['c01'])
        base.update(kind='thread',fact_key='thread:quay')
        with self.assertRaisesRegex(ContractError,'plot thread'):delta({'memories':[base]},base['text'],['c01'])
    def test_small_script_has_room_for_visible_text_and_thinking(self):
        calls=[]
        def serve(req,timeout):
            calls.append(json.loads(req.data));return io.BytesIO(json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'Complete script.'}]}}]}).encode())
        with tempfile.TemporaryDirectory() as d,patch('urllib.request.urlopen',side_effect=serve):
            h=GoogleHosted(d,key='test',backup_keys=[],distinct_projects=False)
            h.complete('lite','system','prompt',1360,role='writer_beat',policy={'timeout':20,'quality_routing':True,'estimate_small_calls':True,'estimate_max_bytes':10000,'output_retry_reserve':1024})
        self.assertEqual(calls[-1]['generationConfig']['maxOutputTokens'],4432)
    def test_repeated_hash_projection_is_lossless_and_preserves_all_facts(self):
        req=self.req();facts=[{'id':str(i),'text':'Distinct fact '+str(i),'known_by':['c01'],'evidence_prose_sha256':'a'*64} for i in range(200)]
        packet={'prior_canon':{'facts':facts},'pov_known_facts':{'facts':copy.deepcopy(facts)}}
        original=copy.deepcopy(packet);result=concise_packet(packet,req)
        self.assertEqual(packet,original);self.assertEqual(len(result['prior_canon']['facts']),200)
        restored=copy.deepcopy(result['prior_canon']['facts'])
        for fact in restored:fact['evidence_prose_sha256']=result['evidence_source_fingerprints'][fact.pop('evidence_source_ref')]
        self.assertEqual(restored,facts);self.assertLess(len(json.dumps(result)),len(json.dumps(packet)))
    def test_expanded_project_failover_is_still_bounded(self):
        req=self.req();self.assertEqual(configuration(req)['extra_requests'],12);self.assertEqual(req['execution_policy']['max_hosted_requests'],6)
        req['execution_policy']['provider_outage_recovery']['extra_requests']=13
        with self.assertRaises(ContractError):configuration(req)
    def test_output_only_truncation_does_not_trigger_capacity_sleep(self):
        from storyforge.provider_recovery import wait_to_retry
        from storyforge.hosted import HostedError
        with tempfile.TemporaryDirectory() as d,patch('storyforge.provider_recovery.time.sleep',side_effect=AssertionError('Not an outage')):
            self.assertFalse(wait_to_retry([HostedError('Hosted generation did not finish naturally: MAX_TOKENS')],d,'writer_beat',1,configuration(self.req())))
    def test_expanded_context_cannot_be_used_with_implicit_local_fallback(self):
        req=self.req();req['context_chars']=192000
        self.assertEqual(request(copy.deepcopy(req))['context_chars'],192000)
        req['execution_policy']['hosted_required_roles']=[]
        with self.assertRaisesRegex(ContractError,'hosted-only'):request(req)
    def test_truncated_visible_prose_is_preserved_but_not_accepted(self):
        from storyforge.hosted import HostedError
        from storyforge.batch_pipeline import cached_prose
        result={'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'Hidden reasoning.','thought':True},{'text':'Mara reaches the quay, but'}]}}]}
        with tempfile.TemporaryDirectory() as d,patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(result).encode())):
            h=GoogleHosted(d,key='test',backup_keys=[],distinct_projects=False)
            with self.assertRaisesRegex(HostedError,'MAX_TOKENS'):h.complete('lite','s','p',100,role='writer_beat',policy={'timeout':20,'quality_routing':True,'estimate_small_calls':True,'estimate_max_bytes':10000})
            saved=json.loads((Path(d)/'incomplete-generation.json').read_text());self.assertFalse(saved['verified']);self.assertNotIn('Hidden reasoning',saved['text']);self.assertEqual(cached_prose(d),'Mara reaches the quay, but')
    def test_nineteen_project_pool_waits_then_uses_fresh_projects(self):
        clock=[0.];base=time.time();calls=[];req=self.req()
        def serve(http_request,timeout):
            calls.append((http_request.get_header('X-goog-api-key'),clock[0]))
            if len(calls)<=6:raise urllib.error.HTTPError('https://example.invalid',503,'Unavailable',{'Retry-After':'60'},io.BytesIO(b'{"error":{"status":"UNAVAILABLE"}}'))
            return io.BytesIO(json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'Recovered transport candidate.'}]}}]}).encode())
        def sleep(seconds):clock[0]+=seconds
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'GEMINI_API_KEY':'test-project-0','GEMINI_API_KEYS':json.dumps(['test-project-'+str(i) for i in range(1,19)]),'GEMINI_DISTINCT_PROJECTS':'true','STORY_QUOTA_DIR':str(Path(d)/'quota'),'GITHUB_JOB':'pool-test','STORY_BATCH':'0'}),patch('urllib.request.urlopen',side_effect=serve),patch('storyforge.provider_recovery.random.uniform',return_value=0),patch('storyforge.provider_recovery.time.monotonic',side_effect=lambda:clock[0]),patch('storyforge.provider_recovery.time.time',side_effect=lambda:base+clock[0]),patch('storyforge.provider_recovery.time.sleep',side_effect=sleep),patch('storyforge.local_worker.execute',side_effect=AssertionError('No immediate CPU downgrade')):
            result=Executor(req,d,'worker').call('writer_beat',{},'Transport test only.',tokens=100,output_format='text')
            pool=json.loads((Path(d)/'provider-pool.json').read_text());self.assertEqual(pool['independent_projects'],19)
        self.assertEqual(result,'Recovered transport candidate.');self.assertEqual(len(calls),7)
        self.assertEqual(len({key for key,_ in calls}),7);self.assertGreaterEqual(calls[-1][1],60)

if __name__=='__main__':unittest.main()
