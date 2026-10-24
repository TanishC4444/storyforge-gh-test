import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import yaml


class GeminiRAGTests(unittest.TestCase):
    def test_sequential_graph_installs_hybrid_encoder_and_saves_verification(self):
        from scripts.living_pipeline import build
        steps=yaml.safe_load(build())['jobs']['prepare']['steps']
        setup=next(s for s in steps if s.get('name')=='Install Gemini RAG encoder when requested')
        self.assertIn("'.[rag]'",setup['run'])
        task=next(s for s in steps if s.get('id')=='task')
        self.assertIn('scripts.verify_gemini_rag --if-hybrid',task['run'])
        self.assertIn('GEMINI_API_KEY',task['env'])

    def test_live_smoke_brief_is_valid_for_living_workflow(self):
        req=json.loads(Path('examples/rag-gemini-practice.json').read_text())
        self.assertEqual(req['retrieval_mode'],'hybrid')
        self.assertTrue(req['performance']['classic_expansion'])
        self.assertTrue(req['performance']['living_universe'])
        self.assertTrue(req['performance']['living_bounded'])
        self.assertEqual(req['scenes_per_chapter'],1)

    @unittest.skipUnless(importlib.util.find_spec('numpy') and importlib.util.find_spec('dotenv'),'Optional RAG dependencies')
    def test_query_and_document_tasks_validate_and_normalize_vectors(self):
        from rag.embeddings import encode_query,encode_texts
        from rag.identity import EMBEDDING_DIMENSIONS
        calls=[]
        def respond(body,key):
            calls.extend(body['requests'])
            return {'embeddings':[{'values':[2.0]+[0.0]*(EMBEDDING_DIMENSIONS-1)} for _ in body['requests']]}
        with patch('rag.embeddings.api_key',return_value='placeholder'),patch('rag.embeddings._post',side_effect=respond):
            self.assertEqual(encode_texts(['A document.'])[0][0],1.0)
            self.assertEqual(encode_query('A query.')[0],1.0)
        self.assertEqual([c['taskType'] for c in calls],['RETRIEVAL_DOCUMENT','RETRIEVAL_QUERY'])
        self.assertTrue(all(c['outputDimensionality']==768 for c in calls))
        with patch('rag.embeddings.api_key',return_value='placeholder'),patch('rag.embeddings._post',return_value={'embeddings':[{'values':[0.0]*768}]}):
            with self.assertRaises(ValueError):encode_query('Bad vector')
