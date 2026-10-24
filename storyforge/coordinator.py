from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
from . import contracts
from .evidence import payload as evidence_payload
from .inference import Executor, ROOT
from .retrieval import retrieve, application_packet
from .brief import scene_controls
from .storage import export, load, lock, save

PLAN_INSTRUCTION = '''Return only JSON with keys threads (array of strings), scenes.
Create exactly the requested chapter and scene counts, in reading order. Scenes have keys id (ch01-sc01, etc.), chapter (integer), pov (character ID), participants (character IDs), location, time, goal, obstacle, intended_change.
Honor requested length: each chapter is built from its scene word budgets. Follow PLAN mode, but this JSON contract overrides the attached brief's kickoff questions and free-form output rules. Intended changes are plans, not accepted events. Use only supplied character IDs. Build the requested local resolution by the final chapter while preserving explicitly requested unresolved larger-story threads. Each scene must introduce a distinct consequential action, changed option, commitment, cost, or interpretation. Do not spend multiple scenes proving what is already established. Include the choice and consequence in intended_change. Treat scene word counts as guidance unless the user requires strict counts. Apply scoped references as mechanisms, not transplanted plots. No prose chapter yet.'''
MEMORY_INSTRUCTION = '''Return only JSON {"memories": [{"kind": "event"|"belief"|"claim"|"resource"|"relationship"|"thread", "text": string, "evidence_ids": ["p001"], "known_by": [character IDs or "public"], "holder": character ID for beliefs, "claim_source": character ID for claims}]}.
The ordered evidence_passages contain the complete CURRENT scene. Select 1–3 existing passage IDs per memory; do not copy or reconstruct quotations. The application resolves evidence directly from the source text. Extract at most 6 consequential updates. Distinguish facts, claims, and beliefs. Identify who actually makes a claim; another character quoting or challenging them is not the same speaker. Knowledge acquisition must be supported, not inferred from presence. Use public only for an in-world public disclosure. No plans, hypotheticals, rejected drafts, or inferred offstage facts. Preserve uncertainty. For explicit life-state changes use kind=event, subject=character ID, life_state=alive/dead/missing/unknown, fact_key=life:<id>, supersedes=prior current lifecycle ID when present. A threat or apparent death is not confirmed dead. Track foreshadowing and unresolved promises as kind=thread, thread_id=stable identifier, thread_state=seeded/escalating/payoff/closed, fact_key=thread:<id>; preserve the same identity through updates. These optional fields require exact supporting evidence; never infer a death or payoff from the plan.'''


def planning_packet(req, refinement, retrieval):
    from .craft import development_projection
    refinement={**refinement,'expanded_story_elements':development_projection({'refinement':refinement},budget=4000)}
    operational = {'profile', 'max_repairs', 'max_stage_retries', 'context_chars', 'n_ctx', 'runner_repo', 'retrieval_mode', 'auto_approve_plan', 'min_words_ratio', 'max_words_ratio'}
    return {'request': {k: v for k, v in req.items() if k not in operational},
            'refinement': {k: refinement[k] for k in ['refined_prompt', 'central_conflict', 'character_tensions', 'subplot_possibilities', 'world_constraints','expanded_story_elements','assumptions','open_decisions']},
            'inspiration': application_packet(req, retrieval, 'architect')}


def visible(memories, character=None, scene_audiences=None):
    def public_for(memory):
        if 'public' not in memory['known_by']:return False
        if scene_audiences is None or memory.get('source')=='user_input':return True
        return character in scene_audiences.get(memory.get('source'),[])
    return [m for m in memories if public_for(m) or (character is not None and character in m['known_by'])]


def compact(memories, count=24, char_budget=4500):
    # Full evidence stays in authoritative state. Working context gets bounded summaries.
    selected, used = [], 0
    for memory in reversed(memories[-count:]):
        item = {k: v for k, v in memory.items() if k not in {'evidence', 'evidence_ids', 'evidence_spans', 'evidence_match', 'evidence_prose_sha256'}}
        size = len(json.dumps(item, ensure_ascii=False))
        if used + size > char_budget:
            continue
        selected.append(item)
        used += size
    return list(reversed(selected))


