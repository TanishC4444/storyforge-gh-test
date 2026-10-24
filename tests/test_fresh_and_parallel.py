import copy,io,json,os,shutil,tempfile,unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import yaml
from storyforge import planned_parallel as pp,memory_batches as memory,batch_pipeline as b
from storyforge.storage import load,save
from storyforge.dag import stage
from storyforge.living_prepare import prepare
from storyforge.fresh_resume import restore
from storyforge.universe_events import normalize_existing_cast,extended_request
from storyforge.contracts import ContractError


class FreshAndParallelTests(unittest.TestCase):
    def test_existing_cast_alias_is_normalized_without_overwriting_profile(self):
        req={'characters':[{'id':'c05','name':'Nadi Vale','goal':'Immutable goal.'}]}
        proposal={'new_characters':[{'id':'c05','name':'Nadi Vale','goal':'Wrong replacement goal.'}]}
        value=normalize_existing_cast(req,proposal)
        self.assertEqual(value['new_characters'],[]);self.assertEqual(req['characters'][0]['goal'],'Immutable goal.')
        self.assertEqual(len(proposal['new_characters']),1)
        wrong={'new_characters':[{'id':'c05','name':'Another Person'}]}
        self.assertEqual(normalize_existing_cast(req,wrong),wrong)
        with self.assertRaises(ContractError):extended_request(req,wrong)
    def test_mixed_attempt_memory_artifacts_ignore_old_plan_but_not_missing_current_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with redirect_stdout(io.StringIO()):
                stage('prepare',p/'none',p/'prepared',request_file='hard-chronology',profile='fast',backend='fixture')
                state=prepare(p/'prepared/snapshot.json',p/'quick')
            prose='Mara waited.';save(p/'edited/prose.txt',prose);save(p/'memory/memory.json',{'memories':[]})
            plan=memory.plan(state,p,p/'plan','final')
            for item in plan['batches']:memory.check(state,state['plan']['scenes'][0],p,p/'batches'/item['id'],'fixture',item['id'])
            save(p/'batches/leftover/memory-check-batch.json',{'id':'999','plan_sha256':'previous-attempt','review':{'pass':True,'issues':[]}})
            self.assertTrue(memory.join(state,p,p/'out')['pass'])
            shutil.rmtree(p/'batches'/plan['batches'][0]['id'])
            verdict=memory.join(state,p,p/'missing');self.assertFalse(verdict['pass']);self.assertTrue(verdict['missing_batches'])
    def test_fresh_import_keeps_approved_prefix_and_rechecks_unfinished_drafts(self):
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()):
            p=Path(d);source=p/'source'
            stage('prepare',p/'none',p/'prepared',request_file='hard-chronology',profile='fast',backend='fixture')
            base=prepare(p/'prepared/snapshot.json',source/'quickstart')
            state=copy.deepcopy(base);prose='Mara waited at the quay.';review={'pass':True,'issues':[]}
            accepted={**state['plan']['scenes'][0],'prose':prose,'canon_committed':True,'quality_status':'reviewed','review':review,'rhetoric_review':review,'memory_review':review}
            state['accepted']=[accepted];state['version']=1
            save(source/'s01_accept/snapshot.json',state)
            save(source/'s01_accept/acceptance-state.json',base);save(source/'s01_accept/consumed-memory.json',{'memories':[]});save(source/'s01_accept/acceptance-binding.json',{})
            proof={'pass':True,'source_sha256':b.digest(prose),'state_sha256':b.bind_state(base),'memory_sha256':b.bind_state({'memories':[]})}
            save(source/'s01_accept/consumed-proof.json',proof)
            save(source/'s02_final_check/prose.txt','Sera entered the archive yesterday.')
            restored=restore(base,source,p/'fresh')
            self.assertEqual(restored['accepted'],state['accepted']);self.assertEqual(restored['memories'],state['memories'])
            self.assertEqual(restored['fresh_resume']['resume_index'],1)
            self.assertFalse(restored['fresh_drafts']['1']['approved'])
            self.assertTrue((p/'fresh/seed-results/s01_accept/consumed-proof.json').exists())
            changed=copy.deepcopy(base);changed['request']['world_rules'].append('Different world.')
            with self.assertRaisesRegex(ContractError,'same author brief'):restore(changed,source,p/'wrong')
    def test_parallel_full_transport_and_stale_patch_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);bundle=pp.prepare('hard-chronology',p/'prepare');bundle=pp.outline(bundle,p/'outline','fixture')
            for card in bundle['plan']['scenes']:pp.refine(bundle,card['id'],p/'descriptions'/card['id'],'fixture')
            bundle=pp.lock(bundle,p/'descriptions',p/'locked','fixture')
            for card in bundle['plan']['scenes']:
                scene=pp.write(bundle,card['id'],p/'drafts'/card['id'],'fixture')
                pp.check_scene(bundle,scene,p/'checked'/card['id'],'fixture')
            audit=pp.audit(bundle,p/'checked',p/'audit','fixture')
            for card in bundle['plan']['scenes']:
                scene=load(p/'checked'/card['id']/'scene.json');pp.patch(bundle,scene,audit,p/'patched'/card['id'],'fixture')
            report=pp.publish(bundle,p/'patched',p/'final','fixture')
            self.assertTrue(report['pass']);self.assertEqual(report['scenes'],4)
            state=load(p/'final/snapshot.json');self.assertEqual(len(state['accepted']),4)
            self.assertEqual(state['memories'][:len(bundle['initial_memory'])],bundle['initial_memory'])
            scene['prose']+=' Changed after review.'
            with self.assertRaisesRegex(ContractError,'Stale reconciler'):pp.patch(bundle,scene,audit,p/'stale','fixture')
    def test_experiment_and_fresh_handoff_are_separate_and_writers_are_simultaneous(self):
        root=Path(__file__).resolve().parents[1]
        living=yaml.safe_load((root/'.github/workflows/living-universe-pipeline.yml').read_text())
        self.assertIn('fresh_run',living['on']['workflow_dispatch']['inputs']);self.assertGreater(len(living['jobs']),100)
        self.assertIn('resume_index',living['jobs']['quickstart']['outputs'])
        parallel=yaml.safe_load((root/'.github/workflows/planned-parallel.yml').read_text())
        writer=parallel['jobs']['write'];self.assertEqual(writer['strategy']['max-parallel'],4)
        self.assertEqual(writer['needs'],['prepare','lock']);self.assertFalse(writer['strategy']['fail-fast'])
        self.assertEqual(parallel['jobs']['results']['if'],'always()')
