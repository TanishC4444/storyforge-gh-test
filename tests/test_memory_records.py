"""Record repair freezes valid facts and cannot overwrite resource history."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.contracts import request,ContractError
from storyforge.evidence import payload
from storyforge.inference import Executor
from storyforge.resilience import memory_extract
from storyforge.storage import load

PROSE='Tony and Yinsen watched Omer put a manifest on the bench.\n\nTony used three rolls of gauze to insulate the coil.\n\nTony and Yinsen still owed each other a joint escape plan.'
PRIOR=[{'id':'stock','kind':'resource','fact_key':'workshop-stock','text':'Medical dressings are restricted.','known_by':['tony','yinsen']}]

class MemoryRecordTests(unittest.TestCase):
    def req(self):
        r=request(load('examples/iron-man-alternate-origin.json'));r['profile']='fast';r['max_stage_retries']=0
        r['characters'].append({'id':'omer','name':'Omer'})
        return r
    def raw(self):
        return {'memories':[
            {'kind':'event','text':'Omer put a manifest on the bench.','known_by':['tony','yinsen','omer'],'evidence_ids':['p001'],'fact_key':'manifest','supersedes':[]},
            {'kind':'thread','text':'Tony and Yinsen still owed each other a joint escape plan.','evidence_ids':['p003'],'fact_key':'thread:shared-escape','thread_id':'shared-escape','thread_state':'escalating','supersedes':[]},
            {'kind':'event','text':'Tony used three rolls of gauze to insulate the coil.','known_by':['tony','yinsen'],'evidence_ids':['p002'],'fact_key':'spent-dressings','supersedes':['stock']}]}
    def patches(self):return {'repairs':{'r1':{'known_by':['tony','yinsen']},'r2':{'fact_key':'spent-dressings','supersedes':[]}}}
    def run_extract(self,d,raw,fixes):
        req=self.req();packet={**payload(PROSE),'prior_canon':copy.deepcopy(PRIOR)}
        with patch('storyforge.hosted.GoogleHosted.complete',side_effect=[(json.dumps(raw),{'finish_reason':'stop','model':'first'}),(json.dumps(fixes),{'finish_reason':'stop','model':'backup'})]) as provider:
            value=memory_extract(Executor(req,d,'worker'),req,d,PROSE,packet,'Extract all material facts.')
        return value,provider
    def test_missing_witnesses_and_invalid_resource_link_are_repaired_together(self):
        raw=self.raw();before=copy.deepcopy(raw)
        with tempfile.TemporaryDirectory() as d:
            result,provider=self.run_extract(d,raw,self.patches())
            self.assertEqual(provider.call_count,2);self.assertEqual(len(result['memories']),3)
            for k,v in raw['memories'][0].items():self.assertEqual(result['memories'][0][k],v)
            self.assertEqual(result['memories'][1]['known_by'],['tony','yinsen'])
            self.assertEqual(result['memories'][2]['kind'],'event');self.assertEqual(result['memories'][2]['supersedes'],[])
            self.assertEqual(result['memories'][2]['text'],raw['memories'][2]['text'])
            report=load(Path(d)/'memory-record-repairs.json');self.assertEqual(report['valid_record_indices_preserved'],[0])
            packet=load(next((Path(d)/'record-repair/packets').glob('*.json')))['input']
            self.assertEqual([p['record_index'] for p in packet['records_needing_repair']],[1,2])
            self.assertIn({'id':'omer','name':'Omer'},packet['character_registry'])
        self.assertEqual(raw,before);self.assertEqual(PRIOR[0]['fact_key'],'workshop-stock')
    def test_multiple_faults_in_one_record_are_fixed_in_one_pass(self):
        raw=self.raw();raw['memories'][1]['text']='Too long. '*100
        fixes=self.patches();fixes['repairs']['r1']['text']='Tony and Yinsen still owed each other a joint escape plan.'
        with tempfile.TemporaryDirectory() as d:
            result,provider=self.run_extract(d,raw,fixes)
            self.assertEqual(provider.call_count,2);self.assertEqual(result['memories'][1]['text'],fixes['repairs']['r1']['text'])
    def test_foreign_sibling_edits_are_rejected_and_valid_records_retained(self):
        raw=self.raw();fixes=self.patches();fixes['repairs']['r0']={'text':'A fabricated replacement.'}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ContractError,'recovery failed'):self.run_extract(d,raw,fixes)
            partial=load(Path(d)/'memory-partial.json')
            self.assertTrue(partial['unverified']);self.assertEqual(len(partial['memories']),1)
            self.assertEqual(partial['memories'][0]['text'],raw['memories'][0]['text'])
            self.assertEqual(load(Path(d)/'memory-rejected-records.json'),raw)
    def test_unknown_character_ids_cannot_be_defaulted_or_accepted(self):
        raw=self.raw();fixes=self.patches();fixes['repairs']['r1']['known_by']=['invented-person']
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ContractError,'recovery failed'):self.run_extract(d,raw,fixes)
            self.assertTrue(load(Path(d)/'memory-partial.json')['unverified'])
    def test_nested_holder_types_reach_recovery_instead_of_crashing(self):
        raw=self.raw();raw['memories'][1]['known_by']=[{'name':'Tony'}]
        with tempfile.TemporaryDirectory() as d:
            result,_=self.run_extract(d,raw,self.patches())
            self.assertEqual(result['memories'][1]['known_by'],['tony','yinsen'])
    def test_invalid_supersedes_shapes_are_repaired_without_changing_fact(self):
        raw=self.raw();raw['memories'][2]['supersedes']='stock'
        fixes=self.patches();fixes['repairs']['r2']={'supersedes':[]}
        with tempfile.TemporaryDirectory() as d:
            result,_=self.run_extract(d,raw,fixes)
            self.assertEqual(result['memories'][2]['supersedes'],[])
    def test_outer_array_can_be_normalized_without_losing_any_fact(self):
        raw=self.raw();raw['memories'][1]['known_by']=['tony','yinsen'];raw['memories'][2]['supersedes']=[]
        req=self.req()
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',return_value=(json.dumps(raw['memories']),{'finish_reason':'stop','model':'first'})) as provider:
            result=memory_extract(Executor(req,d,'worker'),req,d,PROSE,{**payload(PROSE),'prior_canon':PRIOR},'Extract facts.')
            self.assertEqual(provider.call_count,1);self.assertEqual(len(result['memories']),3)

    def test_unverified_memory_stops_at_handoff_and_keeps_the_draft(self):
        from storyforge import living_stages as stages
        from storyforge.storage import save
        state={'request':self.req(),'plan':{'scenes':[{'id':'ch01-sc01'}]}}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);save(root/'source/state/snapshot.json',state)
            save(root/'source/edited/prose.txt','The scene remains available for recovery.')
            save(root/'source/memory-review/review.json',{'pass':False,'unverified':True,'error':'A witness list remains unresolved'})
            with patch('storyforge.living_stages.stage',side_effect=AssertionError('No acceptance without verified memory')):
                with self.assertRaisesRegex(ContractError,'Memory handoff blocked before acceptance'):
                    stages.execute('accept',root/'source',root/'out',0,'fixture')
            self.assertEqual((root/'out/prose.txt').read_text(),'The scene remains available for recovery.')
            self.assertFalse(load(root/'out/blocked-handoff.json')['canon_committed'])
            self.assertFalse((root/'out/snapshot.json').exists())
