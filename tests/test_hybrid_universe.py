import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge import media,canon,section_reviews as sr,batch_pipeline as b
from storyforge.contracts import request,delta,ContractError
from storyforge.storage import save,load
from storyforge.universe_events import extended_request,current_life,resume_cast
from storyforge.writing_policy import instructions
from storyforge.review_policy import contract
from storyforge.dag import stage
from storyforge.expansion import prepare

class HybridUniverseTests(unittest.TestCase):
    def scene(self,p):
        stage('prepare',p/'none',p/'base',request_file='stage-play-practice',profile='fast',backend='fixture')
        s=prepare(p/'base/snapshot.json',p/'prepared');return s,s['plan']['scenes'][0]
    def test_medium_decider_obeys_explicit_choice_and_detects_formats_without_inference(self):
        for prompt,expected in [('Write a novel','book'),('A theater play','stage_play'),('A screenplay','screenplay'),('An audio drama','audio_drama'),('A comic script','comic_script'),('A short story','short_story')]:
            r={'premise':prompt};media.choose(r,lambda ok,msg:self.assertTrue(ok,msg));self.assertEqual(r['medium'],expected);self.assertEqual(r['medium_decision']['model_calls'],0)
        r={'medium':'novel','premise':'A theater play'};media.choose(r,lambda ok,msg:self.assertTrue(ok,msg));self.assertEqual(r['medium'],'book')
        self.assertTrue(contract({'medium':'play'})['medium']['script']);self.assertIn('speaker cues',instructions({'medium':'play'},'writer'))
    def test_memory_bridge_keeps_all_facts_and_private_knowledge_boundaries(self):
        facts=[{'id':'m'+str(i),'kind':'event','text':'Precise source fact '+str(i)+' detail'*50,'known_by':['a'] if i%2 else ['b'],'source':'user_input'} for i in range(80)]
        s={'memories':facts,'accepted':[]};self.assertEqual(len(canon.bridge(s)['facts']),80);self.assertEqual(canon.bridge(s)['omitted_ids'],[])
        visible=canon.bridge(s,'a')['facts'];self.assertEqual(len(visible),40);self.assertTrue(all('a' in m['known_by'] for m in visible))
    def test_episode_public_disclosure_is_visible_to_its_actual_audience(self):
        s={'universe_episode':2,'memories':[{'kind':'event','text':'The alarm sounds.','known_by':['public'],'source':'episode-000002/ch01-sc01'}],'accepted':[{'id':'ch01-sc01','participants':['a']}]}
        self.assertEqual(len(canon.bridge(s,'a')['facts']),1);self.assertFalse(canon.bridge(s,'b')['facts'])
    def test_death_and_thread_metadata_survive_canon_without_silent_resurrection(self):
        prose='Val died at the gate. The red lamp remained unexplained.'
        updates=delta({'memories':[{'kind':'event','text':'Val died.','known_by':['a'],'evidence_ids':['p001'],'subject':'val','life_state':'dead','fact_key':'life:val','supersedes':[]},{'kind':'thread','text':'The red lamp remains unexplained.','known_by':['a'],'evidence_ids':['p001'],'thread_id':'red-lamp','thread_state':'seeded','fact_key':'thread:red-lamp','supersedes':[]}]},prose,['val','a'])['memories']
        s={'version':1,'request':{'creative_freedom':{'enabled':True}},'memories':[]};canon.append(s,updates,'s1')
        self.assertEqual(current_life(s['memories']),{'val':'dead'});self.assertEqual(canon.cards(s['memories'])[1]['thread_state'],'seeded')
        before=copy.deepcopy(s)
        for status in ['alive','unknown','missing']:
            with self.assertRaisesRegex(ContractError,'resurrection'):canon.append(s,[{**updates[0],'life_state':status,'supersedes':['m00000']}],'s2')
            self.assertEqual(s,before)
        s['request']['creative_freedom']['protected_characters']=['val'];s['memories']=[]
        with self.assertRaisesRegex(ContractError,'death'):canon.append(s,[updates[0]],'s1')
    def test_new_characters_are_atomic_proposals_and_resume_preserves_identity(self):
        r={'characters':[{'id':'a','name':'Ada'}],'creative_freedom':{'enabled':True}}
        new={'id':'n','name':'Neri','goal':'Secure passage.','voice':'Clipped demands.','introduction_cause':'Arrives to collect an existing debt.'}
        expanded=extended_request(r,{'new_characters':[new]});self.assertEqual(len(r['characters']),1);self.assertEqual(expanded['characters'][1]['cast_status'],'proposed')
        with self.assertRaises(ContractError):extended_request(r,{'new_characters':[{**new,'id':'a'}]})
        resumed=copy.deepcopy(r);resume_cast(resumed,{'request':expanded});self.assertEqual(resumed['characters'][1]['id'],'n')
    def test_concrete_beats_share_exact_entry_and_exit_contracts(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);c['writing_beats']=[{'action':'Expose the paper discrepancy.','entry_state':'Cyra has the original.','exit_state':'Ben sees the changed seal.'},{'action':'Force the commitment.','entry_state':'Ben sees the changed seal.','exit_state':'Ada promises the third seat.'}]
            save(p/'direction/direction.txt','Shared concrete direction')
            with patch('storyforge.inference.Executor.call',side_effect=AssertionError('No extra planning call')):plan=b.plan_draft(s,c,p,p/'plan','fixture')
            self.assertEqual(plan['beats'][0]['exit'],plan['beats'][1]['entry']);self.assertEqual(plan['beats'][1]['purpose'],'Force the commitment.')
    def test_hybrid_checks_local_text_and_global_summaries_and_marks_missing_batches(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);text='\n\n'.join('Unique action '+str(i)+'.' for i in range(8))
            save(p/'edited/prose.txt',text);save(p/'original/prose.txt',text);plan=sr.plan(s,p,p/'plan')
            for sec in plan['sections']:sr.summarize(s,c,p,p/'batches'/sec['id'],'fixture',sec['id'])
            sr.join_summaries(s,p,p/'summaries');packets=[]
            def reviewer(executor,role,data,instruction,**kw):
                packets.append(data)
                return kw['validator']({'pass':True,'checks':[{'id':key,'verdict':'pass','evidence_ids':[data['evidence_passages'][0]['id']],'reason':'Fixture source assessment exercises this required dimension only.'} for key in data['required_checks']],'issues':[]})
            with patch('storyforge.inference.Executor.call',autospec=True,side_effect=reviewer):
                sr.final_review(s,c,p,p/'final-batches/story-0','worker','story-0');sr.final_review(s,c,p,p/'final-batches/local-1-0','worker','local-1-0')
            self.assertEqual(len(packets[0]['evidence_passages']),2);self.assertIn('current_scene_summaries',packets[0]);self.assertLess(len(packets[1]['evidence_passages']),8)
            self.assertTrue(sr.final_join(s,p)['unverified'])
            summaries=load(p/'summaries/summaries.json');summaries['unverified']=True;save(p/'summaries/summaries.json',summaries)
            result=sr.final_review(s,c,p,p/'failed','fixture','story-1');self.assertTrue(result['review']['unverified'])
    def test_unchanged_source_reuses_summary_without_another_model_call(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);s,c=self.scene(p);text='Original action.\n\nOriginal consequence.'
            save(p/'edited/prose.txt',text);save(p/'original/prose.txt',text);plan=sr.plan(s,p,p/'plan');v=sr.summarize(s,c,p,p/'first','fixture','0')
            save(p/'previous-summaries/summaries.json',{'source_sha256':b.digest(text),'sections':[v]})
            with patch('storyforge.inference.Executor.call',side_effect=AssertionError('No repeated summary inference')):reused=sr.summarize(s,c,p,p/'second','worker','0')
            self.assertTrue(reused['reused_exact_source'])
    def test_workflow_graph_has_no_cycles_and_supports_two_scene_practices(self):
        from scripts.build_expansion_workflow import build_expansion,build_living
        import yaml
        for document in [build_expansion(),build_living()]:
            graph=yaml.safe_load(document);jobs=graph['jobs'];visiting=set();done=set()
            def visit(key):
                self.assertNotIn(key,visiting);self.assertIn(key,jobs)
                if key in done:return
                visiting.add(key)
                for dep in jobs[key].get('needs',[]):visit(dep)
                visiting.remove(key);done.add(key)
            for key in jobs:visit(key)
            # Expanded shape stays below the failure threshold; aliases shrink the serialized parser input further.
            def nodes(v):
                if isinstance(v,dict):return 1+sum(1+nodes(x) for x in v.values())
                if isinstance(v,list):return 1+sum(nodes(x) for x in v)
                return 1
            self.assertLess(nodes(graph),40000)
            self.assertIn('env',graph);self.assertNotIn('GEMINI_API_KEY',graph['env'])
            self.assertIn('2',graph['on']['workflow_dispatch']['inputs']['scene_limit']['options'])
            self.assertIn('s01_repair',jobs['s01_memory_refresh_plan']['needs']);self.assertNotIn('s01_final_check',jobs['s01_memory_refresh_plan']['needs'])
            self.assertIn('s01_final_memory',jobs['s01_final_batches']['needs']);self.assertIn('final_reviews',jobs['s01_final_sections']['outputs'])
