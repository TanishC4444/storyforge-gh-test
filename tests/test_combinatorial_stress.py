import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from scripts.combinatorial_stress import covering_cases, combinations, pairs, make_request, live_cases
from storyforge.contracts import request
from storyforge.storage import save, load


class CombinatorialStressTests(unittest.TestCase):
    def test_seeded_covering_array_covers_every_pair_without_exhaustive_execution(self):
        cases = covering_cases()
        expected = set().union(*(pairs(c) for c in combinations()))
        self.assertEqual(set().union(*(pairs(c) for c in cases)), expected)
        self.assertEqual(cases, covering_cases())
        self.assertNotEqual(cases, covering_cases(17))
        self.assertLess(len(cases), 100)
        self.assertEqual(len(combinations()), 6480)

    def test_live_cases_cover_all_requested_levels_and_have_valid_authored_plans(self):
        from scripts.combinatorial_stress import DIMENSIONS
        from storyforge.craft import compile_scene_plan
        for axis, values in DIMENSIONS.items():
            self.assertEqual({c[axis] for c in live_cases()}, set(values))
        for i, case in enumerate(live_cases()):
            req = make_request(case, f'live-{i}')
            self.assertEqual(len(compile_scene_plan(req)['scenes']), case['scenes'])
            self.assertEqual(len(req['characters']), case['cast'])
            self.assertEqual(req['words_per_scene'], case['words'])
            self.assertNotIn('Troy', req['premise'])
            self.assertEqual(req['adaptation']['strength'], 0)

    def test_invalid_boundaries_cannot_enter_the_graph(self):
        base = make_request(live_cases()[0], 'invalid-boundaries')
        invalid = [dict(words_per_scene=99), dict(words_per_scene=1601),
                   dict(chapters=0), dict(chapters=13), dict(scenes_per_chapter=0),
                   dict(scenes_per_chapter=9), dict(characters=[]), dict(medium='unsupported'),
                   dict(characters=[base['characters'][0]]*2),
                   dict(initial_facts=[{'text':'Secret','known_by':['unknown-person']}]),
                   dict(creative_freedom={'enabled':True,'cast_limit':33})]
        for override in invalid:
            with self.subTest(override=override), self.assertRaises(ValueError):
                request({**copy.deepcopy(base), **override})

    def test_live_measures_reject_short_output_even_when_actions_and_reviews_pass(self):
        from scripts.live_matrix_stress import assess_measures
        case = live_cases()[0]
        req = make_request(case, 'measure-test')
        row = {'pass':True,'audit':{'expected_scenes':1,'cast':1,'retained_initial_facts':0,
               'scenes':[{'scene':'ch01-sc01','words':100,'approved':True,'factual_proof_bound':True}]}}
        self.assertTrue(assess_measures(case, row, req)['pass'])
        row['audit']['scenes'][0]['words'] = 20
        self.assertFalse(assess_measures(case, row, req)['pass'])
        row['audit']['scenes'][0]['words'] = 2000
        self.assertFalse(assess_measures(case, row, req)['pass'])

    def test_episode_audit_cannot_shrink_the_requested_scene_count(self):
        from storyforge.episode_audit import audit
        from storyforge.batch_pipeline import bind_state
        from storyforge.patching import digest
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prose = 'The keeper opens the gate.'
            passed = {'pass':True}
            scene = {'id':'ch01-sc01','prose':prose,'canon_committed':True,
                     'quality_status':'reviewed','review':passed,'rhetoric_review':passed,'memory_review':passed}
            state = {'accepted':[scene],'plan':{'scenes':[{}]},'request':{'characters':[]},'memories':[]}
            before = {'accepted':[]}
            facts = {'memories':[]}
            proof = {'pass':True,'source_sha256':digest(prose),'state_sha256':bind_state(before),'memory_sha256':bind_state(facts)}
            save(root/'results/s01_accept/snapshot.json',state)
            save(root/'results/s01_design/snapshot.json',before)
            save(root/'results/s01_final_memory/memory.json',facts)
            save(root/'results/s01_memory_review/review.json',proof)
            self.assertTrue(audit(root/'results',root/'one',1)['pass'])
            result = audit(root/'results',root/'two',2)
            self.assertFalse(result['pass'])
            self.assertEqual(result['expected_scenes'], 2)
            self.assertIn('Expected 2 scenes; found 1',result['errors'])

    def test_ledger_lock_serializes_independent_processes(self):
        # Actual child processes exercise the OS lock, not a mocked lock API.
        program = '''import sys,time
from pathlib import Path
from storyforge.file_lock import flock,LOCK_EX
p=Path(sys.argv[1])
for _ in range(12):
 with (p/'ledger.lock').open('a') as lock:
  flock(lock,LOCK_EX)
  n=int((p/'counter').read_text())
  time.sleep(.001)
  (p/'counter').write_text(str(n+1))
'''
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'counter').write_text('0')
            def child(_):
                return subprocess.run([sys.executable,'-c',program,folder],capture_output=True,text=True,timeout=30)
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(child, range(4)))
            self.assertTrue(all(p.returncode==0 for p in results), [p.stderr for p in results])
            self.assertEqual((Path(folder)/'counter').read_text(), '48')


if __name__ == '__main__':
    unittest.main()
