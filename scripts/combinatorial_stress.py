"""Seeded, measured input coverage of the actual separate-runner Actions graph.

Fixture execution tests orchestration and contracts, never model quality. Live
cases use scripts.live_matrix_stress and the unchanged Living pipeline. Reports
keep those two kinds of evidence separate and failures always fail this suite.
"""
from __future__ import annotations
import argparse
import copy
from contextlib import redirect_stdout
import fnmatch
import io
import itertools
import json
import os
from pathlib import Path
import random
import shlex
import shutil
import sys
import tempfile
import time
import traceback
from unittest.mock import patch
import yaml
from storyforge.storage import load, save

ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS = {
    'medium': ['short_story', 'book', 'screenplay', 'stage_play', 'audio_drama', 'comic_script'],
    'genre': ['mystery', 'fantasy', 'science fiction', 'romance', 'historical', 'horror'],
    'scenes': [1, 2, 4],
    'words': [100, 350, 800, 1600],
    'cast': [1, 2, 8, 16, 32],
    'complexity': ['simple', 'layered', 'dense'],
}


def combinations():
    return [dict(zip(DIMENSIONS, values)) for values in itertools.product(*DIMENSIONS.values())]


def pairs(case):
    return {(a, str(case[a]), b, str(case[b])) for a, b in itertools.combinations(DIMENSIONS, 2)}


def covering_cases(seed=104729):
    """Greedy covering array with an independently checkable coverage proof."""
    candidates = combinations()
    random.Random(seed).shuffle(candidates)
    indexed = [(case, pairs(case)) for case in candidates]
    uncovered = set().union(*(p for _, p in indexed))
    chosen = []
    while uncovered:
        case, covered = max(indexed, key=lambda item: len(item[1] & uncovered))
        chosen.append(case)
        uncovered -= covered
    return chosen


def make_request(case, ident):
    template = load(ROOT/'examples/living-scale-practice.json')
    req = copy.deepcopy(template)
    # Replace the author material as well as the settings: do not keep Troy
    # characters or source influence in an unrelated genre test.
    req.update(project_id=ident, title=ident, universe_id=ident, medium=case['medium'],
               genre=case['genre'], chapters=case['scenes'], scenes_per_chapter=1,
               words_per_scene=case['words'], brief_version=2, references=[],
               premise=f"An original {case['genre']} {case['medium']}: a keeper must decide whether to open a storm-damaged refuge. Each scene changes the available options; preserve costs and private knowledge.",
               pov='Third person, past tense. One focal character per scene.',
               tone_mood='Specific and restrained; earn emotion through choices.',
               sensory_detail='Use details appropriate to the chosen genre and location.',
               reader_experience='A consequential choice under growing pressure.',
               ending_tendency='Resolve the immediate decision; preserve its costs.',
               must_avoid=['Unmotivated rescue', 'Private knowledge leaking to other characters'],
               chapter_arcs=[], quality_contract=[], reference_policy='Original story; no pinned adaptation.',
               retrieval_query=case['genre']+' choices duty trust consequence',
               adaptation={'strength':0, 'mode':'mechanisms', 'max_active_sources_per_scene':0, 'preserve_user_choices':True},
               style={'figurative_language':{'density':'sparse','devices':['metaphor'],'image_domains':['weather']},
                      'interiority':'selective','dialogue':'character specific'},
               keywords=[{'term':case['genre'],'kind':'theme','priority':3}],
               length_policy={'scene_words':'strict','chapter_words':'target','allow_compression':False})
    req.pop('chapter_contract', None)
    req.pop('narrative_contract', None)
    count = {'simple':0, 'layered':16, 'dense':96}[case['complexity']]
    req['characters'] = []
    for i in range(case['cast']):
        char = copy.deepcopy(template['characters'][0])
        char.update(id=f'person{i:02}', name=f'Keeper {i}', goal=f'Protect obligation {i}',
                    voice=f'Precise practical language; recurring concern {i}.')
        req['characters'].append(char)
    ids = [c['id'] for c in req['characters']]
    req['creative_freedom'] = {'enabled':True,'new_characters':False,'character_deaths':False,
                               'protected_characters':ids,'max_new_per_scene':0,'cast_limit':32}
    req['initial_facts'] = [{'kind':'event','text':f'{req["characters"][i % len(ids)]["name"]} holds private obligation {i}.',
                            'known_by':[ids[i % len(ids)]],'fact_key':f'obligation:{i}'} for i in range(count)]
    req['world_rules'] = [f'Refuge section {i} can be opened only by physical work, never by a convenient unexplained rescue.'
                          for i in range({'simple':1,'layered':8,'dense':24}[case['complexity']])]
    req['world_design'] = {'technology':'Manual gates and lamps','institutions':'A refuge with contested access',
                           'physical_systems':'Storm damage limits access','deadlines':'The next tide'}
    req['plot_design'] = {'central_question':'What will the keeper risk to admit a stranger?',
                          'causal_dependencies':['Each decision reduces the remaining time.'],
                          'subplots':[{'id':'trust','owner':ids[0],'question':'Can duty coexist with trust?',
                                       'intersection':'The gate decision','removal_cost':'Lose personal stakes'}],
                          'alternatives_and_costs':['Keep the gate shut and abandon someone outside.']}
    req['scene_designs'] = []
    for i in range(case['scenes']):
        participants = [ids[(i+j) % len(ids)] for j in range(min(len(ids), 2 if case['complexity']=='simple' else 8))]
        req['scene_designs'].append({'id':f'ch{i+1:02}-sc01','pov':participants[0],'participants':participants,
            'location':f'Refuge gate {i+1}','setting':'A crowded refuge during a damaging storm.',
            'time':('Yesterday, a witnessed cause' if case['complexity']=='dense' and i==1 else f'Today, interval {i+1}'),
            'dramatic_function':f'Make the next distinct decision at gate {i+1}.',
            'development':'An observable bargain changes access and creates a cost.',
            'restrictions':'No reuse of spent resources; do not share private information without witnessing it.',
            'choice_and_consequence':f'The keeper risks obligation {i}; one gate opens and another option closes.'})
    from storyforge.contracts import request
    return request(req)


