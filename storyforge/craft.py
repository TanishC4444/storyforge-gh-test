"""Explicit author brief and revision contracts; no model-written rules or canon."""
import re
from .media import contract as medium_contract
from .contracts import require, refinement

REVISION = '''Revise the complete scene in two priorities: dramatic causality, then language.
A paragraph must change the physical situation, deepen a live choice, or reveal a specific cost.
Preserve meaningful quiet work; remove restated bargains, duplicate actions, explanatory echoes,
and generic gestures. Never replay an earlier scene's discovery or commitment. Start from its
actual exit state. Bridge travel and custody explicitly without summarizing decisive action.
Render the focal character's competing duties through a concrete choice and its consequence.
Preserve author facts and private knowledge boundaries. Never manufacture a new event to fix prose.
For this no-dialogue story, narrate offers and refusals indirectly and show what they change.
Use material, ancient comparisons with a clear point; elevated syntax must remain intelligible.
Do not imitate a translation, invoke a Muse, add headings, or announce the moral.
Read prior chapter prose for repetition, setup/payoff, time, inventory, and tonal continuity.
Keep the current scene's earned dramatic length. Return only the entire revised scene.'''


def compile_brief(req):
    """The user already supplied a developed brief. Normalize it without expanding it."""
    return refinement({
        'original_prompt':req['premise'], 'refined_prompt':req['premise'],
        'central_conflict':req['plot_design']['central_question'],
        'reader_experience':req['reader_experience'],
        'preserved_user_choices':[req['pov'],*req['world_rules']],
        'expanded_story_elements':[],
        'character_tensions':[s['question'] for s in req['plot_design'].get('subplots',[])],
        'subplot_possibilities':[s['question'] for s in req['plot_design'].get('subplots',[])],
        'world_constraints':req['world_rules'], 'suggested_techniques':[],
        'retrieval_references':[r['record_id'] for r in req.get('references',[])],
        'assumptions':[], 'open_decisions':[],
    },req)


def compile_scene_plan(req):
    """A supplied scene layout can serve as a basic plan without invented events."""
    from .contracts import plan,require
    require(len(req['scene_designs'])==req['chapters']*req['scenes_per_chapter'],'Basic layout needs every scene')
    scenes=[]
    for i,source in enumerate(req['scene_designs']):
        require(source.get('pov') and source.get('participants') and source.get('choice_and_consequence'),'Basic scene layout needs POV, participants and a consequential choice')
        scenes.append({'id':source['id'],'chapter':i//req['scenes_per_chapter']+1,
                       'pov':source['pov'],'participants':source['participants'],
                       'location':source['location'],'time':source.get('time','Continue from the preceding accepted exit state; establish elapsed time explicitly.'),
                       'goal':source['dramatic_function'],'obstacle':source.get('restrictions') or source['development'],
                       'intended_change':source['choice_and_consequence']})
    return plan({'title':req['title'],'scenes':scenes,'threads':[s['question'] for s in req['plot_design'].get('subplots',[])]},req)


def chapter_history(state,card):
    """Exact bounded excerpts; full accepted prose remains in immutable checkpoints."""
    import hashlib
    history=[]
    for scene in state['accepted']:
        if scene['chapter']!=card['chapter']:continue
        prose=scene['prose'];item={'id':scene['id'],'prose':prose}
        if len(prose)>1000:
            item.update(prose=prose[-1000:],omitted_prefix_characters=len(prose)-1000,
                        source_sha256=hashlib.sha256(prose.encode()).hexdigest())
        history.append(item)
    return history


def development_projection(state,budget=1000):
    # Only optional model proposals are selected; explicit author controls stay intact.
    selected=[];used=0
    for item in state.get('refinement',{}).get('expanded_story_elements',[]):
        if used+len(item)<=budget:selected.append(item);used+=len(item)
    return selected


def author_packet(req,state,card):
    return {
        'nonnegotiable_form':req['pov'],
        'chapter_contract':req.get('chapter_contract',{}),
        'scene_contract':next((s for s in req['scene_designs'] if s['id']==card['id']),{}),
        'completed_events':chapter_history(state,card),
        'earlier_chapter_continuity':'Use source-bound canon and exact chapter excerpts. Omitted prose remains in checkpoints; do not infer unseen details. Planned outcomes are not evidence.',
        'continuity_instruction':'Completed events are author evidence, not shared character knowledge. Continue their consequences; never reenact them.',
        'quality_contract':req.get('quality_contract',[]),
        'development_proposals':development_projection(state),
        'proposal_policy':'Development guidance and planned twists are proposals, not facts or character knowledge. Use only what serves this scene. Setup must precede payoff; explicit user restrictions override proposals.',
        'scene_layout':next((s for s in state.get('scene_layout',[]) if s['id']==card['id']),{}),
    }


def length_status(prose,req):
    words=len(prose.split());target=req['words_per_scene']
    minimum=target*req.get('min_words_ratio',.75);maximum=target*req.get('max_words_ratio',1.3)
    overflow=words>maximum
    return {'words':words,'target':target,'minimum':minimum,'suggested_maximum':maximum,
            'overflow':overflow,'advisory':overflow and req.get('length_policy',{}).get('overflow')=='advisory',
            'excess_words':max(0,words-int(maximum))}


def validate_prose(prose,req,*,check_length=False):
    require(isinstance(prose,str) and bool(prose.strip()),'Empty prose')
    errors=[]
    if check_length and req.get('length_policy',{}).get('scene_words')=='strict':
        words=len(prose.split());target=req['words_per_scene']
        if words<target*req.get('min_words_ratio',.75) or (words>target*req.get('max_words_ratio',1.3) and req.get('length_policy',{}).get('overflow')!='advisory'):
            errors.append(f'Scene has {words} words; required range is {target*req.get("min_words_ratio",.75):g}–{target*req.get("max_words_ratio",1.3):g} words (target {target}). Develop choices and consequences without padding')
    paragraphs=[re.sub(r'\s+',' ',p).strip() for p in re.split(r'\n\s*\n',prose) if len(p.split())>=12]
    if len(paragraphs)!=len(set(paragraphs)):errors.append('Duplicate prose paragraph; revise before review')
    if 'no dialogue' in req.get('pov','').lower():
        if re.search(r'[“”"]',prose):errors.append('Quoted speech violates the no-dialogue contract. Narrate offers, refusals and commitments indirectly; do not reproduce speech or voice-example lines')
        if not medium_contract(req)['script'] and re.search(r'(?im)^\s*(?:sing,?\s+muse|o\s+muse|#{1,6}\s)',prose):errors.append('Invocation or heading violates prose contract')
    require(not errors,'; '.join(errors))
    return prose
