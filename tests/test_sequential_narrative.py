import tempfile,unittest
from pathlib import Path
from storyforge.artifact_fetch import fetch
from storyforge.editorial_transport import factual_ids
from storyforge.contracts import ContractError
from storyforge.narrative_context import context
from storyforge.patching import digest


class SequentialNarrativeTests(unittest.TestCase):
    def test_recovery_artifacts_beyond_first_hundred_are_fetched(self):
        class API:
            def __init__(self):self.downloads=[];self.pages=[]
            def api(self,path):
                self.pages.append(path)
                rows=[{'id':i,'name':f'noise-{i}'} for i in range(100)] if '&page=1' in path else [{'id':100,'name':'quickstart'},{'id':101,'name':'s01_accept'}]
                return {'artifacts':rows,'total_count':102}
            def artifact(self,a,dest):self.downloads.append((a['name'],Path(dest)))
        api=API()
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(fetch(api,123,d,pattern='{quickstart,s*_accept}'),['quickstart','s01_accept'])
            self.assertEqual(set(api.downloads),{('quickstart',Path(d)/'quickstart'),('s01_accept',Path(d)/'s01_accept')})
            api.downloads=[];fetch(api,123,d,name='quickstart')
            self.assertEqual(api.downloads,[('quickstart',Path(d))])
        self.assertEqual(len(api.pages),4)
    def test_nonblocking_missing_suggestion_retains_advisory_and_source(self):
        prose='The clerk handed Sera the ledger.'
        v=factual_ids('PASS\nISSUE advisory | memory | category | p001 | Clarify this holder.',prose,{'p001'})
        self.assertTrue(v['pass']);self.assertEqual(len(v['issues']),1)
        self.assertEqual(v['issues'][0]['problem'],'Clarify this holder.')
        self.assertEqual(v['issues'][0]['quote'],prose)
        with self.assertRaises(ContractError):factual_ids('PASS\nISSUE advisory | memory | category | p099 | Clarify.',prose,{'p001'})
        with self.assertRaises(ContractError):factual_ids('FAIL\nISSUE blocking | memory | category | p001 | Wrong holder.',prose,{'p001'})
        self.assertFalse(factual_ids('PASS\nISSUE blocking | memory | category | p001 | Wrong holder. | Correct holder.',prose,{'p001'})['pass'])
    def test_threads_use_exact_source_and_keep_reading_order_distinct_from_time(self):
        prose='The bell rang twice before the bridge sank.'
        state={'request':{'scene_designs':[{'id':'now','time':'Today'},{'id':'past','time':'Yesterday'}]},
               'accepted':[{'id':'now','prose':prose}],
               'memories':[{'id':'m1','kind':'thread','thread_id':'bell','thread_state':'seeded','text':'Two bells preceded the collapse.','known_by':['c1'],'source':'now','evidence_prose_sha256':digest(prose),'evidence_ids':['p001']},
                           {'id':'m2','kind':'thread','thread_id':'fake','text':'Planned clue.','source':'now','evidence_prose_sha256':'stale','evidence_ids':['p001']}]}
        c=context(state,{'id':'past'})
        self.assertEqual([x['scene_id'] for x in c['reading_order']],['now','past'])
        self.assertEqual(c['established_threads'][0]['source_evidence'][0]['text'],prose)
        self.assertNotIn('source_evidence',c['established_threads'][1])
        self.assertEqual(state['memories'][0]['known_by'],['c1'])
        self.assertIn('does not reset the present',c['policy'])

if __name__=='__main__':unittest.main()
