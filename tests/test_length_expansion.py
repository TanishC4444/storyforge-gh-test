import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storyforge.length_expansion import expand
from storyforge.evidence import passages
from storyforge.storage import load,save
from storyforge.dag import stage
from storyforge.living_prepare import prepare
from storyforge import batch_pipeline as b

class LengthExpansionTests(unittest.TestCase):
    def prose(self):return '\n\n'.join(' '.join('part'+str(part)+'action'+str(i) for i in range(n)) for part,n in enumerate([250,250,176]))
    def addition(self,n=224):return ' '.join('detail'+str(i) for i in range(n))
    def req(self):return {'words_per_scene':900,'min_words_ratio':.8,'max_words_ratio':1.3,'length_policy':{'scene_words':'strict'},'pov':'third person, no dialogue'}
    def test_insertions_reach_target_and_preserve_every_original_paragraph(self):
        prose=self.prose();addition=self.addition()
        class Editor:
            def call(self,role,data,instruction,**kwargs):
                self.data=data
                return kwargs['validator']('INSERT_AFTER p001\n'+addition+'\nEND_INSERT')
        editor=Editor()
        with tempfile.TemporaryDirectory() as d:
            revised=expand(editor,self.req(),prose,{},d)
            self.assertEqual(len(revised.split()),900)
            self.assertTrue(revised.endswith(passages(prose)[-1]['text']))
            for p in passages(prose):self.assertIn(p['text'],revised)
            self.assertEqual(editor.data['length_repair']['minimum_new_words'],224)
            self.assertTrue(load(Path(d)/'length-expansion.json')['existing_prose_preserved'])
    def test_short_or_foreign_insertions_cannot_pass(self):
        for patch_text in ['INSERT_AFTER p001\n'+self.addition(25)+'\nEND_INSERT','INSERT_AFTER p003\n'+self.addition()+'\nEND_INSERT','A rewritten scene without insertion blocks.']:
            class Editor:
                def call(self,role,data,instruction,**kwargs):return kwargs['validator'](patch_text)
            with tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):expand(Editor(),self.req(),self.prose(),{},d)
    def test_live_writer_path_uses_one_insertion_repair_instead_of_rewriting(self):
        prose=self.prose();patch_text='INSERT_AFTER p001\n'+self.addition()+'\nEND_INSERT'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stage('prepare',root/'none',root/'base',request_file='living-scale-practice',backend='fixture')
            state=prepare(root/'base/snapshot.json',root/'quick',backend='fixture');card=state['plan']['scenes'][0]
            save(root/'source/direction/direction.txt','Preserve exact canon and private knowledge.')
            b.plan_draft(state,card,root/'source',root/'source/plan','fixture')
            with patch('storyforge.hosted.GoogleHosted.complete',side_effect=[(prose,{'finish_reason':'stop','model':'test'}),(patch_text,{'finish_reason':'stop','model':'backup'})]) as provider:
                result=b.write_batch(state,card,root/'source',root/'out','worker','0')
            self.assertEqual(provider.call_count,2);self.assertTrue(result['verified_form'])
            self.assertEqual(len(result['prose'].split()),900)
            self.assertIn('INSERT_AFTER',provider.call_args_list[1].args[1])
    def test_failed_patch_keeps_original_prose_not_raw_protocol(self):
        prose=self.prose();bad_patch='INSERT_AFTER p001\nToo little.\nEND_INSERT'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stage('prepare',root/'none',root/'base',request_file='living-scale-practice',backend='fixture')
            state=prepare(root/'base/snapshot.json',root/'quick',backend='fixture');card=state['plan']['scenes'][0]
            save(root/'source/direction/direction.txt','Preserve canon.')
            b.plan_draft(state,card,root/'source',root/'source/plan','fixture')
            with patch('storyforge.hosted.GoogleHosted.complete',side_effect=[(prose,{'finish_reason':'stop','model':'test'}),(bad_patch,{'finish_reason':'stop','model':'backup'})]):
                result=b.write_batch(state,card,root/'source',root/'out','worker','0')
            self.assertFalse(result['verified_form']);self.assertEqual(result['prose'],prose)
            self.assertNotIn('INSERT_AFTER',result['prose'])
