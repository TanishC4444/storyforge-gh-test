import copy,io,json,shutil,tempfile,unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
from storyforge.dag import stage
from storyforge.inference import Executor,ROOT
from storyforge.experimental_parts import changes,stitch,repair
from storyforge.experimental import choose,memory_hash
from storyforge.storage import load,save
from storyforge.contracts import ContractError
from test_story import example

class ParallelPrimitiveTests(unittest.TestCase):
    def test_patch_groups_and_reverse_application(self):
        req=example();req['execution_policy']={'experimental':True,'concurrency':{'repair':2}}
        prose='First paragraph.\n\nSecond paragraph.\n\nThird paragraph.'
        reviews=[{'reviewed_sha256':__import__('hashlib').sha256(prose.encode()).hexdigest(),'issues':[{'paragraph':0,'fix':'one'},{'paragraph':2,'fix':'two'},{'paragraph':0,'fix':'three'}]}]
        class Fake:
            def __init__(self):self.calls=[]
            def call(self,role,packet,instruction,**kwargs):
                self.calls.append(packet)
                return {'replacement':packet['paragraph']+' Patched.','facts_changed':False}
        fake=Fake();result,metadata=repair(fake,req,prose,reviews)
        self.assertEqual(result,'First paragraph. Patched.\n\nSecond paragraph.\n\nThird paragraph. Patched.')
        self.assertEqual(len(fake.calls),2);self.assertTrue(metadata['facts_changed'])
        self.assertEqual(len(metadata['diff']['changed']),2)
    def test_stitch_requires_every_beat(self):
        self.assertEqual(stitch([' A ','B ']),'A\n\nB')
        with self.assertRaises(ContractError):stitch(['A',''])
    def test_accept_source_fallback_prefers_repair(self):
        with tempfile.TemporaryDirectory() as d:
            save(Path(d)/'edited/prose.txt','Original')
            self.assertEqual(choose(d,'repair','edited','prose.txt').read_text(),'Original')
            save(Path(d)/'repair/prose.txt','Repaired')
            self.assertEqual(choose(d,'repair','edited','prose.txt').read_text(),'Repaired')
    def test_diff_maps_unchanged_evidence_after_insertion(self):
        result=changes('Old A.\n\nOld B.','New paragraph.\n\nOld A.\n\nOld B.')
        self.assertEqual(result['unchanged'],{'p001':'p002','p002':'p003'})
        self.assertEqual([p['id'] for p in result['changed']],['p001'])
    def test_retry_is_counted_in_timeline(self):
        from storyforge.hosted import GoogleHosted,HostedError
        from storyforge.tracking import Tracker,_CURRENT
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()),patch('storyforge.hosted.time.sleep'):
            tracker=Tracker(d,'test');token=_CURRENT.set(tracker)
            result={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'OK'}]}}]}
            try:
                hosted=GoogleHosted(Path(d)/'provider-budget','placeholder')
                with patch.object(hosted,'request',side_effect=[{'totalTokens':10},HostedError('Google HTTP 503'),result]):hosted.complete('gemma','s','p',20,role='writer_beat')
            finally:_CURRENT.reset(token)
            events=[json.loads(line) for line in (Path(d)/'events.jsonl').read_text().splitlines()]
            retry=next(e for e in events if e['phase']=='api_retry')
            self.assertEqual(retry['stage'],'writer_beat');self.assertEqual(retry['status_code'],503)

