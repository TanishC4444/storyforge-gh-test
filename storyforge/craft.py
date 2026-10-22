"""Explicit author brief and revision contracts; no model-written rules or canon."""
import re
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


def author_packet(req,state,card):
    return {
        'nonnegotiable_form':req['pov'],
        'chapter_contract':req.get('chapter_contract',{}),
        'scene_contract':next((s for s in req['scene_designs'] if s['id']==card['id']),{}),
        'completed_events':[{'id':s['id'],'prose':s['prose']} for s in state['accepted'] if s['chapter']==card['chapter']],
        'earlier_chapter_continuity':'Use the source-bound canon and recent endings in scene_context; planned outcomes are not evidence.',
        'continuity_instruction':'Completed events are author evidence, not shared character knowledge. Continue their consequences; never reenact them.',
        'quality_contract':req.get('quality_contract',[]),
        'development_proposals':state.get('refinement',{}).get('expanded_story_elements',[]),
        'proposal_policy':'Development guidance and planned twists are proposals, not facts or character knowledge. Use only what serves this scene. Setup must precede payoff; explicit user restrictions override proposals.',
        'scene_layout':next((s for s in state.get('scene_layout',[]) if s['id']==card['id']),{}),
    }


def validate_prose(prose,req,*,check_length=False):
    require(isinstance(prose,str) and bool(prose.strip()),'Empty prose')
    if check_length and req.get('length_policy',{}).get('scene_words')=='strict':
        words=len(prose.split());target=req['words_per_scene']
        require(target*req.get('min_words_ratio',.75)<=words<=target*req.get('max_words_ratio',1.3),f'Scene has {words} words; required range is {target*req.get("min_words_ratio",.75):g}–{target*req.get("max_words_ratio",1.3):g} words (target {target}). Develop choices and consequences without padding')
    paragraphs=[re.sub(r'\s+',' ',p).strip() for p in re.split(r'\n\s*\n',prose) if len(p.split())>=12]
    require(len(paragraphs)==len(set(paragraphs)),'Duplicate prose paragraph; revise before review')
    if 'no dialogue' in req.get('pov','').lower():
        require(not re.search(r'[“”"]',prose),'Quoted speech violates the no-dialogue contract')
        require(not re.search(r'(?im)^\s*(?:sing,?\s+muse|o\s+muse|#{1,6}\s)',prose),'Invocation or heading violates prose contract')
    return prose
