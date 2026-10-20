"""Artifact-driven stages for one visible Actions DAG, with a single canon writer."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from . import contracts
from .coordinator import compact, packet, visible, PLAN_INSTRUCTION, MEMORY_INSTRUCTION
from .inference import Executor, ROOT
from .retrieval import retrieve
from .storage import load, save, export

REFINE = 'Develop the premise, preserving explicit user choices and marking assumptions. Return only JSON with original_prompt (exact request premise), refined_prompt, central_conflict, reader_experience (strings), and preserved_user_choices, expanded_story_elements, character_tensions, subplot_possibilities, world_constraints, suggested_techniques, retrieval_references, assumptions, open_decisions (arrays). No chapters yet.'


def output(name, value):
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(name + '=' + (value if isinstance(value, str) else json.dumps(value)) + '\n')


def context(req, state, card):
    return packet(req, state, card)


def actor_packet(req, state, card, cid):
    contracts.require(cid in card['participants'], 'Character not in this scene')
    return {'character': next(c for c in req['characters'] if c['id'] == cid),
            'situation': {'location': card['location'], 'time': card['time']},
            'known_facts': compact(visible(state['memories'], cid)), 'world_rules': req['world_rules']}


def stage(task, source, out, index=0, character=None, request_file='silent-bell-full', profile='balanced', backend='fixture'):
    source, out = Path(source), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if task == 'prepare':
        req = contracts.request(load(ROOT / 'examples' / f'{request_file}.json'))
        req['profile'] = profile
        contracts.require(req['chapters'] == 3 and req['scenes_per_chapter'] == 3, 'This test DAG has exactly three chapters of three scenes')
        contracts.require(req['auto_approve_plan'], 'This automated DAG requires explicit auto_approve_plan in the request')
        state = {'version': 0, 'backend': backend, 'accepted': [],
                 'memories': [dict(f, kind='event', source='user_input') for f in req['initial_facts']],
                 'request_hash': hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest(),
                 'retrieval': retrieve(req), 'request': req}
        save(out / 'snapshot.json', state)
        return state
    state = load(source / 'state' / 'snapshot.json')
    req = state['request']
    executor = Executor(req, out, backend)
    if task == 'refine':
        state['refinement'] = executor.call('refiner', {'request': req, 'inspiration': state['retrieval']}, REFINE, tokens=2400, validator=lambda x: contracts.refinement(x, req))
        save(out / 'refinement.json', state['refinement'])
        save(out / 'snapshot.json', state)
        return state
    if task == 'plan':
        state['plan'] = executor.call('architect', {'request': req, 'refinement': state['refinement'], 'inspiration': state['retrieval']}, PLAN_INSTRUCTION, tokens=3800, validator=lambda x: contracts.plan(x, req), skill=(ROOT / 'skills/story_architect.md').read_text().split('TECHNIQUE LIBRARY')[0])
        state['plan_approved'] = True
        save(out / 'plan.json', state['plan'])
        save(out / 'snapshot.json', state)
        output('characters', state['plan']['scenes'][0]['participants'])
        return state
    card = state['plan']['scenes'][index]
    scene_packet = context(req, state, card)
    budget = min(2400, int(req['words_per_scene'] * 2.2) + 200)
    quality_skill = (ROOT / 'skills/story_quality.md').read_text()
    if task == 'character':
        result = executor.call('character', actor_packet(req, state, card, character), 'Propose one observable action or spoken line pursuing your goal in this situation. Use only known facts. Do not disclose private reasoning or secrets as commentary.', tokens=220)
        save(out / 'proposal.json', {'character': character, 'observable_proposal': result, 'state_version': state['version']})
        return
    if task == 'director':
        proposals = [load(p) for p in sorted((source / 'characters').rglob('proposal.json'))]
        contracts.require(len(proposals) == len(card['participants']) and {p['character'] for p in proposals} == set(card['participants']), 'Missing/duplicate character proposals')
        contracts.require(all(p['state_version'] == state['version'] for p in proposals), 'Stale character proposal')
        result = executor.call('director', {'scene_context': scene_packet, 'proposals': proposals}, 'Propose 3–5 concise beats. Respect POV, knowledge, rules, and intended change. Proposals are optional and are not canon.', tokens=500)
        save(out / 'direction.txt', result)
        return
    if task == 'writer':
        scene_packet['direction'] = (source / 'direction/direction.txt').read_text()
        result = executor.call('writer', scene_packet, 'Write complete scene prose at target_words. No summary, heading, commentary, or canon delta. Respect POV, knowledge, rules, and voices. Give choices consequences.', tokens=budget)
        save(out / 'draft.txt', result)
        return
    if task == 'edit':
        draft = (source / 'draft/draft.txt').read_text()
        result = executor.call('humanizer', {'context': scene_packet, 'prose': draft}, 'Edit only what needs improvement. Preserve events, evidence, knowledge, POV, deliberate style, and approximate length. Return complete prose alone.', tokens=budget, skill=(ROOT / 'skills/distinct_writing.md').read_text())
        save(out / 'prose.txt', result)
        return
    if task == 'repair':
        prose = (source / 'edited/prose.txt').read_text()
        review = load(source / 'diagnosis/review.json')
        changed = not review['pass'] and req['max_repairs'] > 0
        before = hashlib.sha256(prose.encode()).hexdigest()
        if changed:
            prose = executor.call('writer', {'context': scene_packet, 'prose': prose, 'review': review},
                'Repair the cited violations. Preserve unaffected facts and deliberate voice. Return complete scene prose near target_words, with no commentary.', tokens=budget, skill=(ROOT / 'skills/distinct_writing.md').read_text())
        save(out / 'prose.txt', prose)
        save(out / 'repair.json', {'changed': changed, 'reviewed_sha256': before, 'candidate_sha256': hashlib.sha256(prose.encode()).hexdigest()})
        return
    if task in {'story_review', 'verify', 'memory', 'memory_final'}:
        prose = (source / 'edited/prose.txt').read_text()
        if task in {'verify', 'memory_final'}:
            repair = load(source / 'edited/repair.json')
            contracts.require(hashlib.sha256(prose.encode()).hexdigest() == repair['candidate_sha256'], 'Candidate hash mismatch')
            if not repair['changed']:
                contracts.require(repair['candidate_sha256'] == repair['reviewed_sha256'], 'Cannot reuse review after prose changes')
                if task == 'verify':
                    save(out / 'review.json', contracts.review(load(source / 'diagnosis/review.json'), prose))
                else:
                    save(out / 'memory.json', contracts.delta(load(source / 'initial-memory/memory.json'), prose, [c['id'] for c in req['characters']]))
                return
        if task in {'story_review', 'verify'}:
            verdict = executor.call('story_quality', {'scene': card, 'request': {k: req.get(k) for k in ['premise', 'pov', 'world_rules', 'must_avoid', 'ending_tendency', 'initial_facts']}, 'accepted_memories': compact(state['memories'], 36), 'original_draft': (source / 'draft/draft.txt').read_text(), 'current_prose': prose}, 'Review current_prose and return the required JSON.', tokens=1400, validator=lambda x: contracts.review(x, prose), skill=quality_skill)
            words = len(prose.split())
            if backend != 'fixture' and not req['words_per_scene'] * req['min_words_ratio'] <= words <= req['words_per_scene'] * req['max_words_ratio']:
                verdict['pass'] = False
                verdict['issues'].append({'severity': 'blocking', 'category': 'length', 'quote': prose[:80], 'problem': f'{words} words outside target tolerance', 'fix': f'Return a complete scene near {req["words_per_scene"]} words.'})
            save(out / 'review.json', verdict)
        else:
            result = executor.call('memory', {'prose': prose, 'scene': card, 'characters': [c['id'] for c in req['characters']], 'existing': compact(state['memories'])}, MEMORY_INSTRUCTION, tokens=1600, validator=lambda x: contracts.delta(x, prose, [c['id'] for c in req['characters']]))
            save(out / 'memory.json', result)
        return
    if task == 'memory_review':
        prose = (source / 'edited/prose.txt').read_text()
        verdict = executor.call('memory_quality', {'current_prose': prose, 'proposed_memory': load(source / 'memory/memory.json'), 'prior_memory': compact(state['memories'], 36)}, 'Check proposed_memory for unsupported inference, contradiction, false knowledge acquisition, or belief/claim presented as fact. Return required review JSON with quotations from current_prose.', tokens=1200, validator=lambda x: contracts.review(x, prose), skill=quality_skill)
        save(out / 'review.json', verdict)
        return
    if task == 'accept':
        contracts.require(len(state['accepted']) == index, 'Commit does not follow accepted scene order')
        review = load(source / 'story-review/review.json')
        memory_review = load(source / 'memory-review/review.json')
        save(out / 'reviews.json', {'story': review, 'memory': memory_review})
        contracts.require(review['pass'] and memory_review['pass'], 'Review rejected scene or memory; no canon commit. Inspect saved review artifacts.')
        prose = (source / 'edited/prose.txt').read_text()
        memory = contracts.delta(load(source / 'memory/memory.json'), prose, [c['id'] for c in req['characters']])
        if (index + 1) % req['scenes_per_chapter'] == 0:
            chapter_prose = '\n\n'.join([s['prose'] for s in state['accepted'] if s['chapter'] == card['chapter']] + [prose])
            chapter_review = executor.call('chapter_quality', {'chapter': card['chapter'], 'current_prose': chapter_prose, 'rules': req['world_rules'], 'chapter_plan': [s for s in state['plan']['scenes'] if s['chapter'] == card['chapter']]}, 'Review full chapter for continuity and intended progression. Return review JSON; quote current_prose.', tokens=1400, validator=lambda x: contracts.review(x, chapter_prose), skill=quality_skill)
            save(out / 'chapter-review.json', chapter_review)
            contracts.require(chapter_review['pass'], 'Chapter review rejected; no final scene commit')
        result = copy.deepcopy(state)
        result['version'] += 1
        result['accepted'].append({'id': card['id'], 'chapter': card['chapter'], 'pov': card['pov'], 'participants': card['participants'], 'prose': prose, 'review': review, 'memory_review': memory_review, 'state_version': result['version']})
        result['memories'].extend(dict(m, source=card['id']) for m in memory['memories'])
        result['complete'] = len(result['accepted']) == len(result['plan']['scenes'])
        save(out / 'snapshot.json', result)
        export(out, result, req)
        output('characters', result['plan']['scenes'][index + 1]['participants'] if not result['complete'] else [])
        return result
    raise ValueError(f'Unknown DAG task: {task}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('task')
    parser.add_argument('--source', default='inputs')
    parser.add_argument('--out', default='out')
    parser.add_argument('--index', type=int, default=0)
    parser.add_argument('--character')
    parser.add_argument('--request-file', default='silent-bell-full')
    parser.add_argument('--profile', default='balanced')
    parser.add_argument('--backend', choices=['fixture', 'worker'], default='fixture')
    args = parser.parse_args()
    stage(args.task, args.source, args.out, args.index, args.character, args.request_file, args.profile, args.backend)

if __name__ == '__main__':
    main()
