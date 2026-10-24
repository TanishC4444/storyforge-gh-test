"""Six bounded, sequential live runs of the full existing Actions pipeline."""
import json
import os
from pathlib import Path
from scripts.combinatorial_stress import live_cases
from scripts.stress_queue import GitHub, Queue, validate_suite
from storyforge.storage import load, save


def assess_measures(case, row, req):
    audit = row.get('audit', {})
    scenes = audit.get('scenes', [])
    errors = []
    low = req['words_per_scene'] * req['min_words_ratio']
    high = req['words_per_scene'] * req['max_words_ratio']
    if len(scenes) != case['scenes'] or audit.get('expected_scenes') != case['scenes']:
        errors.append('Requested scene count not delivered')
    if audit.get('cast') != case['cast']:
        errors.append('Audit cast differs from requested cast')
    if audit.get('retained_initial_facts') != len(req['initial_facts']):
        errors.append('Initial memory count changed')
    for scene in scenes:
        words = scene.get('words', 0)
        if not low <= words <= high:
            errors.append(f'{scene.get("scene")}: {words} words outside {low:g}–{high:g}')
        if not scene.get('approved') or not scene.get('factual_proof_bound'):
            errors.append(f'{scene.get("scene")}: approval or final-source binding missing')
    return {'pass':not errors, 'errors':errors, 'requested_words_per_scene':req['words_per_scene'],
            'allowed_word_range':[low,high], 'actual_scene_words':[s.get('words',0) for s in scenes],
            'word_ratios':[round(s.get('words',0)/req['words_per_scene'],3) for s in scenes],
            'genre_and_form':'Included in the author contract and model reviews; human literary assessment remains separate.'}


class MeasuredQueue(Queue):
    def collect(self, case, run):
        row = super().collect(case, run)
        req = load(Path(__file__).resolve().parents[1]/'examples'/f'{case["request_file"]}.json')
        row['measures'] = assess_measures(case, row, req)
        row['pass'] = row['pass'] and row['measures']['pass']
        row['assessment'] = 'approved' if row['pass'] else 'needs_revision'
        save(self.out/case['id']/'result.json', row)
        return row


def main():
    suite = {'version':1,'per_run_timeout_minutes':20,'poll_seconds':30,
             'max_scene_retries':0,'cases':[
                 {'id':f'matrix-{i+1:02}','request_file':f'matrix-live-{i+1:02}',
                  'medium':c['medium'],'words_per_scene':c['words'],'scenes':c['scenes'],
                  'cast':c['cast'],'genre':c['genre'],'complexity':c['complexity']}
                 for i,c in enumerate(live_cases())]}
    validate_suite(suite)
    api = GitHub(os.environ['GITHUB_REPOSITORY'],os.environ['GH_TOKEN'])
    queue = MeasuredQueue(api,suite,'live-matrix-results',os.environ['GITHUB_REF_NAME'],os.environ['GITHUB_SHA'],
                  'matrix-'+os.environ['GITHUB_RUN_ID'])
    try:
        passed = queue.run()
    finally:
        if queue.active:
            api.api(f'actions/runs/{queue.active}/cancel','POST')
        queue.save()
    if not passed:
        raise SystemExit('Live matrix contains unapproved or incomplete cases; inspect report.json.')


if __name__ == '__main__':
    main()