def packet(req, state, card):
    excerpt_chars=1200 if req.get('performance',{}).get('compact_packets') else 2500
    result={
        'scene': card,
        'brief': {k: req.get(k) for k in ['premise', 'genre', 'reader_experience', 'pov', 'world_rules', 'must_avoid']},
        'characters': [{k: c.get(k) for k in ['id', 'name', 'goal', 'value', 'fear', 'arc', 'contradiction', 'emotional_behavior', 'voice', 'voice_design']} for c in req['characters'] if c['id'] in card['participants']],
        'pov_profile': next(c for c in req['characters'] if c['id'] == card['pov']),
        'pov_visible_memory': compact(visible(state['memories'],card['pov'],{s['id']:s['participants'] for s in state['accepted']})),
        'recent_ending': state['accepted'][-1]['prose'][-1600:] if state['accepted'] and state['accepted'][-1]['pov'] == card['pov'] else '',
        'author_continuity':{'instruction':'Prior prose is an author record, NOT automatic knowledge for any character. Preserve each character’s supported knowledge boundaries.','recent_scenes':[{'id':s['id'],'pov':s['pov'],'quality_status':s.get('quality_status','reviewed'),'canon_committed':s.get('canon_committed',True),'excerpt':s['prose'][-excerpt_chars:],'omitted_prefix_characters':max(0,len(s['prose'])-excerpt_chars),'source_sha256':hashlib.sha256(s['prose'].encode()).hexdigest()} for s in (state.get('universe_history',[])+state['accepted'])[-2:]]},
        'threads': state['plan']['threads'],
        'creative_controls': {**scene_controls(req, card['id']), 'subplots':[s for s in req['plot_design'].get('subplots',[]) if s.get('owner') in card['participants']]},
        'literary_application': application_packet(req, state['retrieval'], 'writer', card['id']),
        'style_and_controls': {k: req.get(k) for k in ['tone_mood', 'sensory_detail', 'creative_freedom', 'surprise', 'ending_tendency', 'reference_policy']},
        'target_words': req['words_per_scene'],
    }
    if req.get('performance',{}).get('pipelined_living'):
        from .narrative_context import context
        result['narrative_context']=context(state,card)
    if req.get('performance',{}).get('canon_index'):
        from .canon import working
        result['author_continuity']['current_state']=working(state,query=json.dumps(card),budget=None if req.get('performance',{}).get('classic_expansion') else req.get('performance',{}).get('working_memory_chars',6500))
        result['pov_visible_memory']=working(state,card['pov'],query=json.dumps(card),budget=None if req.get('performance',{}).get('classic_expansion') else req.get('performance',{}).get('working_memory_chars',6500))['facts']
    if req.get('performance',{}).get('classic_expansion'):
        result['recent_ending']=''
        result['author_continuity']['recent_scenes']=[{k:s.get(k) for k in ['id','pov','quality_status','canon_committed']} for s in (state.get('universe_history',[])+state['accepted'])[-2:]]
    return result


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
                     'memories': [dict(f, kind=f.get('kind','event'), source='user_input') for f in req['initial_facts']]}
            save(folder / 'request.json', req)
            save(state_path, state)
        executor = Executor(req, folder, backend)
        if 'retrieval' not in state:
            state['retrieval'] = retrieve(req)
            save(folder / 'retrieval.json', state['retrieval'])
            save(state_path, state)
        if 'refinement' not in state:
            state['refinement'] = executor.call('refiner', {'request': req, 'inspiration': application_packet(req,state['retrieval'],'refiner')},
                'Develop the initial premise into a specific, consequential story proposal. Preserve every explicit user choice and restriction; mark invented details as proposals or assumptions. Do not shorten away important constraints. Return only JSON with original_prompt (the exact request premise), refined_prompt, central_conflict, reader_experience (strings), and preserved_user_choices, expanded_story_elements, character_tensions, subplot_possibilities, world_constraints, suggested_techniques, retrieval_references, assumptions, open_decisions (arrays). References must use supplied source IDs. No chapters yet.',
                tokens=2400, validator=lambda x: contracts.refinement(x, req))
            save(folder / 'refinement.json', state['refinement'])
            save(state_path, state)
        if 'plan' not in state:
            planner_packet = planning_packet(req, state['refinement'], state['retrieval'])
            state['plan'] = executor.call('architect', planner_packet, PLAN_INSTRUCTION, tokens=2800,
                                         validator=lambda x: contracts.plan(x, req),
                                         skill=(ROOT / 'skills/story_architect.md').read_text().split('TECHNIQUE LIBRARY')[0])
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
                critic_packet = {'scene': card, 'request': {k: req.get(k) for k in ['premise', 'genre', 'reader_experience', 'pov', 'world_rules', 'must_avoid', 'tone_mood', 'sensory_detail', 'ending_tendency', 'initial_facts']}, 'accepted_memories': compact(state['memories'], 36),
                                 'original_draft': draft, 'current_prose': polished}
                verdict = executor.call('story_quality', critic_packet, 'Review current_prose. Return the required JSON only.', tokens=1400,
                                        validator=lambda x: contracts.review(x, polished), skill=(ROOT / 'skills/story_quality.md').read_text())
                words = len(polished.split())
                if backend != 'fixture' and req.get('length_policy',{}).get('scene_words')=='strict' and not req['words_per_scene'] * req['min_words_ratio'] <= words <= req['words_per_scene'] * req['max_words_ratio']:
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
            memory = executor.call('memory', {**evidence_payload(accepted), 'scene': card, 'characters': [c['id'] for c in req['characters']],
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
