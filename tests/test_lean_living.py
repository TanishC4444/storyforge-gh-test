"""Execute the generated Living scene graph, not a separate coordinator approximation."""
import copy,fnmatch,io,json,os,shlex,shutil,sys,tempfile,unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import yaml
from storyforge.dag import stage
from storyforge.living_prepare import prepare
from storyforge.storage import load,save
from storyforge import batch_pipeline as batch

class LeanLivingTests(unittest.TestCase):
    def test_generated_scene_graph_keeps_all_checks_and_canon_gate(self):
        workflow=yaml.safe_load(Path('.github/workflows/living-universe.yml').read_text());jobs=workflow['jobs']
        for key,job in jobs.items():
            self.assertTrue(set(job.get('needs',[]))<=set(jobs),key)
        self.assertNotIn('s01_summaries',jobs);self.assertNotIn('s01_final_batches',jobs)
        self.assertEqual(jobs['s01_story_batches']['strategy']['matrix']['batch'],[0])
        self.assertEqual(jobs['s01_rhetoric_batches']['strategy']['matrix']['batch'],[0])
        for name in ['s01_characters','s01_write_batches','s01_memory_extract_batches','s01_memory_preflight_batches','s01_repair_batches','s01_memory_final_batches','s01_accept']:
            self.assertIn(name,jobs)
        # Execute the first scene's generated dependencies and artifact handoffs locally.
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'STORY_LEAN_LIVING':'true','STORY_HOSTED_ONLY':'true'}),redirect_stdout(io.StringIO()):
            root=Path(d);artifacts={}
            stage('prepare',root/'none',root/'prepare',request_file='local-universe-massive',profile='fast',backend='fixture');artifacts['prepare']=root/'prepare'
            state=prepare(root/'prepare/snapshot.json',root/'quickstart',backend='fixture');artifacts['quickstart']=root/'quickstart'
            self.assertTrue(state['request']['performance']['lean_living_checks'])
            pending={k for k in jobs if k.startswith('s01_')};done={'prepare','quickstart'}
            while pending:
                ready=sorted(k for k in pending if set(jobs[k].get('needs',[]))<=done)
                self.assertTrue(ready,'No ready stages: '+str(pending))
                for key in ready:
                    job=jobs[key];matrix=job.get('strategy',{}).get('matrix',{})
                    if 'character' in matrix:values=state['plan']['scenes'][0]['participants'];axis='character'
                    elif 'batch' in matrix:
                        axis='batch';value=matrix['batch']
                        if isinstance(value,list):values=value
                        else:
                            upstream=value.split('needs.',1)[1].split('.outputs.',1)[0]
                            file='draft-plan.json' if upstream.endswith('draft_plan') else 'repair-plan.json' if upstream.endswith('repair_plan') else 'extract-plan.json' if upstream.endswith(('extract_plan','refresh_plan')) else 'memory-plan.json'
                            plan=load(artifacts[upstream]/file);values=[b['id'] for b in plan.get('batches',plan.get('beats',[]))]
                    else:values=[None];axis=None
                    for value in values:
                        folder=root/key/(str(value) if value is not None else 'single');source=folder/'inputs';out=folder/'out'
                        for step in job['steps']:
                            if step.get('uses')!='actions/download-artifact@v4':continue
                            spec=step['with'];dest=folder/spec['path']
                            if 'name' in spec:shutil.copytree(artifacts[spec['name']],dest,dirs_exist_ok=True)
                            else:
                                names=[name for name in artifacts if fnmatch.fnmatch(name,spec['pattern'])]
                                self.assertTrue(names,spec['pattern'])
                                for name in names:shutil.copytree(artifacts[name],dest/name,dirs_exist_ok=True)
                        step=next(s for s in job['steps'] if s.get('id')=='task')
                        if 'storyforge.batch_pipeline' in step['run']:
                            command=next(line for line in step['run'].splitlines() if line.startswith('python -m storyforge.batch_pipeline'))
                            command=command.replace('$backend','fixture').replace('$STORY_BATCH',str(value))
                            args=shlex.split(command)[3:]+['--source',str(source),'--out',str(out)]
                            with patch.object(sys,'argv',['batch_pipeline']+args):batch.main()
                        else:
                            task=next(line for line in step['run'].splitlines() if line.startswith('python -m storyforge.dag')).split()[3]
                            stage(task,source,out,index=0,character=value if axis=='character' else None,profile='fast',backend='fixture')
                        artifacts[key+('-'+str(value) if axis else '')]=out
                    done.add(key);pending.remove(key)
            accepted=load(artifacts['s01_accept']/'snapshot.json')
            self.assertTrue(accepted['complete']);self.assertTrue(accepted['accepted'][0]['canon_committed'])
            final=load(artifacts['s01_final_check']/'repair.json')['editorial_adjudication']
            self.assertTrue(final['verdict']['pass']);self.assertEqual(final['judgment_calls'],0)
            self.assertTrue(load(artifacts['s01_memory_review']/'review.json')['reused_preflight'])
    def test_hosted_setup_retains_cpu_support_for_other_workflows(self):
        setup=Path('.github/actions/setup-worker/action.yml').read_text()
        self.assertIn("default: 'false'",setup)
        self.assertIn("inputs.hosted-only != 'true'",setup)
        self.assertIn('Install lightweight hosted application',setup)
    def test_changed_prose_gets_one_strict_judgment_instead_of_reusing_passes(self):
        from storyforge.editorial import STORY_CHECKS,RHETORIC_CHECKS
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'STORY_LEAN_LIVING':'true'}),redirect_stdout(io.StringIO()):
            root=Path(d)
            stage('prepare',root/'none',root/'prepare',request_file='local-universe-massive',profile='fast',backend='fixture')
            state=prepare(root/'prepare/snapshot.json',root/'quickstart',backend='fixture');card=state['plan']['scenes'][0]
            before='Thestor put down the tongs.';after='Thestor put down the tongs and forfeited his payment.'
            save(root/'source/original/prose.txt',before);save(root/'source/edited/prose.txt',after);save(root/'source/edited/repair.json',{'changed':True})
            for kind,checks in [('story',STORY_CHECKS),('rhetoric',RHETORIC_CHECKS)]:
                verdict={'pass':True,'issues':[],'checks':[{'id':c,'verdict':'pass','evidence_ids':['p001'],'reason':'The original supplied scene supports this requested dimension.'} for c in checks],'state_sha256':batch.bind_state(state),'source_sha256':batch.digest(before)}
                save(root/'source'/f'{kind}-review/review.json',verdict)
            facts={'memories':[]};save(root/'source/initial-memory/memory.json',facts)
            save(root/'source/memory-review/review.json',{'pass':True,'issues':[],'state_sha256':batch.bind_state(state),'source_sha256':batch.digest(before),'memory_sha256':batch.bind_state(facts)})
            result=batch.finalize(state,card,root/'source',root/'final','fixture')
            self.assertEqual(result['judgment_calls'],1);self.assertEqual(result['judgment_rounds'],1)
    def test_hosted_only_mode_cannot_enter_cpu_fallback(self):
        from storyforge.contracts import request,ContractError
        from storyforge.inference import Executor
        req=request(load('examples/chaos-novel-practice.json'));req['execution_policy']={};req['api_roles']={}
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'STORY_HOSTED_ONLY':'true'}),patch('storyforge.local_worker.execute',side_effect=AssertionError('Unexpected CPU inference')):
            with self.assertRaisesRegex(ContractError,'disabled CPU fallback'):
                Executor(req,d,'worker').call('writer',{},'Write source prose.',tokens=100,response_schema=False,output_format='text',validator=lambda x:x)
