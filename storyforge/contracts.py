from __future__ import annotations
import re
from .evidence import EvidenceError, bind, quote_span

class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def request(value):
    require(isinstance(value, dict), 'Request must be an object')
    require(bool(re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', value.get('project_id', ''))), 'Invalid project ID')
    require(isinstance(value.get('premise'), str) and bool(value['premise'].strip()), 'Premise required')
    for name, low, high, default in [('chapters', 1, 12, 3), ('scenes_per_chapter', 1, 8, 3), ('words_per_scene', 100, 1600, 850), ('max_repairs', 0, 3, 1), ('max_stage_retries', 0, 3, 1), ('context_chars', 4000, 192000, 22000), ('n_ctx', 4096, 16384, 8192)]:
        value.setdefault(name, default)
        require(type(value[name]) is int and low <= value[name] <= high, f'Invalid {name}')
    if value['context_chars']>48000:
        required=set(value.get('execution_policy',{}).get('hosted_required_roles',[]))
        roles=set(value.get('api_roles',{}))
        require(value.get('performance',{}).get('pipelined_living') and roles and roles<=required,'Extended context requires an explicitly hosted-only pipeline; CPU context remains bounded')
    chars = value.get('characters', [])
    from .universe_events import freedom,validate_config
    validate_config(value)
    cast_limit=freedom(value).get('cast_limit',8) if freedom(value)['enabled'] else 8
    require(isinstance(chars, list) and 1 <= len(chars) <= cast_limit, 'Character cast exceeds configured limit')
    ids = [c.get('id') for c in chars if isinstance(c, dict)]
    require(len(ids) == len(chars) and all(isinstance(x, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', x) for x in ids) and len(ids) == len(set(ids)), 'Character IDs must be unique and safe')
    for field in ['world_rules', 'must_avoid']:
        value.setdefault(field, [])
        require(isinstance(value[field], list) and all(isinstance(x, str) for x in value[field]), f'Invalid {field}')
    value.setdefault('initial_facts', [])
    for fact in value['initial_facts']:
        require(isinstance(fact, dict) and isinstance(fact.get('text'), str), 'Invalid initial fact')
        require(isinstance(fact.get('known_by'), list) and set(fact['known_by']) <= set(ids) | {'public'}, 'Invalid initial knowledge holders')
    for name, default in [('min_words_ratio', .75), ('max_words_ratio', 1.3)]:
        value.setdefault(name, default)
        require(type(value[name]) in (int, float) and .1 <= value[name] <= 3, f'Invalid {name}')
    require(value['min_words_ratio'] <= value['max_words_ratio'], 'Invalid length range')
    value.setdefault('profile', 'balanced')
    require(value['profile'] in {'balanced', 'expressive', 'small','fast'}, 'Unknown profile')
    value.setdefault('retrieval_mode', 'keyword')
    require(value['retrieval_mode'] in {'keyword', 'hybrid'}, 'Unknown retrieval mode')
    value.setdefault('auto_approve_plan', False)
    require(type(value['auto_approve_plan']) is bool, 'auto_approve_plan must be boolean')
    value.setdefault('runner_repo', 'storyforge-inference-runner')
    require(bool(re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', value['runner_repo'])), 'Invalid runner repo')
    from .brief import validate
    return validate(value, require)


def plan(value, req):
    require(isinstance(value, dict) and isinstance(value.get('scenes'), list), 'Plan requires scenes')
    require(len(value['scenes']) == req['chapters'] * req['scenes_per_chapter'], 'Wrong scene count')
    ids = {x['id'] for x in req['characters']}
    for i, scene in enumerate(value['scenes']):
        chapter = i // req['scenes_per_chapter'] + 1
        expected = f'ch{chapter:02}-sc{i % req["scenes_per_chapter"] + 1:02}'
        require(scene.get('id') == expected and scene.get('chapter') == chapter, f'Expected scene {expected}')
        require(scene.get('pov') in ids, 'Unknown POV')
        require(isinstance(scene.get('participants'), list) and bool(scene['participants']) and len(scene['participants']) == len(set(scene['participants'])) and set(scene['participants']) <= ids and scene['pov'] in scene['participants'], 'Invalid participants')
        for name in ['goal', 'obstacle', 'intended_change', 'location', 'time']:
            require(isinstance(scene.get(name), str) and bool(scene[name].strip()), f'Scene needs {name}')
    require(isinstance(value.get('threads'), list) and all(isinstance(x, str) for x in value['threads']), 'Plan needs thread strings')
    return value


def review(value, prose):
    require(isinstance(value, dict) and type(value.get('pass')) is bool and isinstance(value.get('issues'), list), 'Invalid quality review')
    require(all(isinstance(issue, dict) for issue in value['issues']), 'Review issues must be objects')
    value = {**value, 'issues': [dict(issue) for issue in value['issues']]}
    for issue in value['issues']:
        require(issue.get('severity') in {'blocking', 'advisory'}, 'Invalid severity')
        for key in ['category', 'quote', 'problem', 'fix']:
            require(isinstance(issue.get(key), str) and bool(issue[key].strip()), f'Review needs {key}')
        try:
            start, end, method = quote_span(issue['quote'], prose)
            issue['quote'] = prose[start:end]
            issue['quote_match'] = method
        except EvidenceError as exc:
            raise ContractError('Review quote is not supported by current prose: ' + str(exc)) from exc
    require(not (value['pass'] and any(x['severity'] == 'blocking' for x in value['issues'])), 'Pass contradicts blocking issues')
    return value


def delta(value, prose, ids):
    require(isinstance(value, dict) and isinstance(value.get('memories'), list), 'Memory output needs memories array')
    require(all(isinstance(m, dict) for m in value['memories']), 'Memory entries must be objects')
    value = {**value, 'memories': [dict(m) for m in value['memories']]}
    for index, m in enumerate(value['memories']):
        require(isinstance(m.get('kind'),str) and m['kind'] in {'event', 'belief', 'claim', 'resource', 'relationship', 'thread'}, 'Invalid memory kind')
        require(isinstance(m.get('text'), str) and bool(m['text'].strip()) and len(m['text']) <= 600, f'Invalid memory text at record {index + 1}: text is required, nonempty, and at most 600 characters')
        try:
            m = bind(m, prose)
            value['memories'][index] = m
        except EvidenceError as exc:
            raise ContractError(f'Memory {index + 1} evidence is unsupported: {exc}') from exc
        require(isinstance(m.get('known_by'), list) and all(isinstance(cid,str) for cid in m['known_by']) and set(m['known_by']) <= set(ids) | {'public'}, 'Invalid memory knowledge holders')
        if 'supersedes' in m:
            links=m['supersedes']
            require(isinstance(links,list) and len(links)<=3 and all(isinstance(x,str) for x in links) and len(links)==len(set(links)),'Invalid supersedes links')
        if 'life_state' in m or 'subject' in m or isinstance(m.get('fact_key'),str) and m['fact_key'].startswith('life:'):
            require(m.get('kind')=='event' and m.get('subject') in ids and m.get('life_state') in {'alive','dead','missing','unknown'},'Invalid lifecycle memory')
            require(m.get('fact_key')=='life:'+m['subject'],'Lifecycle memory needs stable life:<id> fact key')
        if m['kind']=='thread' or 'thread_id' in m or 'thread_state' in m:
            require(m.get('kind')=='thread' and isinstance(m.get('thread_id'),str) and bool(re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',m['thread_id'])) and m.get('thread_state') in {'seeded','escalating','payoff','closed'},'Invalid plot thread memory')
            require(m.get('fact_key')=='thread:'+m['thread_id'],'Thread needs stable thread:<id> fact key')
        if m['kind'] == 'belief':
            require(isinstance(m.get('holder'),str) and m['holder'] in ids and m['holder'] in m['known_by'], 'Belief needs holder')
    return value


def refinement(value, req):
    require(isinstance(value, dict), 'Refinement must be an object')
    # Canonicalize losslessly equivalent presentation shapes, never invent content.
    value = dict(value)
    experience = value.get('reader_experience')
    if isinstance(experience, list) and experience and all(isinstance(x, str) and x.strip() for x in experience):
        value['reader_experience'] = '; '.join(experience)
    arrays = ['preserved_user_choices', 'expanded_story_elements', 'character_tensions', 'subplot_possibilities', 'world_constraints', 'suggested_techniques', 'retrieval_references', 'assumptions', 'open_decisions']
    for key in arrays:
        if isinstance(value.get(key), dict):
            value[key] = [{'name': name, 'value': item} for name, item in value[key].items()]
    require(value.get('original_prompt') == req['premise'], 'Refinement must preserve original prompt verbatim')
    for key in ['refined_prompt', 'central_conflict', 'reader_experience']:
        require(isinstance(value.get(key), str) and bool(value[key].strip()), f'Refinement {key} must be a nonempty string (received {type(value.get(key)).__name__})')
    for key in arrays:
        require(isinstance(value.get(key), list), f'Refinement {key} must be an array (received {type(value.get(key)).__name__})')
    return value
