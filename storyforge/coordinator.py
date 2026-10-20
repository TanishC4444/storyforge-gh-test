from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
from . import contracts
from .inference import Executor, ROOT
from .retrieval import retrieve
from .storage import export, load, lock, save

PLAN_INSTRUCTION = '''Return only JSON with keys title, threads (array of strings), technique_stack (array of strings), scenes.
Create exactly the requested chapter and scene counts, in reading order. Scenes have keys id (ch01-sc01, etc.), chapter (integer), pov (character ID), participants (character IDs), location, time, goal, obstacle, intended_change.
Honor requested length: each chapter is built from its scene word budgets. Follow PLAN mode, but this JSON contract overrides the attached brief's kickoff questions and free-form output rules. Intended changes are plans, not accepted events. Use only supplied character IDs. Build a complete local resolution by the final chapter. No prose chapter yet.'''
MEMORY_INSTRUCTION = '''Return only JSON {"memories": [{"kind": "event"|"belief"|"claim"|"resource"|"relationship"|"thread", "text": string, "evidence": exact quote of at least 12 characters from CURRENT prose, "known_by": [character IDs or "public"], "holder": character ID for beliefs}]}.
Extract at most 6 consequential updates. Facts, claims, and beliefs are distinct. A spoken claim is not objective truth. Only record knowledge acquisition supported in this scene; presence alone is not proof. Use public only for a public in-world disclosure, never just because the reader knows. No hypothetical, planned, rejected, or inferred offstage event. Preserve uncertainty. Only current prose is evidence.'''


def visible(memories, character=None):
    return [m for m in memories if 'public' in m['known_by'] or (character is not None and character in m['known_by'])]


def compact(memories, count=24):
    # Full source history remains on disk. This is explicit bounded working context.
    return memories[-count:]


def packet(req, state, card):
    return {
        'scene': card,
        'brief': {k: req.get(k) for k in ['premise', 'genre', 'reader_experience', 'pov', 'world_rules', 'must_avoid']},
        'characters': [{k: c.get(k) for k in ['id', 'name', 'voice']} for c in req['characters'] if c['id'] in card['participants']],
        'pov_profile': next(c for c in req['characters'] if c['id'] == card['pov']),
        'pov_visible_memory': compact(visible(state['memories'], card['pov'])),
        'recent_ending': state['accepted'][-1]['prose'][-1600:] if state['accepted'] and state['accepted'][-1]['pov'] == card['pov'] else '',
        'threads': state['plan']['threads'],
        'target_words': req['words_per_scene'],
    }


