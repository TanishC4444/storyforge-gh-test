"""Small role packets; full source material remains in checkpoints and provenance."""
import copy

OPERATIONAL={'project_id','profile','max_repairs','max_stage_retries','context_chars','n_ctx',
             'runner_repo','auto_approve_plan','execution_intent','execution_policy','performance',
             'api_roles','min_words_ratio','max_words_ratio','retrieval_mode','retrieval_query'}


def creative_brief(req):
    brief={k:copy.deepcopy(v) for k,v in req.items() if k not in OPERATIONAL}
    for character in brief.get('characters',[]):
        # Voice examples repeat dialogue in a no-dialogue run; retain the register.
        if 'no dialogue' in req.get('pov','').lower() or 'no dialogue' in req.get('premise','').lower():
            if isinstance(character.get('voice_design'),dict):character['voice_design'].pop('examples',None)
    return brief


def concise_packet(packet,req):
    result=copy.deepcopy(packet)
    if isinstance(result.get('request'),dict):result['request']=creative_brief(result['request'])
    # Shared facts are written once; the POV list remains an explicit visibility
    # allowlist rather than granting access to all author knowledge.
    author=result.get('author_continuity',{}).get('current_state',{}).get('facts',[])
    known={m.get('id'):m for m in author if m.get('id')}
    if known and isinstance(result.get('pov_visible_memory'),list):
        result['pov_visible_memory']=[{'fact_id':m['id'],'source':'author_continuity.current_state.facts'}
            if m.get('id') in known and m==known[m['id']] else m for m in result['pov_visible_memory']]
        result['pov_knowledge_policy']='Only facts explicitly listed in pov_visible_memory are known to this POV. fact_id references the identical source fact in author_continuity; other author facts stay private.'
    if isinstance(result.get('pov_profile'),dict) and isinstance(result.get('characters'),list):
        focal=result['pov_profile']
        result['characters']=[{'id':c['id'],'profile_source':'pov_profile'} if c.get('id')==focal.get('id') else c for c in result['characters']]
    # Chapter excerpts already contain these endings; keep one source projection.
    if result.get('completed_events') and isinstance(result.get('author_continuity'),dict):
        covered={s['id'] for s in result['completed_events']}
        result['author_continuity']['recent_scenes']=[s for s in result['author_continuity'].get('recent_scenes',[]) if s['id'] not in covered]
        if result.get('recent_ending'):result.pop('recent_ending')
    # Craft text is retained once: the role skill supplies the rubric while scoped
    # reference mechanisms, limits, requested purposes and IDs remain intact.
    def walk(value):
        if isinstance(value,dict):
            if 'references' in value and 'craft' in value:value.pop('craft',None)
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(result)
    return result