class ParallelFlowTests(unittest.TestCase):
    def run_scene(self,force,beats,mismatch=False,complete=False):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        req=example();req.update(chapters=1,scenes_per_chapter=2)
        req['execution_policy']={'experimental':True,'continue_with_warnings':True,'gate_repair_threshold':'blocking','writer_beats':beats,'fixture_needs_repair':force,'concurrency':{'api':2,'reviews':3,'repair':2,'writer':2}}
        req['performance']={'application_plan_binding':True,'application_prompt_binding':True,'compact_packets':True,'canon_index':True}
        (root/'examples').mkdir();(root/'skills').symlink_to(ROOT/'skills',target_is_directory=True)
        save(root/'examples/fixture-parallel.json',req)
        def task(name,kind,state=None,extras=(),index=0,character=None):
            inputs=root/name/'inputs';inputs.mkdir(parents=True,exist_ok=True)
            if state:shutil.copytree(state,inputs/'state')
            for path,target in extras:shutil.copytree(path,inputs/target)
            out=root/name/'out'
            with patch('storyforge.dag.ROOT',root):stage(kind,inputs,out,index,character,'fixture-parallel','fast','fixture')
            return out
        state=task('prepare','prepare');state=task('refine','refine_bundle',state);state=task('plan','plan_bundle',state)
        state=task('design','scene_design',state)
        actors=[(task('actor'+cid,'character',state,character=cid),'characters/'+cid) for cid in load(state/'snapshot.json')['plan']['scenes'][0]['participants']]
        direction=task('direction','director',state,actors)
        draft=task('writer','writer',state,[(direction,'direction')]);edit=task('edit','edit',state,[(draft,'draft')])
        story=task('story','story_review',state,[(edit,'edited')]);rhetoric=task('rhetoric','rhetoric_review',state,[(edit,'edited')])
        memory=task('memory','memory',state,[(edit,'edited')])
        spec=task('anticipate','anticipate_design',state,[(edit,'edited'),(memory,'memory')],1)
        extras=[(edit,'edited'),(story,'initial-story'),(rhetoric,'initial-rhetoric'),(memory,'memory')]
        if load(story/'review.json')['needs_repair'] or load(rhetoric/'review.json')['needs_repair']:
            patched=task('repair','repair',state,[(edit,'edited'),(story,'diagnosis'),(rhetoric,'rhetoric')])
            verified=task('verify','verify',state,[(patched,'edited'),(story,'diagnosis')])
            vr=task('verifyr','verify_rhetoric',state,[(patched,'edited'),(rhetoric,'rhetoric')])
            finalmem=task('finalmem','memory_final',state,[(patched,'edited'),(memory,'initial-memory')])
            extras += [(patched,'repair'),(verified,'verified'),(vr,'verified-rhetoric'),(finalmem,'final-memory')]
            if load(finalmem/'memory.json').get('changed_memories'):
                mr=task('memoryreview','memory_review',state,[(patched,'edited'),(finalmem,'memory')]);extras.append((mr,'memory-review'))
            packets=[load(p)['input'] for p in (verified/'packets').glob('*.json')]
            self.assertTrue(all('prose' not in packet for packet in packets))
            self.assertTrue(all('changed_paragraphs' in packet for packet in packets))
        accepted=task('accept','accept',state,extras)
        if mismatch:
            snapshot=load(spec/'snapshot.json');snapshot['design_memory_hash']='forced-stale-hash';save(spec/'snapshot.json',snapshot)
        settled=task('settle','settle',accepted,[(spec,'anticipated')],1)
        self.assertEqual(load(settled/'snapshot.json')['design_memory_hash'],memory_hash(load(accepted/'snapshot.json')))
        if mismatch:self.assertTrue(load(settled/'settle.json')['design_rerun'])
        if complete:
            state=settled
            actors=[(task('2actor'+cid,'character',state,index=1,character=cid),'characters/'+cid) for cid in load(state/'snapshot.json')['plan']['scenes'][1]['participants']]
            direction=task('2direction','director',state,actors,1)
            draft=task('2writer','writer',state,[(direction,'direction')],1);edit=task('2edit','edit',state,[(draft,'draft')],1)
            story=task('2story','story_review',state,[(edit,'edited')],1);rhetoric=task('2rhetoric','rhetoric_review',state,[(edit,'edited')],1)
            memory=task('2memory','memory',state,[(edit,'edited')],1)
            accepted=task('2accept','accept',state,[(edit,'edited'),(story,'initial-story'),(rhetoric,'initial-rhetoric'),(memory,'memory')],1)
            self.assertTrue(load(accepted/'snapshot.json')['complete'])
        return load(accepted/'snapshot.json')
    def test_no_repair_path(self):
        with redirect_stdout(io.StringIO()):self.assertEqual(len(self.run_scene(False,1)['accepted']),1)
    def test_repair_path_and_stale_design_rerun(self):
        with redirect_stdout(io.StringIO()):self.assertEqual(len(self.run_scene(True,1,True)['accepted']),1)
    def test_beat_writer_path(self):
        with redirect_stdout(io.StringIO()):self.assertEqual(len(self.run_scene(False,2)['accepted']),1)
    def test_full_two_scene_flow_after_settle(self):
        with redirect_stdout(io.StringIO()):self.assertEqual(len(self.run_scene(False,2,complete=True)['accepted']),2)
    def test_generated_graph_gates_and_overlap(self):
        text=(ROOT/'.github/workflows/troy-parallel-experiment.yml').read_text()
        self.assertIn('needs.s01_story.outputs.needs_repair',text)
        self.assertIn("needs.s01_repair.outputs.facts_changed == 'true'",text)
        self.assertIn('needs: [s01_design, s01_edit, s01_memory]',text)
        self.assertIn('needs: [s01_accept, s02_design]',text)
        self.assertIn('fromJSON(needs.s01_settle.outputs.characters)',text)
        self.assertNotIn('backend: worker',text)

class ParallelSafetyTests(unittest.TestCase):
    def test_verified_unchanged_memory_is_rebound_without_reextraction(self):
        from storyforge.experimental import bind_memory
        from storyforge.contracts import delta
        before='Original opening.\n\nMara checked the tower latch.'
        memory=delta({'memories':[{'kind':'event','text':'Mara checked the tower latch.','known_by':['mara'],'evidence':'Mara checked the tower latch.'}]},before,['mara'])
        kept,diff=bind_memory(memory,before,'Edited opening.\n\nMara checked the tower latch.')
        self.assertEqual(len(kept),1);self.assertEqual(kept[0]['evidence_ids'],['p002'])
        kept,_=bind_memory(memory,before,'Original opening.\n\nMara left the latch untouched.')
        self.assertEqual(kept,[])
    def test_global_repair_runs_only_for_null_paragraph_findings(self):
        req=example();req['execution_policy']={'concurrency':{'repair':2}}
        class Fake:
            def __init__(self):self.roles=[]
            def call(self,role,packet,instruction,**kwargs):
                self.roles.append(role)
                return packet['prose']+' Whole-scene repair.' if role=='global_repair' else {'replacement':packet['paragraph']+' Local repair.','facts_changed':False}
        fake=Fake();prose='One paragraph.'
        result,metadata=repair(fake,req,prose,[{'issues':[{'paragraph':None,'fix':'Resolve the whole-scene issue.'}]}])
        self.assertEqual(fake.roles,['global_repair']);self.assertTrue(metadata['global_pass'])
        self.assertIn('Whole-scene repair',result)
    def test_api_semaphore_caps_concurrent_requests(self):
        import threading,time
        from storyforge.worker_policy import parallel,permit
        req=example();req['execution_policy']={'concurrency':{'api':2,'reviews':4}}
        active=0;peak=0;lock=threading.Lock()
        def request(_):
            nonlocal active,peak
            with permit(req):
                with lock:active+=1;peak=max(peak,active)
                time.sleep(.01)
                with lock:active-=1
        parallel(req,'reviews',list(range(8)),request)
        self.assertEqual(peak,2)
