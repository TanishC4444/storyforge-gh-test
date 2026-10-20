from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from storyforge.dag import stage
from storyforge.storage import load
from storyforge.contracts import ContractError
from storyforge.inference import Executor
from test_story import example


class DagTests(unittest.TestCase):
    def test_all_chapters_with_parallel_isolated_branches(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            root = Path(temp)
            def task(name, kind, state=None, extras=(), index=0, character=None):
                work = root / name
                inputs = work / 'inputs'
                if state:
                    shutil.copytree(state, inputs / 'state')
                for source, target in extras:
                    shutil.copytree(source, inputs / target)
                result = work / 'out'
                stage(kind, inputs, result, index, character, 'silent-bell-full', 'balanced', 'fixture')
                return result
            state = task('prepare', 'prepare')
            state = task('refine', 'refine', state)
            state = task('plan', 'plan', state)
            for i in range(9):
                prefix = f's{i}'
                ids = load(state / 'snapshot.json')['plan']['scenes'][i]['participants']
                with ThreadPoolExecutor(max_workers=3) as pool:
                    futures = [pool.submit(task, prefix+c, 'character', state, (), i, c) for c in ids]
                    characters = [f.result() for f in futures]
                # Both proposals are based on exactly the same immutable canon version.
                self.assertEqual({load(p/'proposal.json')['state_version'] for p in characters}, {i})
                extras = [(p, 'characters/'+c) for p,c in zip(characters,ids)]
                direction = task(prefix+'direction','director',state,extras,i)
                draft = task(prefix+'draft','writer',state,[(direction,'direction')],i)
                edit = task(prefix+'edit','edit',state,[(draft,'draft')],i)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    story_future = pool.submit(task,prefix+'story','story_review',state,[(draft,'draft'),(edit,'edited')],i)
                    memory_future = pool.submit(task,prefix+'memory','memory',state,[(edit,'edited')],i)
                    story, memory = story_future.result(), memory_future.result()
                repaired = task(prefix+'repair','repair',state,[(edit,'edited'),(story,'diagnosis')],i)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    verified_future = pool.submit(task,prefix+'verify','verify',state,[(repaired,'edited'),(story,'diagnosis'),(draft,'draft')],i)
                    final_memory_future = pool.submit(task,prefix+'final_memory','memory_final',state,[(repaired,'edited'),(memory,'initial-memory')],i)
                    story, memory = verified_future.result(), final_memory_future.result()
                edit = repaired
                memory_review = task(prefix+'memory_review','memory_review',state,[(edit,'edited'),(memory,'memory')],i)
                if i == 0:
                    rejected = load(story/'review.json')
                    (story/'review.json').write_text(json.dumps({'pass':False,'issues':[]}))
                    with self.assertRaises(ContractError):
                        task('rejected','accept',state,[(edit,'edited'),(story,'story-review'),(memory,'memory'),(memory_review,'memory-review')],i)
                    self.assertFalse((root/'rejected/out/snapshot.json').exists())
                    self.assertEqual(load(state/'snapshot.json')['version'],0)
                    (story/'review.json').write_text(json.dumps(rejected))
                state = task(prefix+'accept','accept',state,[(edit,'edited'),(story,'story-review'),(memory,'memory'),(memory_review,'memory-review')],i)
            final = load(state/'snapshot.json')
            self.assertEqual(final['version'],9)
            self.assertTrue(final['complete'])
            self.assertEqual(len(list((state/'chapters').glob('*.txt'))),3)

    def test_failed_refinement_is_recovered_without_regeneration(self):
        from storyforge.fixture import respond
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
            root = Path(d)
            initial = stage('prepare', root/'unused', root/'prepare', backend='worker')
            shutil.copytree(root/'prepare', root/'inputs/state')
            seed = root/'inputs/seed'
            (seed/'calls').mkdir(parents=True)
            (seed/'packets').mkdir()
            raw = json.loads(respond('refiner', {}, initial['request']))
            raw['reader_experience'] = ['Investigation', 'Costly hope']
            (seed/'calls/refiner-seed.json').write_text(json.dumps({'output':json.dumps(raw)}))
            (seed/'packets/refiner-seed.json').write_text(json.dumps({'input':{'request':initial['request']}}))
            with patch('storyforge.dag.Executor.call', side_effect=AssertionError('Must reuse saved generation')):
                recovered = stage('refine', root/'inputs', root/'recovered', backend='worker')
            self.assertEqual(recovered['refinement']['reader_experience'], 'Investigation; Costly hope')
            self.assertIn('refinement_recovery', recovered)

    def test_worker_backend_does_not_dispatch_remote_workflows(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()), patch('storyforge.local_worker.execute',return_value=('Complete artifact',{'finish_reason':'stop'})) as worker:
            result = Executor(example(),folder,'worker').call('writer',{'only':'scoped context'},'write')
            self.assertEqual(result,'Complete artifact')
            worker.assert_called_once()

    def test_generated_workflow_is_current_and_has_parallel_branches(self):
        import importlib.util
        path = Path(__file__).resolve().parents[1] / 'scripts/build_workflow.py'
        spec = importlib.util.spec_from_file_location('workflow_builder',path)
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        workflow = builder.build()
        self.assertEqual(workflow,(path.parents[1]/'.github/workflows/story.yml').read_text())
        self.assertIn('max-parallel: 3',workflow)
        self.assertIn('s01_story:',workflow)
        self.assertIn('s01_memory:',workflow)
        self.assertNotIn('GH_AI_TOKEN',workflow)
        self.assertNotIn('/dispatches',workflow)

if __name__ == '__main__':
    unittest.main()
