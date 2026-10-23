"""Explicit synthetic transport responses. Never a literary-quality demonstration."""
import json


def respond(role, packet, req):
    if role=='refiner_part':return json.dumps({'guidance':['Preserve the supplied '+packet['category']+' constraints through concrete action.'],'assumptions':[],'open_decisions':[]})
    if role=='repair':return json.dumps({'replacement':packet['paragraph']+' FIXTURE repaired.','facts_changed':False})
    if role=='global_repair':return packet['prose']
    if role=='seam':return packet['right_entry']
    if role=='writer_beat':return 'FIXTURE beat '+packet['beat']['action']+'.\n\nMara checked the tower latch. The hinge caught halfway.'
    if role=='director' and 'count' in packet:
        return json.dumps({'beats':[{'action':str(i),'entry_state':str(i),'exit_state':str(i+1)} for i in range(packet['count'])]})
    if role == 'refiner':
        value = {k: [] for k in ['preserved_user_choices', 'expanded_story_elements', 'character_tensions', 'subplot_possibilities', 'world_constraints', 'suggested_techniques', 'retrieval_references', 'assumptions', 'open_decisions']}
        value.update(original_prompt=req['premise'], refined_prompt=req['premise'], central_conflict='FIXTURE conflict', reader_experience='FIXTURE only')
        return json.dumps(value)
    if role == 'development_editor':
        if packet.get('candidate_evidence'):
            return json.dumps({'pass':True,'checks':{key:{'verdict':'pass','evidence_id':packet['candidate_evidence'][0]['id'],'reason':'Synthetic fixture assessment validates transport only, not literary quality.'} for key in packet['required_checks']},'issues':[]})
        candidate=packet['review_document']['candidate']
        path='candidate.refined_prompt' if 'refined_prompt' in candidate else 'candidate.scenes.0.intended_change'
        return json.dumps({'pass':True,'checks':[{'id':key,'verdict':'pass','path':path,'reason':'Synthetic fixture assessment validates transport only, not literary quality.'} for key in packet['required_checks']],'issues':[]})
    if role == 'scene_designer':
        card=dict(packet['proposed_scene'])
        card.update(choice='FIXTURE attempt a practical check',consequence='FIXTURE cooperation changes the next task',new_development='FIXTURE transition '+card['id'],reference_uses=[])
        if packet.get('writing_batch_count'):card['writing_beats']=[{'action':f'FIXTURE assigned action {i}','entry_state':f'FIXTURE state {i}','exit_state':f'FIXTURE state {i+1}'} for i in range(packet['writing_batch_count'])]
        return json.dumps(card)
    if role == 'architect':
        ids = [c['id'] for c in req['characters']]
        scenes = []
        for ch in range(1, req['chapters'] + 1):
            for sc in range(1, req['scenes_per_chapter'] + 1):
                scenes.append({'id': f'ch{ch:02}-sc{sc:02}', 'chapter': ch, 'pov': ids[0], 'participants': ids[:2],
                               'location': 'bell tower', 'time': f'day {ch}, interval {sc}', 'goal': 'inspect the bell mechanism',
                               'obstacle': 'access requires cooperation', 'intended_change': 'a practical decision changes the inspection'})
        for scene in scenes:
            authored=next((s for s in req.get('scene_designs',[]) if s['id']==scene['id']),{})
            for key in ['pov','participants','location']:
                if key in authored:scene[key]=authored[key]
        return json.dumps({'title': req.get('title'), 'threads': ['bell repair', 'trust'], 'technique_stack': ['consequential choice'], 'scenes': scenes})
    if role in {'story_quality', 'rhetoric_quality', 'memory_quality', 'chapter_quality'}:
        if packet.get('required_checks'):
            evidence_id=packet['evidence_passages'][0]['id']
            return json.dumps({'pass':True,'checks':[{'id':key,'verdict':'pass','evidence_ids':[evidence_id],'reason':'Synthetic fixture assessment validates the contract only, not literary quality.'} for key in packet['required_checks']],'issues':[]})
        return json.dumps({'pass': True, 'issues': []})
    if role == 'memory':
        if 'mara' not in {c['id'] for c in req['characters']}:
            passage=packet['evidence_passages'][0]
            return json.dumps({'memories':[{'kind':'event','text':passage['text'],'evidence_ids':[passage['id']],'known_by':[req['characters'][0]['id']]}]})
        return json.dumps({'memories': [{'kind': 'event', 'text': 'Mara checked the tower latch.', 'evidence': 'Mara checked the tower latch.', 'known_by': ['mara']} ]})
    if role == 'character':
        return packet['character'].get('name', packet['character']['id']) + ' checks the nearest fastening.'
    if role == 'director':
        return 'Inspect the latch; ask for access; cooperate on a practical check.'
    if role == 'structural_editor':return packet['prose']
    if role == 'humanizer':
        if 'paragraphs' in packet:return json.dumps({'replacements':{p['id']:p['original'] for p in packet['paragraphs']}})
        return packet['prose']
    if role == 'writer':
        card = packet.get('scene', packet.get('context', {}).get('scene', {}))
        if 'no dialogue' in req.get('pov','').lower():
            return f'FIXTURE {card.get("id", "repair")}: transport test only. The smith checked the storm-damaged fastening and chose to remain beside the damaged object. His companion observed the work. No literary quality is established by this synthetic response.'
        return (f'[FIXTURE {card.get("id", "repair")}: transport test only.]\n\nMara checked the tower latch. '
                'The hinge caught halfway. She put the lamp down before trying again.\n\n'
                '“Hold this,” she said.\n\nOren kept his hand on the rail. “Tell me what you are checking.”\n\n'
                '“Whether it opens from inside.”\n\nHe took the lamp. She eased the pin free, keeping it in her palm '
                'so it could not fall between the boards. Neither moved toward the stairs until she had replaced it.')
    return 'FIXTURE AUDIT: deterministic test responses establish file coordination only. No model or literary quality was tested.'
