import base64
import json
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import zlib
from storyforge import image_studio as studio
from storyforge.production_research import ProviderError
from storyforge.production_web import ProductionServer


def png(w=64,h=64):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x64\x80\xa0'*w)*h))+chunk(b'IEND',b'')


def spec():
    return {'id':'moss-image','name':'MOSS-Image','architecture':{'output_modalities':['image']},'supported_parameters':{'size':{'multiple_of':16,'min_area':4096,'max_area':16384,'max_ratio':4},'aspect_ratio':{'values':['1:1','16:9'],'default':'1:1'},'resolution':{'values':['1K','4K'],'sizes':{'1:1':{'1K':'64x64','4K':'256x256'},'16:9':{'1K':'128x64'}}},'n':{'max':4},'seed':True,'steps':{'min':20,'max':50,'default':30}}}


def settings(**overrides):
    return {'model':'moss-image','prompt':'A bronze smith at his forge','kind':'scene','title':'The forge','aspect_ratio':'1:1','resolution':'1K','n':1,**overrides}


@patch.dict('os.environ',{'VULTR_INFERENCE_API_KEY':'test-image-key'})
class ImageStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'story.txt').write_text('Ancient Troy.\n\nThestor is a bronze smith.\n\nMeles waits beside the shore.')

    def test_local_prompt_and_custom_no_story(self):
        with patch('storyforge.image_studio.Muse') as llm:
            value=studio.prepare_prompt(self.root,{'kind':'character','subject':'Thestor'})
            self.assertIn('bronze smith',value['prompt']);llm.assert_not_called()
        with patch('storyforge.image_studio.context') as read:
            custom=studio.prepare_prompt(self.root,{'kind':'custom','subject':'A red teapot','use_story':False})
            self.assertIn('red teapot',custom['prompt']);read.assert_not_called()
        with self.assertRaises(ValueError):studio.input_spec({'use_story':False})

    def test_story_subject_passage_selection(self):
        text='\n\n'.join('Unrelated passage '+str(i) for i in range(100))+'\n\nAster wears a blue cloak beside a brass lamp.'
        (self.root/'story.txt').write_text(text)
        excerpts=studio.narrative(self.root,studio.input_spec({'subject':'Aster'}))
        self.assertIn('Aster wears a blue cloak',excerpts[0]['text'])

    def test_muse_prompt_is_editable_and_source_bound(self):
        with patch('storyforge.image_studio.Muse') as llm:
            llm.return_value.ask.return_value={'prompt':'Thestor at a bronze anvil','title':'Thestor','assumptions':['Warm dawn light']}
            llm.return_value.calls=[]
            value=studio.prepare_prompt(self.root,{'kind':'character','subject':'Thestor'},True)
            self.assertEqual(value['prompt_provider'],'Vultr Muse Glimmer')
            self.assertEqual(value['sources'],['story.txt'])
            self.assertIn('bronze smith',str(llm.return_value.ask.call_args.args[1]))

    def test_model_catalog_is_cached_no_silent_alias(self):
        catalog=studio.ImageModels()
        with patch('storyforge.image_studio.request_json',return_value={'data':[spec()]}) as request:
            catalog.get('moss-image');catalog.get('moss-image');self.assertEqual(request.call_count,1)
            with self.assertRaises(ValueError):catalog.get('muse-image')

    def test_settings_reject_invalid_before_generation(self):
        self.assertEqual(studio.generation_settings(settings(seed=12),spec())['seed'],12)
        for data in [settings(n=True),settings(n=5),settings(seed=-1),settings(seed=1.2),settings(steps=1),settings(resolution='4K'),settings(aspect_ratio='unknown'),settings(prompt=''),settings(prompt='x'*4001)]:
            with self.assertRaises(ValueError):studio.generation_settings(data,spec())

    def test_generation_records_actual_model_and_saves_png(self):
        response={'data':[{'b64_json':base64.b64encode(png()).decode()}],'usage':{'cost':0.01}}
        with patch.object(studio.CATALOG,'get',return_value=spec()),patch('storyforge.image_studio.request_json',return_value=response) as request:
            value=studio.generate(self.root,settings(api_key='must-not-save'))
        self.assertEqual(value['status'],'completed');self.assertEqual(value['model'],'moss-image')
        self.assertEqual(studio.image_file(self.root,value['id'],0).read_bytes(),png())
        self.assertEqual(request.call_args.args[0],studio.BASE+'/images/generations')
        self.assertEqual(request.call_args.args[1]['response_format'],'b64_json')
        self.assertNotIn('must-not-save',studio.record_path(self.root,value['id']).read_text())
        self.assertEqual(len(studio.gallery(self.root)),1)
        with self.assertRaises(ValueError):studio.image_file(self.root,'../anything',0)
        with self.assertRaises(ValueError):studio.image_file(self.root,value['id'],3)

    def test_provider_failure_never_retries_or_switches_model(self):
        with patch.object(studio.CATALOG,'get',return_value=spec()),patch('storyforge.image_studio.request_json',side_effect=ProviderError('Provider HTTP 429')) as request:
            with self.assertRaises(ProviderError):studio.generate(self.root,settings())
            self.assertEqual(request.call_count,1)
        self.assertEqual(studio.gallery(self.root)[0]['status'],'failed')

    def test_bad_image_and_mismatched_dimensions_rejected(self):
        for blob in (b'not an image',png(128,64)):
            with patch.object(studio.CATALOG,'get',return_value=spec()),patch('storyforge.image_studio.request_json',return_value={'data':[{'b64_json':base64.b64encode(blob).decode()}]}):
                with self.assertRaises(ProviderError):studio.generate(self.root,settings())
        self.assertFalse(list((self.root/'images').glob('*.png')))

    def test_http_generation_gallery_and_media(self):
        server=ProductionServer(('127.0.0.1',0),self.root);threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.pool.shutdown);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)
        with urlopen(base+'/images') as response:self.assertIn(b'Image studio',response.read())
        with self.assertRaises(HTTPError) as caught:urlopen(Request(base+'/api/images/generate',data=b'{}',headers={'Content-Type':'application/json'}))
        self.assertEqual(caught.exception.code,403);caught.exception.close()
        result={'data':[{'b64_json':base64.b64encode(png()).decode()}],'usage':{'cost':0.01}}
        with patch.object(studio.CATALOG,'get',return_value=spec()),patch('storyforge.image_studio.request_json',return_value=result):
            request=Request(base+'/api/images/generate',data=json.dumps(settings()).encode(),headers={'Content-Type':'application/json','X-Storyforge-Token':server.csrf})
            with urlopen(request) as response:job=json.load(response)['job_id']
            for _ in range(100):
                with urlopen(base+'/api/job/'+job) as response:value=json.load(response)
                if value['status'] in ('complete','failed'):break
                time.sleep(.01)
        self.assertEqual(value['status'],'complete')
        with urlopen(base+'/api/images') as response:gallery=json.load(response)['images']
        self.assertEqual(len(gallery),1)
        with urlopen(base+gallery[0]['images'][0]['url']+'?download=1') as response:
            self.assertEqual(response.headers['Content-Type'],'image/png')
            self.assertIn('attachment',response.headers['Content-Disposition'])
            self.assertEqual(response.read(),png())

if __name__=='__main__':unittest.main()
