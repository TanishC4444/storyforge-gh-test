from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from storyforge.contracts import ContractError, request, delta, review
from storyforge.coordinator import run, visible
from storyforge.fixture import respond
from storyforge.retrieval import ROOT, retrieve
from storyforge.storage import load, lock


def example():
    return request(json.loads((ROOT / 'examples/harbor.json').read_text()))


class WorkflowTests(unittest.TestCase):
    def test_full_three_chapter_resume(self):
        req = example()
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
            run(req, d, stop_after=2)
            self.assertEqual(len(load(Path(d) / 'state.json')['accepted']), 2)
            state = run(req, d)
            self.assertTrue(state['complete'])
            self.assertEqual(len(state['accepted']), 9)
            self.assertEqual(len(list((Path(d) / 'chapters').glob('*.txt'))), 3)
            self.assertIn('FIXTURE', (Path(d) / 'story.txt').read_text())
            calls = len(list((Path(d) / 'calls').glob('*.json')))
            run(req, d)
            self.assertEqual(calls, len(list((Path(d) / 'calls').glob('*.json'))))

    def test_rejected_scene_does_not_change_canon(self):
        def reject(role, packet, req):
            if role == 'story_quality':
                return json.dumps({'pass': False, 'issues': [{'severity': 'blocking', 'category': 'test', 'quote': 'Mara checked the tower latch.', 'problem': 'Injected failure', 'fix': 'Do not accept.'}]})
            return respond(role, packet, req)
        with tempfile.TemporaryDirectory() as d, patch('storyforge.fixture.respond', reject), redirect_stdout(io.StringIO()):
            with self.assertRaises(ContractError):
                run(example(), d)
            state = load(Path(d) / 'state.json')
            self.assertEqual(state['version'], 0)
            self.assertEqual(state['accepted'], [])

    def test_rejected_memory_does_not_change_canon(self):
        def reject(role, packet, req):
            if role == 'memory':
                return json.dumps({'memories': [{'kind': 'event', 'text': 'Unfounded', 'evidence': 'Never written in prose', 'known_by': ['mara']}]})
            return respond(role, packet, req)
        with tempfile.TemporaryDirectory() as d, patch('storyforge.fixture.respond', reject), redirect_stdout(io.StringIO()):
            with self.assertRaises(ContractError):
                run(example(), d)
            self.assertEqual(load(Path(d) / 'state.json')['accepted'], [])

    def test_private_knowledge_packet(self):
        facts = example()['initial_facts']
        self.assertEqual(len(visible(facts, 'mara')), 1)
        self.assertEqual(len(visible(facts, 'oren')), 2)
        self.assertEqual(visible(facts), [])

    def test_evidence_and_review_contracts(self):
        with self.assertRaises(ContractError):
            delta({'memories': [{'kind': 'event', 'text': 'x', 'evidence': 'made-up quote longer', 'known_by': ['mara']}]}, 'Actual prose', ['mara'])
        with self.assertRaises(ContractError):
            review({'pass': True, 'issues': [{'severity': 'blocking', 'category': 'x', 'quote': 'Actual', 'problem': 'x', 'fix': 'x'}]}, 'Actual prose')

    def test_request_cannot_change_during_resume(self):
        req = example()
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
            run(req, d, stop_after=1)
            changed = copy.deepcopy(req)
            changed['premise'] += ' New premise.'
            with self.assertRaises(ContractError):
                run(changed, d)
            with self.assertRaises(ContractError):
                run(req, d, backend='github')

    def test_lock_prevents_two_writers(self):
        with tempfile.TemporaryDirectory() as d, lock(d):
            with self.assertRaises(RuntimeError):
                with lock(d):
                    pass

    def test_retrieval_excludes_disabled_and_detects_stale_index(self):
        result = retrieve(example())
        corpus = json.loads((ROOT / 'data/literary-corpus.json').read_text())['records']
        enabled = {r['id'] for r in corpus if r.get('retrieval', {}).get('enabled', True)}
        self.assertTrue(result['sources'])
        self.assertTrue(all(r['id'] in enabled for r in result['sources']))
        req = example()
        req['retrieval_mode'] = 'hybrid'
        # Corrupt only a temporary index to test stale-vector rejection after rebuilding.
        import shutil, sqlite3
        with tempfile.TemporaryDirectory() as d, patch('storyforge.retrieval.ROOT', Path(d)):
            (Path(d)/'data').mkdir()
            for name in ['literary-corpus.json','literary_rag.db','MASTER_GUIDE.md']:
                shutil.copy2(ROOT/'data'/name,Path(d)/'data'/name)
            with sqlite3.connect(Path(d)/'data/literary_rag.db') as db:
                db.execute("UPDATE rag_documents SET content='stale' WHERE record_id=(SELECT min(record_id) FROM rag_documents)")
            with self.assertRaisesRegex(ValueError,'stale'):
                retrieve(req)

    def test_plan_requires_approval_unless_explicit(self):
        req = example()
        req['auto_approve_plan'] = False
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
            state = run(req, d)
            self.assertFalse(state['plan_approved'])
            self.assertEqual(state['accepted'], [])
            state = run(req, d, approve_plan=True, stop_after=1)
            self.assertEqual(len(state['accepted']), 1)

    def test_refinement_preserves_input_and_precedes_plan(self):
        from storyforge.contracts import refinement
        req = example()
        refined = json.loads(respond('refiner', {}, req))
        refinement(refined, req)
        refined['original_prompt'] = 'Changed user premise'
        with self.assertRaises(ContractError):
            refinement(refined, req)
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
            state = run(req, d, stop_after=1)
            self.assertEqual(state['refinement']['original_prompt'], req['premise'])
            architect = next((Path(d) / 'packets').glob('architect-*.json'))
            self.assertEqual(load(architect)['input']['refinement']['refined_prompt'], state['refinement']['refined_prompt'])

    def test_refinement_normalizes_equivalent_shapes_without_inventing_fields(self):
        from storyforge.contracts import refinement
        req = example()
        raw = json.loads(respond('refiner', {}, req))
        raw['reader_experience'] = ['Investigation', 'Costly hope']
        raw['expanded_story_elements'] = {'conflict': {'owner': 'mara', 'cost': 'trust'}}
        normalized = refinement(raw, req)
        self.assertEqual(normalized['reader_experience'], 'Investigation; Costly hope')
        self.assertEqual(normalized['expanded_story_elements'], [{'name': 'conflict', 'value': {'owner':'mara','cost':'trust'}}])
        self.assertIsInstance(raw['reader_experience'], list)
        del raw['reader_experience']
        with self.assertRaises(ContractError):
            refinement(raw, req)

    def test_live_adapter_uses_fresh_scoped_agents(self):
        from dataclasses import dataclass
        import types
        from storyforge.inference import Executor
        @dataclass
        class Result:
            finish_reason: str = 'stop'
        made = []
        class FakeAgent:
            def __init__(self, **kwargs):
                self.options = kwargs
                self.last_result = Result()
                made.append(self)
            def run(self, prompt, **kwargs):
                self.prompt = prompt
                return 'A complete test artifact.'
        module = types.ModuleType('gh_ai_runner')
        module.Agent = FakeAgent
        module.GitHubAIRunner = lambda *a, **kw: object()
        req = example()
        req['profile'] = 'expressive'
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()), patch.dict('sys.modules', {'gh_ai_runner': module}), patch.dict('os.environ', {'GH_AI_TOKEN': 'unit-test-placeholder'}):
            executor = Executor(req, d, 'github')
            executor.call('writer', {'only': 'writer context'}, 'write')
            executor.call('humanizer', {'only': 'editor context'}, 'edit')
        self.assertEqual(len(made), 2)
        self.assertFalse(made[0].options['remember'])
        self.assertFalse(made[1].options['remember'])
        self.assertEqual(made[0].options['model'], 'glitter-12b')
        self.assertEqual(made[1].options['model'], 'gemma-4-12b')
        self.assertNotIn('writer context', made[1].prompt)

    def test_truncation_not_accepted(self):
        from storyforge.inference import Executor
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
            ex = Executor(example(), d, 'fixture')
            ex.call('director', {}, 'x')
            path = next((Path(d) / 'calls').glob('*.json'))
            value = load(path)
            value['diagnostic']['finish_reason'] = 'length'
            path.write_text(json.dumps(value))
            # Second attempt is a fresh, uncached fixture response; it repairs truncation.
            self.assertTrue(ex.call('director', {}, 'x'))
            self.assertEqual(len(list((Path(d) / 'calls').glob('*.json'))), 2)

if __name__ == '__main__':
    unittest.main()
