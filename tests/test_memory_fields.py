"""Memory defaults preserve source and metadata; model repair owns only text."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.contracts import request,ContractError
from storyforge.evidence import payload
from storyforge.inference import Executor
from storyforge.resilience import memory_extract
from storyforge.memory_fields import source_defaults
from storyforge.storage import load,save
from storyforge import memory_batches as m,batch_pipeline as b

class MemoryFieldTests(unittest.TestCase):
    def req(self):
        req=request(load('examples/living-scale-practice.json'));req['profile']='fast';req['max_stage_retries']=0
        return req
    def record(self):
        return {'kind':'thread','thread_id':'return-lyra','thread_state':'escalating','fact_key':'thread:return-lyra','supersedes':[],'known_by':['lyra'],'evidence_ids':['p001']}
    def test_schema_requires_nonempty_bounded_text_even_for_threads(self):
        from storyforge.output_schema import memory_schema
        item=memory_schema(payload('Lyra kept the borrowed pin.'),['lyra'])['properties']['memories']['items']
        self.assertIn('text',item['required']);self.assertEqual(item['properties']['text'],{'type':'string','minLength':1,'maxLength':600})
    def test_short_complete_source_is_default_without_an_extra_api_call(self):
        prose='Lyra kept the borrowed pin, but her promise to return it remained unpaid.'
        raw={'memories':[self.record()]};before=copy.deepcopy(raw)
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',return_value=(json.dumps(raw),{'finish_reason':'stop','model':'test'})) as provider:
            result=memory_extract(Executor(self.req(),d,'worker'),self.req(),d,prose,{**payload(prose),'prior_canon':[]},'Extract memory.')
            self.assertEqual(provider.call_count,1);fact=result['memories'][0]
            self.assertEqual(fact['text'],prose)
            for key,value in before['memories'][0].items():self.assertEqual(fact[key],value)
            self.assertEqual(load(Path(d)/'memory-field-defaults.json')['changes'][0]['method'],'complete_verbatim_evidence')
        self.assertEqual(raw,before)
    def test_long_evidence_gets_only_missing_text_repaired_and_keeps_siblings(self):
        prose=('Lyra held the borrowed pin and still owed its return. '+('The rain struck the gate. '*30)).rstrip()+'\n\nThe gate opened.'
        raw={'memories':[{'kind':'event','text':'The gate opened.','fact_key':'gate-open','supersedes':[],'known_by':['lyra'],'evidence_ids':['p002']},self.record()]}
        fixed='Lyra retained the borrowed pin and still owed its return.'
        responses=[(json.dumps(raw),{'finish_reason':'stop','model':'test'}),(json.dumps({'repairs':[{'record_index':1,'text':fixed}]}),{'finish_reason':'stop','model':'backup'})]
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=responses) as provider:
            result=memory_extract(Executor(self.req(),d,'worker'),self.req(),d,prose,{**payload(prose),'prior_canon':[]},'Extract memory.')
            self.assertEqual(provider.call_count,2)
            self.assertEqual(result['memories'][1]['text'],fixed)
            for index,original in enumerate(raw['memories']):
                for key,value in original.items():self.assertEqual(result['memories'][index][key],value)
            packet=load(next((Path(d)/'text-repair/packets').glob('*.json')))['input']
            self.assertEqual([r['record_index'] for r in packet['records_needing_text']],[1])
            self.assertEqual([p['id'] for p in packet['evidence_passages']],['p001'])
            self.assertNotIn('The gate opened.',json.dumps(packet))
            self.assertEqual(load(Path(d)/'memory-field-repairs.json')['repairs'][0]['text'],fixed)
    def test_defaults_never_guess_witnesses_or_accept_foreign_evidence(self):
        prose='Lyra kept the pin.'
        for changes in [{'evidence_ids':['foreign']},{'evidence_ids':['p001'],'evidence_prose_sha256':'stale'}]:
            raw={'memories':[{**self.record(),**changes}]}
            with tempfile.TemporaryDirectory() as d:self.assertNotIn('text',source_defaults(raw,payload(prose),prose,d)['memories'][0])
        raw={'memories':[self.record()]};raw['memories'][0].pop('known_by')
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',return_value=(json.dumps(raw),{'finish_reason':'stop','model':'test'})) as provider:
            with self.assertRaisesRegex(ContractError,'knowledge holders'):
                memory_extract(Executor(self.req(),d,'worker'),self.req(),d,prose,{**payload(prose),'prior_canon':[]},'Extract memory.')
            self.assertEqual(provider.call_count,1)
    def test_field_repair_cannot_mutate_metadata_or_hide_failure(self):
        prose='Lyra owed the return of the pin. '+('Rain fell against the gate. '*30)
        raw={'memories':[self.record()]}
        response={'repairs':[{'record_index':0,'text':'Lyra owed the pin.','known_by':['public']}]}
        with tempfile.TemporaryDirectory() as d,patch('storyforge.hosted.GoogleHosted.complete',side_effect=[(json.dumps(raw),{'finish_reason':'stop','model':'test'}),(json.dumps(response),{'finish_reason':'stop','model':'backup'})]):
            with self.assertRaisesRegex(ContractError,'Memory field-only recovery failed'):
                memory_extract(Executor(self.req(),d,'worker'),self.req(),d,prose,{**payload(prose),'prior_canon':[]},'Extract memory.')
            self.assertEqual((Path(d)/'memory-source.txt').read_text(),prose)
            self.assertEqual(load(Path(d)/'memory-rejected-records.json'),raw)
    def test_incomplete_extraction_schedules_one_blocked_check_and_never_passes(self):
        state={'request':self.req(),'memories':[],'accepted':[]};prose='The pin remains borrowed.'
        facts={'memories':[],'unverified':True,'error':'Record 2 could not be repaired'}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);save(root/'edited/prose.txt',prose);save(root/'memory/memory.json',facts)
            plan=m.plan(state,root,root/'plan','final')
            self.assertEqual(len(plan['batches']),1)
            self.assertEqual(plan['batches'][0]['id'],'0')
            result=m.check(state,{},root,root/'batches/blocked','worker','0')
            self.assertTrue(result['review']['unverified']);self.assertFalse(result['review']['pass'])
            self.assertIn('Record 2',result['review']['error'])
            merged=m.join(state,root,root/'joined');self.assertFalse(merged['pass']);self.assertTrue(merged['unverified'])
