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