def run(req, folder, backend='fixture', *, stop_after=None, approve_plan=False):
    folder = Path(folder)
    with lock(folder):
        fingerprint = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()
        state_path = folder / 'state.json'
        if state_path.exists():
            state = load(state_path)
            contracts.require(state['request_hash'] == fingerprint, 'Request changed. Use a new run folder; in-place upstream edits are not supported.')
            contracts.require(state['backend'] == backend, 'Cannot mix fixture and live state')
        else:
            state = {'version': 0, 'backend': backend, 'request_hash': fingerprint, 'accepted': [],
                     'memories': [dict(f, kind='event', source='user_input') for f in req['initial_facts']]}
            save(folder / 'request.json', req)
            save(state_path, state)
        executor = Executor(req, folder, backend)
        if 'retrieval' not in state:
            state['retrieval'] = retrieve(req)
            save(folder / 'retrieval.json', state['retrieval'])
            save(state_path, state)
        if 'plan' not in state:
            planner_packet = {'request': req, 'inspiration': state['retrieval']}
            state['plan'] = executor.call('architect', planner_packet, PLAN_INSTRUCTION, tokens=3800,
                                         validator=lambda x: contracts.plan(x, req),
                                         skill=(ROOT / 'skills/story_architect.md').read_text())
            state['plan_approved'] = bool(req['auto_approve_plan'] or approve_plan)
            save(folder / 'plan.json', state['plan'])
            save(state_path, state)
        if approve_plan:
            state['plan_approved'] = True
            save(state_path, state)
        if not state['plan_approved']:
            print('Plan saved. Review plan.json, then resume with --approve-plan. Do not edit accepted state files.')
            return state
        export(folder, state, req)  # Rebuild projections after an interrupted write.
        completed_now = 0
        for card in state['plan']['scenes'][len(state['accepted']):]:
            sid = card['id']
            scene_dir = folder / 'work' / sid
            scene_packet = packet(req, state, card)
            proposals = []
            for cid in card['participants']:
                actor_packet = {'character': next(c for c in req['characters'] if c['id'] == cid),
                                'situation': {'location': card['location'], 'time': card['time']},
                                'known_facts': compact(visible(state['memories'], cid)),
                                'world_rules': req['world_rules']}
                proposal = executor.call('character', actor_packet,
                    'Propose one observable action or spoken line pursuing your goal in this situation. Remain within known facts. Return only the outward action; do not disclose private reasoning or secrets as commentary.', tokens=220)
                proposals.append({'character': cid, 'observable_proposal': proposal})
            direction = executor.call('director', {'scene_context': scene_packet, 'proposals': proposals},
                'Propose 3–5 concise beats for this scene. Preserve POV and knowledge boundaries. Proposals are optional; reconcile incompatible actions through plausible consequences. Do not invent a solution unsupported by the world rules. Return only beats.', tokens=500)
            scene_packet['direction'] = direction
            draft = executor.call('writer', scene_packet,
                'Write complete scene prose at target_words. No summary, title, commentary, or canon delta. Respect POV access, rules, voices, and planned scene function; give choices consequences. Techniques should serve this scene without being named.', tokens=min(2400, int(req['words_per_scene'] * 2.2) + 200))
            save(scene_dir / 'draft.txt', draft)
            accepted = None
            for repair in range(req['max_repairs'] + 1):
                polished = executor.call('humanizer', {'context': scene_packet, 'prose': draft},
                    'Edit only what needs improvement. Preserve events, evidence, private knowledge, POV, and deliberate style. Preserve approximate length. Return complete revised prose alone.',
                    tokens=min(2400, int(req['words_per_scene'] * 2.2) + 200), skill=(ROOT / 'skills/distinct_writing.md').read_text())
                save(scene_dir / f'distinct-{repair}.txt', polished)
                critic_packet = {'scene': card, 'request': req, 'accepted_memories': compact(state['memories'], 36),
                                 'original_draft': draft, 'current_prose': polished}
                verdict = executor.call('story_quality', critic_packet, 'Review current_prose. Return the required JSON only.', tokens=1400,
                                        validator=lambda x: contracts.review(x, polished), skill=(ROOT / 'skills/story_quality.md').read_text())
                words = len(polished.split())
                if backend != 'fixture' and not req['words_per_scene'] * req['min_words_ratio'] <= words <= req['words_per_scene'] * req['max_words_ratio']:
                    verdict['pass'] = False
                    verdict['issues'].append({'severity': 'blocking', 'category': 'length', 'quote': polished[:80], 'problem': f'{words} words outside requested tolerance', 'fix': f'Return a complete scene near {req["words_per_scene"]} words.'})
                save(scene_dir / f'review-{repair}.json', verdict)
                if verdict['pass']:
                    accepted = polished
                    break
                if repair < req['max_repairs']:
                    draft = executor.call('writer', {'context': scene_packet, 'prose': polished, 'review': verdict},
                                          'Repair the cited problems without changing unaffected facts. Return complete scene prose only.', tokens=min(2400, int(req['words_per_scene'] * 2.2) + 200))
            if accepted is None:
                raise contracts.ContractError(f'{sid} blocked after bounded repairs. Canon unchanged. Inspect work/{sid}. Start a new run for edited upstream inputs.')
            memory = executor.call('memory', {'prose': accepted, 'scene': card, 'characters': [c['id'] for c in req['characters']],
                                            'existing': compact(state['memories'])}, MEMORY_INSTRUCTION, tokens=1600,
                                   validator=lambda x: contracts.delta(x, accepted, [c['id'] for c in req['characters']]))
            # Second independent check of inference, not just quotation matching.
            memory_verdict = executor.call('memory_quality', {'current_prose': accepted, 'proposed_memory': memory,
                                                           'prior_memory': compact(state['memories'], 36)},
                'Check proposed_memory for unsupported inference, contradiction, false knowledge acquisition, or a belief/claim mislabeled as fact. Return the same review JSON contract; cite current_prose for every issue. A quote existing is not sufficient evidence that a conclusion follows.',
                tokens=1200, validator=lambda x: contracts.review(x, accepted), skill=(ROOT / 'skills/story_quality.md').read_text())
            save(scene_dir / 'memory.json', memory)
            save(scene_dir / 'memory-review.json', memory_verdict)
            contracts.require(memory_verdict['pass'], f'{sid} memory rejected; canon unchanged. Inspect memory review.')
            if card['id'] == state['plan']['scenes'][card['chapter'] * req['scenes_per_chapter'] - 1]['id']:
                chapter_prose = '\n\n'.join([x['prose'] for x in state['accepted'] if x['chapter'] == card['chapter']] + [accepted])
                chapter_verdict = executor.call('chapter_quality', {'chapter': card['chapter'], 'current_prose': chapter_prose,
                                                                  'rules': req['world_rules'], 'pov': req.get('pov'),
                                                                  'chapter_plan': [x for x in state['plan']['scenes'] if x['chapter'] == card['chapter']]},
                    'Review this complete chapter for repeated scene functions, continuity, information leaks, and whether its intended developments occur. Return the required review JSON; quote current_prose.',
                    tokens=1400, validator=lambda x: contracts.review(x, chapter_prose), skill=(ROOT / 'skills/story_quality.md').read_text())
                save(scene_dir / 'chapter-review.json', chapter_verdict)
                contracts.require(chapter_verdict['pass'], f'Chapter {card["chapter"]} review blocked; final scene not committed.')
            next_state = copy.deepcopy(state)
            next_state['version'] += 1
            next_state['accepted'].append({'id': sid, 'chapter': card['chapter'], 'pov': card['pov'], 'participants': card['participants'],
                                           'prose': accepted, 'review': verdict, 'memory_review': memory_verdict,
                                           'state_version': next_state['version']})
            next_state['memories'].extend(dict(m, source=sid) for m in memory['memories'])
            # state.json is the sole atomic source of truth. Other files are projections.
            save(state_path, next_state)
            state = next_state
            save(folder / 'checkpoints' / f'{sid}.json', state)
            export(folder, state, req)
            completed_now += 1
            print(f'Accepted {sid}; state version {state["version"]}; {words} words', flush=True)
            if stop_after is not None and completed_now >= stop_after:
                return state
        # This is still a fallible model audit; no hidden automatic rewrite after acceptance.
        if not state.get('complete'):
            final = executor.call('final_quality', {'outline': state['plan'], 'request': req,
                                                  'scene_endings': [{'id': s['id'], 'ending': s['prose'][-500:]} for s in state['accepted']],
                                                  'memories': compact(state['memories'], 24)},
                'Audit this compact story record for unresolved central promises and unsupported outcomes. You see endings and selected memory, not full prose. Return plain text findings with limitations; do not claim a full manuscript audit.', tokens=1000)
            save(folder / 'final-review.txt', final)
            state['complete'] = True
            state['completion_note'] = 'All scenes accepted by configured checks; final compact audit may contain unresolved issues.'
            save(state_path, state)
        export(folder, state, req)
        return state
