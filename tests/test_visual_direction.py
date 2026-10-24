import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from storyforge.image_studio import prepare_prompt
from storyforge.visual_direction import art_direction
class VisualDirectionTests(unittest.TestCase):
 def direction(self,text,**spec):
  return art_direction({'kind':'scene','style':'Auto - match story','natural_finish':True,**spec},[{'text':text}])
 def test_story_genres_get_different_media(self):
  for text,style in [('Ancient Troy, bronze tools.','Period film still'),('An orbital spacecraft approaches a starship.','Grounded science fiction'),('A detective investigates a murder.','Noir photography'),('A whimsical bedtime fairy tale.','Gouache storybook')]:
   with self.subTest(text=text):self.assertEqual(self.direction(text)['style'],style)
 def test_explicit_style_wins_over_genre(self):
  result=self.direction('A detective in ancient Troy.',style='Oil painting')
  self.assertEqual(result['style'],'Oil painting');self.assertFalse(result['automatic'])
  self.assertIn('brushwork',result['guidance']);self.assertNotIn('skin texture',result['guidance'])
 def test_storyboard_readability_and_no_context(self):
  self.assertEqual(self.direction('A spacecraft.',kind='storyboard')['style'],'Pencil storyboard')
  self.assertEqual(self.direction('')['style'],'Documentary film still')
 def test_finish_can_be_disabled(self):
  self.assertIn('waxy skin',self.direction('')['guidance'])
  self.assertNotIn('waxy skin',self.direction('',natural_finish=False)['guidance'])
 def test_local_and_enhanced_prompts_receive_direction(self):
  with tempfile.TemporaryDirectory() as folder:
   Path(folder,'story.txt').write_text('Ancient Troy. A bronze smith shapes a shield.')
   local=prepare_prompt(folder,{'subject':'smith'})
   self.assertEqual(local['art_direction']['style'],'Period film still')
   self.assertIn('material-specific wear',local['prompt'])
   with patch('storyforge.image_studio.Muse') as llm:
    llm.return_value.ask.return_value={'prompt':'A smith at his forge','assumptions':[]};llm.return_value.calls=[]
    prepare_prompt(folder,{'subject':'smith'},True)
    self.assertEqual(llm.return_value.ask.call_args.args[1]['art_direction']['style'],'Period film still')