def validate_grid(cases=None):
    from storyforge.craft import compile_scene_plan
    errors = []
    all_cases = combinations() if cases is None else cases
    for i, case in enumerate(all_cases):
        try:
            req = make_request(case, f'grid-{i:05}')
            plan = compile_scene_plan(req)
            if len(plan['scenes']) != case['scenes'] or len(req['characters']) != case['cast']:
                raise AssertionError('Compiled dimensions differ from supplied inputs')
        except Exception as exc:
            errors.append({'case':case,'error':str(exc)})
    return {'total':len(all_cases),'passed':len(all_cases)-len(errors),'failures':errors}


def execute_graph(case, destination, ident):
    """Run the YAML's real jobs and artifact manifests in dependency order.

    Every stage has its own directory, immutable upstream copies and the same
    matrix expansion as Actions. No single-coordinator replacement is used.
    """
    from storyforge import batch_pipeline as b, living_stages as ls, dag
    from storyforge.living_prepare import prepare
    from storyforge.episode_audit import audit
    started = time.monotonic()
    dest = Path(destination)
    req = make_request(case, ident)
    save(dest/'request.json', req)
    jobs = yaml.safe_load((ROOT/'.github/workflows/living-universe-pipeline.yml').read_text(encoding='utf-8'))['jobs']
    executed = []
    active = 'prepare'
    try:
        with tempfile.TemporaryDirectory(prefix='sf-matrix-') as scratch, patch.dict(os.environ, {
            'STORY_LEAN_LIVING':'true','STORY_LIVING_PIPELINE':'true','STORY_HOSTED_ONLY':'true'}), redirect_stdout(io.StringIO()):
            root = Path(scratch)
            save(root/'examples'/f'{ident}.json', req)
            with patch.object(dag, 'ROOT', root):
                dag.stage('prepare',root/'none',root/'prepare',request_file=ident,profile='fast',backend='fixture')
            prepare(root/'prepare/snapshot.json',root/'quickstart',backend='fixture')
            artifacts = {'prepare':root/'prepare','quickstart':root/'quickstart'}
            prefixes = tuple(f's{i+1:02}_' for i in range(case['scenes']))
            pending = {k for k in jobs if k.startswith(prefixes)}
            done = {'prepare','quickstart'}
            def required(prefix, field):
                if field == 'repair_required':
                    proof = load(artifacts[prefix]/'review.json')
                    return not proof.get('pass') or proof.get('unverified',False)
                filename = 'extract-plan.json' if field=='refresh_required' else 'memory-plan.json'
                value = load(artifacts[prefix]/filename)
                return any(x['ids'] for x in value['batches']) if field=='refresh_required' else not bool(value.get('reused_preflight'))
            while pending:
                ready = sorted(k for k in pending if set(jobs[k].get('needs',[])) <= done)
                if not ready:
                    raise AssertionError('Blocked graph: '+','.join(sorted(pending)))
                for key in ready:
                    active = key
                    job = jobs[key]
                    index = int(key[1:3])-1
                    prefix = key[:3]
                    skip = (key.endswith('_memory_refresh_batches') and not required(prefix+'_repair','refresh_required')) or (key.endswith('_memory_final_batches') and not required(prefix+'_final_memory','checks_required'))
                    if ('_memory_recovery_' in key or key.endswith('_memory_recovered')) and not required(prefix+'_memory_review','repair_required'):
                        skip = True
                    if skip:
                        done.add(key); pending.remove(key)
                        continue
                    matrix = job.get('strategy',{}).get('matrix',{})
                    axis = None
                    if 'character' in matrix:
                        axis = 'character'
                        values = load(artifacts[prefix+'_design']/'snapshot.json')['plan']['scenes'][index]['participants']
                    elif 'batch' in matrix:
                        axis = 'batch'
                        value = matrix['batch']
                        if isinstance(value,list):
                            values = value
                        else:
                            upstream = value.split('needs.',1)[1].split('.outputs.',1)[0]
                            filename = 'draft-plan.json' if upstream.endswith('_direction') else 'extract-plan.json' if upstream.endswith(('_draft','_repair','_memory_recovery_plan')) else 'repair-plan.json' if upstream.endswith('_repair_plan') else 'memory-plan.json'
                            value = load(artifacts[upstream]/filename)
                            values = [x['id'] for x in value.get('batches',value.get('beats',[]))]
                    else:
                        values = [None]
                    for value in values:
                        folder = root/key/(str(value) if value is not None else 'single')
                        source, out = folder/'inputs', folder/'out'
                        arrangement = next(s for s in job['steps'] if s.get('name')=='Bind downloaded artifacts to explicit source aliases')
                        manifest = json.loads(arrangement['env']['STORY_ARTIFACT_MANIFEST'])
                        for name, artifact in artifacts.items():
                            if any(fnmatch.fnmatch(name,spec['name']) for spec in manifest):
                                shutil.copytree(artifact,folder/'incoming'/name)
                        needs = {}
                        for suffix,field in [('_repair','refresh_required'),('_final_memory','checks_required'),('_memory_review','repair_required')]:
                            if prefix+suffix in artifacts:
                                needs[prefix+suffix] = {'outputs':{field:str(bool(required(prefix+suffix,field))).lower()}}
                        ls.arrange(folder/'incoming',source,manifest,needs)
                        command = next(s['run'] for s in job['steps'] if s.get('id')=='task')
                        line = next(line for line in command.splitlines() if line.startswith('python -m'))
                        parts = shlex.split(line.replace('$backend','fixture').replace('$STORY_BATCH',str(value)).replace('$STORY_CHARACTER',str(value)))
                        if parts[2]=='storyforge.living_stages':
                            ls.execute(parts[3],source,out,index,'fixture')
                        elif parts[2]=='storyforge.dag':
                            dag.stage(parts[3],source,out,index=index,character=value if axis=='character' else None,profile='fast',backend='fixture')
                        else:
                            with patch.object(sys,'argv',['batch_pipeline']+parts[3:]+['--source',str(source),'--out',str(out)]):
                                b.main()
                        artifacts[key+('-'+str(value) if axis else '')] = out
                        executed.append({'job':key,'matrix':value})
                    done.add(key);pending.remove(key)
            for name, folder in artifacts.items():
                if name.endswith(('_accept','_design','_final_memory','_memory_review','_memory_recovery_join')):
                    shutil.copytree(folder,root/'results'/name)
            assessment = audit(root/'results',dest/'audit',case['scenes'])
            final = load(artifacts[f's{case["scenes"]:02}_accept']/'snapshot.json')
            save(dest/'final-snapshot.json',final)
            save(dest/'readable.txt','FIXTURE TRANSPORT ONLY; NOT MODEL QUALITY\n\n'+'\n\n'.join(s['prose'] for s in final['accepted']))
            if not assessment['pass'] or not final['complete'] or len(final['accepted']) != case['scenes']:
                raise AssertionError('Final scene approvals/count/evidence audit failed')
            if assessment['retained_initial_facts'] != len(req['initial_facts']):
                raise AssertionError('Initial facts changed')
        result = {'id':ident,'inputs':case,'pass':True,'audit':assessment}
    except (Exception, SystemExit) as exc:
        result = {'id':ident,'inputs':case,'pass':False,'failed_job':active,'error':str(exc),'traceback':traceback.format_exc()}
    result.update(seconds=round(time.monotonic()-started,3),executed_jobs=len(executed),
                  execution='fixture_separate_runner_graph',model_quality_tested=False,length_quality_tested=False)
    save(dest/'result.json',result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',default='stress-matrix-results')
    p.add_argument('--seed',type=int,default=104729)
    p.add_argument('--case',type=int)
    p.add_argument('--limit',type=int)
    p.add_argument('--grid-only',action='store_true')
    p.add_argument('--coverage',choices=['representative','pairwise'],default='representative')
    p.add_argument('--exhaustive-contracts',action='store_true',help='Opt in to the 6,480 input-contract combinations')
    p.add_argument('--emit-live',action='store_true')
    args = p.parse_args()
    out = Path(args.out);out.mkdir(parents=True,exist_ok=True)
    cases = covering_cases(args.seed) if args.coverage=='pairwise' else representative_cases()
    full = set().union(*(pairs(c) for c in combinations()))
    covered = set().union(*(pairs(c) for c in cases))
    manifest = {'seed':args.seed,'strategy':args.coverage,'dimensions':DIMENSIONS,'cartesian_count':len(combinations()),
                'selected_cases':len(cases),'covered_pairs':len(covered),'total_pairs':len(full),
                'pairwise_complete':covered==full,'cases':cases}
    save(out/'manifest.json',manifest)
    if args.emit_live:
        for i, case in enumerate(live_cases()):
            save(ROOT/'examples'/f'matrix-live-{i+1:02}.json',make_request(case,f'matrix-live-{i+1:02}'))
        return
    if args.case is not None:
        index = args.case
        result = execute_graph(cases[index],out/f'case-{index+1:03}',f'matrix-{index+1:03}')
        print(json.dumps({k:v for k,v in result.items() if k not in ('traceback','audit')}),flush=True)
        raise SystemExit(0 if result['pass'] else 1)
    grid = validate_grid(None if args.exhaustive_contracts else cases)
    save(out/'grid.json',grid)
    if args.grid_only:
        print(json.dumps({'grid':grid,'coverage':{k:v for k,v in manifest.items() if k not in ('cases','dimensions')}}))
        raise SystemExit(bool(grid['failures']))
    results = []
    selected = cases[:args.limit] if args.limit else cases
    for i, case in enumerate(selected):
        result = execute_graph(case,out/f'case-{i+1:03}',f'matrix-{i+1:03}')
        results.append(result)
        report = {'pass':not grid['failures'] and len(results)==len(cases) and all(r['pass'] for r in results),
                  'complete':len(results)==len(cases),'grid':grid,'coverage':manifest,'cases':results,
                  'scope':'Synthetic graph/contract evidence only; live generation is reported separately.'}
        save(out/'report.json',report)
        print(f'{i+1}/{len(cases)} {case} -> {result["pass"]} ({result["seconds"]}s)',flush=True)
    raise SystemExit(0 if report['pass'] else 1)


def live_cases():
    # All genres and media, each scene level, each length level, each cast level.
    # Sequential hosted calls; no Cartesian explosion of paid generation.
    return [dict(zip(DIMENSIONS, values)) for values in [
        ('short_story','mystery',1,100,1,'simple'),
        ('screenplay','fantasy',2,350,2,'layered'),
        ('audio_drama','science fiction',1,800,8,'dense'),
        ('stage_play','romance',2,350,16,'layered'),
        ('comic_script','historical',4,350,32,'dense'),
        ('book','horror',2,1600,8,'dense'),
    ]]


def representative_cases():
    # One case per genre/format covers every individual input level. Add one
    # combined upper boundary to expose scale interactions, rather than repeat
    # all combinations or spend model calls on each one.
    return live_cases()+[{'medium':'book','genre':'fantasy','scenes':4,'words':1600,
                          'cast':32,'complexity':'dense'}]


if __name__ == '__main__':
    main()
