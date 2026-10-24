import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from storyforge import image_studio as s
from tests.test_image_studio import png
class MuseTests(unittest.TestCase):
 def test_muse_response_and_actual_dimensions(self):
  response={'status':'completed','output':[{'type':'message'},{'type':'image_generation_call','status':'completed','result':base64.b64encode(png()).decode()}]}
  with tempfile.TemporaryDirectory() as folder,patch.object(s.CATALOG,'get',return_value=s.MUSE_MODEL),patch.object(s,'muse_key',return_value='secret'),patch.object(s,'request_json',return_value=response) as request:
   result=s.generate(folder,{'model':'muse-image-1.0','prompt':'A storyboard of a forge','kind':'storyboard'})
   self.assertEqual(result['provider'],'Meta Model API')
   self.assertEqual(result['images'][0]['width'],64)
   self.assertEqual(request.call_args.args[0],s.META_BASE+'/responses')
   self.assertFalse(request.call_args.args[1]['store'])
   self.assertNotIn('secret',s.record_path(folder,result['id']).read_text())
 def test_unsupported_controls(self):
  for extra in ({'seed':1},{'steps':10},{'n':2}):
   with self.assertRaises(ValueError):s.generation_settings({'prompt':'scene',**extra},s.MUSE_MODEL)
 def test_meta_without_vultr(self):
  with patch.dict('os.environ',{'VULTR_INFERENCE_API_KEY':''}),patch.object(s,'muse_key',return_value='secret'):
   self.assertEqual(s.ImageModels().list(),[s.MUSE_MODEL])

 def test_vultr_backup_after_muse_failure(self):
  from tests.test_image_studio import spec
  from storyforge.production_research import ProviderError
  response={'data':[{'b64_json':base64.b64encode(png()).decode()}]}
  with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'VULTR_INFERENCE_API_KEY':'backup-secret'}),patch.object(s.CATALOG,'get',side_effect=[s.MUSE_MODEL,spec()]),patch.object(s.CATALOG,'vultr_list',return_value=[spec()]),patch.object(s,'muse_key',return_value='secret'),patch.object(s,'request_json',side_effect=[ProviderError('Provider HTTP 503'),response]) as request:
   result=s.generate(folder,{'model':'muse-image-1.0','prompt':'A forge','kind':'scene'})
   self.assertEqual(result['model'],'moss-image')
   self.assertEqual(result['fallback']['requested_model'],'muse-image-1.0')
   self.assertEqual(request.call_count,2)
