import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from storyforge.memory_recovery import recover,prose_findings
from storyforge.contracts import ContractError
from storyforge.experimental import dispatch,UNHANDLED
from storyforge.storage import save,load
from storyforge.patching import digest

PROSE='An iron tripod was offered. The silver tripod would buy passage.'
OLD={'memories':[{'text':'Residue clung to his thumb.'}]}
NEW={'memories':[{'text':'Residue clung to his nail.'}]}
def finding(target):
    return {'target':target,'severity':'blocking','category':'fact_contradiction','quote':'iron tripod','problem':'The tripod changes material.','fix':'Keep its material consistent.'}

class RecoveryTests(unittest.TestCase):
    def test_memory_only_rejection_is_regenerated_and_independently_rechecked(self):
        extract=Mock(return_value=copy.deepcopy(NEW));verify=Mock(side_effect=[{'pass':False,'issues':[finding('memory')]},{'pass':True,'issues':[]}])
        with tempfile.TemporaryDirectory() as d:
            result,verdict=recover(None,{},Path(d),PROSE,{},'Extract',extract,verify,result=copy.deepcopy(OLD))
            self.assertEqual(result,NEW);self.assertTrue(verdict['pass'])
            self.assertEqual(verify.call_count,2);self.assertEqual(extract.call_count,1)
            self.assertEqual(extract.call_args.args[4]['rejected_memory'],OLD)
            self.assertEqual(load(Path(d)/'memory-rejected.json'),OLD)

    def test_repeated_rejection_stays_rejected_and_stops_after_one_regeneration(self):
        extract=Mock(return_value=copy.deepcopy(NEW));verify=Mock(return_value={'pass':False,'issues':[finding('memory')]})
        with tempfile.TemporaryDirectory() as d:
            _,verdict=recover(None,{},Path(d),PROSE,{},'Extract',extract,verify,result=copy.deepcopy(OLD))
            self.assertFalse(verdict['pass']);self.assertEqual(extract.call_count,1);self.assertEqual(verify.call_count,2)

    def test_prose_contradiction_routes_to_paragraph_repair_without_memory_only_retry(self):
        extract=Mock();verdict={'pass':False,'issues':[finding('prose'),finding('memory')]}
        with tempfile.TemporaryDirectory() as d:
            result,review=recover(None,{},Path(d),PROSE,{},'Extract',extract,Mock(return_value=verdict),result=copy.deepcopy(OLD))
            extract.assert_not_called();self.assertFalse(review['pass']);self.assertEqual(result,OLD)
            routed=prose_findings(review,PROSE)
            self.assertEqual(len(routed['issues']),1);self.assertEqual(routed['issues'][0]['paragraph'],0)
            self.assertEqual(routed['issues'][0]['evidence_ids'],['p001']);self.assertEqual(routed['reviewed_sha256'],digest(PROSE))

    def test_empty_recovery_cannot_turn_nonempty_rejected_memory_into_pass(self):
        with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(ContractError,'discard all'):
            recover(None,{},Path(d),PROSE,{},'Extract',Mock(return_value={'memories':[]}),Mock(return_value={'pass':False,'issues':[finding('memory')]}),result=copy.deepcopy(OLD))

    def test_accept_uses_corrected_memory_artifact_and_matching_prose_reviews(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'inputs';out=root/'out'
            save(source/'edited/prose.txt',PROSE)
            save(source/'memory/memory.json',OLD)
            save(source/'final-memory/memory.json',OLD)
            save(source/'memory-review/memory.json',NEW)
            save(source/'memory-review/review.json',{'pass':True,'issues':[]})
            for name in ['initial-story','initial-rhetoric']:
                save(source/name/'review.json',{'reviewed_sha256':digest(PROSE),'pass':True,'issues':[]})
            result=dispatch('accept',source,out,{'request':{'execution_policy':{}}},0,'small','fixture','unused')
            self.assertIs(result,UNHANDLED);self.assertEqual(load(source/'memory/memory.json'),NEW)

    def test_live_workflow_repairs_memory_discovered_prose_errors(self):
        for filename in ['troy-practice.yml','troy-parallel-experiment.yml']:
            text=(Path('.github/workflows')/filename).read_text()
            self.assertIn("needs.s01_memory.outputs.needs_repair == 'true'",text)
            self.assertIn('needs: [s01_design, s01_edit, s01_story, s01_rhetoric, s01_memory]',text)
            self.assertIn('path: inputs/initial-memory',text)
