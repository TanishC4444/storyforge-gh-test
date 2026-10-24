"""Six bounded, sequential live runs of the full existing Actions pipeline."""
import json
import os
from pathlib import Path
from scripts.combinatorial_stress import live_cases
from scripts.stress_queue import GitHub, Queue, validate_suite


def main():
    suite = {'version':1,'per_run_timeout_minutes':20,'poll_seconds':30,
             'max_scene_retries':0,'cases':[
                 {'id':f'matrix-{i+1:02}','request_file':f'matrix-live-{i+1:02}',
                  'medium':c['medium'],'words_per_scene':c['words'],'scenes':c['scenes'],
                  'cast':c['cast'],'genre':c['genre'],'complexity':c['complexity']}
                 for i,c in enumerate(live_cases())]}
    validate_suite(suite)
    api = GitHub(os.environ['GITHUB_REPOSITORY'],os.environ['GH_TOKEN'])
    queue = Queue(api,suite,'live-matrix-results',os.environ['GITHUB_REF_NAME'],os.environ['GITHUB_SHA'],
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
