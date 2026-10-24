"""Small role packets; full source material remains in checkpoints and provenance."""
import copy,json

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
    # One complete author ledger, with a lossless POV visibility allowlist.
    prior=result.get('prior_canon',{});view=result.get('pov_known_facts',{})
    if isinstance(prior,dict) and isinstance(view,dict):
        by_id={m.get('id'):m for m in prior.get('facts',[]) if m.get('id')}
        if by_id and 'facts' in view:
            view['facts']=[{'fact_id':m['id'],'source':'prior_canon.facts'} if m.get('id') in by_id and m==by_id[m['id']] else m for m in view['facts']]
            view['visibility_policy']='Only these listed facts are known to this POV; other author facts remain private. References resolve against the complete prior_canon ledger above.'
    if req.get('performance',{}).get('pipelined_living'):
        # Lossless sharing only: one ledger, explicit knowledge allowlists, and
        # authored profiles remain complete. Do not summarize or slice memory.
        if result.get('world_rules')==result.get('author_contract',{}).get('world_rules'):
            result.pop('world_rules',None)
        if isinstance(result.get('direction'),str):
            try:direction=json.loads(result['direction'])
            except ValueError:direction=None
            if isinstance(direction,dict):
                if 'scene' in direction and direction['scene']==result.get('scene'):
                    direction['scene']={'source':'scene'}
                ledger={m.get('id') for m in result.get('prior_canon',{}).get('facts',[])}
                for actor in direction.get('observable_proposals',[]):
                    if actor.get('method')!='source_bound_character_context_no_inference':continue
                    actor['known_facts']=[m['fact_id'] if isinstance(m,dict) and m.get('source')=='prior_canon.facts' and m.get('fact_id') in ledger else m for m in actor.get('known_facts',[])]
                    actor['knowledge_policy']+=' String IDs in known_facts resolve only against prior_canon.facts; all other facts stay private.'
                result['direction']=direction
        if result.get('your_beat') in result.get('ordered_beat_plan',[]):
            result['your_beat']={'id':result['your_beat']['id'],'source':'ordered_beat_plan'}
        # Share repeated provenance fingerprints without removing a single fact
        # or source hash. The immutable history and all knowledge allowlists stay.
        fingerprints={}
        def share_hashes(value):
            if isinstance(value,dict):
                h=value.get('evidence_prose_sha256')
                if isinstance(h,str) and len(h)==64:
                    key=next((k for k,v in fingerprints.items() if v==h),None)
                    if key is None:key='h'+str(len(fingerprints)+1);fingerprints[key]=h
                    value.pop('evidence_prose_sha256');value['evidence_source_ref']=key
                for child in value.values():share_hashes(child)
            elif isinstance(value,list):
                for child in value:share_hashes(child)
        share_hashes(result)
        if fingerprints:result['evidence_source_fingerprints']=fingerprints
    # Chapter excerpts already contain these endings; keep one source projection.
    if result.get('completed_events') and isinstance(result.get('author_continuity'),dict):
        covered={s['id'] for s in result['completed_events']}
        result['author_continuity']['recent_scenes']=[s for s in result['author_continuity'].get('recent_scenes',[]) if s['id'] not in covered]
        if result.get('recent_ending'):result.pop('recent_ending')
    # Craft text is retained once: the role skill supplies the rubric while scoped
    # reference mechanisms, limits, requested purposes and IDs remain intact.
    def walk(value):
        if isinstance(value,dict):
            if 'no dialogue' in req.get('pov','').lower() and isinstance(value.get('voice_design'),dict):
                value['voice_design'].pop('examples',None)
            if 'references' in value and 'craft' in value:value.pop('craft',None)
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(result)
    return result
